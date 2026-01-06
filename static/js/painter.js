// painter.js

// --- 1. Global Variables (Initialized to be set later) ---
// These are set by the Jinja template's nonced script block
const GRID_SIZE_X = CONFIG.GRID_SIZE_X;
const GRID_SIZE_Y = CONFIG.GRID_SIZE_Y;

// References to DOM elements, initialized globally but set inside DOMContentLoaded
let gridElement;
let colorInput;

let currentColor;
let isMouseDown = false;

// --- 2. Painting Handlers ---
function paintPixel(pixel) {
  // Sets the background color of a pixel div to the currently selected color.
  pixel.style.backgroundColor = currentColor;
}

function startPainting(e) {
  isMouseDown = true;
  // Prevent browser's default behavior (like dragging/selecting text)
  e.preventDefault();
  paintPixel(e.target);
}

function paintIfDragging(e) {
  if (isMouseDown) {
    paintPixel(e.target);
  }
}

function stopPainting() {
  isMouseDown = false;
}

// Global listener handles mouse release anywhere on the page
document.addEventListener('mouseup', stopPainting);

// --- 3. Grid Management Functions ---

function initializeGrid() {
  // Note: gridElement is guaranteed to be a valid DOM element here.
  const totalPixels = GRID_SIZE_X * GRID_SIZE_Y;

  for (let i = 0; i < totalPixels; i++) {
    const pixel = document.createElement('div');
    pixel.id = `p-${i}`;

    // Ensure starting color is defined (e.g., black)
    pixel.style.backgroundColor = '#000000';
    pixel.classList.add('aspect-square', 'border', 'border-gray-800');

    // Attach interaction handlers
    pixel.addEventListener('mousedown', startPainting);
    pixel.addEventListener('mouseover', paintIfDragging);
    pixel.addEventListener('mouseup', stopPainting);

    gridElement.appendChild(pixel);
  }
}

function clearBoard() {
  const pixels = gridElement.children;
  const defaultColor = '#000000';

  // Iterate over every pixel div and reset its background color
  for (let i = 0; i < pixels.length; i++) {
    pixels[i].style.backgroundColor = defaultColor;
  }
}

function generateRawPixelData() {
  const pixels = gridElement.children;
  const flatRGBArray = [];

  // CORRECTION: Make this function robust for both Hex (#RRGGBB) and RGB (rgb(r, g, b)) formats.
  function colorToRgbArray(colorString) {
    if (!colorString || colorString === '#000000' || colorString === 'initial' || colorString === 'transparent') {
      return [0, 0, 0];
    }
    
    // 1. Handle Hex format (e.g., #FF00AA)
    if (colorString.startsWith('#')) {
      const bigint = parseInt(colorString.slice(1), 16);
      const r = (bigint >> 16) & 255;
      const g = (bigint >> 8) & 255;
      const b = bigint & 255;
      return [r, g, b];
    }

    // 2. Handle RGB format (e.g., rgb(255, 0, 0)) - This is the critical fix!
    if (colorString.startsWith('rgb')) {
        // Use a simple regex to pull the numbers out of the string
        const match = colorString.match(/\d+/g);
        if (match && match.length >= 3) {
            // Convert matched strings to integers
            return [parseInt(match[0]), parseInt(match[1]), parseInt(match[2])];
        }
    }
    
    // Default to black if all parsing fails
    return [0, 0, 0];
  }

  for (let i = 0; i < pixels.length; i++) {
    const pixel = pixels[i];
    
    // Get the color set in the style attribute.
    let colorValue = pixel.style.backgroundColor;
    
    // If the style property is empty or 'initial', use the computed style (which will be an RGB string)
    // NOTE: Accessing computed style is safer but slightly slower, but for 1024 pixels, it's fine.
    if (!colorValue || colorValue === 'initial') {
         colorValue = window.getComputedStyle(pixel).backgroundColor;
    }

    const [r, g, b] = colorToRgbArray(colorValue);

    flatRGBArray.push(r, g, b);
  }

  // --- Base64 Encoding (Should be correct from last attempt, but repeating the robust version) ---
  const rawData = new Uint8Array(flatRGBArray);
  let binaryString = '';
  const len = rawData.byteLength;
  for (let i = 0; i < len; i++) {
    binaryString += String.fromCharCode(rawData[i]);
  }
  
  const base64String = btoa(binaryString);

  return base64String;
}

function setupEventListeners() {
  // 1. Color Input Listener (moved here to ensure colorInput is available)
  colorInput.addEventListener('input', (e) => {
    currentColor = e.target.value;
  });

  // 2. Clear Board Listener
  const clearButton = document.getElementById('clear-board-button');
  if (clearButton) {
    clearButton.addEventListener('click', clearBoard);
  }

  // 3. HTMX Form Listener to prep data
  // Using htmx:configRequest to reliably inject data into the request payload.
  document.body.addEventListener('htmx:configRequest', (evt) => {
    const form = evt.detail.elt;

    if (form.id === 'paint-form') {
      console.log(
        'HTMX Config Request Fired! Injecting data directly into payload...'
      );

      // Check if this is avatar mode (has mode=paint hidden input)
      const modeInput = form.querySelector('input[name="mode"]');
      const isAvatarMode = modeInput && modeInput.value === 'paint';

      let base64Data;
      if (isAvatarMode) {
        // For avatar mode, export canvas as PNG
        const canvas = document.createElement('canvas');
        canvas.width = CONFIG.GRID_SIZE_X;
        canvas.height = CONFIG.GRID_SIZE_Y;
        const ctx = canvas.getContext('2d');
        const pixels = gridElement.children;
        
        // Draw pixels to canvas
        const pixelSize = canvas.width / CONFIG.GRID_SIZE_X;
        for (let i = 0; i < pixels.length; i++) {
          const pixel = pixels[i];
          const x = (i % CONFIG.GRID_SIZE_X) * pixelSize;
          const y = Math.floor(i / CONFIG.GRID_SIZE_X) * pixelSize;
          const color = pixel.style.backgroundColor || window.getComputedStyle(pixel).backgroundColor;
          ctx.fillStyle = color || 'rgb(0, 0, 0)';
          ctx.fillRect(x, y, pixelSize, pixelSize);
        }
        
        // Export as PNG base64
        base64Data = canvas.toDataURL('image/png').split(',')[1];
      } else {
        // For message mode, use RGB data
        base64Data = generateRawPixelData();
      }

      // CRITICAL FIX: Inject the data directly into the HTMX request parameters.
      // This is far more reliable than setting the hidden input's value just before submission.
      evt.detail.parameters['pixel_data'] = base64Data;

      console.log('Data payload length:', base64Data.length);
      console.log('Data successfully added to request parameters.');
    }
  });
}

// --- 4. Execution (Fix for Race Condition) ---
// We defer all DOM access and initialization until the DOM is fully loaded.
document.addEventListener('DOMContentLoaded', () => {
  // CRITICAL: Retrieve the DOM element references here where they are guaranteed to exist
  gridElement = document.getElementById('pixel-grid');
  colorInput = document.getElementById('current-color');

  // Initialize state variables that depend on the elements
  currentColor = colorInput.value;

  // Initialize the grid (which creates the 1024 pixel children)
  initializeGrid();

  // Setup all event listeners
  setupEventListeners();
});
