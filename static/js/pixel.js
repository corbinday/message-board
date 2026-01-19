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
      `${Math.max(1, Math.round(snapped / 6))}px`
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
    const ctx = canvas.getContext('2d');

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
    const ctx = canvas.getContext('2d');

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
    fadeSpeed = '8s'
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
            '8s'
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
    
    // Bind resize handler to instance
    this._handleWindowResize = this._handleWindowResize.bind(this);
    this._handleKeyDown = this._handleKeyDown.bind(this);
    this._resizeDebounce = null;
  }

  resolveAndSnapPixelSize() {
    // Handle pixel-grow mode (dynamic sizing to fill container)
    if (this.classList.contains('pixel-grow')) {
       // Find the main wrapper to determine available width
       const wrapper = this.firstElementChild;
       if (wrapper) {
          const style = getComputedStyle(wrapper);
          const paddingX = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
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
            const snapped = Math.min(24, Math.max(1, Math.floor(size)));
            
            this.style.setProperty('--pixel-size', `${snapped}px`);
            this.style.setProperty('--pixel-gap', `${Math.max(1, Math.round(snapped/6))}px`);
          }
       }
    } else {
      // Standard mode: Remove inline style to read from CSS classes
      this.style.removeProperty('--pixel-size');
      this.style.removeProperty('--pixel-gap');
    }

    // Call parent method to get the new snapped pixel size (reads the property we just set or CSS)
    const snapped = super.resolveAndSnapPixelSize();
    
    // Update the grid layout with new dimensions
    if (this.grid && this.pixelDivs.length > 0) {
      const width = parseInt(this.getAttribute('width'), 10) || 32;
      const height = parseInt(this.getAttribute('height'), 10) || 32;
      const pixelGap = this.style.getPropertyValue('--pixel-gap') || '2px';
      
      const pSize = snapped;
      const pGap = parseFloat(pixelGap);
      
      // Calculate total dimensions
      const totalWidth = (width * pSize) + ((width - 1) * pGap) + pGap; 
      const totalHeight = (height * pSize) + ((height - 1) * pGap) + pGap;
      
      // Update container
      this.grid.style.width = `${totalWidth}px`;
      this.grid.style.height = `${totalHeight}px`;
      this.grid.style.padding = `calc(${pixelGap} / 2)`;
      this.grid.style.gridTemplateColumns = `repeat(${width}, ${pSize}px)`;
      this.grid.style.gridAutoRows = `${pSize}px`;
      this.grid.style.gap = pixelGap;
      
      // Update individual pixels
      this.pixelDivs.forEach(div => {
        div.style.width = `${pSize}px`;
        div.style.height = `${pSize}px`;
      });
      
      // Update recent colors size too
      const recentContainer = document.getElementById('recent-colors');
      if (recentContainer) {
        Array.from(recentContainer.children).forEach(div => {
          div.style.width = `${pSize}px`;
          div.style.height = `${pSize}px`;
        });
      }
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
        subtree: true
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

    // Create internal canvas as source of truth
    this.canvas = document.createElement('canvas');
    this.canvas.width = width;
    this.canvas.height = height;
    this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });

    // Initialize canvas with transparent background
    this.ctx.clearRect(0, 0, width, height);

    // Ensure CSS variables are accessible to the nested grid div
    // Read from inline style (set by resolveAndSnapPixelSize) or computed style
    const pixelSize = this.style.getPropertyValue('--pixel-size') || 
                      getComputedStyle(this).getPropertyValue('--pixel-size') || '10px';
    const pixelGap = this.style.getPropertyValue('--pixel-gap') || 
                     getComputedStyle(this).getPropertyValue('--pixel-gap') || '2px';
    
    // Explicitly set CSS variables on grid div to ensure they're accessible
    this.grid.style.setProperty('--pixel-size', pixelSize);
    this.grid.style.setProperty('--pixel-gap', pixelGap);
    
    // Set up grid display on the grid div using explicit values to avoid inheritance issues
    this.grid.style.display = 'grid';
    this.grid.style.gridTemplateColumns = `repeat(${width}, ${pixelSize})`;
    // We don't need gridAutoRows if we set height on divs, but keeping it is good practice
    this.grid.style.gridAutoRows = pixelSize;
    this.grid.style.gap = pixelGap;
    
    // Apply grid styling to match style.css for visibility
    // Dark background for the grid container (shows through gaps)
    this.grid.style.backgroundColor = 'var(--blank-pixel-color, #262626)';
    this.grid.style.padding = `calc(${pixelGap} / 2)`;
    
    // Calculate total dimensions to force container size (prevent collapsing)
    const pSize = parseFloat(pixelSize);
    const pGap = parseFloat(pixelGap);
    const totalWidth = (width * pSize) + ((width - 1) * pGap) + pGap; // + padding
    const totalHeight = (height * pSize) + ((height - 1) * pGap) + pGap; // + padding
    
    this.grid.style.width = `${totalWidth}px`;
    this.grid.style.height = `${totalHeight}px`;
    
    // Remove w-fit/h-fit classes if present as they can cause collapsing issues
    this.grid.classList.remove('w-fit', 'h-fit');

    // Create pixel divs
    const fragment = document.createDocumentFragment();
    this.pixelDivs = [];

    for (let i = 0; i < width * height; i++) {
      const div = document.createElement('div');
      // Set explicit size on pixels to be robust against grid auto-sizing failures
      div.style.width = pixelSize;
      div.style.height = pixelSize;
      div.style.backgroundColor = 'transparent';
      
      // Styling for grid lines and interaction
      div.style.boxShadow = 'inset 0 0 0 0.5px rgba(255, 255, 255, 0.15)';
      div.style.cursor = 'crosshair';
      div.style.transition = 'background-color 0.05s ease';
      
      // Add hover effect via JS since we can't easily inject CSS rules
      div.addEventListener('mouseenter', () => {
        // White border that fills the grid lines (outer glow)
        // Active even when drawing
        div.style.boxShadow = 'inset 0 0 0 0.5px rgba(255, 255, 255, 0.15), 0 0 0 1px white';
        div.style.zIndex = '10';
      });
      div.addEventListener('mouseleave', () => {
        // Reset to base style
        div.style.boxShadow = 'inset 0 0 0 0.5px rgba(255, 255, 255, 0.15)';
        div.style.zIndex = 'auto';
      });

      this.pixelDivs.push(div);
      fragment.appendChild(div);
    }

    this.grid.replaceChildren(fragment);
    this.markRendered();

    // Load initial image if provided
    if (initialSrc) {
      await this.loadBytes(initialSrc);
    }

    // Bind mouse/touch events
    this.setupDrawingEvents();
    
    // Bind tool controls
    this.setupControls();
    
    // Initial render of recent colors
    this.renderRecentColors();
    
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

  setupControls() {
    // Find controls within the light/shadow DOM or document
    // We look in document because the controls are in the light DOM slots/children
    const colorPicker = document.getElementById('color-picker');
    const penBtn = document.getElementById('pen');
    const eraserBtn = document.getElementById('eraser');
    const dropperBtn = document.getElementById('dropper');
    const clearBtn = document.getElementById('clear');

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
    
    this.updateToolUI();
  }

  updateToolUI() {
    const tools = {
      'pen': document.getElementById('pen'),
      'eraser': document.getElementById('eraser'),
      'dropper': document.getElementById('dropper')
    };
    
    // Reset all
    Object.values(tools).forEach(btn => {
      if (btn) {
        btn.classList.remove('bg-slate-600', 'border-slate-400', 'text-white');
        btn.classList.add('bg-slate-800', 'border-slate-600', 'text-gray-300');
      }
    });

    // Highlight active
    const activeBtn = tools[this.currentTool];
    if (activeBtn) {
      activeBtn.classList.remove('bg-slate-800', 'border-slate-600', 'text-gray-300');
      activeBtn.classList.add('bg-slate-600', 'border-slate-400', 'text-white');
    }
  }

  clearCanvas() {
    const width = parseInt(this.getAttribute('width'), 10) || 32;
    const height = parseInt(this.getAttribute('height'), 10) || 32;
    
    // Clear canvas
    this.ctx.clearRect(0, 0, width, height);
    
    // Clear divs
    this.pixelDivs.forEach(div => {
      div.style.backgroundColor = 'transparent';
    });
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
      e.preventDefault();
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

    // Mouse events - attach to grid div
    this.grid.addEventListener('mousedown', handleStart);
    this.grid.addEventListener('mousemove', handleMove);
    this.grid.addEventListener('mouseup', handleEnd);
    this.grid.addEventListener('mouseleave', handleEnd);

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
        // Set pixel color
        div.style.backgroundColor = this.currentColor;
        // Update canvas
        this.ctx.fillStyle = this.currentColor;
        this.ctx.fillRect(x, y, 1, 1);
        
        // Add to recents when used to paint
        this.addToRecents(this.currentColor);
      } else if (this.currentTool === 'eraser') {
        // Clear pixel
        div.style.backgroundColor = 'transparent';
        // Clear from canvas
        this.ctx.clearRect(x, y, 1, 1);
      } else if (this.currentTool === 'dropper') {
        // Pick color
        // Read from canvas data to get accurate color
        const p = this.ctx.getImageData(x, y, 1, 1).data;
        if (p[3] > 0) { // If not transparent
           // Convert to hex
           const hex = '#' + [p[0], p[1], p[2]].map(x => {
             const hex = x.toString(16);
             return hex.length === 1 ? '0' + hex : hex;
           }).join('');
           
           this.setColor(hex);
           
           // Update color picker UI
           const picker = document.getElementById('color-picker');
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
    this.recentColors = this.recentColors.filter(c => c !== color);
    
    // Add to front
    this.recentColors.unshift(color);
    
    // Limit to 10
    if (this.recentColors.length > 10) {
      this.recentColors.length = 10;
    }
    
    this.renderRecentColors();
  }

  renderRecentColors() {
    const container = document.getElementById('recent-colors');
    if (!container) return;
    
    container.replaceChildren(); // Clear
    
    // Use pixel size for the recent color swatches too
    const pixelSize = this.style.getPropertyValue('--pixel-size') || 
                      getComputedStyle(this).getPropertyValue('--pixel-size') || '10px';
    
    this.recentColors.forEach(color => {
      const div = document.createElement('div');
      div.style.backgroundColor = color;
      div.style.width = pixelSize;
      div.style.height = pixelSize;
      div.style.border = '1px solid rgba(255,255,255,0.2)';
      div.style.cursor = 'pointer';
      
      div.addEventListener('click', () => {
        this.currentColor = color;
        const picker = document.getElementById('color-picker');
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

        // Validate dimensions
        if (img.width !== width || img.height !== height) {
          reject(new Error(`Image dimensions must be ${width}x${height}`));
          return;
        }

        // Draw image to canvas
        this.ctx.clearRect(0, 0, width, height);
        this.ctx.drawImage(img, 0, 0);

        // Update grid UI
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
            div.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
          } else {
            div.style.backgroundColor = 'transparent';
          }
        }

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
        div.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
      } else {
        div.style.backgroundColor = 'transparent';
      }
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    
    window.removeEventListener('resize', this._handleWindowResize);
    window.removeEventListener('keydown', this._handleKeyDown);
    if (this._resizeDebounce) {
      clearTimeout(this._resizeDebounce);
    }
    
    if (this.canvas) {
      // Clean up canvas
      this.canvas = null;
      this.ctx = null;
    }
  }
}

customElements.define('pixel-editor', PixelEditor);
