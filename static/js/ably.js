/**
 * ably.js - Ably Realtime client for SpaceOS web dashboard
 *
 * Handles:
 * - Token auth via /ably/token
 * - Presence on status:{currentUserId}
 * - Friend presence subscription
 * - Command channel subscription (for notifications)
 * - localStorage-based log system
 */

const SpaceOSAbly = (() => {
  const LOG_KEY = 'spaceos-logs';
  const MAX_LOG_ENTRIES = 100;
  const DISPLAY_LOG_COUNT = 10;

  let ably = null;
  let currentUserId = null;

  // =========================================================
  // LOGGING SYSTEM
  // =========================================================

  function addLog(level, message) {
    const entries = getLogEntries();
    entries.unshift({
      timestamp: new Date().toISOString(),
      level: level,
      message: message,
    });

    // Trim to max entries
    if (entries.length > MAX_LOG_ENTRIES) {
      entries.length = MAX_LOG_ENTRIES;
    }

    try {
      localStorage.setItem(LOG_KEY, JSON.stringify(entries));
    } catch (e) {
      // localStorage might be full or unavailable
    }

    // Update UI live
    renderLogs();
  }

  function getLogEntries() {
    try {
      const raw = localStorage.getItem(LOG_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function clearLogs() {
    localStorage.removeItem(LOG_KEY);
    renderLogs();
  }

  function renderLogs() {
    const container = document.getElementById('log-entries');
    if (!container) return;

    const entries = getLogEntries();
    const displayEntries = entries.slice(0, DISPLAY_LOG_COUNT);

    if (displayEntries.length === 0) {
      container.innerHTML =
        '<p class="text-slate-600 text-xs">No log entries yet.</p>';
      return;
    }

    container.innerHTML = displayEntries
      .map((entry) => {
        const levelClass = {
          INFO: 'text-pico-blue',
          SUCCESS: 'text-pico-green',
          WARN: 'text-yellow-500',
          ERROR: 'text-pico-red',
          COMMAND: 'text-purple-400',
        }[entry.level] || 'text-slate-400';

        const time = new Date(entry.timestamp);
        const timeStr = time.toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
        });

        return `<p><span class="text-slate-600">[${timeStr}]</span> <span class="${levelClass}">[${entry.level}]</span> ${entry.message}</p>`;
      })
      .join('');

    // Update "all logs" count
    const countEl = document.getElementById('log-count');
    if (countEl) {
      countEl.textContent = `${entries.length} total`;
    }
  }

  // =========================================================
  // PRESENCE INDICATORS
  // =========================================================

  function setOnline(elementSelector, online) {
    const elements = document.querySelectorAll(elementSelector);
    elements.forEach((el) => {
      const indicator = el.querySelector('[data-presence-indicator]');
      if (indicator) {
        if (online) {
          indicator.classList.remove('bg-slate-600');
          indicator.classList.add('bg-pico-green');
          indicator.setAttribute('title', 'Online');
        } else {
          indicator.classList.remove('bg-pico-green');
          indicator.classList.add('bg-slate-600');
          indicator.setAttribute('title', 'Offline');
        }
      }

      const label = el.querySelector('[data-presence-label]');
      if (label) {
        label.textContent = online ? 'online' : 'offline';
        if (online) {
          label.classList.remove('text-slate-600');
          label.classList.add('text-pico-green');
        } else {
          label.classList.remove('text-pico-green');
          label.classList.add('text-slate-600');
        }
      }
    });
  }

  // =========================================================
  // ABLY CONNECTION
  // =========================================================

  async function init(userId) {
    currentUserId = userId;

    if (!userId) {
      addLog('WARN', 'No user ID provided, skipping Ably connection');
      return;
    }

    // Check if Ably SDK is loaded
    if (typeof Ably === 'undefined') {
      addLog('WARN', 'Ably SDK not loaded');
      return;
    }

    try {
      // Connect with token auth
      ably = new Ably.Realtime({
        authUrl: '/ably/token',
        authMethod: 'GET',
        clientId: userId,
      });

      ably.connection.on('connected', () => {
        addLog('SUCCESS', 'Connected to Ably Realtime');
        subscribeToPresence();
        subscribeToCommands();
      });

      ably.connection.on('disconnected', () => {
        addLog('WARN', 'Disconnected from Ably');
      });

      ably.connection.on('failed', (stateChange) => {
        addLog(
          'ERROR',
          `Ably connection failed: ${stateChange.reason?.message || 'unknown'}`
        );
      });
    } catch (e) {
      addLog('ERROR', `Ably init error: ${e.message}`);
    }
  }

  // =========================================================
  // BOARD INVENTORY CALLBACKS
  // =========================================================

  const inventoryCallbacks = [];

  function onBoardInventory(callback) {
    inventoryCallbacks.push(callback);
  }

  // =========================================================
  // PRESENCE / STATUS
  // =========================================================

  function subscribeToPresence() {
    if (!ably || !currentUserId) return;

    const statusChannel = ably.channels.get(`status:${currentUserId}`);

    // Subscribe to board_status messages (published by server when a board
    // authenticates). This is the authoritative online signal — boards connect
    // via MQTT and the server publishes this event.
    statusChannel.subscribe('board_status', (message) => {
      const data = message.data || {};
      const boardId = data.board_id;
      if (!boardId) return;
      if (data.online) {
        addLog('SUCCESS', `Board ${boardId.substring(0, 8)} came online`);
        setOnline(`[data-board-id="${boardId}"]`, true);
      } else {
        addLog('INFO', `Board ${boardId.substring(0, 8)} went offline`);
        setOnline(`[data-board-id="${boardId}"]`, false);
      }
    });

    // Subscribe to board_inventory messages and dispatch to registered callbacks
    statusChannel.subscribe('board_inventory', (message) => {
      const data = message.data || {};
      inventoryCallbacks.forEach((cb) => {
        try { cb(data); } catch (e) { /* ignore */ }
      });
    });

    // Subscribe to friends' presence channels
    const friendElements = document.querySelectorAll('[data-friend-id]');
    friendElements.forEach((el) => {
      const friendId = el.dataset.friendId;
      if (!friendId) return;

      const friendChannel = ably.channels.get(`status:${friendId}`);

      friendChannel.presence.subscribe('enter', () => {
        setOnline(`[data-friend-id="${friendId}"]`, true);
      });

      friendChannel.presence.subscribe('leave', () => {
        // Check if any members remain before marking offline
        friendChannel.presence.get((err, members) => {
          if (!err && members.length === 0) {
            setOnline(`[data-friend-id="${friendId}"]`, false);
          }
        });
      });

      // Get initial presence
      friendChannel.presence.get((err, members) => {
        if (!err && members.length > 0) {
          setOnline(`[data-friend-id="${friendId}"]`, true);
        }
      });
    });
  }

  function subscribeToCommands() {
    if (!ably || !currentUserId) return;

    const commandChannel = ably.channels.get(`commands:${currentUserId}`);
    commandChannel.subscribe('new_message', (message) => {
      addLog(
        'COMMAND',
        `New message received (${message.data?.messageId?.substring(0, 8) || 'unknown'}...)`
      );
    });

    addLog('INFO', 'Subscribed to command channel');
  }

  // =========================================================
  // PUBLIC API
  // =========================================================

  return {
    init,
    addLog,
    clearLogs,
    getLogEntries,
    renderLogs,
    onBoardInventory,
  };
})();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  // Render existing logs immediately
  SpaceOSAbly.renderLogs();

  // Wire up clear logs button
  const clearBtn = document.getElementById('clear-logs-btn');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      SpaceOSAbly.clearLogs();
    });
  }

  // Wire up view all logs
  const viewAllBtn = document.getElementById('view-all-logs-btn');
  if (viewAllBtn) {
    viewAllBtn.addEventListener('click', () => {
      const entries = SpaceOSAbly.getLogEntries();
      const logWindow = window.open('', '_blank');
      if (!logWindow) return;

      const html = entries
        .map(
          (e) =>
            `<div style="font-family:monospace;font-size:12px;margin:2px 0;color:#ccc"><span style="color:#666">[${new Date(e.timestamp).toLocaleString()}]</span> <span style="color:${
              { INFO: '#58a6ff', SUCCESS: '#3fb950', WARN: '#d29922', ERROR: '#f85149', COMMAND: '#bc8cff' }[e.level] || '#8b949e'
            }">[${e.level}]</span> ${e.message}</div>`
        )
        .join('');

      logWindow.document.write(
        `<html><head><title>SpaceOS Logs</title></head><body style="background:#0d1117;padding:20px">${html || '<p style="color:#8b949e">No logs</p>'}</body></html>`
      );
    });
  }

  // Auto-init if user ID is in the page
  const userIdEl = document.querySelector('[data-current-user-id]');
  if (userIdEl) {
    const userId = userIdEl.dataset.currentUserId;
    SpaceOSAbly.init(userId);
  }
});
