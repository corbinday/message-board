"""Utility functions for avatar generation and handling."""

import zlib
import struct


def generate_default_avatar() -> bytes:
    """
    Generate a default 32x32 pixel avatar.
    Returns PNG bytes.
    Creates a simple PNG manually without PIL.
    """
    # PNG signature
    png_signature = b"\x89PNG\r\n\x1a\n"

    # Create 32x32 RGB image data
    # Dark grey background (40, 40, 40)
    # Red square in center (255, 0, 0)
    width, height = 32, 32
    pixels = []

    for y in range(height):
        row = []
        for x in range(width):
            # Red square in center (8-24)
            if 8 <= x < 24 and 8 <= y < 24:
                r, g, b = 255, 0, 0
            # Border
            elif x == 0 or x == 31 or y == 0 or y == 31:
                r, g, b = 100, 100, 100
            # Background
            else:
                r, g, b = 40, 40, 40
            row.extend([r, g, b])
        # Add filter byte (0 = none)
        pixels.append(bytes([0] + row))

    # Combine all scanlines
    image_data = b"".join(pixels)

    # Compress with zlib
    compressed = zlib.compress(image_data, level=9)

    # Build PNG chunks
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr_chunk = (
        struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
    )

    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat_chunk = (
        struct.pack(">I", len(compressed))
        + b"IDAT"
        + compressed
        + struct.pack(">I", idat_crc)
    )

    iend_chunk = (
        struct.pack(">I", 0)
        + b"IEND"
        + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    )

    # Combine all chunks
    return png_signature + ihdr_chunk + idat_chunk + iend_chunk
