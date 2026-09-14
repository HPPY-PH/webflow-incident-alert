import os
import requests
from flask import Flask
from datetime import datetime

app = Flask(__name__)

SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
SLACK_TOKEN = os.getenv('SLACK_TOKEN')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL', '#test12')

WEBFLOW_STATUS_API = "https://status.webflow.com/api/v2/incidents/unresolved.json"

# In-memory store to track already notified incident updates (Incident_ID + Update_ID)
NOTIFIED_UPDATES = set()

def format_and_send_to_slack(incident):
    """Helper function to build Slack message and send it."""
    status = incident.get('status', 'unknown')
    name = incident.get('name', 'Webflow Status Update')
    impact = incident.get('impact', 'unknown')
    
    # Extract latest update description if available
    incident_updates = incident.get('incident_updates', [])
    description = incident_updates[0].get('body') if incident_updates else 'No description provided'

    status_map = {
        'investigating': ('danger', 'Investigating'),
        'identified': ('warning', 'Identified'),
        'monitoring': ('warning', 'Monitoring'),
        'resolved': ('good', 'Resolved'),
        'postmortem': ('good', 'Postmortem')
    }
    
    color, display_status = status_map.get(status, ('warning', status))
    
    slack_message = {
        "text": f"Webflow Incident Alert: {name}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"[WEBFLOW] {name}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Status*\n{display_status}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Impact*\n{impact.title()}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"_{description}_"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | <https://status.webflow.com|View Status>"
                    }
                ]
            }
        ]
    }
    
    if SLACK_WEBHOOK:
        response = requests.post(SLACK_WEBHOOK, json=slack_message)
        response.raise_for_status()
        return True
    elif SLACK_TOKEN:
        slack_api_message = {
            "channel": SLACK_CHANNEL,
            "blocks": slack_message.get("blocks", []),
            "text": slack_message.get("text", "")
        }
        headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            json=slack_api_message,
            headers=headers
        )
        result = response.json()
        if not result.get("ok"):
            raise Exception(f"Slack API error: {result.get('error')}")
        return True
    return False

@app.route('/fetch-status', methods=['GET', 'POST'])
def fetch_webflow_status():
    """Fetches unresolved incidents from Webflow and sends to Slack ONLY if new/updated issues exist."""
    try:
        response = requests.get(WEBFLOW_STATUS_API, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        incidents = data.get('incidents', [])
        
        # 1. No active incidents on Webflow -> Do nothing and return quietly
        if not incidents:
            return {
                "ok": True, 
                "message": "All systems operational. No notification sent."
            }, 200

        sent_count = 0
        for incident in incidents:
            incident_id = incident.get('id')
            incident_updates = incident.get('incident_updates', [])
            latest_update_id = incident_updates[0].get('id') if incident_updates else 'no-update-id'
            
            # Combine incident ID and update ID to create a unique tracker key
            unique_key = f"{incident_id}_{latest_update_id}"
            
            # 2. Skip if we already posted this exact update to Slack
            if unique_key in NOTIFIED_UPDATES:
                continue
                
            # 3. Send new incident alert to Slack & record tracker key
            format_and_send_to_slack(incident)
            NOTIFIED_UPDATES.add(unique_key)
            sent_count += 1
            
        return {
            "ok": True, 
            "message": f"Processed active incidents. Sent {sent_count} new notification(s)."
        }, 200

    except Exception as e:
        print(f"Error fetching status: {str(e)}")
        return {"ok": False, "error": str(e)}, 500
