/* =========================================================
 * SHARED BASE CLASS
 * ========================================================= */

class PixelGridBase extends HTMLElement {
  resolveAndSnapPixelSize() {
    const computed = getComputedStyle(this);
    let raw = parseFloat(computed.getPropertyValue('--pixel-size'));

    if (!Number.isFinite(raw) || raw <= 0) {
      raw = 10;
    }

    const snapped = Math.max(1, Math.round(raw));

    this.style.setProperty('--pixel-size', `${snapped}px`);
    this.style.setProperty(
      '--pixel-gap',
      `${Math.max(1, Math.round(snapped / 6))}px`
    );

    return snapped;
  }

  markRendered() {
    this.setAttribute('rendered', 'true');
  }

  isRendered() {
    return this.hasAttribute('rendered');
  }

  disconnectedCallback() {
    if (this._cleanup) this._cleanup();
  }
}

/* =========================================================
 * PIXEL ANIMATION
 * ========================================================= */

class PixelAnimation extends PixelGridBase {
  async connectedCallback() {
    if (this.isRendered()) return;

    this.resolveAndSnapPixelSize();

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
          div.style.opacity = '0';
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
        div.style.setProperty('--base-opacity', '0');
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
