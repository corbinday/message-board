class PixelArt extends HTMLElement {
  constructor() {
    super();
    // Lowered baseline rain opacity as requested
    this.RAIN_OPACITY = 0.3;
    this.TRAIL_OPACITY = 1.0;

    this.currentRainCount = 0;
    this.MAX_RAIN_CONCURRENCY = 30;
    this.RAIN_ACTIVE_HOLD = 4000;
  }

  async connectedCallback() {
    if (this.hasAttribute('rendered')) return;

    const src = this.getAttribute('src');
    const override = this.getAttribute('color-override');
    const trailOverride = this.getAttribute('trail-color-override');
    const hasHover = this.hasAttribute('hover-trail');
    const hasRain = this.hasAttribute('digital-rain');

    // 1. Parse Rain Colors
    // Expected format: "255,0,0 | 0,255,0 | 0,0,255"
    const rainAttr = this.getAttribute('rain-colors');
    this.rainColors = rainAttr
      ? rainAttr.split('|').map((c) => `rgb(${c.trim()})`)
      : ['rgb(255,0,0)', 'rgb(0,255,0)', 'rgb(0,0,255)'];

    const img = new Image();
    img.crossOrigin = 'Anonymous';
    img.src = src;

    try {
      await img.decode();
    } catch (e) {
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
        const r = data[i],
          g = data[i + 1],
          b = data[i + 2];
        const color = override ? `rgb(${override})` : `rgb(${r},${g},${b})`;
        div.style.backgroundColor = color;
        div.style.setProperty('--base-opacity', '1');
      } else {
        div.style.setProperty('--base-opacity', '0');
        this.emptyPixels.push(div);
      }

      if (hasHover) {
        div.addEventListener('mouseenter', () => {
          // Use trailOverride if present, otherwise default to red
          const tColor = trailOverride
            ? `rgb(${trailOverride})`
            : 'rgb(255, 0, 0)';
          this.triggerEffect(div, tColor, this.TRAIL_OPACITY, 200, '0s', '1s');
        });
      }

      fragment.appendChild(div);
    }

    this.innerHTML = '';
    this.appendChild(fragment);
    this.setAttribute('rendered', 'true');

    if (hasRain && this.emptyPixels.length > 0) {
      setTimeout(() => this.startGlobalRainLoop(), 1000);
    }
  }

  // Frequency logic: 60:30:10 style decay
  getWeightedRainColor() {
    const n = this.rainColors.length;
    if (n === 1) return this.rainColors[0];

    // Create weights based on a decay curve (Power 2)
    // For 3 colors: Weight 1 is 9, Weight 2 is 4, Weight 3 is 1.
    // Total 14. 9/14 = ~64%, 4/14 = ~28%, 1/14 = ~8%
    const weights = this.rainColors.map((_, i) => Math.pow(n - i, 2));
    const totalWeight = weights.reduce((a, b) => a + b, 0);

    let random = Math.random() * totalWeight;
    for (let i = 0; i < n; i++) {
      if (random < weights[i]) return this.rainColors[i];
      random -= weights[i];
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
    setTimeout(() => {
      el.classList.remove('active-pixel');
    }, duration);
  }

  startGlobalRainLoop() {
    const rainTick = () => {
      if (this.currentRainCount < this.MAX_RAIN_CONCURRENCY) {
        const randomPixel =
          this.emptyPixels[Math.floor(Math.random() * this.emptyPixels.length)];

        if (!randomPixel.classList.contains('active-pixel')) {
          this.currentRainCount++;
          const rainColor = this.getWeightedRainColor();

          this.triggerEffect(
            randomPixel,
            rainColor,
            this.RAIN_OPACITY,
            this.RAIN_ACTIVE_HOLD,
            '2s',
            '8s'
          );

          setTimeout(() => {
            this.currentRainCount--;
          }, this.RAIN_ACTIVE_HOLD);
        }
      }
      const nextDelay = Math.random() * 800 + 100;
      setTimeout(rainTick, nextDelay);
    };
    rainTick();
  }
}

customElements.define('pixel-art', PixelArt);
