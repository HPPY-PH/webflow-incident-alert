import os
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
SLACK_TOKEN = os.getenv('SLACK_TOKEN')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL', '#franklins-playground')

# Webflow Statuspage API URLs
WEBFLOW_SUMMARY_API = "https://status.webflow.com/api/v2/summary.json"

NOTIFIED_UPDATES = set()

def send_slack_message(slack_message):
    """Sends a formatted message to Slack via Webhook or Token API."""
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

def build_incident_slack_block(incident):
    """Formats incident payloads for Slack."""
    status = incident.get('status', 'unknown')
    name = incident.get('name', 'Webflow Status Update')
    impact = incident.get('impact', 'unknown')
    
    description = incident.get('description')
    if not description:
        incident_updates = incident.get('incident_updates', [])
        description = incident_updates[0].get('body') if incident_updates else 'No description provided'

    status_map = {
        'investigating': 'Investigating',
        'identified': 'Identified',
        'monitoring': 'Monitoring',
        'resolved': 'Resolved',
        'postmortem': 'Postmortem'
    }
    
    display_status = status_map.get(status, status.title())

    return {
        "text": f"Webflow Incident Alert: {name}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{name}"
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
                        "text": f"Source: Real-time <https://status.webflow.com|Webflow Status> | Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    }
                ]
            }
        ]
    }

@app.route('/', methods=['GET'])
def index():
    return {
        "service": "Webflow Status Monitor",
        "status": "operational",
        "endpoints": ["/health", "/webflow-status", "/fetch-status"]
    }, 200

@app.route('/health', methods=['GET'])
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}, 200

@app.route('/webflow-status', methods=['POST'])
def webflow_webhook():
    """Receives POST test payloads or direct Webflow Statuspage webhooks"""
    try:
        data = request.json or {}
        incident = data.get('incident', {})
        if not incident:
            return {"ok": False, "error": "No incident data in request body"}, 400
            
        slack_msg = build_incident_slack_block(incident)
        send_slack_message(slack_msg)
        return {"ok": True, "message": f"Notification sent to {SLACK_CHANNEL}"}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

@app.route('/fetch-status', methods=['GET', 'POST'])
def fetch_webflow_status():
    """Fetches real live status directly from Webflow Statuspage API"""
    try:
        response = requests.get(WEBFLOW_SUMMARY_API, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        incidents = data.get('incidents', [])
        page_status = data.get('status', {}).get('description', 'All Systems Operational')
        
        # Scenario 1: Active Incidents Found on Webflow Source
        if incidents:
            sent_count = 0
            for incident in incidents:
                incident_id = incident.get('id')
                incident_updates = incident.get('incident_updates', [])
                latest_update_id = incident_updates[0].get('id') if incident_updates else 'no-update-id'
                
                unique_key = f"{incident_id}_{latest_update_id}"
                
                if unique_key in NOTIFIED_UPDATES:
                    continue
                    
                slack_msg = build_incident_slack_block(incident)
                send_slack_message(slack_msg)
                NOTIFIED_UPDATES.add(unique_key)
                sent_count += 1
                
            return {
                "ok": True, 
                "source": "Webflow Status API",
                "message": f"Fetched live data. Sent {sent_count} incident update(s) to Slack."
            }, 200

        # Scenario 2: Webflow is Operational -> Check query parameter to force a summary
        force_report = request.args.get('force', 'false').lower() == 'true'
        
        if force_report:
            summary_msg = {
                "text": f"Webflow Status: {page_status}",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "[WEBFLOW] Live Status Report"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Current Status:* {page_status}\nNo active incidents reported by Webflow."}
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Source: <https://status.webflow.com|Webflow Official Status> | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                            }
                        ]
                    }
                ]
            }
            send_slack_message(summary_msg)
            return {"ok": True, "message": "Sent live operational summary report to Slack."}, 200

        return {"ok": True, "message": f"Webflow status is '{page_status}'. No incident alert needed."}, 200

    except Exception as e:
        print(f"Error fetching status: {str(e)}")
        return {"ok": False, "error": str(e)}, 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
