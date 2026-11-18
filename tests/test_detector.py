"""Pruebas del detector de colores con fotogramas sintéticos.

Las pruebas no necesitan cámara: construyen imágenes BGR con la geometría que
espera el detector, de modo que la suite sea determinista y rápida.

Ejecutar con::

    pytest tests/test_detector.py -v
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from src.cube_state import Color
from src.detector import (
    DEFAULT_COLOR_RANGES,
    ColorDetector,
    DetectorError,
    HSVRange,
    Rect,
)

#: Colores BGR sintéticos que representan cada pegatina en condiciones ideales.
STICKER_BGR = {
    Color.WHITE: (255, 255, 255),
    Color.YELLOW: (0, 255, 255),
    Color.RED: (0, 0, 255),
    Color.ORANGE: (0, 110, 255),
    Color.BLUE: (255, 0, 0),
    Color.GREEN: (0, 255, 0),
}

FRAME_SHAPE = (480, 640, 3)
BACKGROUND = (80, 80, 80)


def make_frame() -> np.ndarray:
    """Crea un fotograma de fondo neutro."""
    return np.full(FRAME_SHAPE, BACKGROUND, dtype=np.uint8)


def paint_cell(frame: np.ndarray, index: int, color: Color) -> None:
    """Rellena una celda de la cuadrícula con el color indicado."""
    detector = ColorDetector()
    rect = detector.cell_rects(frame.shape)[index]
    frame[rect.as_slice()] = STICKER_BGR[color]


def paint_face(frame: np.ndarray, colors: list[Color]) -> None:
    """Pinta las nueve celdas en orden de lectura."""
    for index, color in enumerate(colors):
        paint_cell(frame, index, color)


class TestGeometry:
    """Comprobaciones de la cuadrícula de muestreo."""

    def test_grid_is_centered_square_multiple_of_three(self) -> None:
        detector = ColorDetector()
        grid = detector.grid_rect(FRAME_SHAPE)
        assert grid.width == grid.height
        assert grid.width % 3 == 0
        assert grid.x == (FRAME_SHAPE[1] - grid.width) // 2
        assert grid.y == (FRAME_SHAPE[0] - grid.height) // 2

    def test_nine_cells_cover_the_grid_without_overlap(self) -> None:
        detector = ColorDetector()
        grid = detector.grid_rect(FRAME_SHAPE)
        cells = detector.cell_rects(FRAME_SHAPE)
        assert len(cells) == 9
        area = sum(cell.width * cell.height for cell in cells)
        assert area == grid.width * grid.height
        for cell in cells:
            assert cell.x >= grid.x and cell.y >= grid.y
            assert cell.x2 <= grid.x2 and cell.y2 <= grid.y2

    def test_sample_rects_are_inside_their_cells(self) -> None:
        detector = ColorDetector()
        cells = detector.cell_rects(FRAME_SHAPE)
        samples = detector.sample_rects(FRAME_SHAPE)
        for cell, sample in zip(cells, samples, strict=True):
            assert cell.x < sample.x and cell.y < sample.y
            assert sample.x2 < cell.x2 and sample.y2 < cell.y2

    def test_frame_too_small_is_rejected(self) -> None:
        detector = ColorDetector()
        with pytest.raises(DetectorError):
            detector.grid_rect((40, 40, 3))

    def test_inset_rejects_invalid_margin(self) -> None:
        with pytest.raises(DetectorError):
            Rect(0, 0, 30, 30).inset(0.6)


class TestClassification:
    """Clasificación de colores en condiciones controladas."""

    @pytest.mark.parametrize("color", list(Color))
    def test_each_color_is_recognized(self, color: Color) -> None:
        detector = ColorDetector()
        frame = make_frame()
        paint_face(frame, [color] * 9)
        samples = detector.sample_face(frame)
        assert all(sample.color is color for sample in samples)
        assert all(sample.confidence > 0.9 for sample in samples)

    def test_mixed_face_returns_expected_colors(self) -> None:
        expected = [
            Color.WHITE,
            Color.YELLOW,
            Color.RED,
            Color.ORANGE,
            Color.BLUE,
            Color.GREEN,
            Color.GREEN,
            Color.RED,
            Color.WHITE,
        ]
        detector = ColorDetector()
        frame = make_frame()
        paint_face(frame, expected)
        samples = detector.sample_face(frame)
        assert [sample.color for sample in samples] == expected

    def test_specular_highlight_does_not_change_the_color(self) -> None:
        detector = ColorDetector()
        frame = make_frame()
        paint_face(frame, [Color.RED] * 9)
        rect = detector.cell_rects(frame.shape)[4]
        center = rect.center
        cv2.circle(frame, center, max(2, rect.width // 8), (255, 255, 255), -1)
        samples = detector.sample_face(frame)
        assert samples[4].color is Color.RED
        assert samples[4].confidence > 0.7

    def test_salt_and_pepper_noise_keeps_the_dominant_color(self) -> None:
        detector = ColorDetector()
        frame = make_frame()
        paint_face(frame, [Color.BLUE] * 9)
        rect = detector.sample_rects(frame.shape)[0]
        region = frame[rect.as_slice()]
        generator = np.random.default_rng(2026)
        noise = generator.integers(0, 2, (rect.height, rect.width, 1)) * 255
        frame[rect.as_slice()] = np.where(noise == 255, 255 - region, region)
        samples = detector.sample_face(frame)
        assert samples[0].color is Color.BLUE
        assert samples[0].confidence > 0.4

    def test_dark_frame_produces_no_color(self) -> None:
        detector = ColorDetector()
        frame = np.full(FRAME_SHAPE, 25, dtype=np.uint8)
        samples = detector.sample_face(frame)
        assert all(sample.color is None for sample in samples)

    @pytest.mark.parametrize(
        ("hsv", "expected"),
        [
            ((0, 10, 240), Color.WHITE),
            ((30, 220, 220), Color.YELLOW),
            ((0, 220, 220), Color.RED),
            ((178, 220, 220), Color.RED),
            ((13, 220, 220), Color.ORANGE),
            ((115, 220, 200), Color.BLUE),
            ((60, 200, 160), Color.GREEN),
            ((0, 5, 60), None),
        ],
    )
    def test_classify_hsv(self, hsv: tuple[int, int, int], expected: Color | None) -> None:
        detector = ColorDetector()
        color, confidence = detector.classify_hsv(hsv)
        assert color is expected
        assert 0.0 <= confidence <= 1.0

    def test_color_outside_all_ranges_is_reported_as_unknown(self) -> None:
        detector = ColorDetector()
        frame = make_frame()
        frame[:] = (255, 0, 255)  # magenta: no está en ningún rango
        samples = detector.sample_face(frame)
        assert all(sample.color is None for sample in samples)
        assert all(sample.coverage == 0.0 for sample in samples)


class TestIllumination:
    """Diagnóstico de iluminación."""

    def test_bright_frame_is_ok(self) -> None:
        detector = ColorDetector()
        frame = np.full(FRAME_SHAPE, 220, dtype=np.uint8)
        illumination = detector.measure_illumination(frame)
        assert illumination.is_ok
        assert illumination.level == "correcta"

    def test_very_dark_frame_is_rejected(self) -> None:
        detector = ColorDetector()
        frame = np.full(FRAME_SHAPE, 20, dtype=np.uint8)
        illumination = detector.measure_illumination(frame)
        assert not illumination.is_ok
        assert "oscur" in illumination.level

    def test_advice_is_not_empty(self) -> None:
        detector = ColorDetector()
        frame = np.full(FRAME_SHAPE, 30, dtype=np.uint8)
        assert detector.measure_illumination(frame).advice


class TestValidation:
    """Validación de entradas y de la configuración."""

    def test_frame_must_be_bgr_uint8(self) -> None:
        detector = ColorDetector()
        with pytest.raises(DetectorError):
            detector.sample_face(np.zeros((480, 640), dtype=np.uint8))
        with pytest.raises(DetectorError):
            detector.sample_face(np.zeros((480, 640, 3), dtype=np.float32))
        with pytest.raises(DetectorError):
            detector.sample_face("no soy una imagen")  # type: ignore[arg-type]

    def test_missing_color_range_is_rejected(self) -> None:
        ranges = dict(DEFAULT_COLOR_RANGES)
        del ranges[Color.BLUE]
        with pytest.raises(DetectorError):
            ColorDetector(ranges)

    def test_invalid_hsv_range_is_rejected(self) -> None:
        ranges = dict(DEFAULT_COLOR_RANGES)
        ranges[Color.RED] = (HSVRange((0, 0, 0), (400, 255, 255)),)
        with pytest.raises(DetectorError):
            ColorDetector(ranges)

    def test_even_denoise_kernel_is_rejected(self) -> None:
        with pytest.raises(DetectorError):
            ColorDetector(denoise_kernel=4)

    def test_color_mask_highlights_known_colors(self) -> None:
        detector = ColorDetector()
        frame = make_frame()
        paint_cell(frame, 0, Color.RED)
        mask = detector.build_color_mask(frame)
        assert mask.shape == frame.shape
        rect = detector.cell_rects(frame.shape)[0]
        center_y, center_x = rect.center[1], rect.center[0]
        assert tuple(mask[center_y, center_x]) != (0, 0, 0)
