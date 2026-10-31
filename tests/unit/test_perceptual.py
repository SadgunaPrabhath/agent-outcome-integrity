"""Perceptual hashing primitives — deterministic, dependency-free."""

from __future__ import annotations

import pytest

from engine.verification.perceptual import average_hash, dhash, hamming, similarity


def _uniform(value: int, w: int = 16, h: int = 16) -> list[int]:
    return [value] * (w * h)


def _checkerboard(w: int = 16, h: int = 16) -> list[int]:
    return [255 if (x + y) % 2 == 0 else 0 for y in range(h) for x in range(w)]


def test_hash_is_stable_and_hex():
    img = _checkerboard()
    h1 = average_hash(img, 16, 16)
    h2 = average_hash(img, 16, 16)
    assert h1 == h2
    assert len(h1) == 16  # 64 bits -> 16 hex chars
    int(h1, 16)  # parses as hex


def test_uniform_image_hashes_all_ones():
    # Every downsampled cell equals the mean, so every bit is set.
    assert average_hash(_uniform(0), 16, 16) == "f" * 16
    assert average_hash(_uniform(255), 16, 16) == "f" * 16


def test_identical_images_have_zero_distance():
    img = _checkerboard()
    a = average_hash(img, 16, 16)
    assert hamming(a, a) == 0
    assert similarity(a, a) == 1.0


def _vertical_split(w: int = 16, h: int = 16) -> list[int]:
    # Left half dark, right half light — structure that survives downsampling.
    return [0 if x < w // 2 else 255 for _y in range(h) for x in range(w)]


def test_opposite_structure_is_far_apart():
    left_dark = _vertical_split()
    right_dark = [255 - p for p in left_dark]  # mirror image
    a = average_hash(left_dark, 16, 16)
    b = average_hash(right_dark, 16, 16)
    # Opposite layouts differ in every bit; similarity is minimal.
    assert hamming(a, b) == 64
    assert similarity(a, b) == 0.0


def test_fine_checkerboard_averages_out():
    # A known aHash property: sub-cell detail below the downsample grid is lost,
    # so a fine checkerboard and its inverse both flatten to a uniform hash.
    board = _checkerboard()
    inverse = [255 - p for p in board]
    assert average_hash(board, 16, 16) == average_hash(inverse, 16, 16)


def test_dhash_detects_horizontal_gradient():
    # Brightness strictly increases left-to-right: every dHash bit is 0
    # (each pixel is darker than its right neighbour).
    gradient = [int(255 * x / 15) for _y in range(16) for x in range(16)]
    assert dhash(gradient, 16, 16) == "0" * 16


def test_hamming_rejects_length_mismatch():
    with pytest.raises(ValueError):
        hamming("ff", "ffff")


def test_downsample_handles_tiny_images():
    # 2x2 source, 8x8 hash: nearest-pixel fallback, still total and deterministic.
    h = average_hash([0, 255, 255, 0], 2, 2)
    assert len(h) == 16
    assert h == average_hash([0, 255, 255, 0], 2, 2)


def test_bad_dimensions_raise():
    with pytest.raises(ValueError):
        average_hash([1, 2, 3], 4, 4)  # buffer too small
