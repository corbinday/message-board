# ably_mqtt.py - MQTT connection to Ably with LWT and pub/sub
import json
import ssl
import time
from umqtt.simple import MQTTClient

import config


_client = None
_on_command = None  # callback for incoming commands


def _build_lwt_payload():
    """Build the Last Will and Testament payload."""
    return json.dumps({"state": "offline", "type": "presence"})


def _on_message(topic, msg):
    """Internal message handler dispatching to registered callbacks."""
    topic_str = topic.decode("utf-8") if isinstance(topic, bytes) else topic
    msg_str = msg.decode("utf-8") if isinstance(msg, bytes) else msg

    print(f"[MQTT] Received: {topic_str} -> {msg_str[:100]}")

    # Route command channel messages
    if topic_str.startswith("commands:") and _on_command:
        try:
            payload = json.loads(msg_str)
            _on_command(payload)
        except Exception as e:
            print(f"[MQTT] Error parsing command: {e}")


def connect(ably_token, on_command=None):
    """
    Connect to Ably via MQTT with LWT for offline presence.

    Args:
        ably_token: Ably token string for authentication
        on_command: Callback function for command messages
    """
    global _client, _on_command
    _on_command = on_command

    client_id = f"spaceos-{config.BOARD_ID}"
    status_topic = f"status/{config.USER_ID}/{config.BOARD_ID}"
    lwt_payload = _build_lwt_payload()

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_ctx.verify_mode = ssl.CERT_NONE

    _client = MQTTClient(
        client_id,
        config.ABLY_MQTT_HOST,
        port=config.ABLY_MQTT_PORT,
        user=ably_token,
        password="",
        ssl=ssl_ctx,
        keepalive=60,
    )

    # Set Last Will and Testament
    _client.set_last_will(status_topic, lwt_payload, retain=False, qos=1)

    # Set message callback
    _client.set_callback(_on_message)

    print(f"[MQTT] Connecting to {config.ABLY_MQTT_HOST}:{config.ABLY_MQTT_PORT} as {client_id}")
    print(f"[MQTT] Token: {ably_token[:20]}...")
    _client.connect()
    print("[MQTT] Connected to Ably MQTT.")

    # Publish online presence
    online_payload = json.dumps({"state": "online", "type": "presence"})
    _client.publish(status_topic, online_payload, qos=1)
    print(f"[MQTT] Published online to {status_topic}")

    # Subscribe to command channel
    command_topic = f"commands:{config.USER_ID}"
    _client.subscribe(command_topic, qos=1)
    print(f"[MQTT] Subscribed to {command_topic}")


def check_messages():
    """Non-blocking check for incoming MQTT messages."""
    if _client:
        try:
            _client.check_msg()
        except Exception as e:
            print(f"[MQTT] check_msg error: {e}")


def publish_read_receipt(message_id):
    """Publish a read receipt to the status channel."""
    if not _client:
        return

    topic = f"status/{config.USER_ID}/{config.BOARD_ID}"
    payload = json.dumps({
        "action": "mark_read",
        "msg_id": message_id,
        "type": "read_receipt",
    })
    try:
        _client.publish(topic, payload, qos=1)
        print(f"[MQTT] Read receipt sent for {message_id}")
    except Exception as e:
        print(f"[MQTT] Error sending read receipt: {e}")


def disconnect():
    """Gracefully disconnect from MQTT."""
    global _client
    if _client:
        try:
            # Publish offline before disconnecting
            topic = f"status/{config.USER_ID}/{config.BOARD_ID}"
            payload = json.dumps({"state": "offline", "type": "presence"})
            _client.publish(topic, payload, qos=1)
            _client.disconnect()
        except Exception:
            pass
        _client = None
        print("[MQTT] Disconnected.")


def is_connected():
    """Check if MQTT client exists (basic connectivity check)."""
    return _client is not None
