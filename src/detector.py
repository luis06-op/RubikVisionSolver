"""Detección de las nueve pegatinas de una cara mediante análisis HSV.

El detector recibe un fotograma BGR, localiza una cuadrícula de 3x3 en el
centro de la imagen y clasifica el color dominante de cada celda. Para ser
tolerante a brillos, sombras y ruido de la cámara:

* se trabaja en el espacio HSV, separando el tono de la iluminación;
* se aplica un filtro de mediana para eliminar píxeles aislados;
* se clasifica cada celda por votación de píxeles dentro de los rangos de
  color, no por un único píxel;
* se calcula la mediana de la celda como valor representativo y se usa para
  desempatar colores próximos (rojo/naranja, naranja/amarillo);
* se descartan las celdas con poca confianza, de modo que la interfaz pueda
  pedir al usuario que vuelva a colocar la cara.

Examples:
    >>> import numpy as np
    >>> from src.detector import ColorDetector
    >>> detector = ColorDetector()
    >>> frame = np.zeros((480, 640, 3), dtype=np.uint8)
    >>> len(detector.cell_rects(frame.shape))
    9
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np

from .cube_state import Color

__all__ = [
    "DEFAULT_COLOR_RANGES",
    "GRID_SIZE",
    "ColorDetector",
    "DetectorError",
    "FaceletSample",
    "HSVRange",
    "Illumination",
    "Rect",
]

#: Lado de la cuadrícula de muestreo.
GRID_SIZE: Final[int] = 3


class DetectorError(RuntimeError):
    """Error de configuración o de entrada del detector."""


@dataclass(frozen=True)
class HSVRange:
    """Rango inclusivo de color en el espacio HSV de OpenCV.

    Los canales se expresan en el rango de OpenCV para imágenes de 8 bits:
    ``H`` en ``0-179``, ``S`` en ``0-255`` y ``V`` en ``0-255``.

    Attributes:
        lower: Valor mínimo ``(H, S, V)``.
        upper: Valor máximo ``(H, S, V)``.
    """

    lower: tuple[int, int, int]
    upper: tuple[int, int, int]

    def mask(self, hsv_image: np.ndarray) -> np.ndarray:
        """Genera la máscara binaria de los píxeles dentro del rango.

        Args:
            hsv_image: Imagen HSV de tipo ``uint8``.

        Returns:
            Máscara ``uint8`` con 255 en los píxeles incluidos.
        """
        return cv2.inRange(hsv_image, self.lower, self.upper)


#: Rangos HSV por defecto, pensados para luz blanca difusa y una cámara con
#: balance de blancos automático. El rojo necesita dos rangos porque el tono es
#: circular y cruza el 0.
DEFAULT_COLOR_RANGES: Final[dict[Color, tuple[HSVRange, ...]]] = {
    Color.WHITE: (HSVRange((0, 0, 140), (179, 70, 255)),),
    Color.YELLOW: (HSVRange((19, 90, 120), (35, 255, 255)),),
    Color.RED: (
        HSVRange((0, 110, 80), (6, 255, 255)),
        HSVRange((173, 110, 80), (179, 255, 255)),
    ),
    Color.ORANGE: (HSVRange((7, 110, 100), (18, 255, 255)),),
    Color.BLUE: (HSVRange((95, 100, 70), (130, 255, 255)),),
    Color.GREEN: (HSVRange((40, 70, 60), (88, 255, 255)),),
}


@dataclass(frozen=True)
class Rect:
    """Rectángulo en coordenadas de píxel con origen en la esquina superior.

    Attributes:
        x: Coordenada horizontal de la esquina superior izquierda.
        y: Coordenada vertical de la esquina superior izquierda.
        width: Ancho en píxeles.
        height: Alto en píxeles.
    """

    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        """Coordenada horizontal del borde derecho (exclusiva)."""
        return self.x + self.width

    @property
    def y2(self) -> int:
        """Coordenada vertical del borde inferior (exclusiva)."""
        return self.y + self.height

    @property
    def center(self) -> tuple[int, int]:
        """Centro del rectángulo redondeado a píxeles."""
        return self.x + self.width // 2, self.y + self.height // 2

    def as_slice(self) -> tuple[slice, slice]:
        """Devuelve el rectángulo como índices de ``numpy``."""
        return slice(self.y, self.y2), slice(self.x, self.x2)

    def inset(self, ratio: float) -> Rect:
        """Reduce el rectángulo manteniendo su centro.

        Args:
            ratio: Fracción del tamaño que se recorta por cada lado (0-0.45).

        Returns:
            Nuevo rectángulo más pequeño.

        Raises:
            DetectorError: Si el margen deja el rectángulo sin área.
        """
        if not 0.0 <= ratio < 0.5:
            raise DetectorError("El margen de muestreo debe estar entre 0 y 0.5")
        dx = round(self.width * ratio)
        dy = round(self.height * ratio)
        width = self.width - 2 * dx
        height = self.height - 2 * dy
        if width < 1 or height < 1:
            raise DetectorError("La celda es demasiado pequena para muestrear")
        return Rect(self.x + dx, self.y + dy, width, height)


@dataclass(frozen=True)
class FaceletSample:
    """Resultado del análisis de una celda de la cuadrícula.

    Attributes:
        index: Índice de la celda en orden de lectura (0-8).
        color: Color detectado, o ``None`` si la confianza es insuficiente.
        confidence: Fracción de píxeles dentro del rango del color ganador.
        coverage: Fracción de píxeles que caen en algún rango de color.
        median_hsv: Mediana HSV de la celda, útil para calibrar.
    """

    index: int
    color: Color | None
    confidence: float
    coverage: float
    median_hsv: tuple[int, int, int]

    @property
    def row(self) -> int:
        """Fila de la celda (0-2)."""
        return self.index // GRID_SIZE

    @property
    def col(self) -> int:
        """Columna de la celda (0-2)."""
        return self.index % GRID_SIZE

    @property
    def is_confident(self) -> bool:
        """Indica si la celda tiene un color fiable."""
        return self.color is not None

    @property
    def label(self) -> str:
        """Etiqueta corta para la interfaz."""
        return self.color.name_es if self.color else "?"


@dataclass(frozen=True)
class Illumination:
    """Diagnóstico de iluminación de la zona de muestreo.

    Attributes:
        mean_value: Brillo medio (canal ``V``) en ``0-255``.
        mean_saturation: Saturación media (canal ``S``) en ``0-255``.
        level: Categoría cualitativa de la iluminación.
        advice: Recomendación para el usuario.
        is_ok: Indica si la iluminación es adecuada para detectar colores.
    """

    mean_value: float
    mean_saturation: float
    level: str
    advice: str
    is_ok: bool


class ColorDetector:
    """Clasifica las pegatinas de la cara enfocada por la cámara.

    Attributes:
        ranges: Rangos HSV usados para cada color.
        grid_ratio: Lado de la cuadrícula como fracción del menor lado del
            fotograma.
        cell_margin: Margen recortado en cada celda antes de promediar.
        min_confidence: Confianza mínima para aceptar un color.
        denoise_kernel: Tamaño del filtro de mediana (impar; 1 lo desactiva).
    """

    def __init__(
        self,
        ranges: Mapping[Color, Sequence[HSVRange]] | None = None,
        *,
        grid_ratio: float = 0.46,
        cell_margin: float = 0.22,
        min_confidence: float = 0.35,
        denoise_kernel: int = 3,
    ) -> None:
        """Configura el detector.

        Args:
            ranges: Rangos HSV por color. Si es ``None`` se usan los valores
                por defecto; se puede pasar una copia modificada para calibrar.
            grid_ratio: Tamaño de la cuadrícula respecto al lado menor.
            cell_margin: Margen interno de cada celda para evitar los bordes.
            min_confidence: Fracción mínima de píxeles del color ganador.
            denoise_kernel: Tamaño del filtro de mediana; debe ser impar.

        Raises:
            DetectorError: Si la configuración no es coherente.
        """
        if not 0.1 <= grid_ratio <= 0.9:
            raise DetectorError("grid_ratio debe estar entre 0.1 y 0.9")
        if not 0.0 <= cell_margin < 0.5:
            raise DetectorError("cell_margin debe estar entre 0 y 0.5")
        if not 0.0 < min_confidence <= 1.0:
            raise DetectorError("min_confidence debe estar en (0, 1]")
        if denoise_kernel < 1 or denoise_kernel % 2 == 0:
            raise DetectorError("denoise_kernel debe ser impar y mayor que cero")

        self.ranges: dict[Color, tuple[HSVRange, ...]] = self._validate_ranges(
            ranges if ranges is not None else DEFAULT_COLOR_RANGES
        )
        self.grid_ratio = grid_ratio
        self.cell_margin = cell_margin
        self.min_confidence = min_confidence
        self.denoise_kernel = denoise_kernel

    @staticmethod
    def _validate_ranges(
        ranges: Mapping[Color, Sequence[HSVRange]],
    ) -> dict[Color, tuple[HSVRange, ...]]:
        """Comprueba que existan los seis colores y que los rangos sean válidos.

        Args:
            ranges: Rangos propuestos.

        Returns:
            Copia normalizada de los rangos.

        Raises:
            DetectorError: Si falta algún color o algún rango es inválido.
        """
        missing = [color.name_es for color in Color if color not in ranges]
        if missing:
            raise DetectorError(f"Faltan rangos HSV para: {', '.join(missing)}")

        normalized: dict[Color, tuple[HSVRange, ...]] = {}
        limits = ((179, "H"), (255, "S"), (255, "V"))
        for color in Color:
            entries = tuple(ranges[color])
            if not entries:
                raise DetectorError(f"El color {color.name_es} no tiene ningun rango")
            for entry in entries:
                if not isinstance(entry, HSVRange):
                    raise DetectorError("Los rangos deben ser instancias de HSVRange")
                for channel, (maximum, name) in enumerate(limits):
                    low = entry.lower[channel]
                    high = entry.upper[channel]
                    if not 0 <= low <= high <= maximum:
                        raise DetectorError(
                            f"Rango invalido de {name} para {color.name_es}: "
                            f"[{low}, {high}]"
                        )
            normalized[color] = entries
        return normalized

    # -- Geometría ---------------------------------------------------------

    def grid_rect(self, frame_shape: Sequence[int]) -> Rect:
        """Calcula la cuadrícula de muestreo centrada en el fotograma.

        Args:
            frame_shape: Forma del fotograma (alto, ancho, canales).

        Returns:
            Rectángulo cuadrado cuyo lado es múltiplo de 3.

        Raises:
            DetectorError: Si el fotograma es demasiado pequeño.
        """
        height, width = int(frame_shape[0]), int(frame_shape[1])
        side = int(min(height, width) * self.grid_ratio)
        side -= side % GRID_SIZE
        if side < GRID_SIZE * 9:
            raise DetectorError(
                "El fotograma es demasiado pequeno para la cuadricula de escaneo"
            )
        return Rect((width - side) // 2, (height - side) // 2, side, side)

    def cell_rects(self, frame_shape: Sequence[int]) -> tuple[Rect, ...]:
        """Devuelve los nueve rectángulos de las celdas, en orden de lectura."""
        grid = self.grid_rect(frame_shape)
        cell = grid.width // GRID_SIZE
        return tuple(
            Rect(grid.x + col * cell, grid.y + row * cell, cell, cell)
            for row in range(GRID_SIZE)
            for col in range(GRID_SIZE)
        )

    def sample_rects(self, frame_shape: Sequence[int]) -> tuple[Rect, ...]:
        """Devuelve los rectángulos internos que se promedian por celda."""
        return tuple(rect.inset(self.cell_margin) for rect in self.cell_rects(frame_shape))

    # -- Clasificación -----------------------------------------------------

    def sample_face(self, frame: np.ndarray) -> tuple[FaceletSample, ...]:
        """Analiza las nueve celdas de la cuadrícula de un fotograma.

        Args:
            frame: Imagen BGR de tipo ``uint8``.

        Returns:
            Nueve muestras en orden de lectura.

        Raises:
            DetectorError: Si el fotograma no es una imagen BGR válida.
        """
        self._require_frame(frame)
        grid = self.grid_rect(frame.shape)
        # Conserva el halo del filtro para obtener los mismos píxeles que al
        # filtrar la imagen completa, también con márgenes de celda de cero.
        radius = self.denoise_kernel // 2
        x0, y0 = max(0, grid.x - radius), max(0, grid.y - radius)
        x1 = min(frame.shape[1], grid.x2 + radius)
        y1 = min(frame.shape[0], grid.y2 + radius)
        working = frame[y0:y1, x0:x1]
        if self.denoise_kernel > 1:
            working = cv2.medianBlur(working, self.denoise_kernel)
        hsv = cv2.cvtColor(working, cv2.COLOR_BGR2HSV)

        samples: list[FaceletSample] = []
        for index, rect in enumerate(self.sample_rects(frame.shape)):
            patch = hsv[rect.y - y0 : rect.y2 - y0, rect.x - x0 : rect.x2 - x0]
            color, confidence, coverage, median = self._classify_patch(patch)
            samples.append(
                FaceletSample(
                    index=index,
                    color=color,
                    confidence=confidence,
                    coverage=coverage,
                    median_hsv=median,
                )
            )
        return tuple(samples)

    def classify_hsv(self, hsv: Sequence[int]) -> tuple[Color | None, float]:
        """Clasifica una única muestra HSV.

        Args:
            hsv: Terna ``(H, S, V)`` en el rango de OpenCV.

        Returns:
            Color detectado (o ``None``) y confianza en ``[0, 1]``.
        """
        pixel = np.array([[list(hsv)]], dtype=np.uint8)
        color, confidence, _, _ = self._classify_patch(pixel)
        return color, confidence

    def _classify_patch(
        self, patch: np.ndarray
    ) -> tuple[Color | None, float, float, tuple[int, int, int]]:
        """Clasifica una celda completa.

        Args:
            patch: Región HSV de tipo ``uint8`` con forma ``(alto, ancho, 3)``.

        Returns:
            Tupla ``(color, confianza, cobertura, mediana_hsv)``.
        """
        total = float(patch.shape[0] * patch.shape[1])
        scores: dict[Color, float] = {}
        union = np.zeros(patch.shape[:2], dtype=np.uint8)
        for color, ranges in self.ranges.items():
            matched = ranges[0].mask(patch)
            for entry in ranges[1:]:
                cv2.bitwise_or(matched, entry.mask(patch), dst=matched)
            cv2.bitwise_or(union, matched, dst=union)
            scores[color] = cv2.countNonZero(matched) / total

        coverage = cv2.countNonZero(union) / total

        median_channels = np.median(patch.reshape(-1, 3), axis=0)
        median_hsv = (
            round(float(median_channels[0])),
            round(float(median_channels[1])),
            round(float(median_channels[2])),
        )

        best_color = max(scores, key=lambda color: scores[color])
        best_score = scores[best_color]
        runner_up = sorted(scores.values(), reverse=True)[1]
        if best_score - runner_up < 0.03:
            candidates = [color for color, score in scores.items() if score >= best_score - 0.03]
            best_color = min(
                candidates, key=lambda color: self._hue_distance(median_hsv, color)
            )

        if best_score < self.min_confidence:
            return None, best_score, coverage, median_hsv
        return best_color, best_score, coverage, median_hsv

    @staticmethod
    def _hue_distance(median_hsv: tuple[int, int, int], color: Color) -> float:
        """Distancia circular aproximada entre la mediana y un color de referencia.

        Args:
            median_hsv: Mediana HSV de la celda.
            color: Color candidato.

        Returns:
            Distancia no negativa; el blanco se compara por saturación.
        """
        if color is Color.WHITE:
            return float(median_hsv[1])
        hue = median_hsv[0] * 2.0  # Se pasa a grados para trabajar con círculos.
        references = {
            Color.RED: (0.0, 358.0),
            Color.ORANGE: (30.0,),
            Color.YELLOW: (58.0,),
            Color.GREEN: (120.0,),
            Color.BLUE: (225.0,),
        }[color]
        return min(
            abs(hue - reference) if abs(hue - reference) <= 180 else 360 - abs(hue - reference)
            for reference in references
        )

    @staticmethod
    def frame_error(frame: object) -> str | None:
        """Describe por qué un objeto no sirve como fotograma BGR.

        Args:
            frame: Objeto recibido de la cámara.

        Returns:
            Mensaje de error, o ``None`` si el fotograma es utilizable.
        """
        if not isinstance(frame, np.ndarray):
            return "El fotograma debe ser un numpy.ndarray"
        if frame.ndim != 3 or frame.shape[2] != 3:
            return "El fotograma debe tener forma (alto, ancho, 3)"
        if frame.dtype != np.uint8:
            return "El fotograma debe ser uint8"
        if frame.shape[0] < 60 or frame.shape[1] < 60:
            return "El fotograma es demasiado pequeno"
        return None

    @classmethod
    def is_valid_frame(cls, frame: object) -> bool:
        """Indica si un objeto es una imagen BGR de 8 bits utilizable.

        Args:
            frame: Objeto recibido de la cámara.

        Returns:
            ``True`` si el detector puede analizarlo.
        """
        return cls.frame_error(frame) is None

    @staticmethod
    def _require_frame(frame: np.ndarray) -> None:
        """Valida que el fotograma sea una imagen BGR de 8 bits.

        Args:
            frame: Objeto recibido de la cámara.

        Raises:
            DetectorError: Si el tipo, la forma o el tipo de dato no son válidos.
        """
        reason = ColorDetector.frame_error(frame)
        if reason is not None:
            raise DetectorError(reason)

    # -- Diagnóstico -------------------------------------------------------

    def measure_illumination(self, frame: np.ndarray) -> Illumination:
        """Evalúa el brillo y la saturación de la zona de muestreo.

        Args:
            frame: Imagen BGR de tipo ``uint8``.

        Returns:
            Diagnóstico con una recomendación para el usuario.

        Raises:
            DetectorError: Si el fotograma no es válido.
        """
        self._require_frame(frame)
        region = frame[self.grid_rect(frame.shape).as_slice()]
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        mean_value = float(np.mean(hsv[:, :, 2]))
        mean_saturation = float(np.mean(hsv[:, :, 1]))

        if mean_value < 55:
            return Illumination(
                mean_value,
                mean_saturation,
                "muy oscura",
                "Enciende una luz frontal o acerca el cubo a la lampara",
                False,
            )
        if mean_value < 90:
            return Illumination(
                mean_value,
                mean_saturation,
                "oscura",
                "Hay poca luz: los colores apagados se confunden entre si",
                False,
            )
        if mean_value > 245 and mean_saturation < 40:
            return Illumination(
                mean_value,
                mean_saturation,
                "sobreexpuesta",
                "Evita el foco directo o aleja el cubo de la lampara",
                False,
            )
        return Illumination(
            mean_value,
            mean_saturation,
            "correcta",
            "Iluminacion adecuada para detectar los seis colores",
            True,
        )

    def build_color_mask(self, frame: np.ndarray) -> np.ndarray:
        """Construye una vista de depuración con cada píxel pintado por color.

        Los píxeles que no pertenecen a ningún rango se dejan en negro. Es útil
        para comprobar la calibración con ``--debug-mask``.

        Args:
            frame: Imagen BGR de tipo ``uint8``.

        Returns:
            Imagen BGR del mismo tamaño con la clasificación por colores.
        """
        self._require_frame(frame)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        canvas = np.zeros_like(frame)
        for color, ranges in self.ranges.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for entry in ranges:
                mask = cv2.bitwise_or(mask, entry.mask(hsv))
            canvas[mask.astype(bool)] = COLOR_MASK_BGR[color]
        return canvas


#: Colores BGR usados únicamente en la vista de depuración de la máscara.
COLOR_MASK_BGR: Final[dict[Color, tuple[int, int, int]]] = {
    Color.WHITE: (245, 245, 245),
    Color.YELLOW: (0, 235, 235),
    Color.RED: (40, 40, 235),
    Color.ORANGE: (0, 140, 250),
    Color.BLUE: (235, 90, 40),
    Color.GREEN: (60, 200, 60),
}
