## Browser-Based Board Flashing — Implementation Plan

### How It Works

The Web Serial API lets the browser open a serial connection to the Pico's MicroPython REPL. To write a file, the browser enters **raw REPL mode** (sends `\x01`), then executes Python code like `f = open('main.py', 'wb'); f.write(b'...'); f.close()`. To wipe the board first, it runs `os.listdir()` and `os.remove()` recursively. No drivers, no native app — just JavaScript talking to the REPL over USB.

### New Files

**`static/js/flasher.js`** — The Web Serial flashing engine. Handles:
- Browser compatibility detection (`navigator.serial` exists = Chromium)
- Serial port connection (`navigator.serial.requestPort()`, open at 115200 baud)
- Raw REPL protocol: send `\x01` to enter raw mode, `\x04` to execute, read `OK` acknowledgment
- Raw paste mode for faster transfers (`\x05A\x01`, check for `R\x01` response)
- `wipeBoard()` — enters raw REPL, runs Python to recursively delete all files and directories (except the MicroPython internals), so `os.listdir('/')` → remove each file, recurse into subdirectories, `os.rmdir()` empty dirs
- `writeFile(path, content)` — enters raw REPL, sends Python to open/write/close a file. For binary content, base64-encodes the data in JS and sends `import binascii; f = open(path, 'wb'); f.write(binascii.a2b_base64('...')); f.close()`. Text files (`.py`) can be written directly with proper escaping
- `reboot()` — sends `\x04` (Ctrl-D) in normal REPL mode to trigger a soft reset
- Progress callback support so the UI can update a progress bar
- Chunked writes for large files (the raw paste flow control window is 256 bytes, so content is sent in chunks with flow control)

**`templates/app/board/flash_ui.html`** — A new partial template rendered inside `#setup-area` alongside (or replacing) the existing key-details content. Contains:
- Chromium detection banner: if `navigator.serial` is undefined, show a warning: "USB flashing requires Chrome, Edge, or another Chromium-based browser. You can still download secrets.py manually below."
- "Connect Board via USB" button — calls `navigator.serial.requestPort()`, shows the browser's port picker
- Once connected: progress UI showing steps (Connecting → Wiping board → Writing files → Rebooting)
- Status text and progress bar for each file being written
- Success/error state at the end

### Modified Files

**`templates/app/board/key-details.html`** — Add the flash UI below the existing "Download secrets.py" button. The flow becomes:
1. User generates access key (existing flow, unchanged)
2. User enters WiFi credentials (existing flow, unchanged)
3. User chooses: **"Flash to Board via USB"** (new, primary action) or **"Download secrets.py"** (existing, secondary/fallback)
4. If they click Flash, the JS reads `secret_key`, `wifi_ssid`, `wifi_password` from the form inputs already on the page, generates `secrets.py` content client-side using the same template structure as `secrets.py.j2`, then runs the full wipe → write → reboot cycle

**`templates/app/board/details.html`** — Add `{% block extra_scripts %}` override to include `flasher.js` with the nonce. Also add Chromium detection: a small inline script (with nonce) that checks `navigator.serial` and toggles a CSS class or data attribute on the body, so the template can conditionally show/hide the USB flash option.

**`api/routers/app.py`** — Add a new endpoint `GET /api/spaceos/files` that returns a JSON manifest of all the OS files and their contents. The flasher JS calls this to get the current versions of all files to write. Response shape:
```json
{
  "files": [
    {"path": "main.py", "content": "..."},
    {"path": "app.py", "content": "..."},
    {"path": "config.py", "content": "..."},
    ...
  ]
}
```
This endpoint reads from the `space-os/` directory on the server, excluding `secrets.py` (which is generated client-side from form values). This keeps the source of truth in version control — same files the OTA system will serve.

**`templates/auth/secrets.py.j2`** — Remove `board_type`, `board_width`, and `board_height` from the template. With self-detection, the board derives its type and dimensions from hardware at runtime. The generated `secrets.py` is reduced to pure identity and connectivity:
```python
secrets = {
    "ssid": "{{ ssid }}",
    "password": "{{ password }}",
    "pmb_secret_key": "{{ secret_key }}",
    "api_url": "{{ api_url }}",
    "board_id": "{{ board_id }}",
    "user_id": "{{ user_id }}",
}
```

