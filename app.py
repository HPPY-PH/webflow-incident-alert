import os
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
SLACK_TOKEN = os.getenv('SLACK_TOKEN')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL', '#test12')

WEBFLOW_STATUS_API = "https://status.webflow.com/api/v2/incidents/unresolved.json"

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
        "text": "Webflow Status Alert",
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
    """Fetches real unresolved incidents from Webflow and posts them to Slack."""
    try:
        response = requests.get(WEBFLOW_STATUS_API, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        incidents = data.get('incidents', [])
        
        if not incidents:
            # If Webflow has no active incidents, send a sample system check or clear notification
            return {
                "ok": True, 
                "message": "No active incidents found on Webflow status page."
            }, 200

        sent_count = 0
        for incident in incidents:
            format_and_send_to_slack(incident)
            sent_count += 1
            
        return {
            "ok": True, 
            "message": f"Successfully fetched and sent {sent_count} active incident(s) to Slack."
        }, 200

    except Exception as e:
        print(f"Error fetching status: {str(e)}")
        return {"ok": False, "error": str(e)}, 500

@app.route('/health', methods=['GET'])
def health():
    return {"status": "healthy"}, 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
