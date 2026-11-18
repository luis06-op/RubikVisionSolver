"""Regresiones del recorte HSV y del ciclo de vida de la interfaz."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from src.cube_state import Color
from src.detector import ColorDetector, FaceletSample
from src.main import AppState

from tests.test_application import build_application, paint_frame


@pytest.mark.parametrize("kernel", [1, 3, 5])
@pytest.mark.parametrize("margin", [0.0, 0.22])
def test_roi_matches_full_image_filter(kernel: int, margin: float) -> None:
    """El halo debe conservar exactamente clasificación, mediana y confianza."""
    detector = ColorDetector(denoise_kernel=kernel, cell_margin=margin)
    frame = np.random.default_rng(21).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    full = cv2.medianBlur(frame, kernel) if kernel > 1 else frame
    hsv = cv2.cvtColor(full, cv2.COLOR_BGR2HSV)
    expected = []
    for index, rect in enumerate(detector.sample_rects(frame.shape)):
        color, confidence, coverage, median = detector._classify_patch(hsv[rect.as_slice()])
        expected.append(FaceletSample(index, color, confidence, coverage, median))
    assert detector.sample_face(frame) == tuple(expected)


def test_repeated_processing_preserves_capture() -> None:
    """La UI no debe contaminar el siguiente análisis ni el último fotograma."""
    frame = paint_frame([Color.WHITE] * 9)
    original = frame.copy()
    app, _ = build_application(frame)
    first = app.process(frame)
    second = app.process(frame)
    np.testing.assert_array_equal(frame, original)
    np.testing.assert_array_equal(first, second)
    assert not np.shares_memory(first, frame)


def test_window_creation_failure_releases_camera(monkeypatch: pytest.MonkeyPatch) -> None:
    """La cámara también se libera si la GUI falla antes del primer fotograma."""
    app, capture = build_application()

    def unavailable(*args: object) -> None:
        raise cv2.error("Sin entorno grafico")

    monkeypatch.setattr(cv2, "namedWindow", unavailable)
    monkeypatch.setattr(cv2, "destroyAllWindows", unavailable)
    with pytest.raises(cv2.error, match="Sin entorno grafico"):
        app.run()
    assert capture.released


def test_window_close_exits_and_releases_camera(monkeypatch: pytest.MonkeyPatch) -> None:
    app, capture = build_application()
    monkeypatch.setattr(cv2, "namedWindow", lambda *args: None)
    monkeypatch.setattr(cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(cv2, "waitKeyEx", lambda delay: -1)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 0.0)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda: None)
    app.run()
    assert app.state is AppState.QUIT
    assert capture.released


def test_slow_frame_does_not_add_another_frame_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tras gastar el presupuesto temporal solo queda el mínimo de eventos GUI."""
    app, _ = build_application()
    ticks = iter((0.0, 0.1))
    delays: list[int] = []

    def wait(delay: int) -> int:
        delays.append(delay)
        return -1

    monkeypatch.setattr("src.main.time.perf_counter", lambda: next(ticks))
    monkeypatch.setattr(cv2, "namedWindow", lambda *args: None)
    monkeypatch.setattr(cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(cv2, "waitKeyEx", wait)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 0.0)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda: None)
    app.run()
    assert delays == [1]