**`api/routers/app.py` (`download_config`)** — Remove the `size_map` lookup and `board_type`/`board_width`/`board_height` from the template context, since `secrets.py` no longer includes them.

### The Full User Flow

1. User creates a board on the web UI (existing: picks Stellar/Galactic/Cosmic)
2. User clicks "Generate Access Key" on the board details page (existing)
3. User enters WiFi SSID and password (existing form)
4. **New:** If on a Chromium browser, a "Flash to Board via USB" button appears as the primary action
5. User plugs in their Pico via USB and clicks the button
6. Browser shows the serial port picker — user selects their Pico
7. JS connects, wipes the board's filesystem clean
8. JS fetches all OS files from `/api/spaceos/files`
9. JS generates `secrets.py` client-side from the form values (secret key, WiFi credentials, board ID, API URL, user ID)
10. JS writes each file to the Pico via raw REPL, updating the progress bar
11. JS sends a soft reboot command
12. Board boots into SpaceOS, self-detects its hardware type and dimensions, connects to WiFi, registers with the server
13. UI shows success — board status indicator should flip to online within seconds

**Non-Chromium fallback:** The existing "Download secrets.py" button remains. Users on Firefox/Safari download the file and manually copy all OS files to the board via Thonny or mpremote — the current workflow.

### Prerequisite the User Must Handle

MicroPython firmware must already be installed on the Pico. This is a one-time drag-and-drop of a `.uf2` file (hold BOOTSEL → plug in → copy file to the USB drive that appears). The browser can't do this step — UF2 uses USB mass storage, which the Web Serial API can't access. But it's a 30-second process with clear instructions that can be documented on the page with a download link to the correct Pimoroni MicroPython `.uf2`.

### Considerations

- **CSP compliance:** `flasher.js` loaded as an external script via `{% block extra_scripts %}` with `nonce="{{ nonce }}"`. No inline script needed beyond the Chromium detection one-liner.
- **The `/api/spaceos/files` endpoint** should be authenticated (require the user to be logged in) so OS source code isn't publicly exposed. It can reuse the existing session auth.
- **Error handling:** If the serial connection drops mid-write, the board will have partial files. On next USB flash attempt, the wipe step clears everything first. If the user just reboots the board without re-flashing, it'll likely crash — but that's expected for an interrupted flash. The OTA `.updating` flag doesn't apply here since this is initial provisioning, not an OTA update.


## SpaceOS OTA Update Plan

**Source of truth:** The `space-os/` directory in version control. No upload endpoint, no database state. Commit and redeploy = new release.

**Versioning:** SHA-256 hash of the update bundle, computed by the server at startup. No semantic versioning to manually bump. The board stores the hash of its last successful update in an `os_hash` file.

**Signing workflow:** The Ed25519 private key is stored in your password manager and never leaves your machine. When you're ready to release, you run a local signing script that bundles the updatable `space-os/` files, signs the bundle, and outputs a signed artifact (e.g., `spaceos-update.bin`). This signed artifact is committed to the repo. The server reads and serves it as-is at startup — no signing logic on the server, no access to the private key. The server's only job is to compute the SHA-256 hash of the pre-signed bundle for the version check endpoint.

**Boot sequence:**

MicroPython runs `main.py` on startup — this is the only entry point. `main.py` is immutable and acts as the bootstrapper:

1. Check: does `.updating` flag exist on flash?
   - Yes → previous update was interrupted. Clean up any `.new` partial files, retry the full update from scratch.
   - No → continue.
2. Connect to WiFi.
3. `GET /api/spaceos/check?hash=<os_hash>` to check for updates.
   - `204` → up to date, continue to step 4.
   - `200` → bundle received. Verify Ed25519 signature, write `.updating` flag, write new files with `.new` suffix, remove old files, rename `.new` → original, write new hash to `os_hash`, remove `.updating` flag, call `machine.reset()`.
4. `import app; app.run()` — hands off to the updatable OS entry point.

Everything that currently lives in `main.py` — hardware init, boot sync, Ably connection, the main loop — moves to `app.py`, which is OTA-updatable. `main.py` stays frozen and only knows how to: connect WiFi, make one HTTP request, verify a signature, write files, and hand off to `app`.

**Update notification — two paths:**

