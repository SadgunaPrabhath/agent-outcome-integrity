"""Pure-Python PNG codec — round-trips and filter reconstruction, no image lib."""

from __future__ import annotations

import struct
import zlib

import pytest

from engine.verification.png import PngError, decode_png_gray, encode_png


def test_grayscale_round_trip():
    gray = [0, 64, 128, 192, 255, 32]  # 3x2
    data = encode_png(gray, 3, 2, channels=1)
    out, w, h = decode_png_gray(data)
    assert (w, h) == (3, 2)
    assert out == gray


def test_rgb_luma_conversion():
    # One red, one green, one blue pixel (1x3 image).
    rgb = [255, 0, 0, 0, 255, 0, 0, 0, 255]
    data = encode_png(rgb, 3, 1, channels=3)
    out, w, h = decode_png_gray(data)
    assert (w, h) == (3, 1)
    # Rec.601 luma weights.
    assert out == [round(0.299 * 255), round(0.587 * 255), round(0.114 * 255)]


def test_rgba_ignores_alpha():
    rgba = [255, 255, 255, 0, 0, 0, 0, 255]  # opaque white, transparent black (1x2)
    data = encode_png(rgba, 2, 1, channels=4)
    out, _, _ = decode_png_gray(data)
    assert out == [255, 0]


def test_grayscale_alpha_takes_gray_channel():
    ga = [100, 255, 200, 0]  # (gray, alpha) x2
    data = encode_png(ga, 2, 1, channels=2)
    out, _, _ = decode_png_gray(data)
    assert out == [100, 200]


def _assemble(ihdr: bytes, raw: bytes) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_up_filter_is_reconstructed():
    # 2x2 grayscale, row0 filter None, row1 filter Up (=2): decoded must recover pixels.
    row0, row1 = [10, 20], [40, 60]
    filtered_row1 = bytes([(row1[i] - row0[i]) & 0xFF for i in range(2)])
    raw = b"\x00" + bytes(row0) + b"\x02" + filtered_row1
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 0, 0, 0, 0)  # w,h,depth,colourtype=gray
    out, w, h = decode_png_gray(_assemble(ihdr, raw))
    assert (w, h) == (2, 2)
    assert out == [10, 20, 40, 60]


def test_rejects_non_png():
    with pytest.raises(PngError):
        decode_png_gray(b"not a png at all")


def test_rejects_16bit():
    ihdr = struct.pack(">IIBBBBB", 1, 1, 16, 0, 0, 0, 0)
    with pytest.raises(PngError):
        decode_png_gray(_assemble(ihdr, b"\x00\x00\x00"))


def test_rejects_interlaced():
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 1)  # interlace=1
    with pytest.raises(PngError):
        decode_png_gray(_assemble(ihdr, b"\x00\x00"))
