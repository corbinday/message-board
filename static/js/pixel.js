/* =========================================================
 * SHARED BASE CLASS
 * ========================================================= */

class PixelGridBase extends HTMLElement {
  resolveAndSnapPixelSize() {
    // Find parent container with pixel-context to read the CSS variable
    const container = this.closest('.pixel-context') || this.parentElement;
    const computed = getComputedStyle(container || this);

    let raw = parseFloat(computed.getPropertyValue('--pixel-size'));

    // Fallback: check element's own computed style (for direct inheritance)
    if (!Number.isFinite(raw) || raw <= 0) {
      const selfComputed = getComputedStyle(this);
      raw = parseFloat(selfComputed.getPropertyValue('--pixel-size'));
    }

    // Final fallback to default
    if (!Number.isFinite(raw) || raw <= 0) {
      raw = 10;
    }

    const snapped = Math.max(1, Math.round(raw));

    // Set the snapped value on the element for gap calculation
    this.style.setProperty('--pixel-size', `${snapped}px`);
    this.style.setProperty(
      '--pixel-gap',
      `${Math.max(1, Math.round(snapped / 6))}px`,
    );

    return snapped;
  }

  setupResizeObserver() {
    // Watch for container size changes to re-calculate pixel size
    const container = this.closest('.pixel-context') || this.parentElement;
    if (!container) return;

    // Use ResizeObserver to watch for size changes
    this._resizeObserver = new ResizeObserver(() => {
      // Debounce to avoid excessive recalculations
      if (this._resizeTimeout) {
        clearTimeout(this._resizeTimeout);
      }
      this._resizeTimeout = setTimeout(() => {
        this.resolveAndSnapPixelSize();
      }, 50);
    });

    this._resizeObserver.observe(container);
  }

  markRendered() {
    this.setAttribute('rendered', 'true');
  }

  isRendered() {
    return this.hasAttribute('rendered');
  }

  download(filename = 'pixel-art.png') {
    const src = this.getAttribute('src');
    if (!src) return;

    const a = document.createElement('a');
    a.href = src;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  disconnectedCallback() {
    if (this._cleanup) this._cleanup();
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
    }
    if (this._resizeTimeout) {
      clearTimeout(this._resizeTimeout);
    }
  }
}

/* =========================================================
 * PIXEL ANIMATION
 * ========================================================= */

class PixelAnimation extends PixelGridBase {
  async connectedCallback() {
    if (this.isRendered()) return;

    this.resolveAndSnapPixelSize();
    this.setupResizeObserver();

    const src = this.getAttribute('src');
    const override = this.getAttribute('color-override');
    const frameW = parseInt(this.getAttribute('frame-width'), 10);
    const frameH = parseInt(this.getAttribute('frame-height'), 10);
    const speed = parseInt(this.getAttribute('speed'), 10) || 200;

    if (!src || !frameW || !frameH) return;

    const img = new Image();
    img.crossOrigin = 'Anonymous';
    img.src = src;

    try {
      await img.decode();
    } catch {
      return;
    }

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });

    canvas.width = frameW;
    canvas.height = frameH;

    const totalFrames = Math.floor(img.width / frameW);
    const framesData = [];

    for (let f = 0; f < totalFrames; f++) {
      ctx.clearRect(0, 0, frameW, frameH);
      ctx.drawImage(img, f * frameW, 0, frameW, frameH, 0, 0, frameW, frameH);
      framesData.push(ctx.getImageData(0, 0, frameW, frameH).data);
    }

    this.style.gridTemplateColumns = `repeat(${frameW}, var(--pixel-size))`;

    const fragment = document.createDocumentFragment();
    this.pixelDivs = [];

    for (let i = 0; i < frameW * frameH; i++) {
      const div = document.createElement('div');
      fragment.appendChild(div);
      this.pixelDivs.push(div);
    }

    this.replaceChildren(fragment);
    this.markRendered();

    let currentFrame = 0;
    let running = true;

    const renderFrame = () => {
      if (!running) return;

      const data = framesData[currentFrame];
      const hasNoBlankPixels = this.hasAttribute('no-blank-pixels');

      for (let i = 0; i < this.pixelDivs.length; i++) {
        const idx = i * 4;
        const alpha = data[idx + 3];
        const div = this.pixelDivs[i];

        if (alpha > 10) {
          const r = data[idx];
          const g = data[idx + 1];
          const b = data[idx + 2];
          div.style.backgroundColor = override
            ? `rgb(${override})`
            : `rgb(${r},${g},${b})`;
          div.style.opacity = '1';
        } else {
          // For animations, transparent pixels show blank color by default
          // unless no-blank-pixels attribute is present
          if (hasNoBlankPixels) {
            div.style.backgroundColor = 'transparent';
            div.style.opacity = '0';
          } else {
            // Remove inline style to let CSS default (blank-pixel-color) show through
            div.style.backgroundColor = '';
            div.style.opacity = '1';
          }
        }
      }

      currentFrame = (currentFrame + 1) % totalFrames;

      this._timer = setTimeout(() => {
        requestAnimationFrame(renderFrame);
      }, speed);
    };

    this._cleanup = () => {
      running = false;
      if (this._timer) clearTimeout(this._timer);
    };

    renderFrame();
  }
}

customElements.define('pixel-animation', PixelAnimation);

/* =========================================================
 * PIXEL ART
 * ========================================================= */

class PixelArt extends PixelGridBase {
  constructor() {
    super();
    this.RAIN_OPACITY = 0.3;
    this.TRAIL_OPACITY = 1.0;
    this.currentRainCount = 0;
    this.MAX_RAIN_CONCURRENCY = 30;
    this.RAIN_ACTIVE_HOLD = 4000;
  }

  async connectedCallback() {
    if (this.isRendered()) return;

    this.resolveAndSnapPixelSize();
    this.setupResizeObserver();

    const src = this.getAttribute('src');
    const override = this.getAttribute('color-override');
    const trailOverride = this.getAttribute('trail-color-override');
    const hasHover = this.hasAttribute('hover-trail');
    const hasRain = this.hasAttribute('digital-rain');

    const rainAttr = this.getAttribute('rain-colors');
    this.rainColors = rainAttr
      ? rainAttr.split('|').map((c) => `rgb(${c.trim()})`)
      : ['rgb(255,0,0)', 'rgb(0,255,0)', 'rgb(0,0,255)'];

    const img = new Image();
    img.crossOrigin = 'Anonymous';
    img.src = src;

    try {
      await img.decode();
    } catch {
      return;
    }

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });

    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);

    const data = ctx.getImageData(0, 0, img.width, img.height).data;

    this.style.gridTemplateColumns = `repeat(${img.width}, var(--pixel-size))`;

    const fragment = document.createDocumentFragment();
    this.emptyPixels = [];

    for (let i = 0; i < data.length; i += 4) {
      const alpha = data[i + 3];
      const div = document.createElement('div');

      if (alpha > 10) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        div.style.backgroundColor = override
          ? `rgb(${override})`
          : `rgb(${r},${g},${b})`;
        div.style.setProperty('--base-opacity', '1');
      } else {
        div.style.setProperty('--base-opacity', '1');
        this.emptyPixels.push(div);
      }

      if (hasHover) {
        div.addEventListener('mouseenter', () => {
          const color = trailOverride
            ? `rgb(${trailOverride})`
            : 'rgb(255, 0, 0)';
          this.triggerEffect(div, color, this.TRAIL_OPACITY, 200, '0s', '1s');
        });
      }

      fragment.appendChild(div);
    }

    this.replaceChildren(fragment);
    this.markRendered();

    if (hasRain && this.emptyPixels.length > 0) {
      setTimeout(() => this.startGlobalRainLoop(), 1000);
    }
  }

  getWeightedRainColor() {
    const n = this.rainColors.length;
    if (n === 1) return this.rainColors[0];

    const weights = this.rainColors.map((_, i) => Math.pow(n - i, 2));
    const total = weights.reduce((a, b) => a + b, 0);

    let roll = Math.random() * total;
    for (let i = 0; i < n; i++) {
      if (roll < weights[i]) return this.rainColors[i];
      roll -= weights[i];
    }
    return this.rainColors[0];
  }

  triggerEffect(
    el,
    color,
    opacity,
    duration,
    bloomSpeed = '0s',
    fadeSpeed = '8s',
  ) {
    el.style.setProperty('--effect-color', color);
    el.style.setProperty('--effect-opacity', opacity);
    el.style.setProperty('--bloom-speed', bloomSpeed);
    el.style.setProperty('--fade-speed', fadeSpeed);

    el.classList.add('active-pixel');
    setTimeout(() => el.classList.remove('active-pixel'), duration);
  }

  startGlobalRainLoop() {
    const tick = () => {
      if (this.currentRainCount < this.MAX_RAIN_CONCURRENCY) {
        const px =
          this.emptyPixels[Math.floor(Math.random() * this.emptyPixels.length)];

        if (!px.classList.contains('active-pixel')) {
          this.currentRainCount++;
          this.triggerEffect(
            px,
            this.getWeightedRainColor(),
            this.RAIN_OPACITY,
            this.RAIN_ACTIVE_HOLD,
            '2s',
            '8s',
          );
          setTimeout(() => this.currentRainCount--, this.RAIN_ACTIVE_HOLD);
        }
      }

      setTimeout(tick, Math.random() * 800 + 100);
    };

    tick();
  }
}