1. **Boards that are online:** All boards subscribe to a global `spaceos:system` Ably channel. When the server starts up (i.e., after a redeploy), it publishes `{"type": "os_update"}` to this channel. Boards that receive it immediately begin the update process.
2. **Boards that are offline:** They miss the Ably message. On boot, `main.py` checks for updates via HTTP before handing off to `app.py`. This catches any updates that went live while the board was off.

In both cases, the board hits `GET /api/spaceos/check?hash=<current_hash>`. Server compares against its cached hash — returns `204` if current, or `200` with the signed bundle if stale. Updates are mandatory and take priority over normal operation.

**Security:** Ed25519 code signing. The keypair is generated offline. The private key stays in your password manager and is only used by the local signing script. The public key is embedded in `update_key.py` on each board, which is immutable and never included in updates. The server never has access to the private key — it only serves the pre-signed bundle. Even if the server or Railway account is compromised, an attacker cannot forge a signed update.

**Update bundle:** Single signed archive of all updatable files, built and signed locally from the `space-os/` directory. The signed artifact is committed to the repo and served by the server. Excluded from the bundle: `main.py`, `update_key.py`, `secrets.py`, and `os_hash`.

**Safe write process using `.updating` flag:**

The `.updating` file is written to the board's local filesystem (flash storage, same location as the OS files). `main.py` manages both writing and reading it. The flow:

1. `main.py` writes `.updating` flag to flash
2. Downloads the bundle and verifies the Ed25519 signature
3. Writes each new file with a `.new` suffix (e.g., `app.py.new`, `player.py.new`)
4. Removes the old files, renames `.new` → original
5. Writes the new hash to `os_hash`
6. Removes `.updating` flag
7. Calls `machine.reset()`

The flag matters on the *next boot*. `main.py` checks first thing: does `.updating` exist? If yes, the last update was interrupted (power loss, crash, corrupt download). It cleans up any `.new` partial files and retries the full update from scratch. If no `.updating` file exists, boot continues normally.

The board can only get stuck if `main.py` itself is corrupt — which can't happen because it's excluded from OTA updates.

**Rollback:** Revert the commit and redeploy. Next time boards check in (on boot or via the Ably notification on the new deployment), the hash won't match and they'll pull the reverted version.

**Board self-detection:**

`app.py` detects the board type at startup by trying each Pimoroni module import in sequence, catching `ImportError` to find the correct one — only the matching module exists on each board's firmware:

```python
try:
    from cosmic import CosmicUnicorn
    ...
except ImportError:
    try:
        from galactic import GalacticUnicorn
        ...
    except ImportError:
        from stellar import StellarUnicorn
        ...
```

After initialization, dimensions are read directly from the hardware via `gfx.get_bounds()`, and the board type string is derived from the successful import. This eliminates `BOARD_TYPE`, `BOARD_WIDTH`, and `BOARD_HEIGHT` from both `config.py` and `secrets.py`. The detected values are stored as module-level globals and used everywhere that previously referenced `config.BOARD_WIDTH`/`config.BOARD_HEIGHT` — fallback dimensions in sync, render, and the dimension validation in `commands.py`. With self-detection, `config.py` is reduced to just `FIFO_CAP` and `DEFAULT_FPS`, which are the same across all board types and become part of the OTA-updatable codebase. `secrets.py` is reduced to pure identity and connectivity: WiFi credentials, API URL, board ID, and board secret key.

**Immutable files (never updated OTA):**
- `main.py` — bootstrapper, WiFi connect, update check, signature verification, handoff to `app.py`
- `update_key.py` — Ed25519 public key
- `secrets.py` — WiFi credentials, board ID, API URL, board secret key
- `os_hash` — written by the updater after successful update, not part of the bundle

