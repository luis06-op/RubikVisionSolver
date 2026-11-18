"""Abstracción de la captura de vídeo con OpenCV.

El módulo encapsula ``cv2.VideoCapture`` para que el resto de la aplicación no
dependa de detalles del *backend* de vídeo. Se ocupa de:

* abrir el dispositivo con la resolución y los FPS solicitados;
* reducir el búfer del controlador para evitar fotogramas obsoletos;
* reintentar la lectura cuando el controlador devuelve un fotograma vacío;
* recortar una región de interés (ROI) opcional;
* liberar el dispositivo de forma idempotente, incluso ante excepciones.

Examples:
    >>> from src.camera import CameraConfig, CameraHandler
    >>> handler = CameraHandler(CameraConfig(index=0))
    >>> handler.is_open
    False
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np

__all__ = ["CameraConfig", "CameraError", "CameraHandler", "ROIConfig"]


class CameraError(RuntimeError):
    """No se pudo abrir o leer de la cámara."""


@dataclass(frozen=True)
class ROIConfig:
    """Región de interés expresada en fracciones del fotograma.

    Trabajar con fracciones permite que la ROI se adapte a cualquier resolución
    sin recalcular constantes. El sistema de referencia tiene el origen en la
    esquina superior izquierda.

    Attributes:
        x: Fracción horizontal del borde izquierdo (0-1).
        y: Fracción vertical del borde superior (0-1).
        width: Fracción de ancho (0-1].
        height: Fracción de alto (0-1].
    """

    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0

    def __post_init__(self) -> None:
        """Valida que la región quede dentro del fotograma.

        Raises:
            CameraError: Si las fracciones están fuera de rango.
        """
        if not (0.0 <= self.x < 1.0 and 0.0 <= self.y < 1.0):
            raise CameraError("El origen de la ROI debe estar entre 0 y 1")
        if not (0.0 < self.width <= 1.0 and 0.0 < self.height <= 1.0):
            raise CameraError("El tamano de la ROI debe estar en (0, 1]")
        if self.x + self.width > 1.0 + 1e-9 or self.y + self.height > 1.0 + 1e-9:
            raise CameraError("La ROI se sale del fotograma")

    @property
    def is_full_frame(self) -> bool:
        """Indica si la región cubre todo el fotograma."""
        return (
            self.x == 0.0
            and self.y == 0.0
            and self.width == 1.0
            and self.height == 1.0
        )

    def pixel_bounds(self, frame_shape: Sequence[int]) -> tuple[int, int, int, int]:
        """Convierte la ROI a píxeles.

        Args:
            frame_shape: Forma del fotograma ``(alto, ancho, ...)``.

        Returns:
            Tupla ``(x, y, ancho, alto)`` en píxeles, con al menos un píxel.
        """
        height, width = int(frame_shape[0]), int(frame_shape[1])
        x = round(self.x * width)
        y = round(self.y * height)
        w = max(1, round(self.width * width))
        h = max(1, round(self.height * height))
        return x, y, min(w, width - x), min(h, height - y)

    def crop(self, frame: np.ndarray) -> np.ndarray:
        """Recorta la región de interés de un fotograma.

        Args:
            frame: Imagen BGR.

        Returns:
            Vista recortada; si la ROI es completa se devuelve el original.
        """
        if self.is_full_frame:
            return frame
        x, y, width, height = self.pixel_bounds(frame.shape)
        return frame[y : y + height, x : x + width]


@dataclass(frozen=True)
class CameraConfig:
    """Parámetros de apertura de la cámara.

    Attributes:
        index: Índice del dispositivo (0 suele ser la cámara integrada).
        width: Ancho solicitado en píxeles.
        height: Alto solicitado en píxeles.
        fps: Fotogramas por segundo solicitados.
        buffer_size: Tamaño del búfer del controlador; 1 reduce la latencia.
        roi: Región de interés aplicada a cada fotograma.
        read_attempts: Reintentos antes de considerar fallo de lectura.
        read_backoff: Espera en segundos entre reintentos.
        warmup_frames: Fotogramas descartados al abrir (suelen estar negros).
    """

    index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    buffer_size: int = 1
    roi: ROIConfig = ROIConfig()
    read_attempts: int = 5
    read_backoff: float = 0.02
    warmup_frames: int = 3

    def __post_init__(self) -> None:
        """Valida los parámetros de captura.

        Raises:
            CameraError: Si algún valor carece de sentido físico.
        """
        if self.index < 0:
            raise CameraError("El indice de camara no puede ser negativo")
        if self.width <= 0 or self.height <= 0:
            raise CameraError("La resolucion debe ser positiva")
        if self.fps <= 0:
            raise CameraError("Los FPS deben ser positivos")
        if self.read_attempts < 1:
            raise CameraError("read_attempts debe ser al menos 1")
        if self.warmup_frames < 0:
            raise CameraError("warmup_frames no puede ser negativo")

    @property
    def frame_interval_ms(self) -> int:
        """Intervalo entre fotogramas en milisegundos (mínimo 1)."""
        return max(1, round(1000.0 / self.fps))


#: Fábrica de capturas inyectable para poder probar sin hardware.
CaptureFactory = Callable[[int], cv2.VideoCapture]


class CameraHandler:
    """Gestiona el ciclo de vida de una cámara de vídeo.

    Attributes:
        config: Configuración usada al abrir el dispositivo.
    """

    def __init__(
        self,
        config: CameraConfig | None = None,
        capture_factory: CaptureFactory | None = None,
    ) -> None:
        """Inicializa el manejador sin abrir todavía el dispositivo.

        Args:
            config: Configuración de captura; se usa la predeterminada si es
                ``None``.
            capture_factory: Función que crea el objeto de captura. Permite
                inyectar un doble en las pruebas; por defecto usa
                ``cv2.VideoCapture``.
        """
        self.config = config or CameraConfig()
        self._capture_factory: CaptureFactory = capture_factory or cv2.VideoCapture
        self._capture: cv2.VideoCapture | None = None

    # -- Ciclo de vida -----------------------------------------------------

    def open(self) -> None:
        """Abre el dispositivo y descarta los primeros fotogramas.

        Raises:
            CameraError: Si no se encuentra la cámara o no se puede leer.
        """
        if self.is_open:
            return

        capture = self._capture_factory(self.config.index)
        if not capture.isOpened():
            capture.release()
            raise CameraError(
                f"No se encontro ninguna camara en el indice {self.config.index}. "
                "Comprueba que esta conectada y que otra aplicacion no la esta usando"
            )

        try:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            capture.set(cv2.CAP_PROP_FPS, self.config.fps)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)
        except cv2.error:  # pragma: no cover - depende del backend de vídeo
            # Algunos controladores rechazan propiedades opcionales; no impiden
            # capturar y por eso no se considera un error fatal.
            pass

        self._capture = capture
        for _ in range(self.config.warmup_frames):
            capture.read()

    def read(self) -> np.ndarray:
        """Captura un fotograma recortado según la ROI.

        Returns:
            Imagen BGR de tipo ``uint8``.

        Raises:
            CameraError: Si el dispositivo no está abierto o no entrega imagen
                tras agotar los reintentos.
        """
        if self._capture is None:
            raise CameraError("La camara no esta abierta: llama a open() antes de read()")

        last_error: str = "sin detalle"
        for attempt in range(self.config.read_attempts):
            ok, frame = self._capture.read()
            if ok and frame is not None and frame.size > 0:
                return self.config.roi.crop(frame)
            last_error = f"intento {attempt + 1}/{self.config.read_attempts}"
            if attempt + 1 < self.config.read_attempts:
                time.sleep(self.config.read_backoff * (attempt + 1))
        raise CameraError(f"La camara no entrego ningun fotograma ({last_error})")

    def release(self) -> None:
        """Libera el dispositivo. Es seguro llamarlo varias veces."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def is_open(self) -> bool:
        """Indica si el dispositivo está abierto y operativo."""
        return self._capture is not None and bool(self._capture.isOpened())

    def __enter__(self) -> CameraHandler:
        """Abre la cámara al entrar en un bloque ``with``."""
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Libera la cámara al salir de un bloque ``with``."""
        self.release()

    def __del__(self) -> None:  # pragma: no cover - limpieza defensiva
        """Libera el dispositivo si el objeto se recolecta sin cerrarlo."""
        # Durante el apagado del intérprete OpenCV puede estar descargado y
        # cualquier excepción aquí solo generaría ruido en la salida de error.
        with contextlib.suppress(Exception):
            self.release()


#: Nombre de la ventana usado por la aplicación.
WINDOW_NAME: Final[str] = "RubikVisionSolver"