customElements.define('pixel-art', PixelArt);

/* =========================================================
 * PIXEL EDITOR
 * ========================================================= */

class PixelEditor extends PixelGridBase {
  constructor() {
    super();
    this.currentColor = '#FF0000';
    this.currentTool = 'pen';
    this.isDrawing = false;
    this.canvas = null;
    this.ctx = null;
    this.pixelDivs = [];
    this.grid = null;
    this.recentColors = ['#ff0000']; // Pre-populate with starting red (lowercase)

    // Undo/Redo Stacks
    this.undoStack = [];
    this.redoStack = [];
    this.dragStartSnapshot = null;

    // Frame system for animations
    this.frames = []; // Array of ImageData objects
    this.currentFrameIndex = 0;
    this.allowAnimation = false;
    this.maxFrames = 24;
    this.frameDelay = 100; // Default frame delay in ms

    // Change tracking
    this._dirty = false;
    this._emitChanges = false;
    this._debounceMs = 500;
    this._debounceTimer = null;
    this._thumbnailUpdateTimer = null;

    // Drag-and-drop frame reordering
    this._draggedFrameIndex = undefined;

    // Track last hovered pixel for cleanup
    this._lastHoveredPixel = null;

    // Bind resize handler to instance
    this._handleWindowResize = this._handleWindowResize.bind(this);
    this._handleKeyDown = this._handleKeyDown.bind(this);
    this._handleDocumentMouseUp = null;
    this._resizeDebounce = null;
  }

  resolveAndSnapPixelSize() {
    // Handle pixel-grow mode (dynamic sizing to fill container)
    if (this.classList.contains('pixel-grow')) {
      // Find the main wrapper to determine available width
      const wrapper = this.firstElementChild;
      if (wrapper) {
        const style = getComputedStyle(wrapper);
        const paddingX =
          parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
        // Also account for the grid container's own padding/border (approx 10px overhead)
        const overhead = 10;

        // CRITICAL FIX: Use this.clientWidth (the full component width) instead of wrapper.clientWidth
        // because wrapper is w-fit and will be collapsed initially. We want to fill the *available* space.
        const availableWidth = this.clientWidth - paddingX - overhead;

        if (availableWidth > 0) {
          const width = parseInt(this.getAttribute('width'), 10) || 32;

          // Formula: Width = N*S + (N+1)*(S/6) roughly, but gap is S/6.
          // Using safer integer math floor: S = W / (N * 1.166)
          const size = (availableWidth * 6) / (width * 7);
          const snapped = Math.min(16, Math.max(1, Math.floor(size)));

          this.style.setProperty('--pixel-size', `${snapped}px`);
          this.style.setProperty(
            '--pixel-gap',
            `${Math.max(1, Math.round(snapped / 6))}px`,
          );
        }
      }
    } else {
      // Standard mode: Remove inline style to read from CSS classes
      this.style.removeProperty('--pixel-size');
      this.style.removeProperty('--pixel-gap');
    }

    // Call parent method to get the new snapped pixel size (reads the property we just set or CSS)
    const snapped = super.resolveAndSnapPixelSize();

    // Update the grid layout with new dimensions via CSS custom properties
    if (this.grid && this.pixelDivs.length > 0) {
      const width = parseInt(this.getAttribute('width'), 10) || 32;
      const height = parseInt(this.getAttribute('height'), 10) || 32;
      const pixelGap = this.style.getPropertyValue('--pixel-gap') || '2px';

      const pSize = snapped;
      const pGap = parseFloat(pixelGap);

      // Calculate total dimensions
      const totalWidth = width * pSize + (width - 1) * pGap + pGap;
      const totalHeight = height * pSize + (height - 1) * pGap + pGap;

      // Update via CSS custom properties (CSP-safe)
      this.grid.style.setProperty('--pixel-size', `${pSize}px`);
      this.grid.style.setProperty('--pixel-gap', pixelGap);
      this.grid.style.setProperty('--grid-cols', width);
      this.grid.style.setProperty('--grid-width', `${totalWidth}px`);
      this.grid.style.setProperty('--grid-height', `${totalHeight}px`);
    }

    return snapped;
  }

  /**
   * Find the grid div (can be nested within other divs)
   * @returns {HTMLElement|null} The grid element or null if not found
   */
  findGrid() {
    return this.querySelector('#grid');
  }

