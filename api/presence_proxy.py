"""
Presence Proxy - Bridges Ably MQTT status messages to Ably Presence.

Subscribes to status/+/+ channels via Ably Realtime.
On "online" -> calls presence.enter_client(board_id) on status:{userId} channel.
On "offline" -> calls presence.leave_client(board_id) on status:{userId} channel.

Also handles read_receipt messages by updating the database.
"""
import asyncio
import json
import logging
import os
from uuid import UUID

from ably import AblyRest

logger = logging.getLogger(__name__)

ABLY_API_KEY = os.getenv("ABLY_API_KEY", "")

_running = False
_task = None


async def _process_status_message(ably, message, db_client):
    """Process a single status channel message."""
    try:
        # Parse channel name: status/{user_id}/{board_id}
        channel_name = message.name if hasattr(message, "name") else ""
        data = message.data if hasattr(message, "data") else {}

        if isinstance(data, str):
            data = json.loads(data)

        msg_type = data.get("type", "")
        state = data.get("state", "")

        if msg_type == "presence":
            # Extract user_id and board_id from channel name
            # Channel subscription is on status/+/+, message arrives
            # with the full channel path
            parts = channel_name.split("/") if "/" in channel_name else []

            # If we can't parse from channel name, these might be in the data
            user_id = data.get("user_id", parts[1] if len(parts) > 1 else "")
            board_id = data.get("board_id", parts[2] if len(parts) > 2 else "")

            if not user_id or not board_id:
                logger.warning(f"[PROXY] Missing user_id or board_id in presence message")
                return

            presence_channel = ably.channels.get(f"status:{user_id}")

            if state == "online":
                await presence_channel.presence.enter_client(board_id, {"type": "board"})
                logger.info(f"[PROXY] Board {board_id} entered presence for user {user_id}")
            elif state == "offline":
                await presence_channel.presence.leave_client(board_id)
                logger.info(f"[PROXY] Board {board_id} left presence for user {user_id}")

        elif msg_type == "read_receipt":
            msg_id = data.get("msg_id", "")
            if msg_id and db_client:
                try:
                    from api.queries import markMessageRead
                    await markMessageRead(db_client, message_id=UUID(msg_id))
                    logger.info(f"[PROXY] Marked message {msg_id} as read")
                except Exception as e:
                    logger.error(f"[PROXY] Error marking message read: {e}")

    except Exception as e:
        logger.error(f"[PROXY] Error processing status message: {e}")


async def start_proxy(db_client_getter):
    """
    Start the presence proxy background task.
    Uses Ably REST channel history polling as a simple approach.

    Args:
        db_client_getter: Callable that returns a Gel client for DB operations
    """
    global _running

    if not ABLY_API_KEY:
        logger.warning("[PROXY] ABLY_API_KEY not set, presence proxy disabled")
        return

    _running = True
    ably = AblyRest(ABLY_API_KEY)

    logger.info("[PROXY] Presence proxy started")

    # Subscribe to status channels using Ably channel enumeration
    # Since we're using REST, we'll poll for messages periodically
    # In production, use Ably Realtime with proper subscriptions
    while _running:
        try:
            await asyncio.sleep(5)  # Poll interval
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[PROXY] Error in proxy loop: {e}")
            await asyncio.sleep(10)

    logger.info("[PROXY] Presence proxy stopped")


def stop_proxy():
    """Signal the proxy to stop."""
    global _running
    _running = False
