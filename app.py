import os
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# Single Webhook OR Comma-separated list of Webhooks
SLACK_WEBHOOK_URLS = os.getenv('SLACK_WEBHOOK_URL', '').split(',')

# Slack Bot Token
SLACK_TOKEN = os.getenv('SLACK_TOKEN')

# Target channels (Defaults to both requested channels)
SLACK_CHANNELS = [
    ch.strip() for ch in os.getenv('SLACK_CHANNELS', 'franklins-playground).split(',')
]

WEBFLOW_SUMMARY_API = "https://status.webflow.com/api/v2/summary.json"

NOTIFIED_UPDATES = set()
LAST_KNOWN_STATE = "operational"

def send_slack_message(slack_message):
    """Sends formatted messages to all configured Slack channels or webhooks."""
    sent_successfully = False

    # Option A: Send via Webhook URLs (if provided)
    if any(SLACK_WEBHOOK_URLS):
        for webhook_url in SLACK_WEBHOOK_URLS:
            webhook_url = webhook_url.strip()
            if webhook_url:
                response = requests.post(webhook_url, json=slack_message)
                response.raise_for_status()
                sent_successfully = True

    # Option B: Send via Slack API Bot Token to each channel in SLACK_CHANNELS
    elif SLACK_TOKEN:
        headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
        for channel in SLACK_CHANNELS:
            slack_api_message = {
                "channel": channel,
                "blocks": slack_message.get("blocks", []),
                "text": slack_message.get("text", "")
            }
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                json=slack_api_message,
                headers=headers
            )
            result = response.json()
            if not result.get("ok"):
                print(f"Failed to send to channel {channel}: {result.get('error')}")
            else:
                sent_successfully = True

    return sent_successfully

def build_incident_slack_block(incident):
    """Formats incident payloads with @here mention."""
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
        "text": f"<!here>\n[WEBFLOW] {name}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "<!here>"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"* [WEBFLOW] {name}*"
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
                    "text": f"{description}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Source: <https://status.webflow.com|Webflow Status> | Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    }
                ]
            }
        ]
    }

def build_operational_slack_block(description="All Systems Operational"):
    """Formats operational recovery payload."""
    return {
        "text": f"<!here>\n[WEBFLOW] All Systems Operational",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "<!here>"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*[WEBFLOW] All Systems Operational*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Status*\n{description}\n\nWebflow services are running normally and no active incidents are open."
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Source: <https://status.webflow.com|Webflow Status> | Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
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
        "channels": SLACK_CHANNELS,
        "endpoints": ["/health", "/webflow-status", "/fetch-status"]
    }, 200

@app.route('/health', methods=['GET'])
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}, 200

@app.route('/webflow-status', methods=['POST'])
def webflow_webhook():
    try:
        data = request.json or {}
        incident = data.get('incident', {})
        if not incident:
            return {"ok": False, "error": "No incident data in request body"}, 400
            
        slack_msg = build_incident_slack_block(incident)
        send_slack_message(slack_msg)
        return {"ok": True, "message": f"Notification sent to configured channels"}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

@app.route('/fetch-status', methods=['GET', 'POST'])
def fetch_webflow_status():
    global LAST_KNOWN_STATE
    try:
        response = requests.get(WEBFLOW_SUMMARY_API, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        incidents = data.get('incidents', [])
        page_status = data.get('status', {}).get('description', 'All Systems Operational')
        force_report = request.args.get('force', 'false').lower() == 'true'

        if incidents:
            LAST_KNOWN_STATE = "incident"
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
                "message": f"Active incidents detected. Sent {sent_count} update(s) to channels."
            }, 200

        if LAST_KNOWN_STATE == "incident" or force_report:
            slack_msg = build_operational_slack_block(page_status)
            send_slack_message(slack_msg)
            
            LAST_KNOWN_STATE = "operational"
            return {
                "ok": True, 
                "message": "Webflow restored! Sent 'All Systems Operational' notification to channels."
            }, 200

        return {"ok": True, "message": f"Webflow is normal ({page_status}). No alert sent."}, 200

    except Exception as e:
        print(f"Error fetching status: {str(e)}")
        return {"ok": False, "error": str(e)}, 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
