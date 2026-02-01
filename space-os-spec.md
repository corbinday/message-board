# 🛸 SpaceOS Technical Specification v1.1

SpaceOS is a lightweight, asynchronous firmware for Raspberry Pi Pico 2 W and Pimoroni Space Unicorn LED matrices. It utilizes a **Notify-then-Fetch** architecture and a **Presence Proxy** pattern.

---

## 1. System Communication Flow

1.  **Presence (MQTT):** On boot, Pico publishes `online` to the Status Channel and sets an LWT for `offline`.
2.  **Notify (Ably MQTT):** Server whispers a `Message ID` and `Dimensions` via the Private Command Channel.
3.  **Fetch (FastAPI HTTP):** Pico validates dimensions. If they match, it plays a "Warp" animation while downloading the **Space Pack** binary.
4.  **Acknowledge (Ably MQTT):** After one full animation cycle, Pico publishes a `read_receipt` to the Status Channel.

---

## 2. Presence Proxy & Last Will (LWT)

Since Ably MQTT doesn't natively trigger Presence events, SpaceOS uses a "Proxy" via FastAPI.

### 2.1 Pico-Side Logic
- **Topic:** `status/[user_id]/[board_id]`
- **On Connect:** Publish `{"state": "online", "type": "presence"}`.
- **Last Will:** Set LWT on the same topic: `{"state": "offline", "type": "presence"}`.

### 2.2 FastAPI-Side (The Proxy)
The server subscribes to `status/+/+`. 
- When `state: online` is received: Server calls `channel.presence.enter_client(board_id)`.
- When `state: offline` is received: Server calls `channel.presence.leave_client(board_id)`.
This ensures the HTMX dashboard sees the board in the official Ably Presence set.

---

## 3. Server-Side: The "Space Pack" (SP) Protocol

The FastAPI server pre-processes Gel database entries into a contiguous binary stream.

### 3.1 The Binary Package (The "SP" Format)
| Offset | Field | Size | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 0 | **Magic** | 2B | Char | Always `SP`. |
| 2 | **Message ID** | 16B | UUID | Raw 16-byte binary UUID. |
| 18 | **Meta Len** | 2B | uint16 | Length of JSON metadata string. |
| 20 | **Pixel Len** | 4B | uint32 | Total size of raw RGB888 pixel data. |
| 24 | **Metadata** | Var | JSON | `{"sender": "...", "fps": 10, "is_anim": true}` |
| End | **Pixel Data** | Var | RGB | Raw `R, G, B` bytes. |

---

## 4. Client-Side: SpaceOS Logic

### 4.1 Storage & FIFO
- **Inbox Path:** `/inbox/[uuid].bin` (Raw pixels) and `/inbox/[uuid].json` (Metadata).
- **FIFO Cap:** 20 messages. Oldest files are deleted automatically when the limit is reached to preserve Flash.
- **Flash Wear:** Utilizes LittleFS for wear leveling.

### 4.2 UI Mapping (4-Button OS)
| Button | Action | Logic |
| :--- | :--- | :--- |
| **A** | **Skip** | Increments gallery index; triggers next render immediately. |
| **B** | **Cycle** | Toggles `AUTO_ROTATE`. |
| **C** | **Mode** | Toggles between `/inbox/` and `/art/` directories. |
| **D** | **Action** | **Short:** Toggle play/pause. **Long (2s):** Delete current message. |

---

## 5. Read-Receipts

- **Trigger:** `frame_index == total_frames` (End of first loop).
- **Action:** Publish to `status/[user_id]/[board_id]` with `{"action": "mark_read", "msg_id": "[uuid]"}`.
- **FastAPI:** On receipt, server updates Gel: `update Message filter .id = <uuid>$id set { is_read := true }`.