"""Small dependency-free image helpers for simulator framebuffer artifacts."""

from pathlib import Path
import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def save_rgb565_png(raw: bytes, output: Path | str, width: int, height: int) -> None:
    """Convert little-endian RGB565 pixels to a standard RGB PNG."""
    output = Path(output)
    expected_size = width * height * 2
    if len(raw) != expected_size:
        raise ValueError(
            "Unexpected RGB565 size: {} bytes (expected {})".format(len(raw), expected_size)
        )

    scanlines = bytearray()
    for row in range(height):
        scanlines.append(0)
        start = row * width * 2
        for offset in range(start, start + width * 2, 2):
            pixel = raw[offset] | (raw[offset + 1] << 8)
            scanlines.extend(
                (
                    ((pixel >> 11) & 0x1F) << 3,
                    ((pixel >> 5) & 0x3F) << 2,
                    (pixel & 0x1F) << 3,
                )
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as image:
        image.write(b"\x89PNG\r\n\x1a\n")
        image.write(_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        image.write(_chunk(b"IDAT", zlib.compress(bytes(scanlines))))
        image.write(_chunk(b"IEND", b""))
