import os
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
SLACK_TOKEN = os.getenv('SLACK_TOKEN')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL', '#test12')  # Default to test12 for testing

# Health check endpoint for Render
@app.route('/health', methods=['GET'])
def health():
    """Simple health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "webflow-status-monitor"
    }, 200


@app.route('/webflow-status', methods=['POST'])
def webflow_webhook():
    """Receive webhooks from Webflow Statuspage"""
    try:
        data = request.json
        incident = data.get('incident', {})
        
        # Determine status and color
        status = incident.get('status', 'unknown')
        name = incident.get('name', 'Webflow Status Update')
        impact = incident.get('impact', 'unknown')
        description = incident.get('description', 'No description provided')
        
        # Map status to color
        status_map = {
            'investigating': ('danger', 'Investigating'),
            'identified': ('warning', 'Identified'),
            'monitoring': ('warning', 'Monitoring'),
            'resolved': ('good', 'Resolved'),
            'postmortem': ('good', 'Postmortem')
        }
        
        color, display_status = status_map.get(status, ('warning', status))
        
        # Build Slack message
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
        
        # Send to Slack
        if SLACK_WEBHOOK:
            # Method 1: Using Incoming Webhook
            response = requests.post(SLACK_WEBHOOK, json=slack_message)
            response.raise_for_status()
            return {"ok": True, "message": "Notification sent via webhook"}, 200
        elif SLACK_TOKEN:
            # Method 2: Using Web API (supports multiple channels)
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
            if result.get("ok"):
                return {"ok": True, "message": f"Notification sent to {SLACK_CHANNEL}"}, 200
            else:
                raise Exception(f"Slack API error: {result.get('error')}")
        else:
            return {"ok": True, "message": "Received (Slack not configured)"}, 200
            
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return {"ok": False, "error": str(e)}, 500


@app.route('/', methods=['GET'])
def index():
    """Service information endpoint"""
    return {
        "service": "Webflow Status Monitor",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health (GET)",
            "webhook": "/webflow-status (POST)"
        },
        "status": "operational"
    }, 200


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