  /**
   * Wait for the grid div to be available (handles timing issues)
   * @returns {Promise<HTMLElement>} Promise that resolves with the grid element
   */
  async waitForGrid() {
    // First check if it's already there
    let grid = this.findGrid();
    if (grid) return grid;

    // Wait for DOM to be ready - use MutationObserver to watch for child additions
    // This handles cases where content is added dynamically (e.g., via htmx)
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        observer.disconnect();
        const hasChildren = this.children.length > 0;
        const errorMsg = hasChildren
          ? 'PixelEditor requires a descendant div with id="grid" (can be nested within other elements). Found children but no #grid element.'
          : 'PixelEditor requires a descendant div with id="grid" (can be nested within other elements). No children found.';
        reject(new Error(errorMsg));
      }, 2000); // 2 second timeout

      const observer = new MutationObserver(() => {
        grid = this.findGrid();
        if (grid) {
          clearTimeout(timeout);
          observer.disconnect();
          resolve(grid);
        }
      });

      // Observe the element for child additions (including nested children)
      observer.observe(this, {
        childList: true,
        subtree: true,
      });

      // Also check immediately after observer setup and on next frames
      requestAnimationFrame(() => {
        grid = this.findGrid();
        if (grid) {
          clearTimeout(timeout);
          observer.disconnect();
          resolve(grid);
        } else {
          // Check one more frame in case of slow parsing
          requestAnimationFrame(() => {
            grid = this.findGrid();
            if (grid) {
              clearTimeout(timeout);
              observer.disconnect();
              resolve(grid);
            }
          });
        }
      });
    });
  }

  async connectedCallback() {
    if (this.isRendered()) return;

    this.resolveAndSnapPixelSize();
    this.setupResizeObserver();

    // Wait for grid div to be available (can be nested within other divs)
    // This handles cases where connectedCallback fires before children are parsed
    this.grid = await this.waitForGrid();

    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;
    const initialSrc = this.getAttribute('initial-src');

    // Parse new configuration attributes
    this.allowAnimation = this.hasAttribute('allow-animation');
    this.maxFrames = parseInt(this.getAttribute('max-frames'), 10) || 24;
    this._emitChanges = this.hasAttribute('emit-changes');
    this._debounceMs = parseInt(this.getAttribute('debounce-ms'), 10) || 500;

    // Create internal canvas as source of truth
    this.canvas = document.createElement('canvas');
    this.canvas.width = width;
    this.canvas.height = height;
    this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });

    // Initialize canvas with transparent background
    this.ctx.clearRect(0, 0, width, height);

    // Initialize frame system if animations are allowed
    if (this.allowAnimation) {
      // Store the initial blank frame
      this.frames = [this.ctx.getImageData(0, 0, width, height)];
      this.currentFrameIndex = 0;
    }

    // Ensure CSS variables are accessible to the nested grid div
    // Read from inline style (set by resolveAndSnapPixelSize) or computed style
    const pixelSize =
      this.style.getPropertyValue('--pixel-size') ||
      getComputedStyle(this).getPropertyValue('--pixel-size') ||
      '10px';
    const pixelGap =
      this.style.getPropertyValue('--pixel-gap') ||
      getComputedStyle(this).getPropertyValue('--pixel-gap') ||
      '2px';

    // Use CSS class for base styling, set dynamic values via CSS custom properties
    this.grid.classList.add('editor-grid');
    this.grid.classList.remove('w-fit', 'h-fit');

    // Set CSS custom properties for dynamic sizing (these are allowed by CSP)
    this.grid.style.setProperty('--pixel-size', pixelSize);
    this.grid.style.setProperty('--pixel-gap', pixelGap);
    this.grid.style.setProperty('--grid-cols', width);

    // Calculate total dimensions to force container size (prevent collapsing)
    const pSize = parseFloat(pixelSize);
    const pGap = parseFloat(pixelGap);
    const totalWidth = width * pSize + (width - 1) * pGap + pGap; // + padding
    const totalHeight = height * pSize + (height - 1) * pGap + pGap; // + padding

    // Set dimensions via CSS custom properties
    this.grid.style.setProperty('--grid-width', `${totalWidth}px`);
    this.grid.style.setProperty('--grid-height', `${totalHeight}px`);

    // Create pixel divs
    const fragment = document.createDocumentFragment();
    this.pixelDivs = [];

    for (let i = 0; i < width * height; i++) {
      const div = document.createElement('div');
      // Use CSS class for base styling (avoids inline styles for CSP)
      div.className = 'editor-pixel';

      // Add hover effect via classList toggle, tracking last hovered pixel
      div.addEventListener('mouseenter', () => {
        if (this._lastHoveredPixel && this._lastHoveredPixel !== div) {
          this._lastHoveredPixel.classList.remove('hovered');
        }
        div.classList.add('hovered');
        this._lastHoveredPixel = div;
      });
      div.addEventListener('mouseleave', () => {
        div.classList.remove('hovered');
      });

      this.pixelDivs.push(div);
      fragment.appendChild(div);
    }

    this.grid.replaceChildren(fragment);
    this.markRendered();

    // Load initial image if provided
    if (initialSrc) {
      // If it's a data URL, load it directly
      if (initialSrc.startsWith('data:')) {
        await this.loadBytes(initialSrc);
      } else {
        // If it's a relative URL, fetch it first to avoid cross-origin taint
        try {
          const response = await fetch(initialSrc);
          const blob = await response.blob();
          await this.loadBytes(blob);
        } catch (err) {
          console.error('Failed to load initial image:', err);
        }
      }
    }

    // Bind mouse/touch events
    this.setupDrawingEvents();

    // Bind tool controls
    this.setupControls();

    // Bind transform controls
    this.setupTransformControls();

    // Initial render of recent colors
    this.renderRecentColors();

    // Setup frame controls if animation is allowed
    if (this.allowAnimation) {
      this.setupFrameControls();
      this.renderFrameThumbnails();
    }

    // Listen for window resize to handle CSS media query changes
    window.addEventListener('resize', this._handleWindowResize);

    // Listen for undo/redo shortcuts
    window.addEventListener('keydown', this._handleKeyDown);
  }

  _handleWindowResize() {
    if (this._resizeDebounce) {
      clearTimeout(this._resizeDebounce);
    }
    this._resizeDebounce = setTimeout(() => {
      this.resolveAndSnapPixelSize();
    }, 100);
  }

  /**
   * Find a control element by ID or data-attribute
   * Supports both ID-based (backward compatible) and data-attribute patterns
   * @private
   * @param {string} controlName - The control name (e.g., 'color-picker', 'pen')
   * @returns {HTMLElement|null}
   */
  _findControl(controlName) {
    // First try ID-based (backward compatible)
    const byId = document.getElementById(controlName);
    if (byId) return byId;

    // Then try data-attribute based (scoped to editor context)
    const context = this.closest('[data-editor-context]');
    if (context) {
      const scoped = context.querySelector(
        `[data-editor-control="${controlName}"]`,
      );
      if (scoped) return scoped;
    }

    // Finally try global data-attribute
    return document.querySelector(`[data-editor-control="${controlName}"]`);
  }

  /**
   * Find an action element by data-editor-action attribute
   * Supports both internal (within pixel-editor) and external (within editor context)
   * @private
   * @param {string} actionName - The action name (e.g., 'load-file', 'shift-up')
   * @returns {HTMLElement|null}
   */
  _findAction(actionName) {
    // First try within the pixel-editor element itself
    const internal = this.querySelector(`[data-editor-action="${actionName}"]`);
    if (internal) return internal;

    // Then try within the editor context (for controls placed outside pixel-editor)
    const context = this.closest('[data-editor-context]');
    if (context) {
      const scoped = context.querySelector(
        `[data-editor-action="${actionName}"]`,
      );
      if (scoped) return scoped;
    }

    return null;
  }

  setupControls() {
    // Find controls using both ID-based and data-attribute patterns
    const colorPicker = this._findControl('color-picker');
    const penBtn = this._findControl('pen');
    const eraserBtn = this._findControl('eraser');
    const dropperBtn = this._findControl('dropper');
    const clearBtn = this._findControl('clear');

    if (colorPicker) {
      colorPicker.addEventListener('input', (e) => {
        this.setColor(e.target.value);
        this.setTool('pen'); // Switch to pen when color changes
        this.updateToolUI();
      });
      // Initialize color
      this.currentColor = colorPicker.value;
    }

    if (penBtn) {
      penBtn.addEventListener('click', () => {
        this.setTool('pen');
        this.updateToolUI();
      });
    }

    if (eraserBtn) {
      eraserBtn.addEventListener('click', () => {
        this.setTool('eraser');
        this.updateToolUI();
      });
    }

    if (dropperBtn) {
      dropperBtn.addEventListener('click', () => {
        this.setTool('dropper');
        this.updateToolUI();
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (confirm('Clear entire canvas?')) {
          this.saveState(this.getSnapshot()); // Save before clearing
          this.clearCanvas();
        }
      });
    }

    // PNG file upload handler
    const loadFileInput = this._findAction('load-file');
    if (loadFileInput) {
      loadFileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        e.target.value = ''; // Allow re-selecting same file
        await this.handleFileUpload(file);
      });
    }

    this.updateToolUI();
  }

  setupTransformControls() {
    const shiftUpBtn = this._findAction('shift-up');
    const shiftDownBtn = this._findAction('shift-down');
    const shiftLeftBtn = this._findAction('shift-left');
    const shiftRightBtn = this._findAction('shift-right');

    if (shiftUpBtn) {
      shiftUpBtn.addEventListener('click', () => this.shiftPixels(0, -1));
    }
    if (shiftDownBtn) {
      shiftDownBtn.addEventListener('click', () => this.shiftPixels(0, 1));
    }
    if (shiftLeftBtn) {
      shiftLeftBtn.addEventListener('click', () => this.shiftPixels(-1, 0));
    }
    if (shiftRightBtn) {
      shiftRightBtn.addEventListener('click', () => this.shiftPixels(1, 0));
    }
  }

  shiftPixels(dx, dy) {
    if (!this.ctx || !this.canvas) return;

    const width = this.canvas.width;
    const height = this.canvas.height;

    // Save state for undo
    this.saveState(this.getSnapshot());

    // Get current data
    const currentData = this.ctx.getImageData(0, 0, width, height);
    // Create new blank data
    const newData = this.ctx.createImageData(width, height);

    // Loop through pixels
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        // Calculate source coordinates
        const srcX = x - dx;
        const srcY = y - dy;

        // Check if source is within bounds
        if (srcX >= 0 && srcX < width && srcY >= 0 && srcY < height) {
          const srcIndex = (srcY * width + srcX) * 4;
          const destIndex = (y * width + x) * 4;

          // Copy pixel data
          newData.data[destIndex] = currentData.data[srcIndex];
          newData.data[destIndex + 1] = currentData.data[srcIndex + 1];
          newData.data[destIndex + 2] = currentData.data[srcIndex + 2];
          newData.data[destIndex + 3] = currentData.data[srcIndex + 3];
        }
      }
    }

    // Apply new data
    this.ctx.putImageData(newData, 0, 0);
    this.updatePixelDivsFromCanvas();

    this._markDirty();
    this._queueThumbnailUpdate();
  }

  updateToolUI() {
    const tools = {
      pen: this._findControl('pen'),
      eraser: this._findControl('eraser'),
      dropper: this._findControl('dropper'),
    };

    // Reset all
    Object.values(tools).forEach((btn) => {
      if (btn) {
        btn.classList.remove('bg-slate-600', 'border-slate-400', 'text-white');
        btn.classList.add('bg-slate-800', 'border-slate-600', 'text-gray-300');
      }
    });

    // Highlight active
    const activeBtn = tools[this.currentTool];
    if (activeBtn) {
      activeBtn.classList.remove(
        'bg-slate-800',
        'border-slate-600',
        'text-gray-300',
      );
      activeBtn.classList.add('bg-slate-600', 'border-slate-400', 'text-white');
    }
  }

  clearCanvas() {
    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;

    // Clear canvas
    this.ctx.clearRect(0, 0, width, height);

    // Clear divs via CSS custom property
    this.pixelDivs.forEach((div) => {
      div.style.setProperty('--bg-color', 'transparent');
    });

    // Update frame thumbnail
    this._queueThumbnailUpdate();
  }

  _handleKeyDown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
      e.preventDefault();
      if (e.shiftKey) {
        this.redo();
      } else {
        this.undo();
      }
    } else if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
      e.preventDefault();
      this.redo();
    }
  }

  getSnapshot() {
    if (!this.ctx || !this.canvas) return null;
    return this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
  }

  applySnapshot(imageData) {
    if (!imageData || !this.ctx) return;
    this.ctx.putImageData(imageData, 0, 0);
    this.updatePixelDivsFromCanvas();
  }

  saveState(snapshot) {
    // Limit stack size
    if (this.undoStack.length > 50) {
      this.undoStack.shift();
    }
    this.undoStack.push(snapshot);
    this.redoStack = []; // Clear redo stack on new action
  }

  undo() {
    if (this.undoStack.length === 0) return;

    const current = this.getSnapshot();
    this.redoStack.push(current);

    const previous = this.undoStack.pop();
    this.applySnapshot(previous);
  }

  redo() {
    if (this.redoStack.length === 0) return;

    const current = this.getSnapshot();
    this.undoStack.push(current);

    const next = this.redoStack.pop();
    this.applySnapshot(next);
  }

  setupDrawingEvents() {
    if (!this.grid) {
      this.grid = this.findGrid();
      if (!this.grid) return;
    }

    const handleStart = (e) => {
      e.preventDefault();
      this.isDrawing = true;
      // Capture state before drawing starts
      this.dragStartSnapshot = this.getSnapshot();
      this.drawPixel(e);
    };

    const handleMove = (e) => {
      e.preventDefault();
      if (this.isDrawing) {
        this.drawPixel(e);
      }
    };

    const handleEnd = (e) => {
      if (e && e.cancelable) {
        e.preventDefault();
      }
      if (this.isDrawing) {
        this.isDrawing = false;

        // Save state if changed
        const currentSnapshot = this.getSnapshot();
        // Simple check: if start snapshot exists and something might have changed
        // For robustness, we assume if isDrawing was true, we might have drawn.
        // We could compare data buffers, but pushing valid history is safer.
        if (this.dragStartSnapshot) {
          this.saveState(this.dragStartSnapshot);
        }
        this.dragStartSnapshot = null;
      }
    };

    // Mouse events - attach to grid div for start/move
    this.grid.addEventListener('mousedown', handleStart);
    this.grid.addEventListener('mousemove', handleMove);

    // Listen for mouseup on document so drawing continues if mouse leaves and returns
    this._handleDocumentMouseUp = handleEnd;
    document.addEventListener('mouseup', handleEnd);

    // Touch events - attach to grid div
    this.grid.addEventListener('touchstart', handleStart, { passive: false });
    this.grid.addEventListener('touchmove', handleMove, { passive: false });
    this.grid.addEventListener('touchend', handleEnd);
    this.grid.addEventListener('touchcancel', handleEnd);
  }

  drawPixel(e) {
    if (!this.grid) {
      this.grid = this.findGrid();
      if (!this.grid) return;
    }

    const rect = this.grid.getBoundingClientRect();
    const pixelSize =
      parseInt(getComputedStyle(this).getPropertyValue('--pixel-size')) || 10;
    const pixelGap =
      parseInt(getComputedStyle(this).getPropertyValue('--pixel-gap')) || 1;
    const totalSize = pixelSize + pixelGap;

    // Get coordinates relative to grid element
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;

    const x = Math.floor((clientX - rect.left) / totalSize);
    const y = Math.floor((clientY - rect.top) / totalSize);

    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;

    if (x >= 0 && x < width && y >= 0 && y < height) {
      const index = y * width + x;
      const div = this.pixelDivs[index];

      if (this.currentTool === 'pen') {
        // Set pixel color via CSS custom property
        div.style.setProperty('--bg-color', this.currentColor);
        // Update canvas
        this.ctx.fillStyle = this.currentColor;
        this.ctx.fillRect(x, y, 1, 1);

        // Add to recents when used to paint
        this.addToRecents(this.currentColor);
        this._markDirty();
        // Update frame thumbnail live
        this._queueThumbnailUpdate();
      } else if (this.currentTool === 'eraser') {
        // Clear pixel via CSS custom property
        div.style.setProperty('--bg-color', 'transparent');
        // Clear from canvas
        this.ctx.clearRect(x, y, 1, 1);
        this._markDirty();
        // Update frame thumbnail live
        this._queueThumbnailUpdate();
      } else if (this.currentTool === 'dropper') {
        // Pick color
        // Read from canvas data to get accurate color
        const p = this.ctx.getImageData(x, y, 1, 1).data;
        if (p[3] > 0) {
          // If not transparent
          // Convert to hex
          let hex =
            '#' +
            [p[0], p[1], p[2]]
              .map((x) => {
                const hex = x.toString(16);
                return hex.length === 1 ? '0' + hex : hex;
              })
              .join('');

          // Check for near-duplicates in recent colors to fix precision issues/rounding errors
          // This prevents the "nearly identical" colors problem
          for (const recent of this.recentColors) {
            // Parse recent hex to rgb
            const r = parseInt(recent.substring(1, 3), 16);
            const g = parseInt(recent.substring(3, 5), 16);
            const b = parseInt(recent.substring(5, 7), 16);

            // Calculate squared Euclidean distance
            const distSq =
              Math.pow(p[0] - r, 2) +
              Math.pow(p[1] - g, 2) +
              Math.pow(p[2] - b, 2);

            // Tolerance: allow small deviations (e.g. +/- 2 or 3 on channels)
            if (distSq <= 25) {
              hex = recent; // Snap to existing color
              break;
            }
          }

          this.setColor(hex);

          // Update color picker UI
          const picker = this._findControl('color-picker');
          if (picker) picker.value = hex;

          // Switch back to pen
          this.setTool('pen');
          this.updateToolUI();
        }
      }
    }
  }

  setColor(color) {
    this.currentColor = color;
  }

  addToRecents(color) {
    // Normalize to lowercase for consistent comparison
    color = color.toLowerCase();

    // Only update if it's not already the most recent one
    if (this.recentColors[0] === color) return;

    // Remove if exists elsewhere to move it to top
    this.recentColors = this.recentColors.filter((c) => c !== color);

    // Add to front
    this.recentColors.unshift(color);

    // Limit to 10
    if (this.recentColors.length > 10) {
      this.recentColors.length = 10;
    }

    this.renderRecentColors();
  }

  renderRecentColors() {
    const container = this._findControl('recent-colors');
    if (!container) return;

    container.replaceChildren(); // Clear

    this.recentColors.forEach((color) => {
      const div = document.createElement('div');
      // Use CSS class for styling, set background color via dataset for CSS access
      div.className = 'color-swatch';
      div.dataset.color = color;
      // Background color must be set dynamically since it's user-selected
      // Using a CSS custom property on the element to avoid inline style
      div.style.setProperty('--swatch-color', color);

      div.addEventListener('click', () => {
        this.currentColor = color;
        const picker = this._findControl('color-picker');
        if (picker) picker.value = color;
        this.setTool('pen');
        this.updateToolUI();
      });

      container.appendChild(div);
    });
  }

  setTool(tool) {
    if (['pen', 'eraser', 'dropper'].includes(tool)) {
      this.currentTool = tool;
    }
  }

  async loadBytes(blob) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const url = typeof blob === 'string' ? blob : URL.createObjectURL(blob);

      img.onload = () => {
        const width = parseInt(this.getAttribute('width'), 10) || 32;
        const height = parseInt(this.getAttribute('height'), 10) || 32;

        // Use the spritesheet analyzer to check dimensions
        // This handles single frames AND spritesheets (for animations)
        const analysis = this._analyzeSpritesheetDimensions(
          img.width,
          img.height,
          width,
          height,
        );

        if (analysis.error) {
          console.warn(
            `Dimension mismatch: Image is ${img.width}x${img.height}, Editor is ${width}x${height}`,
          );
          reject(
            new Error(
              `Image dimensions (${img.width}x${img.height}) do not match editor (${width}x${height})`,
            ),
          );
          return;
        }

        // Draw image to canvas
        this.ctx.clearRect(0, 0, width, height);

        // If it's a spritesheet, we just draw the first frame to the main canvas initially
        // The frames array will need to be populated if it's an animation
        if (analysis.orientation === 'horizontal') {
          this.ctx.drawImage(img, 0, 0, width, height, 0, 0, width, height);
        } else if (analysis.orientation === 'vertical') {
          this.ctx.drawImage(img, 0, 0, width, height, 0, 0, width, height);
        } else {
          this.ctx.drawImage(img, 0, 0);
        }

        // Update grid UI for the current frame
        this.updatePixelDivsFromCanvas();

        // If animation is allowed and we have multiple frames, load them all
        if (this.allowAnimation && analysis.frameCount > 1) {
          // Create temp canvas to extract frames
          const tempCanvas = document.createElement('canvas');
          tempCanvas.width = img.width;
          tempCanvas.height = img.height;
          const tempCtx = tempCanvas.getContext('2d', {
            willReadFrequently: true,
          });
          tempCtx.drawImage(img, 0, 0);

          // Rebuild frames array
          this.frames = [];
          for (let i = 0; i < analysis.frameCount; i++) {
            this.frames.push(
              this._extractFrame(tempCtx, i, analysis, width, height),
            );
          }
          this.currentFrameIndex = 0;
          this.renderFrameThumbnails();

          // Notify that frames have changed
          this._emitFrameChange('load');
        } else {
          // Ensure frames array has at least the current state
          this.frames = [this.ctx.getImageData(0, 0, width, height)];
          this.currentFrameIndex = 0;
        }

        // Notify that content has changed (enables finish button)
        this._emitChange();

        if (typeof blob !== 'string') {
          URL.revokeObjectURL(url);
        }
        resolve();
      };

      img.onerror = () => {
        if (typeof blob !== 'string') {
          URL.revokeObjectURL(url);
        }
        reject(new Error('Failed to load image'));
      };

      img.src = url;
    });
  }

  /**
   * Handle file upload from file input
   * @param {File} file - The uploaded file
   */
  async handleFileUpload(file) {
    return new Promise((resolve) => {
      const url = URL.createObjectURL(file);
      const img = new Image();

      img.onload = async () => {
        const editorW = parseInt(this.getAttribute('width'), 10) || 32;
        const editorH = parseInt(this.getAttribute('height'), 10) || 32;

        // Analyze the image dimensions
        const analysis = this._analyzeSpritesheetDimensions(
          img.width,
          img.height,
          editorW,
          editorH,
        );

        if (analysis.error) {
          alert(analysis.error);
          URL.revokeObjectURL(url);
          resolve(false);
          return;
        }

        // Check if editor has existing content
        if (this.hasContent()) {
          // Show import dialog
          this._showImportDialog(url, img, analysis);
        } else {
          // Import directly (replace all for spritesheets, single frame for single images)
          const action =
            analysis.frameCount > 1 ? 'replace-all' : 'replace-frame';
          await this._performImport(url, img, analysis, action);
          URL.revokeObjectURL(url);
        }
        resolve(true);
      };

      img.onerror = () => {
        alert('Failed to load image file');
        URL.revokeObjectURL(url);
        resolve(false);
      };

      img.src = url;
    });
  }

  /**
   * Analyze image dimensions and detect spritesheet layout
   * @param {number} imgW - Image width
   * @param {number} imgH - Image height
   * @param {number} editorW - Editor canvas width
   * @param {number} editorH - Editor canvas height
   * @returns {{frameCount: number, orientation: string}|{error: string}}
   */
  _analyzeSpritesheetDimensions(imgW, imgH, editorW, editorH) {
    // Exact match - single frame
    if (imgW === editorW && imgH === editorH) {
      return { frameCount: 1, orientation: 'single' };
    }

    // Horizontal spritesheet: height matches, width is multiple
    if (imgH === editorH && imgW > editorW && imgW % editorW === 0) {
      return { frameCount: imgW / editorW, orientation: 'horizontal' };
    }

    // Vertical spritesheet: width matches, height is multiple
    if (imgW === editorW && imgH > editorH && imgH % editorH === 0) {
      return { frameCount: imgH / editorH, orientation: 'vertical' };
    }

    // Invalid dimensions
    return {
      error: `Image dimensions (${imgW}x${imgH}) don't match editor size (${editorW}x${editorH}).\n\nExpected:\n• Single frame: ${editorW}x${editorH}\n• Horizontal spritesheet: ${editorW * 2}x${editorH}, ${editorW * 3}x${editorH}, etc.\n• Vertical spritesheet: ${editorW}x${editorH * 2}, ${editorW}x${editorH * 3}, etc.`,
    };
  }

  /**
   * Show import dialog with options for handling existing content
   * @param {string} url - Object URL of the image
   * @param {HTMLImageElement} img - Loaded image element
   * @param {{frameCount: number, orientation: string}} analysis - Spritesheet analysis result
   */
  _showImportDialog(url, img, analysis) {
    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.className =
      'fixed inset-0 bg-black/80 flex items-center justify-center z-50';
    overlay.classList.add('modal-overlay-blur');

    // Create dialog
    const dialog = document.createElement('div');
    dialog.className =
      'bg-slate-900 border-2 border-slate-700 rounded-lg p-6 max-w-md mx-4 shadow-2xl';

    // Header
    const header = document.createElement('h3');
    header.className = "font-['Press_Start_2P'] text-[12px] text-white mb-4";
    header.textContent =
      analysis.frameCount > 1
        ? `Import ${analysis.frameCount} Frames`
        : 'Import Image';
    dialog.appendChild(header);

    // Description
    const desc = document.createElement('p');
    desc.className =
      "font-['Press_Start_2P'] text-[8px] text-slate-400 mb-6 leading-relaxed";
    desc.textContent =
      'Editor has existing content. How would you like to import?';
    dialog.appendChild(desc);

    // Button container
    const buttons = document.createElement('div');
    buttons.className = 'flex flex-col gap-3';

    // Replace Current Frame button
    const replaceFrameBtn = document.createElement('button');
    replaceFrameBtn.className =
      "font-['Press_Start_2P'] text-[8px] bg-slate-800 border-2 border-slate-600 px-4 py-3 text-white hover:bg-slate-700 hover:border-slate-400 transition-all rounded";
    replaceFrameBtn.textContent = 'Replace Current Frame Only';
    replaceFrameBtn.addEventListener('click', async () => {
      await this._performImport(url, img, analysis, 'replace-frame');
      URL.revokeObjectURL(url);
      overlay.remove();
    });
    buttons.appendChild(replaceFrameBtn);

    // Replace All button
    const replaceAllBtn = document.createElement('button');
    replaceAllBtn.className =
      "font-['Press_Start_2P'] text-[8px] bg-pico-blue border-2 border-pico-blue px-4 py-3 text-black hover:bg-pico-blue/80 transition-all rounded";
    replaceAllBtn.textContent =
      analysis.frameCount > 1
        ? `Replace Entire Project (${analysis.frameCount} Frames)`
        : 'Replace Entire Project';
    replaceAllBtn.addEventListener('click', async () => {
      await this._performImport(url, img, analysis, 'replace-all');
      URL.revokeObjectURL(url);
      overlay.remove();
    });
    buttons.appendChild(replaceAllBtn);

    // Cancel button
    const cancelBtn = document.createElement('button');
    cancelBtn.className =
      "font-['Press_Start_2P'] text-[8px] bg-transparent border-2 border-slate-600 px-4 py-3 text-slate-400 hover:border-slate-400 hover:text-white transition-all rounded";
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => {
      URL.revokeObjectURL(url);
      overlay.remove();
    });
    buttons.appendChild(cancelBtn);

    dialog.appendChild(buttons);
    overlay.appendChild(dialog);

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        URL.revokeObjectURL(url);
        overlay.remove();
      }
    });

    // Close on Escape key
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        URL.revokeObjectURL(url);
        overlay.remove();
        document.removeEventListener('keydown', handleEscape);
      }
    };
    document.addEventListener('keydown', handleEscape);

    document.body.appendChild(overlay);
  }

  /**
   * Execute the import operation
   * @param {string} url - Object URL of the image
   * @param {HTMLImageElement} img - Loaded image element
   * @param {{frameCount: number, orientation: string}} analysis - Spritesheet analysis result
   * @param {string} action - 'replace-frame' or 'replace-all'
   */
  async _performImport(url, img, analysis, action) {
    const editorW = parseInt(this.getAttribute('width'), 10) || 32;
    const editorH = parseInt(this.getAttribute('height'), 10) || 32;

    // Create temp canvas to extract frame data
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = img.width;
    tempCanvas.height = img.height;
    const tempCtx = tempCanvas.getContext('2d', { willReadFrequently: true });
    tempCtx.drawImage(img, 0, 0);

    if (action === 'replace-frame' || analysis.frameCount === 1) {
      // Extract first frame only and load into current frame
      const frameData = this._extractFrame(
        tempCtx,
        0,
        analysis,
        editorW,
        editorH,
      );

      // Save state for undo
      this.saveState(this.getSnapshot());

      // Put frame data into canvas
      this.ctx.putImageData(frameData, 0, 0);
      this.updatePixelDivsFromCanvas();

      this._markDirty();
      this._queueThumbnailUpdate();
    } else if (action === 'replace-all' && this.allowAnimation) {
      // Extract all frames and replace frames array
      const newFrames = [];
      for (let i = 0; i < analysis.frameCount; i++) {
        newFrames.push(
          this._extractFrame(tempCtx, i, analysis, editorW, editorH),
        );
      }

      // Replace frames array
      this.frames = newFrames;
      this.currentFrameIndex = 0;

      // Load first frame into canvas
      this._loadFrame(0);

      this._markDirty();
      this.renderFrameThumbnails();
    } else if (action === 'replace-all' && !this.allowAnimation) {
      // No animation support, just load first frame
      const frameData = this._extractFrame(
        tempCtx,
        0,
        analysis,
        editorW,
        editorH,
      );

      this.saveState(this.getSnapshot());
      this.ctx.putImageData(frameData, 0, 0);
      this.updatePixelDivsFromCanvas();

      this._markDirty();
    }
  }

  /**
   * Extract a single frame from spritesheet context
   * @param {CanvasRenderingContext2D} ctx - Source canvas context
   * @param {number} index - Frame index to extract
   * @param {{frameCount: number, orientation: string}} analysis - Spritesheet analysis
   * @param {number} w - Frame width
   * @param {number} h - Frame height
   * @returns {ImageData}
   */
  _extractFrame(ctx, index, analysis, w, h) {
    let x = 0,
      y = 0;

    if (analysis.orientation === 'horizontal') {
      x = index * w;
      y = 0;
    } else if (analysis.orientation === 'vertical') {
      x = 0;
      y = index * h;
    }
    // 'single' orientation: x=0, y=0

    return ctx.getImageData(x, y, w, h);
  }

  exportBlob() {
    return new Promise((resolve, reject) => {
      if (!this.canvas) {
        reject(new Error('Canvas not initialized'));
        return;
      }

      // Convert canvas to blob
      this.canvas.toBlob((blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error('Failed to export blob'));
        }
      }, 'image/png');
    });
  }

  /**
   * Alias for exportBlob() for consistency with avatar template
   * @returns {Promise<Blob>}
   */
  getSerializedData() {
    return this.exportBlob();
  }

  /**
   * Returns raw ImageData object from the canvas
   * @returns {ImageData|null}
   */
  getImageData() {
    if (!this.canvas || !this.ctx) return null;
    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;
    return this.ctx.getImageData(0, 0, width, height);
  }

  /**
   * Check if any non-transparent pixels exist
   * @returns {boolean}
   */
  hasContent() {
    if (!this.canvas || !this.ctx) return false;

    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;
    const imageData = this.ctx.getImageData(0, 0, width, height);
    const data = imageData.data;

    // Check if any pixel has alpha > 0
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] > 0) return true;
    }
    return false;
  }

  /**
   * Public API wrapper for clearCanvas
   */
  clear() {
    this.saveState(this.getSnapshot());
    this.clearCanvas();
    this._markDirty();
  }

  /**
   * Returns true if modified since last save/load
   * @returns {boolean}
   */
  isDirty() {
    return this._dirty;
  }

  /**
   * Reset dirty flag (call after save)
   */
  markClean() {
    this._dirty = false;
  }

  /**
   * Internal method to mark the editor as dirty and emit change event
   * @private
   */
  _markDirty() {
    this._dirty = true;
    if (this._emitChanges) {
      this._emitChange();
    }
  }

  /**
   * Emit editor-changed event with debouncing
   * @private
   */
  _emitChange() {
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
    }

    this._debounceTimer = setTimeout(() => {
      this.dispatchEvent(
        new CustomEvent('editor-changed', {
          bubbles: true,
          detail: {
            hasContent: this.hasContent(),
            frameCount: this.allowAnimation ? this.frames.length : 1,
            currentFrame: this.currentFrameIndex,
            frameDelay: this.frameDelay,
          },
        }),
      );
    }, this._debounceMs);
  }

  /**
   * Emit editor-frame-changed event (not debounced)
   * @private
   * @param {string} action - 'add' | 'remove' | 'switch' | 'duplicate'
   */
  _emitFrameChange(action) {
    this.dispatchEvent(
      new CustomEvent('editor-frame-changed', {
        bubbles: true,
        detail: {
          action,
          frameIndex: this.currentFrameIndex,
          frameCount: this.frames.length,
          maxFrames: this.maxFrames,
        },
      }),
    );
  }

  /**
   * Save current canvas state to the current frame slot
   * @private
   */
  _saveCurrentFrame() {
    if (!this.allowAnimation || !this.ctx) return;
    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;
    this.frames[this.currentFrameIndex] = this.ctx.getImageData(
      0,
      0,
      width,
      height,
    );
  }

  /**
   * Load a frame from the frames array into the canvas
   * @private
   * @param {number} index - Frame index to load
   */
  _loadFrame(index) {
    if (!this.allowAnimation || !this.ctx || !this.frames[index]) return;
    this.ctx.putImageData(this.frames[index], 0, 0);
    this.updatePixelDivsFromCanvas();
  }

  /**
   * Add a new blank frame
   * @returns {boolean} True if frame was added, false if at max frames
   */
  addFrame() {
    if (!this.allowAnimation) return false;
    if (this.frames.length >= this.maxFrames) return false;

    // Save current frame first
    this._saveCurrentFrame();

    // Create new blank frame
    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;
    const blankFrame = this.ctx.createImageData(width, height);

    // Insert after current frame
    this.frames.splice(this.currentFrameIndex + 1, 0, blankFrame);

    // Switch to new frame
    this.currentFrameIndex++;
    this._loadFrame(this.currentFrameIndex);

    this._markDirty();
    this._emitFrameChange('add');
    return true;
  }

  /**
   * Duplicate current or specified frame
   * @param {number} [index] - Frame index to duplicate (defaults to current)
   * @returns {boolean} True if frame was duplicated, false if at max frames
   */
  duplicateFrame(index) {
    if (!this.allowAnimation) return false;
    if (this.frames.length >= this.maxFrames) return false;

    const sourceIndex = index !== undefined ? index : this.currentFrameIndex;
    if (sourceIndex < 0 || sourceIndex >= this.frames.length) return false;

    // Save current frame first
    this._saveCurrentFrame();

    // Clone the frame data
    const sourceFrame = this.frames[sourceIndex];
    const clonedFrame = new ImageData(
      new Uint8ClampedArray(sourceFrame.data),
      sourceFrame.width,
      sourceFrame.height,
    );

    // Insert after the source frame
    this.frames.splice(sourceIndex + 1, 0, clonedFrame);

    // Switch to the new duplicate
    this.currentFrameIndex = sourceIndex + 1;
    this._loadFrame(this.currentFrameIndex);

    this._markDirty();
    this._emitFrameChange('duplicate');
    return true;
  }

  /**
   * Remove frame at index
   * @param {number} [index] - Frame index to remove (defaults to current)
   * @returns {boolean} True if frame was removed, false if only one frame remains
   */
  removeFrame(index) {
    if (!this.allowAnimation) return false;
    if (this.frames.length <= 1) return false;

    const removeIndex = index !== undefined ? index : this.currentFrameIndex;
    if (removeIndex < 0 || removeIndex >= this.frames.length) return false;

    // Remove the frame
    this.frames.splice(removeIndex, 1);

    // Adjust current frame index if needed
    if (this.currentFrameIndex >= this.frames.length) {
      this.currentFrameIndex = this.frames.length - 1;
    } else if (this.currentFrameIndex > removeIndex) {
      this.currentFrameIndex--;
    }

    // Load the now-current frame
    this._loadFrame(this.currentFrameIndex);

    this._markDirty();
    this._emitFrameChange('remove');
    return true;
  }

  /**
   * Delete all frames and reset to a single blank frame
   * @returns {boolean} True if successful
   */
  deleteAllFrames() {
    if (!this.allowAnimation) return false;

    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;

    // Clear canvas
    this.ctx.clearRect(0, 0, width, height);

    // Reset to single blank frame
    this.frames = [this.ctx.getImageData(0, 0, width, height)];
    this.currentFrameIndex = 0;

    // Update pixel divs
    this.updatePixelDivsFromCanvas();

    this._markDirty();
    this._emitFrameChange('delete-all');
    return true;
  }

  /**
   * Reverse the order of all frames
   * @returns {boolean} True if frames were reversed, false if not applicable
   */
  reverseFrames() {
    if (!this.allowAnimation) return false;
    if (this.frames.length <= 1) return false;

    // Save current frame before reversing
    this._saveCurrentFrame();

    // Reverse the frames array
    this.frames.reverse();

    // Adjust currentFrameIndex to maintain the same visual frame
    this.currentFrameIndex = this.frames.length - 1 - this.currentFrameIndex;

    // Load the updated current frame
    this._loadFrame(this.currentFrameIndex);

    this._markDirty();
    this._emitFrameChange('reverse');
    return true;
  }

  /**
   * Reorder a frame from one position to another
   * @param {number} fromIndex - Source frame index
   * @param {number} toIndex - Target frame index
   * @returns {boolean} True if reorder was successful
   */
  reorderFrame(fromIndex, toIndex) {
    if (!this.allowAnimation) return false;
    if (fromIndex < 0 || fromIndex >= this.frames.length) return false;
    if (toIndex < 0 || toIndex >= this.frames.length) return false;
    if (fromIndex === toIndex) return false;

    // Save current frame before reordering
    this._saveCurrentFrame();

    // Remove frame from old position
    const [movedFrame] = this.frames.splice(fromIndex, 1);

    // Insert at new position
    this.frames.splice(toIndex, 0, movedFrame);

    // Adjust currentFrameIndex if affected
    if (this.currentFrameIndex === fromIndex) {
      // We moved the current frame
      this.currentFrameIndex = toIndex;
    } else if (
      fromIndex < this.currentFrameIndex &&
      toIndex >= this.currentFrameIndex
    ) {
      // Frame moved from before current to after/at current
      this.currentFrameIndex--;
    } else if (
      fromIndex > this.currentFrameIndex &&
      toIndex <= this.currentFrameIndex
    ) {
      // Frame moved from after current to before/at current
      this.currentFrameIndex++;
    }

    // Load the updated current frame
    this._loadFrame(this.currentFrameIndex);

    this._markDirty();
    this._emitFrameChange('reorder');
    return true;
  }

  /**
   * Handle drag start for frame reordering
   * @param {DragEvent} e - Drag event
   * @param {number} index - Frame index being dragged
   */
  _handleFrameDragStart(e, index) {
    this._draggedFrameIndex = index;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', index.toString());

    // Add visual feedback
    const wrapper = e.target.closest('.frame-thumbnail-wrapper');
    if (wrapper) {
      wrapper.classList.add('frame-dragging');
    }
  }

  /**
   * Handle drag over for frame reordering
   * @param {DragEvent} e - Drag event
   */
  _handleFrameDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }

  /**
   * Handle drag enter for frame reordering (visual indicator)
   * @param {DragEvent} e - Drag event
   * @param {HTMLElement} wrapper - Wrapper element
   */
  _handleFrameDragEnter(e, wrapper) {
    e.preventDefault();
    if (this._draggedFrameIndex !== undefined) {
      wrapper.classList.add('border-pico-green');
    }
  }

  /**
   * Handle drag leave for frame reordering (remove indicator)
   * @param {DragEvent} e - Drag event
   * @param {HTMLElement} wrapper - Wrapper element
   */
  _handleFrameDragLeave(e, wrapper) {
    wrapper.classList.remove('border-pico-green');
  }

  /**
   * Handle drop for frame reordering
   * @param {DragEvent} e - Drag event
   * @param {number} targetIndex - Target frame index
   */
  _handleFrameDrop(e, targetIndex) {
    e.preventDefault();

    const wrapper = e.target.closest('.frame-thumbnail-wrapper');
    if (wrapper) {
      wrapper.classList.remove('border-pico-green');
    }

    if (
      this._draggedFrameIndex !== undefined &&
      this._draggedFrameIndex !== targetIndex
    ) {
      if (this.reorderFrame(this._draggedFrameIndex, targetIndex)) {
        this.renderFrameThumbnails();
      }
    }

    this._draggedFrameIndex = undefined;
  }

  /**
   * Handle drag end for frame reordering (cleanup)
   * @param {DragEvent} e - Drag event
   */
  _handleFrameDragEnd(e) {
    // Reset opacity on all thumbnails
    const container = this.querySelector(
      '[data-editor-section="frame-thumbnails"]',
    );
    if (container) {
      container.querySelectorAll('.frame-thumbnail-wrapper').forEach((w) => {
        w.classList.remove('frame-dragging', 'border-pico-green');
      });
    }

    this._draggedFrameIndex = undefined;
  }

  /**
   * Reset the editor completely (clear canvas and all frames)
   * Used when changing editor size
   */
  reset() {
    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;

    // Clear canvas
    this.ctx.clearRect(0, 0, width, height);

    // Reset frames if animation is enabled
    if (this.allowAnimation) {
      this.frames = [this.ctx.getImageData(0, 0, width, height)];
      this.currentFrameIndex = 0;
    }

    // Update pixel divs
    this.updatePixelDivsFromCanvas();

    // Re-render frame thumbnails if animation is enabled
    if (this.allowAnimation) {
      this.renderFrameThumbnails();
    }

    this._dirty = false;
  }

  /**
   * Switch to a specific frame
   * @param {number} index - Frame index to switch to
   * @returns {boolean} True if switch was successful
   */
  setCurrentFrame(index) {
    if (!this.allowAnimation) return false;
    if (index < 0 || index >= this.frames.length) return false;
    if (index === this.currentFrameIndex) return true;

    // Save current frame before switching
    this._saveCurrentFrame();

    // Switch to new frame
    this.currentFrameIndex = index;
    this._loadFrame(index);

    this._emitFrameChange('switch');
    return true;
  }

  /**
   * Get current frame index
   * @returns {number}
   */
  getCurrentFrame() {
    return this.currentFrameIndex;
  }

  /**
   * Get total number of frames
   * @returns {number}
   */
  getFrameCount() {
    return this.allowAnimation ? this.frames.length : 1;
  }

  /**
   * Export all frames as a horizontal spritesheet blob
   * @returns {Promise<Blob>} PNG blob of horizontal spritesheet
   */
  getAnimationData() {
    return new Promise((resolve, reject) => {
      if (!this.canvas || !this.ctx) {
        reject(new Error('Canvas not initialized'));
        return;
      }

      const width = parseInt(this.getAttribute('width'), 10) || 32;
      const height = parseInt(this.getAttribute('height'), 10) || 32;

      // If no animation, just export single frame
      if (!this.allowAnimation || this.frames.length <= 1) {
        this.canvas.toBlob((blob) => {
          if (blob) resolve(blob);
          else reject(new Error('Failed to export blob'));
        }, 'image/png');
        return;
      }

      // Save current frame before export
      this._saveCurrentFrame();

      // Create spritesheet canvas (horizontal layout)
      const spritesheetCanvas = document.createElement('canvas');
      spritesheetCanvas.width = width * this.frames.length;
      spritesheetCanvas.height = height;
      const ssCtx = spritesheetCanvas.getContext('2d', {
        willReadFrequently: true,
      });

      // Draw each frame side by side
      this.frames.forEach((frameData, i) => {
        // Create temp canvas to convert ImageData to drawable
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = width;
        tempCanvas.height = height;
        const tempCtx = tempCanvas.getContext('2d', {
          willReadFrequently: true,
        });
        tempCtx.putImageData(frameData, 0, 0);

        // Draw to spritesheet at correct position
        ssCtx.drawImage(tempCanvas, i * width, 0);
      });

      // Export spritesheet as blob
      spritesheetCanvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error('Failed to export spritesheet blob'));
      }, 'image/png');
    });
  }

  /**
   * Update pixel divs to match the current canvas state
   */
  updatePixelDivsFromCanvas() {
    if (!this.canvas || !this.ctx || !this.pixelDivs.length) return;

    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;
    const imageData = this.ctx.getImageData(0, 0, width, height);
    const data = imageData.data;

    for (let i = 0; i < data.length; i += 4) {
      const pixelIndex = i / 4;
      const alpha = data[i + 3];
      const div = this.pixelDivs[pixelIndex];

      if (alpha > 10) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        div.style.setProperty('--bg-color', `rgb(${r}, ${g}, ${b})`);
      } else {
        div.style.setProperty('--bg-color', 'transparent');
      }
    }
  }

  /**
   * Set up frame control buttons (add, duplicate, delete, delay)
   */
  setupFrameControls() {
    // Find buttons within the editor's DOM subtree
    const addFrameBtn = this.querySelector('[data-editor-action="add-frame"]');
    const duplicateFrameBtn = this.querySelector(
      '[data-editor-action="duplicate-frame"]',
    );
    const deleteFrameBtn = this.querySelector(
      '[data-editor-action="delete-frame"]',
    );
    const delayInput = this.querySelector(
      '[data-editor-control="frame-delay"]',
    );

    if (addFrameBtn) {
      addFrameBtn.addEventListener('click', () => {
        if (this.addFrame()) {
          this.renderFrameThumbnails();
        }
      });
    }

    if (duplicateFrameBtn) {
      duplicateFrameBtn.addEventListener('click', () => {
        if (this.duplicateFrame()) {
          this.renderFrameThumbnails();
        }
      });
    }

    if (deleteFrameBtn) {
      deleteFrameBtn.addEventListener('click', () => {
        if (this.frames.length > 1) {
          if (this.removeFrame()) {
            this.renderFrameThumbnails();
          }
        }
      });
    }

    const deleteAllFramesBtn = this.querySelector(
      '[data-editor-action="delete-all-frames"]',
    );
    if (deleteAllFramesBtn) {
      deleteAllFramesBtn.addEventListener('click', () => {
        if (
          this.frames.length > 1 &&
          confirm('Delete all frames and start fresh?')
        ) {
          this.deleteAllFrames();
          this.renderFrameThumbnails();
        }
      });
    }

    if (delayInput) {
      // Initialize with current value
      this.frameDelay = parseInt(delayInput.value, 10) || 100;

      delayInput.addEventListener('change', (e) => {
        let value = parseInt(e.target.value, 10);
        // Clamp to valid range (100-2000ms)
        value = Math.max(100, Math.min(2000, value));
        e.target.value = value;
        this.frameDelay = value;
        this._markDirty();
      });
    }

    // Reverse frames button
    const reverseFramesBtn = this.querySelector(
      '[data-editor-action="reverse-frames"]',
    );
    if (reverseFramesBtn) {
      reverseFramesBtn.addEventListener('click', () => {
        if (this.reverseFrames()) {
          this.renderFrameThumbnails();
        }
      });
    }
  }

  /**
   * Render frame thumbnails as mini pixel grids (CSP-safe, no data URLs)
   */
  renderFrameThumbnails() {
    if (!this.allowAnimation) return;

    const container = this.querySelector(
      '[data-editor-section="frame-thumbnails"]',
    );
    if (!container) return;

    // Save current frame before rendering thumbnails
    this._saveCurrentFrame();

    // Clear existing thumbnails
    container.replaceChildren();

    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;

    // Create a thumbnail for each frame
    this.frames.forEach((frameData, index) => {
      // Create wrapper div for the thumbnail
      const wrapper = document.createElement('div');
      wrapper.className = `frame-thumbnail-wrapper relative cursor-pointer p-1 rounded border-2 transition-all ${
        index === this.currentFrameIndex
          ? 'border-pico-blue bg-pico-blue/20'
          : 'border-slate-600 hover:border-slate-400'
      }`;
      wrapper.dataset.frameIndex = index;

      // Create a mini pixel grid for the thumbnail (CSP-safe, no data URLs)
      const thumbGrid = document.createElement('div');
      thumbGrid.className = 'frame-thumbnail';
      // Use CSS custom property for grid columns
      thumbGrid.style.setProperty('--thumb-cols', width);
      thumbGrid.style.setProperty(
        'grid-template-columns',
        `repeat(${width}, 1px)`,
      );

      // Render each pixel from the frame data
      const data = frameData.data;
      for (let i = 0; i < width * height; i++) {
        const pixelDiv = document.createElement('div');
        pixelDiv.className = 'frame-thumbnail-pixel';

        const idx = i * 4;
        const alpha = data[idx + 3];

        if (alpha > 10) {
          const r = data[idx];
          const g = data[idx + 1];
          const b = data[idx + 2];
          // Use CSS custom property for color
          pixelDiv.style.setProperty('--pixel-color', `rgb(${r},${g},${b})`);
          pixelDiv.classList.add('has-color');
        }

        thumbGrid.appendChild(pixelDiv);
      }

      wrapper.appendChild(thumbGrid);

      // Add frame number label
      const label = document.createElement('span');
      label.className =
        "absolute -bottom-1 -right-1 bg-slate-800 text-[6px] font-['Press_Start_2P'] text-slate-400 px-1 rounded";
      label.textContent = index + 1;
      wrapper.appendChild(label);

      // Click to switch to this frame
      wrapper.addEventListener('click', (e) => {
        // Don't switch frame if this was a drag operation
        if (this._draggedFrameIndex !== undefined) return;
        if (this.setCurrentFrame(index)) {
          this.renderFrameThumbnails();
        }
      });

      // Drag-and-drop reordering
      wrapper.draggable = true;
      wrapper.addEventListener('dragstart', (e) =>
        this._handleFrameDragStart(e, index),
      );
      wrapper.addEventListener('dragover', (e) => this._handleFrameDragOver(e));
      wrapper.addEventListener('dragenter', (e) =>
        this._handleFrameDragEnter(e, wrapper),
      );
      wrapper.addEventListener('dragleave', (e) =>
        this._handleFrameDragLeave(e, wrapper),
      );
      wrapper.addEventListener('drop', (e) => this._handleFrameDrop(e, index));
      wrapper.addEventListener('dragend', (e) => this._handleFrameDragEnd(e));

      container.appendChild(wrapper);
    });

    // Add "add frame" button at the end if under max
    if (this.frames.length < this.maxFrames) {
      const addBtn = document.createElement('div');
      addBtn.className =
        'frame-thumbnail-add border-slate-600 hover:border-pico-green hover:bg-pico-green/10';
      addBtn.innerHTML = `<span class="font-['Press_Start_2P'] text-[10px] text-slate-500">+</span>`;
      addBtn.title = 'Add new frame';

      addBtn.addEventListener('click', () => {
        if (this.addFrame()) {
          this.renderFrameThumbnails();
        }
      });

      container.appendChild(addBtn);
    }
  }

  /**
   * Get the current frame delay in ms
   * @returns {number}
   */
  getFrameDelay() {
    return this.frameDelay || 100;
  }

  /**
   * Queue a thumbnail update with debouncing (for performance during drawing)
   * @private
   */
  _queueThumbnailUpdate() {
    if (!this.allowAnimation) return;

    if (this._thumbnailUpdateTimer) {
      clearTimeout(this._thumbnailUpdateTimer);
    }

    // Update thumbnail after a short delay to batch rapid pixel changes
    this._thumbnailUpdateTimer = setTimeout(() => {
      this.updateCurrentFrameThumbnail();
    }, 50);
  }

  /**
   * Update just the current frame's thumbnail (for live preview while drawing)
   */
  updateCurrentFrameThumbnail() {
    if (!this.allowAnimation) return;

    const container = this.querySelector(
      '[data-editor-section="frame-thumbnails"]',
    );
    if (!container) return;

    const wrapper = container.querySelector(
      `[data-frame-index="${this.currentFrameIndex}"]`,
    );
    if (!wrapper) return;

    const thumbGrid = wrapper.querySelector('.frame-thumbnail');
    if (!thumbGrid) return;

    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;

    // Get current canvas data (not from frames array, as it may not be saved yet)
    const imageData = this.ctx.getImageData(0, 0, width, height);
    const data = imageData.data;

    // Update each pixel in the thumbnail
    const pixels = thumbGrid.querySelectorAll('.frame-thumbnail-pixel');
    for (let i = 0; i < pixels.length && i < width * height; i++) {
      const idx = i * 4;
      const alpha = data[idx + 3];
      const pixelDiv = pixels[i];

      if (alpha > 10) {
        const r = data[idx];
        const g = data[idx + 1];
        const b = data[idx + 2];
        pixelDiv.style.setProperty('--pixel-color', `rgb(${r},${g},${b})`);
        pixelDiv.classList.add('has-color');
      } else {
        pixelDiv.style.removeProperty('--pixel-color');
        pixelDiv.classList.remove('has-color');
      }
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();

    window.removeEventListener('resize', this._handleWindowResize);
    window.removeEventListener('keydown', this._handleKeyDown);
    if (this._handleDocumentMouseUp) {
      document.removeEventListener('mouseup', this._handleDocumentMouseUp);
    }
    if (this._resizeDebounce) {
      clearTimeout(this._resizeDebounce);
    }
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
    }
    if (this._thumbnailUpdateTimer) {
      clearTimeout(this._thumbnailUpdateTimer);
    }

    if (this.canvas) {
      // Clean up canvas
      this.canvas = null;
      this.ctx = null;
    }
  }
}

