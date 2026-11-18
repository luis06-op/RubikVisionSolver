"""Pruebas de la captura de vídeo con un dispositivo simulado.

``CameraHandler`` acepta una fábrica de capturas, de modo que se puede probar
el ciclo de vida completo —apertura, reintentos, ROI y liberación— sin cámara
física ni dependencia del *backend* de vídeo.

Ejecutar con::

    pytest tests/test_camera.py -v
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from src import camera as camera_module
from src.camera import CameraConfig, CameraError, CameraHandler, ROIConfig

FRAME_SHAPE = (120, 160, 3)


def make_frame(value: int = 128) -> np.ndarray:
    """Crea un fotograma BGR uniforme."""
    return np.full(FRAME_SHAPE, value, dtype=np.uint8)


class FakeCapture:
    """Doble de ``cv2.VideoCapture`` con guion de fotogramas."""

    def __init__(self, frames: list[np.ndarray | None] | None = None) -> None:
        self.frames = list(frames or [])
        self.opened = True
        self.released = False
        self.reads = 0
        self.properties: dict[int, float] = {}

    def isOpened(self) -> bool:
        return self.opened and not self.released

    def set(self, prop: int, value: float) -> bool:
        self.properties[prop] = value
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        self.reads += 1
        if not self.frames:
            return False, None
        frame = self.frames.pop(0)
        if frame is None:
            return False, None
        return True, frame

    def release(self) -> None:
        self.released = True


def build_handler(
    capture: FakeCapture,
    *,
    warmup_frames: int = 3,
    read_attempts: int = 5,
    read_backoff: float = 0.02,
    roi: ROIConfig | None = None,
) -> CameraHandler:
    """Construye un manejador con el dispositivo simulado."""
    config = CameraConfig(
        width=FRAME_SHAPE[1],
        height=FRAME_SHAPE[0],
        warmup_frames=warmup_frames,
        read_attempts=read_attempts,
        read_backoff=read_backoff,
        roi=roi or ROIConfig(),
    )
    return CameraHandler(config, capture_factory=lambda _index: capture)


class TestROIConfig:
    """Región de interés expresada en fracciones."""

    def test_full_frame_is_the_default(self) -> None:
        roi = ROIConfig()
        assert roi.is_full_frame
        assert roi.pixel_bounds(FRAME_SHAPE) == (0, 0, 160, 120)
        frame = make_frame()
        assert roi.crop(frame) is frame

    def test_fractional_region_is_converted_to_pixels(self) -> None:
        roi = ROIConfig(0.25, 0.25, 0.5, 0.5)
        assert roi.pixel_bounds(FRAME_SHAPE) == (40, 30, 80, 60)
        cropped = roi.crop(make_frame())
        assert cropped.shape == (60, 80, 3)

    @pytest.mark.parametrize(
        "values",
        [
            (-0.1, 0.0, 0.5, 0.5),
            (0.0, -0.1, 0.5, 0.5),
            (1.0, 0.0, 0.5, 0.5),
            (0.0, 0.0, 0.0, 0.5),
            (0.0, 0.0, 0.5, 0.0),
            (0.5, 0.0, 0.6, 0.5),
            (0.0, 0.5, 0.5, 0.6),
        ],
    )
    def test_invalid_regions_are_rejected(self, values: tuple[float, ...]) -> None:
        with pytest.raises(CameraError):
            ROIConfig(*values)

    def test_region_is_clamped_to_the_frame(self) -> None:
        roi = ROIConfig(0.9, 0.9, 0.1, 0.1)
        x, y, width, height = roi.pixel_bounds(FRAME_SHAPE)
        assert x + width <= FRAME_SHAPE[1]
        assert y + height <= FRAME_SHAPE[0]


class TestCameraConfig:
    """Validación de los parámetros de apertura."""

    def test_defaults(self) -> None:
        config = CameraConfig()
        assert config.index == 0
        assert config.width == 1280
        assert config.height == 720
        assert config.fps == 30
        assert config.frame_interval_ms == 33

    def test_frame_interval_never_reaches_zero(self) -> None:
        assert CameraConfig(fps=1000).frame_interval_ms >= 1

    @pytest.mark.parametrize(
        "values",
        [
            {"index": -1},
            {"width": 0},
            {"height": 0},
            {"fps": 0},
            {"read_attempts": 0},
            {"warmup_frames": -1},
        ],
    )
    def test_invalid_values_are_rejected(self, values: dict[str, int]) -> None:
        with pytest.raises(CameraError):
            CameraConfig(**values)


class TestLifecycle:
    """Apertura, lectura y liberación del dispositivo."""

    def test_open_configures_the_capture(self) -> None:
        capture = FakeCapture([make_frame()])
        handler = build_handler(capture, warmup_frames=0)
        handler.open()
        assert handler.is_open
        assert capture.properties
        handler.release()

    def test_unavailable_device_raises(self) -> None:
        capture = FakeCapture()
        capture.opened = False
        handler = build_handler(capture)
        with pytest.raises(CameraError):
            handler.open()
        assert capture.released

    def test_warmup_frames_are_discarded(self) -> None:
        capture = FakeCapture([make_frame(1), make_frame(2), make_frame(3)])
        handler = build_handler(capture, warmup_frames=2)
        handler.open()
        assert handler.read().mean() == pytest.approx(3)
        handler.release()

    def test_read_returns_the_frame(self) -> None:
        capture = FakeCapture([make_frame(7)])
        handler = build_handler(capture, warmup_frames=0)
        handler.open()
        frame = handler.read()
        assert frame.shape == FRAME_SHAPE
        assert frame.dtype == np.uint8
        assert frame.mean() == pytest.approx(7)
        handler.release()

    def test_read_before_open_raises(self) -> None:
        handler = build_handler(FakeCapture())
        with pytest.raises(CameraError):
            handler.read()

    def test_read_retries_before_failing(self) -> None:
        capture = FakeCapture([None, None])
        handler = build_handler(capture, read_attempts=3, read_backoff=0.0)
        handler.open()
        with pytest.raises(CameraError):
            handler.read()
        assert capture.reads >= 3
        handler.release()

    def test_read_recovers_from_a_transient_failure(self) -> None:
        capture = FakeCapture([None, make_frame(9)])
        handler = build_handler(
            capture, warmup_frames=0, read_attempts=3, read_backoff=0.0
        )
        handler.open()
        assert handler.read().mean() == pytest.approx(9)
        handler.release()

    def test_read_applies_the_roi(self) -> None:
        capture = FakeCapture([make_frame()])
        handler = build_handler(
            capture, warmup_frames=0, roi=ROIConfig(0.25, 0.25, 0.5, 0.5)
        )
        handler.open()
        assert handler.read().shape == (60, 80, 3)
        handler.release()

    def test_release_is_idempotent(self) -> None:
        capture = FakeCapture()
        handler = build_handler(capture)
        handler.open()
        handler.release()
        handler.release()
        assert not handler.is_open
        assert capture.released

    def test_open_is_idempotent(self) -> None:
        capture = FakeCapture([make_frame()])
        handler = build_handler(capture, warmup_frames=0)
        handler.open()
        handler.open()
        assert capture.reads == 0
        handler.release()

    def test_context_manager_releases_the_device(self) -> None:
        capture = FakeCapture([make_frame()])
        with build_handler(capture, warmup_frames=0) as handler:
            assert handler.is_open
        assert capture.released
        assert not handler.is_open

    def test_context_manager_releases_on_error(self) -> None:
        capture = FakeCapture([make_frame()])
        with pytest.raises(RuntimeError), build_handler(capture):
            raise RuntimeError("fallo simulado")
        assert capture.released


class TestBackendSelection:
    """Controladores nativos y alternativas automáticas por sistema operativo."""

    @pytest.mark.parametrize("backend", ["dshow", "msmf", "v4l2"])
    def test_explicit_backend_is_used(self, monkeypatch: pytest.MonkeyPatch, backend: str) -> None:
        seen: list[int] = []

        def factory(index: int, api: int) -> FakeCapture:
            seen.append(api)
            return FakeCapture([make_frame()])

        monkeypatch.setattr(camera_module.cv2, "VideoCapture", factory)
        config = CameraConfig(backend=backend, warmup_frames=0)
        handler = CameraHandler(config)
        handler.open()
        expected = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "v4l2": cv2.CAP_V4L2}
        assert seen == [expected[backend]]
        handler.release()

    def test_auto_falls_back_when_preferred_backend_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts: list[int] = []

        def factory(index: int, api: int) -> FakeCapture:
            attempts.append(api)
            capture = FakeCapture([make_frame()])
            if api == cv2.CAP_V4L2:
                capture.opened = False
            return capture

        monkeypatch.setattr(camera_module.cv2, "VideoCapture", factory)
        monkeypatch.setattr(camera_module.sys, "platform", "linux")
        handler = CameraHandler(CameraConfig(warmup_frames=0))
        handler.open()
        assert handler.is_open
        assert attempts == [cv2.CAP_V4L2, cv2.CAP_ANY]
        handler.release()

    def test_unknown_backend_is_rejected(self) -> None:
        with pytest.raises(CameraError):
            CameraConfig(backend="directshow")
