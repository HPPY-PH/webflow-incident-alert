import os
import requests
from flask import Flask, request
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
    
    # Extract description
    description = incident.get('description')
    if not description:
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

@app.route('/', methods=['GET'])
def index():
    """Service overview endpoint"""
    return {
        "service": "Webflow Status Monitor",
        "endpoints": {
            "health": "/health (GET)",
            "test_webhook": "/webflow-status (POST)",
            "fetch_status": "/fetch-status (GET/POST)"
        }
    }, 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Render/UptimeRobot"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}, 200

@app.route('/webflow-status', methods=['POST'])
def webflow_webhook():
    """Receives manual POST test payloads or direct Webflow Statuspage webhooks"""
    try:
        data = request.json or {}
        incident = data.get('incident', {})
        
        if not incident:
            return {"ok": False, "error": "No incident data provided in payload"}, 400
            
        format_and_send_to_slack(incident)
        return {"ok": True, "message": f"Notification sent to {SLACK_CHANNEL}"}, 200
    except Exception as e:
        print(f"Error handling webhook: {str(e)}")
        return {"ok": False, "error": str(e)}, 500

@app.route('/fetch-status', methods=['GET', 'POST'])
def fetch_webflow_status():
    """Fetches unresolved incidents from Webflow and alerts Slack ONLY on new/updated issues"""
    try:
        response = requests.get(WEBFLOW_STATUS_API, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        incidents = data.get('incidents', [])
        
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
            
            unique_key = f"{incident_id}_{latest_update_id}"
            
            if unique_key in NOTIFIED_UPDATES:
                continue
                
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
