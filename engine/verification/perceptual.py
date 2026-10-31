"""Perceptual hashing — dependency-free image fingerprints for visual checks.

The visual verifier is the second-lowest tier of the hierarchy (confidence 0.5):
it can only tell you that *what was rendered looks like* a reference, never that
persistent state changed. To keep the engine importable without Pillow/OpenCV,
hashing works on a flat grayscale pixel buffer (row-major, one int in 0..255 per
pixel). A real capture backend (Playwright + Pillow, Phase 9) decodes a PNG to
grayscale and calls :func:`average_hash`; tests pass pixels directly.

Two standard fingerprints are provided:
  * ``average_hash`` (aHash) — bit set where a downsampled pixel is >= the mean.
  * ``dhash`` — bit set where a pixel is brighter than its right neighbour;
    more robust to uniform brightness shifts.

Similarity is Hamming distance between two equal-length hex digests: 0 = identical,
higher = more different. Nothing here judges PASS/FAIL — that is the verifier's job.
"""

from __future__ import annotations

from collections.abc import Sequence

_BITS_PER_HEX = 4


def _downsample(gray: Sequence[int], width: int, height: int, size: int) -> list[float]:
    """Box-average an arbitrary ``width``x``height`` buffer down to ``size``x``size``.

    Deterministic and total: each target cell is the mean of the source pixels
    whose centres fall in its block. Empty blocks (when the source is smaller
    than ``size`` in a dimension) fall back to nearest-pixel sampling.
    """
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    if len(gray) < width * height:
        raise ValueError("pixel buffer smaller than width*height")

    out: list[float] = []
    for ty in range(size):
        y0 = (ty * height) // size
        y1 = max(y0 + 1, ((ty + 1) * height) // size)
        for tx in range(size):
            x0 = (tx * width) // size
            x1 = max(x0 + 1, ((tx + 1) * width) // size)
            total = 0
            count = 0
            for y in range(y0, min(y1, height)):
                row = y * width
                for x in range(x0, min(x1, width)):
                    total += gray[row + x]
                    count += 1
            out.append(total / count if count else 0.0)
    return out


def _bits_to_hex(bits: list[bool]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | (1 if bit else 0)
    width = (len(bits) + _BITS_PER_HEX - 1) // _BITS_PER_HEX
    return format(value, f"0{width}x")


def average_hash(
    gray: Sequence[int], width: int, height: int, hash_size: int = 8
) -> str:
    """aHash: ``hash_size**2``-bit fingerprint as a hex string."""
    if hash_size < 1:
        raise ValueError("hash_size must be >= 1")
    cells = _downsample(gray, width, height, hash_size)
    mean = sum(cells) / len(cells)
    return _bits_to_hex([c >= mean for c in cells])


def dhash(gray: Sequence[int], width: int, height: int, hash_size: int = 8) -> str:
    """dHash: bit set where each cell is brighter than its right neighbour."""
    if hash_size < 1:
        raise ValueError("hash_size must be >= 1")
    cells = _downsample(gray, width, height, hash_size + 1)  # need one extra column
    bits: list[bool] = []
    for r in range(hash_size):
        base = r * (hash_size + 1)
        for c in range(hash_size):
            bits.append(cells[base + c] > cells[base + c + 1])
    return _bits_to_hex(bits)


def hamming(hex_a: str, hex_b: str) -> int:
    """Number of differing bits between two equal-length hex digests."""
    if len(hex_a) != len(hex_b):
        raise ValueError(
            f"hash length mismatch: {len(hex_a)} vs {len(hex_b)} hex chars"
        )
    return (int(hex_a, 16) ^ int(hex_b, 16)).bit_count()


def similarity(hex_a: str, hex_b: str) -> float:
    """Fraction of matching bits in [0.0, 1.0] (1.0 = identical)."""
    total_bits = len(hex_a) * _BITS_PER_HEX
    if total_bits == 0:
        return 1.0
    return 1.0 - hamming(hex_a, hex_b) / total_bits
