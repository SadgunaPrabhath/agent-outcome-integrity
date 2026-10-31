"""Minimal, dependency-free PNG codec — just enough to fingerprint screenshots.

The Visual verifier needs grayscale pixels to hash, and a real capture backend
(Playwright/Chromium) hands back a PNG. Rather than pull in Pillow for the whole
engine, this decodes the common screenshot case with the standard library only
(``zlib`` for DEFLATE, hand-rolled scanline defiltering).

Supported: 8-bit, non-interlaced PNGs in grayscale / grayscale+alpha / RGB / RGBA
(colour types 0, 4, 2, 6) — which covers Chromium screenshots. Anything else
(16-bit, interlaced, palette) raises :class:`PngError`, and the screenshot source
turns that into a graceful "unreadable" observation rather than a crash.

A tiny encoder is included so tests and tools can round-trip images without any
image library.
"""

from __future__ import annotations

import struct
import zlib

_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}  # colour type -> samples per pixel


class PngError(Exception):
    """Raised for a malformed or unsupported PNG."""


def _luma(r: int, g: int, b: int) -> int:
    return round(0.299 * r + 0.587 * g + 0.114 * b)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png_gray(data: bytes) -> tuple[list[int], int, int]:
    """Decode a PNG to a flat 8-bit grayscale buffer. Returns (gray, w, h)."""
    if data[:8] != _SIG:
        raise PngError("not a PNG (bad signature)")

    pos = 8
    width = height = color_type = bit_depth = interlace = -1
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length  # length + type + data + crc
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filt, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break

    if width < 0:
        raise PngError("missing IHDR")
    if bit_depth != 8:
        raise PngError(f"unsupported bit depth {bit_depth} (only 8 supported)")
    if interlace != 0:
        raise PngError("interlaced PNG not supported")
    if color_type not in _CHANNELS:
        raise PngError(f"unsupported colour type {color_type}")

    channels = _CHANNELS[color_type]
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    expected = (stride + 1) * height
    if len(raw) < expected:
        raise PngError("truncated image data")

    gray: list[int] = []
    prev = bytearray(stride)
    for row in range(height):
        base = row * (stride + 1)
        ftype = raw[base]
        line = bytearray(raw[base + 1 : base + 1 + stride])
        _defilter(line, prev, ftype, channels)
        _row_to_gray(line, channels, width, gray)
        prev = line
    return gray, width, height


def _defilter(line: bytearray, prev: bytearray, ftype: int, bpp: int) -> None:
    """Reconstruct one scanline in place per the PNG filter algorithms."""
    if ftype == 0:
        return
    for i in range(len(line)):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        x = line[i]
        if ftype == 1:  # Sub
            line[i] = (x + a) & 0xFF
        elif ftype == 2:  # Up
            line[i] = (x + b) & 0xFF
        elif ftype == 3:  # Average
            line[i] = (x + ((a + b) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            line[i] = (x + _paeth(a, b, c)) & 0xFF
        else:
            raise PngError(f"unknown filter type {ftype}")


def _row_to_gray(line: bytearray, channels: int, width: int, out: list[int]) -> None:
    if channels == 1:  # grayscale
        out.extend(line)
    elif channels == 2:  # grayscale + alpha
        out.extend(line[i] for i in range(0, width * 2, 2))
    else:  # RGB (3) or RGBA (4)
        for x in range(width):
            p = x * channels
            out.append(_luma(line[p], line[p + 1], line[p + 2]))


def encode_png(samples: list[int], width: int, height: int, channels: int = 1) -> bytes:
    """Encode an 8-bit PNG (filter 0) from interleaved samples. For tests/tools."""
    if channels not in (1, 2, 3, 4):
        raise PngError("channels must be 1, 2, 3, or 4")
    color_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    stride = width * channels
    raw = bytearray()
    for row in range(height):
        raw.append(0)  # filter type: None
        raw.extend(samples[row * stride : (row + 1) * stride])

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return _SIG + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(
        b"IEND", b""
    )
