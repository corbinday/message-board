class PixelAnimation extends HTMLElement {
  async connectedCallback() {
    if (this.hasAttribute('rendered')) return;

    const src = this.getAttribute('src');
    const override = this.getAttribute('color-override');
    const frameW = parseInt(this.getAttribute('frame-width'));
    const frameH = parseInt(this.getAttribute('frame-height'));
    const speed = parseInt(this.getAttribute('speed')) || 200;

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

    // We only need the canvas to be the size of ONE frame to extract data easily
    canvas.width = frameW;
    canvas.height = frameH;

    // Calculate total frames based on a horizontal layout
    const totalFrames = Math.floor(img.width / frameW);
    const framesData = [];

    // Extracting frames: sx and sy can be adjusted for vertical sheets
    for (let f = 0; f < totalFrames; f++) {
      ctx.clearRect(0, 0, frameW, frameH);

      // drawImage(image, sx, sy, sWidth, sHeight, dx, dy, dWidth, dHeight)
      ctx.drawImage(
        img,
        f * frameW,
        0, // Source X (moves right), Source Y (stays 0)
        frameW,
        frameH, // Source Dimensions
        0,
        0, // Destination X, Y
        frameW,
        frameH // Destination Dimensions
      );

      framesData.push(ctx.getImageData(0, 0, frameW, frameH).data);
    }

    // Initialize the CSS Grid
    this.style.gridTemplateColumns = `repeat(${frameW}, var(--pixel-size))`;
    const fragment = document.createDocumentFragment();
    const pixelDivs = [];

    for (let i = 0; i < frameW * frameH; i++) {
      const div = document.createElement('div');
      fragment.appendChild(div);
      pixelDivs.push(div);
    }

    this.innerHTML = '';
    this.appendChild(fragment);
    this.setAttribute('rendered', 'true');

    // Robust Animation Loop
    let currentFrame = 0;
    const updateFrame = () => {
      const data = framesData[currentFrame];

      for (let i = 0; i < pixelDivs.length; i++) {
        const dataIdx = i * 4;
        const alpha = data[dataIdx + 3];
        const div = pixelDivs[i];

        if (alpha > 10) {
          const r = data[dataIdx],
            g = data[dataIdx + 1],
            b = data[dataIdx + 2];
          div.style.backgroundColor = override
            ? `rgb(${override})`
            : `rgb(${r},${g},${b})`;
        } else {
          div.style.backgroundColor = 'transparent';
        }
      }

      currentFrame = (currentFrame + 1) % totalFrames;

      // Use setTimeout for the speed control, but requestAnimationFrame for the render
      setTimeout(() => {
        requestAnimationFrame(updateFrame);
      }, speed);
    };

    updateFrame();
  }
}

customElements.define('pixel-animation', PixelAnimation);