**Updatable files (everything else in `space-os/`):**
- `app.py` — hardware init, boot sync, Ably connection, main loop (formerly `main.py`'s contents)
- `player.py`, `space_pack.py`, `ably_mqtt.py`, `commands.py`, `storage.py`, `wifi.py`, `config.py`

Now I have all the context I need. Here's your refined backlog:

---

# System Updates

**Schema & Editor**

- **Change `frame_delay_ms` to `fps` with a max of 24fps** — The pixel editor and DB schema currently use `frame_delay_ms` (10–2000ms range) to control animation speed. Replace this with an `fps` field (1–24) throughout the stack: the Gel schema (`PixelAnimation.frame_delay_ms` → `PixelAnimation.fps`), the `DraftGraphic` type, the pixel editor UI (`pixel.js` currently clamps delay with `Math.max(100, Math.min(2000, value))`), the space-pack binary builder, and the SpaceOS player. An FPS slider is more intuitive for users than millisecond delay.

- **Raise frame limit to 150** — `PixelAnimation.frames` is currently constrained to `max_value(24)` in the schema and `this.maxFrames = 24` in `pixel.js`. Up this amount to 96 frames.

- **Add the same constraints to `DraftGraphic` as on `PixelAnimation`** — `DraftGraphic` currently has `frames: int16 { default := 1 }` and `frame_delay_ms: int16 { default := 100 }` with no min/max constraints, while `PixelAnimation` enforces `frames` 2–24 and `frame_delay_ms` 10–2000. Add matching constraints to `DraftGraphic` so invalid values are caught at save time rather than when finishing a draft.

**Web UI — Board Management**

- **Remote board configuration and control from web UI** — The board details page (`templates/app/board/details.html`) currently shows hardware info, key provisioning, and a delete button. Extend it into a live control panel: display current board mode (art/inbox), toggle auto-rotate on/off, change display brightness, and push configuration changes to the board over Ably in real time. This turns the boards view into a remote control for each physical board.

**SpaceOS — Connectivity**

- **Support multiple WiFi networks** — `wifi.py` currently connects to a single SSID/password pair from `secrets.py` with 5 retries. Add a list of known networks in config, scan for available SSIDs at boot, and connect to the strongest known network. Also add a web UI settings page where users can manage their board's WiFi network list (add/remove networks, trigger a network scan, and test connectivity) — pushing updates via the board's sync endpoint or Ably.

- **Retry WiFi connection from the main loop** — If WiFi fails at boot, SpaceOS currently runs in offline mode permanently. Add periodic reconnection attempts in the main loop (e.g. every 60s) so the board recovers from temporary network outages without a power cycle. On reconnection, re-acquire the Ably token and re-sync.

**SpaceOS — Display & UX**

- **Choose display mode (art/inbox) from web UI** — Currently the only way to switch between art and inbox is pressing the C button on the physical board. Allow setting the default display mode from the web UI board control panel, pushed to the board via Ably command.

- **Toggle auto-rotate from web UI** — Auto-rotate is currently toggled only via the B button on the board. Expose this as a remote toggle on the web UI board control panel via Ably, and persist the preference so it survives reboots.

- **SpaceOS startup animation** — There's currently no boot splash — the board goes straight from hardware init to WiFi connect with a blank display. Add a short branded startup animation (e.g. a SpaceOS logo or pixel warp effect) that plays during the boot sequence while WiFi connects and sync runs, giving visual feedback that the board is alive.

- **SpaceOS settings mode** — Add an on-board settings mode (accessible via a button combo or long-press) that displays configurable options directly on the LED matrix: brightness level, current WiFi network, display mode, auto-rotate toggle, and board info (ID, firmware version). Navigate with the existing A/B/C/D buttons.

**SpaceOS — Real-time Sync**

- **Listen for Ably messages to sync both art and inbox** — `_process_commands()` currently saves all incoming Ably messages to `/inbox` only. When the user creates new art on the web UI, it should also push to the board's `/art` directory in real time. Add a command type field to Ably payloads (e.g. `"type": "message"` vs `"type": "art_sync"`) and route accordingly in the command handler.

- **Remove old items as new ones arrive (FIFO over Ably)** — The FIFO cap (`config.FIFO_CAP = 20`) is enforced on disk when saving, but the board doesn't inform the web UI which items were evicted. When the board drops old items to make room, publish a status update over Ably so the web UI can reflect what's actually on the board. Also consider sending a "board inventory" on sync so the server knows the board's current state.

**SpaceOS + Web UI — Live Edit**

- **SpaceOS edit mode (live preview)** — Add a mode where the board acts as a live canvas, receiving pixel data frame-by-frame over Ably and rendering it immediately. This enables real-time preview while drawing in the pixel editor — the user sees their art on the physical board as they paint.

- **Web UI edit mode (live preview)** — In the pixel editor, add a "Preview on Board" toggle that streams the current canvas state to a selected board over Ably whenever pixels change. Requires the board to be online and in edit/preview mode. Debounce updates to avoid flooding the MQTT connection (e.g. send at most 10 updates/second).