customElements.define('pixel-editor', PixelEditor);

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-pixel-download]');
  if (!button) return;

  const card =
    button.closest('[data-pixel-card]') || button.closest('.group') || button;

  // Prefer explicit target in mixed cards (e.g. avatar + artwork).
  const explicitTarget = card.querySelector('[data-pixel-download-target]');
  const pixelElements = card.querySelectorAll('pixel-art, pixel-animation');
  const pixelElement = explicitTarget || pixelElements[pixelElements.length - 1];
  if (!pixelElement || typeof pixelElement.download !== 'function') return;

  const filename = button.getAttribute('data-download-filename') || 'pixel-art.png';
  pixelElement.download(filename);
});

document.addEventListener('editor-changed', (event) => {
  const editor = event.target;
  if (!editor || editor.tagName !== 'PIXEL-EDITOR') return;

  const container = editor.closest('[data-avatar-editor]');
  if (!container) return;

  const hasContent = event.detail && event.detail.hasContent;
  const saveButtons = container.querySelectorAll('[data-editor-action="save"]');

  saveButtons.forEach((btn) => {
    if (hasContent) {
      btn.disabled = false;
      btn.classList.remove('opacity-50', 'cursor-not-allowed');
    } else {
      btn.disabled = true;
      btn.classList.add('opacity-50', 'cursor-not-allowed');
    }
  });
});

