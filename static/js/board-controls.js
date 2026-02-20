/**
 * board-controls.js - Client-side wiring for board control panel
 *
 * Handles:
 * - Brightness slider optimistic UI updates
 * - Board inventory updates via Ably status channel
 * - HTMX event hooks for control panel interactions
 */

(function () {
  'use strict';

  // Brightness slider: update label in real-time as user drags
  function initBrightnessSlider() {
    const slider = document.getElementById('brightness-slider');
    const valueDisplay = document.getElementById('brightness-value');

    if (slider && valueDisplay) {
      slider.addEventListener('input', function () {
        valueDisplay.textContent = this.value + '%';
      });
    }
  }

  // Subscribe to board inventory updates via Ably
  function subscribeToInventory() {
    if (typeof SpaceOSAbly === 'undefined') return;

    const controlPanel = document.getElementById('control-panel');
    if (!controlPanel) return;

    const boardId = controlPanel.dataset.boardId;
    if (!boardId) return;

    // Register callback with the SpaceOSAbly module.
    // When a board_inventory message arrives for this board, trigger an HTMX
    // request to refresh the live inventory section.
    SpaceOSAbly.onBoardInventory(function (data) {
      if (data.board_id !== boardId) return;

      // Build query string with the IDs so the server can render thumbnails
      const artIds = (data.art_ids || []).join(',');
      const inboxIds = (data.inbox_ids || []).join(',');
      const inventoryEl = document.getElementById('board-inventory');
      if (!inventoryEl) return;

      const url = `/app/board/${boardId}/live-inventory?art_ids=${encodeURIComponent(artIds)}&inbox_ids=${encodeURIComponent(inboxIds)}`;
      htmx.ajax('GET', url, { target: '#board-inventory', swap: 'innerHTML' });
    });
  }

  // Re-initialize controls after HTMX swaps (since control panel is re-rendered)
  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (
      event.detail.target.id === 'control-panel' ||
      event.detail.target.closest('#control-panel')
    ) {
      initBrightnessSlider();
    }
  });

  // Flash effect on successful control update
  document.body.addEventListener('htmx:afterSettle', function (event) {
    const controlPanel = document.getElementById('control-panel');
    if (controlPanel && event.detail.target === controlPanel) {
      controlPanel.classList.add('border-blue-600');
      setTimeout(function () {
        controlPanel.classList.remove('border-blue-600');
      }, 300);
    }
  });

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', function () {
    initBrightnessSlider();
    subscribeToInventory();
  });
})();