document.addEventListener('click', async (event) => {
  const saveBtn = event.target.closest('[data-editor-action="save"]');
  if (!saveBtn) return;

  const container = saveBtn.closest('[data-avatar-editor]');
  if (!container) return;

  event.preventDefault();

  const editor = container.querySelector('pixel-editor');
  if (!editor) return;

  if (!editor.hasContent()) {
    alert('Cannot save empty avatar');
    return;
  }

  const form = saveBtn.closest('form');
  if (!form) return;

  const hiddenInput = form.querySelector('[name="pixel_data"]');
  if (hiddenInput) {
    const blob = await editor.getSerializedData();
    const reader = new FileReader();
    reader.onloadend = function () {
      hiddenInput.value = reader.result.split(',')[1];
      if (window.htmx) {
        window.htmx.trigger(form, 'submit');
      } else {
        form.requestSubmit();
      }
    };
    reader.readAsDataURL(blob);
  } else if (window.htmx) {
    window.htmx.trigger(form, 'submit');
  } else {
    form.requestSubmit();
  }
});

const attachAvatarAfterRequestHandler = () => {
  document.body.addEventListener('htmx:afterRequest', (event) => {
    const form = event.detail.elt;
    if (!form || form.id !== 'editor-form') return;
    if (!event.detail.successful) return;

    const successUrl = form.getAttribute('data-avatar-success-url');
    if (successUrl) {
      alert('Avatar saved successfully!');
      window.location.href = successUrl;
    }
  });
};

if (document.body) {
  attachAvatarAfterRequestHandler();
} else {
  document.addEventListener('DOMContentLoaded', attachAvatarAfterRequestHandler, {
    once: true,
  });
}
