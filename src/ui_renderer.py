"""Renderizado de la interfaz sobre el vídeo en vivo y lectura de teclado.

Todo el dibujo se concentra aquí para que los módulos de dominio no dependan de
OpenCV. La interfaz se compone de paneles semitransparentes, texto con sombra
para garantizar la legibilidad sobre cualquier fondo, una cuadrícula de
muestreo con retroalimentación de color por celda y el desglose del estado del
escaneo.

Nota sobre tipografía: las fuentes Hershey de OpenCV solo representan ASCII, por
lo que el texto se normaliza con :func:`to_ascii` antes de dibujarse (las tildes
y símbolos se sustituyen por equivalentes sin acento). Los textos de consola y
la documentación conservan la ortografía completa.

Examples:
    >>> from src.ui_renderer import KeyAction, parse_key
    >>> parse_key(ord("q")) is KeyAction.QUIT
    True
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Final

import cv2
import numpy as np

from .animation import VIEW_NAMES, CubeAnimator, effective_view
from .cube_state import SCAN_ORDER, Color, CubeModel, Face, ValidationReport
from .detector import FaceletSample, Rect
from .solver import Solution

__all__ = [
    "GuidingView",
    "KeyAction",
    "MessageLevel",
    "ScanView",
    "UIRenderer",
    "ValidationView",
    "parse_key",
    "to_ascii",
]

#: Nombre de la ventana de OpenCV.
WINDOW_NAME: Final[str] = "RubikVisionSolver"

# -- Paleta (BGR) -----------------------------------------------------------

_BG: Final[tuple[int, int, int]] = (25, 17, 13)
_TEXT: Final[tuple[int, int, int]] = (250, 245, 237)
_MUTED: Final[tuple[int, int, int]] = (181, 163, 147)
_ACCENT: Final[tuple[int, int, int]] = (193, 232, 91)
_VIOLET: Final[tuple[int, int, int]] = (250, 151, 167)
_OK: Final[tuple[int, int, int]] = (171, 218, 92)
_ERROR: Final[tuple[int, int, int]] = (133, 125, 255)
_WARNING: Final[tuple[int, int, int]] = (115, 204, 255)
_DARK: Final[tuple[int, int, int]] = (43, 32, 25)
_BORDER: Final[tuple[int, int, int]] = (72, 54, 43)

#: Colores BGR aproximados de cada pegatina para dibujar la cuadrícula.
STICKER_BGR: Final[dict[Color, tuple[int, int, int]]] = {
    Color.WHITE: (243, 243, 243),
    Color.YELLOW: (0, 230, 230),
    Color.RED: (40, 40, 225),
    Color.ORANGE: (0, 138, 250),
    Color.BLUE: (230, 88, 40),
    Color.GREEN: (62, 196, 62),
}


@lru_cache(maxsize=24)
def _solid(height: int, width: int, color: tuple[int, int, int]) -> np.ndarray:
    """Reutiliza superficies constantes con una caché de tamaño limitado."""
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = color
    image.flags.writeable = False
    return image


@lru_cache(maxsize=2048)
def _text_size(text: str, scale: float, thickness: int = 1) -> tuple[int, int]:
    """Evita medir de nuevo etiquetas estáticas en cada fotograma."""
    size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, scale, thickness)
    return int(size[0]), int(size[1])


class MessageLevel(Enum):
    """Tono del mensaje mostrado en pantalla."""

    INFO = "info"
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


_LEVEL_BGR: Final[dict[MessageLevel, tuple[int, int, int]]] = {
    MessageLevel.INFO: _TEXT,
    MessageLevel.OK: _OK,
    MessageLevel.WARNING: _WARNING,
    MessageLevel.ERROR: _ERROR,
}


class KeyAction(Enum):
    """Acción abstracta asociada a una tecla."""

    NONE = "none"
    CAPTURE = "capture"
    NEXT = "next"
    PREVIOUS = "previous"
    RESET = "reset"
    QUIT = "quit"
    TOGGLE_MASK = "toggle_mask"
    PAUSE = "pause"
    REPLAY = "replay"
    SPEED = "speed"
    VIEW = "view"


_KEY_MAP: Final[dict[int, KeyAction]] = {
    27: KeyAction.QUIT,  # ESC
    ord("q"): KeyAction.QUIT,
    ord("Q"): KeyAction.QUIT,
    32: KeyAction.CAPTURE,  # ESPACIO
    13: KeyAction.NEXT,  # ENTER
    10: KeyAction.NEXT,
    ord("n"): KeyAction.NEXT,
    ord("N"): KeyAction.NEXT,
    65363: KeyAction.NEXT,  # flecha derecha (GTK/Qt)
    2555904: KeyAction.NEXT,  # flecha derecha (Windows)
    ord("b"): KeyAction.PREVIOUS,
    ord("B"): KeyAction.PREVIOUS,
    65361: KeyAction.PREVIOUS,  # flecha izquierda (GTK/Qt)
    2424832: KeyAction.PREVIOUS,  # flecha izquierda (Windows)
    ord("r"): KeyAction.RESET,
    ord("R"): KeyAction.RESET,
    ord("m"): KeyAction.TOGGLE_MASK,
    ord("M"): KeyAction.TOGGLE_MASK,
    ord("p"): KeyAction.PAUSE,
    ord("P"): KeyAction.PAUSE,
    ord("a"): KeyAction.REPLAY,
    ord("A"): KeyAction.REPLAY,
    ord("s"): KeyAction.SPEED,
    ord("S"): KeyAction.SPEED,
    ord("v"): KeyAction.VIEW,
    ord("V"): KeyAction.VIEW,
}


def parse_key(key: int) -> KeyAction:
    """Traduce el código devuelto por ``cv2.waitKey`` a una acción.

    Args:
        key: Código entero de la tecla (``-1`` si no se pulsó ninguna).

    Returns:
        Acción asociada o :attr:`KeyAction.NONE`.
    """
    if key < 0:
        return KeyAction.NONE
    return _KEY_MAP.get(key, KeyAction.NONE)


@lru_cache(maxsize=512)
def to_ascii(text: str) -> str:
    """Convierte texto Unicode a ASCII apto para las fuentes de OpenCV.

    Args:
        text: Texto original, potencialmente con tildes o símbolos.

    Returns:
        Texto sin caracteres combinados y con los símbolos más habituales
        sustituidos por equivalentes ASCII.
    """
    replacements = {
        "\u00ba": "o",
        "\u00b0": " grados",
        "\u2192": "->",
        "\u2190": "<-",
        "\u21bb": "(horario)",
        "\u21ba": "(antihorario)",
        "\u00d7": "x",
        "\u2026": "...",
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


@dataclass(frozen=True)
class ScanView:
    """Datos necesarios para dibujar la pantalla de escaneo.

    Attributes:
        current_face: Cara que se está pidiendo al usuario.
        instruction: Texto con la posición exacta del cubo.
        cells: Rectángulos de las nueve celdas de muestreo.
        samples: Resultado del análisis de cada celda.
        scanned: Caras ya capturadas junto con el color de su centro.
        message: Mensaje de estado (puede estar vacío).
        level: Tono del mensaje.
        mask: Vista de depuración de la máscara de color, opcional.
    """

    current_face: Face
    instruction: str
    cells: tuple[Rect, ...]
    samples: tuple[FaceletSample, ...] = ()
    scanned: tuple[tuple[Face, Color], ...] = ()
    message: str = ""

    level: MessageLevel = MessageLevel.INFO
    mask: np.ndarray | None = None


@dataclass(frozen=True)
class ValidationView:
    """Datos de la pantalla de confirmación del cubo escaneado.

    Attributes:
        model: Cubo reconstruido.
        report: Resultado de la validación.
        up_face: Cara que debe quedar arriba al resolver.
        front_face: Cara que debe quedar hacia el usuario.
        message: Error del solucionador que debe mostrarse al reintentar.
    """

    model: CubeModel
    report: ValidationReport
    up_face: Face
    front_face: Face
    message: str = ""


@dataclass(frozen=True)
class GuidingView:
    """Datos de la pantalla de resolución paso a paso.

    Attributes:
        solution: Solución calculada.
        index: Índice del movimiento actual (0-based).
        up_color: Color del centro que debe quedar arriba.
        front_color: Color del centro que debe quedar delante.
    """

    solution: Solution
    index: int
    up_color: Color | None
    front_color: Color | None
    cube: CubeModel | None = None
    progress: float = 0.0
    paused: bool = False
    speed: float = 1.0
    viewpoint: int = 0
    message: str = ""
    demo: bool = False


@dataclass(frozen=True)
class _Layout:
    """Medidas derivadas del tamaño del fotograma."""

    width: int
    height: int
    scale: float
    margin: int

    @classmethod
    def from_frame(cls, frame: np.ndarray) -> _Layout:
        """Calcula la maquetación a partir del fotograma."""
        height, width = int(frame.shape[0]), int(frame.shape[1])
        scale = max(0.5, min(1.6, height / 720.0, width / 1100.0))
        return cls(width, height, scale, round(22 * scale))

    def px(self, value: float) -> int:
        """Escala una medida de referencia (pensada para 720p)."""
        return round(value * self.scale)

    def font(self, reference: float) -> float:
        """Escala tipográfica relativa a una pantalla de 720p.

        A diferencia de :meth:`px`, devuelve un flotante sin redondear: es el
        valor que espera ``cv2.putText`` como ``fontScale``. Sin esta
        distinción, escalas como ``0.48`` se redondearían a cero y el texto no
        se vería.

        Args:
            reference: Escala de referencia para 720p.

        Returns:
            Escala de fuente utilizable, nunca inferior a 0.35.
        """
        return max(0.35, reference * self.scale)


class UIRenderer:
    """Dibuja todas las pantallas de la aplicación sobre el fotograma.

    Attributes:
        window_name: Título de la ventana de OpenCV.
        show_mask: Si es ``True`` se muestra el recuadro de la máscara HSV.
    """

    def __init__(self, window_name: str = WINDOW_NAME, *, show_mask: bool = False) -> None:
        """Inicializa el renderizador.

        Args:
            window_name: Título de la ventana.
            show_mask: Activa la vista de depuración de la máscara de color.
        """
        self.window_name = window_name
        self.show_mask = show_mask
        self._buttons: list[tuple[Rect, KeyAction]] = []
        self._animator = CubeAnimator()

    def hit_test(self, x: int, y: int) -> KeyAction:
        """Acción bajo el cursor, en coordenadas de la imagen de HighGUI."""
        for rect, action in self._buttons:
            if rect.x <= x < rect.x2 and rect.y <= y < rect.y2:
                return action
        return KeyAction.NONE

    def _controls(
        self, frame: np.ndarray, layout: _Layout, items: tuple[tuple[str, KeyAction], ...], y: int
    ) -> None:
        """Dibuja botones grandes con las mismas acciones que el teclado."""
        gap = layout.px(8)
        width = min(
            layout.px(194),
            (layout.width - 2 * layout.margin - gap * (len(items) - 1)) // len(items),
        )
        for index, (label, action) in enumerate(items):
            rect = Rect(layout.margin + index * (width + gap), y, width, layout.px(36))
            color = _ACCENT if action in (KeyAction.CAPTURE, KeyAction.NEXT) else _BORDER
            self._blend_rect(frame, rect, color, 1.0)
            self._put_text(
                frame,
                label,
                (rect.center[0], rect.y + layout.px(24)),
                layout.font(0.43),
                _BG if color == _ACCENT else _TEXT,
                anchor="center",
            )
            self._buttons.append((rect, action))

    # -- API pública -------------------------------------------------------

    def draw_scanning(self, frame: np.ndarray, view: ScanView) -> np.ndarray:
        """Dibuja la pantalla de escaneo de caras.

        Args:
            frame: Fotograma BGR sobre el que se dibuja (se modifica in situ).
            view: Estado del escaneo.

        Returns:
            El mismo fotograma con la interfaz superpuesta.
        """
        self._buttons.clear()
        layout = _Layout.from_frame(frame)
        self._draw_header(frame, layout, "Escaneo de caras", self._progress_text(view))
        self._draw_grid(frame, layout, view)
        self._draw_face_checklist(frame, layout, view)
        self._draw_scan_status(frame, layout, view)
        self._draw_footer(frame, layout, view.instruction, view.message, view.level)
        if self.show_mask and view.mask is not None:
            mask = view.mask
            if view.cells and mask.shape == frame.shape:
                mask = mask[
                    view.cells[0].y : view.cells[-1].y2, view.cells[0].x : view.cells[-1].x2
                ]
            self._draw_mask_inset(frame, layout, mask)
        self._draw_key_hints(
            frame,
            layout,
            "ESPACIO  Capturar   |   M  Colores   |   R  Reiniciar   |   Q  Salir",
        )
        self._controls(
            frame,
            layout,
            (
                ("Capturar cara", KeyAction.CAPTURE),
                ("Reiniciar", KeyAction.RESET),
                ("Colores HSV", KeyAction.TOGGLE_MASK),
            ),
            layout.height - layout.px(76),
        )
        return frame

    def draw_validation(self, frame: np.ndarray, view: ValidationView) -> np.ndarray:
        """Dibuja la pantalla de confirmación y validación del cubo.

        Args:
            frame: Fotograma BGR sobre el que se dibuja.
            view: Modelo reconstruido y resultado de la validación.

        Returns:
            El mismo fotograma con la interfaz superpuesta.
        """
        self._buttons.clear()
        layout = _Layout.from_frame(frame)
        self._dim(frame, 0.9)
        self._draw_header(
            frame,
            layout,
            "Verificacion del cubo",
            "6 caras capturadas  /  Revisa los colores antes de continuar",
        )

        top = layout.px(128)
        card_height = layout.height - top - layout.px(110)
        net_panel = Rect(layout.margin, top, int(layout.width * 0.43) - layout.margin, card_height)
        self._panel(frame, net_panel, 1.0)
        self._put_text(
            frame,
            "MAPA DE TU CUBO",
            (net_panel.x + layout.px(20), top + layout.px(34)),
            layout.font(0.46),
            _MUTED,
        )
        net_cell = max(
            4, min((net_panel.width - layout.px(32)) // 12, (card_height - layout.px(120)) // 9)
        )
        net_x = net_panel.x + (net_panel.width - 12 * net_cell) // 2
        net_y = top + (card_height - 9 * net_cell) // 2
        self._draw_net(frame, view.model, net_x, net_y, net_cell)
        self._put_text(
            frame,
            "U arriba / F al frente",
            (net_panel.center[0], net_panel.y2 - layout.px(24)),
            layout.font(0.42),
            _MUTED,
            anchor="center",
        )

        if view.report.is_valid:
            up_color = view.model.center(view.up_face)
            front_color = view.model.center(view.front_face)
            heading = "Todo listo para resolver"
            heading_color = _OK
            lines = [
                "Los colores y las piezas forman un cubo valido.",
                "Comprueba que el mapa coincida con tu cubo.",
                "",
                f"Mantén arriba el centro {self._color_name(up_color)}.",
                f"Orienta hacia ti el centro {self._color_name(front_color)}.",
                "",
                view.message or "Pulsa ESPACIO para calcular la solucion.",
            ]
            line_colors = [_TEXT] * (len(lines) - 1) + [_ERROR if view.message else _ACCENT]
        else:
            heading = "El cubo no es resoluble"
            heading_color = _ERROR
            lines = [
                *view.report.messages,
                "",
                "Revisa el orden de las caras y la iluminacion.",
                "Pulsa R para volver a escanear.",
            ]
            line_colors = [_ERROR if line in view.report.messages else _TEXT for line in lines]

        panel_x = net_panel.x2 + layout.px(18)
        panel_width = layout.width - panel_x - layout.margin
        panel = Rect(panel_x, top, panel_width, card_height)
        self._panel(frame, panel, alpha=1.0)

        text_x = panel.x + layout.px(16)
        text_y = panel.y + layout.px(40)
        text_y = self._draw_paragraph(
            frame,
            heading,
            (text_x, text_y),
            panel.width - layout.px(32),
            layout.font(0.7),
            heading_color,
            max_lines=2,
        )
        text_y += layout.px(28)

        for line, line_color in zip(lines, line_colors, strict=True):
            available = int((panel.y2 - layout.px(24) - text_y) / (32 * layout.font(0.48)))
            if available < 1:
                break
            if not line:
                text_y += layout.px(16)
                continue
            text_y = self._draw_paragraph(
                frame,
                line,
                (text_x, text_y),
                panel.width - layout.px(28),
                layout.font(0.48),
                line_color,
                max_lines=min(3, available),
            )
            text_y += layout.px(10)

        self._draw_key_hints(
            frame,
            layout,
            "ESPACIO  Resolver   |   R  Reescanear   |   Q  Salir"
            if view.report.is_valid
            else "R  Reescanear   |   Q  Salir",
        )
        items = (
            (("Resolver", KeyAction.NEXT), ("Reescanear", KeyAction.RESET))
            if (view.report.is_valid)
            else (("Reescanear", KeyAction.RESET),)
        )
        self._controls(frame, layout, items, layout.height - layout.px(76))
        return frame

    def draw_solving(
        self,
        frame: np.ndarray,
        up_color: Color | None,
        front_color: Color | None,
    ) -> np.ndarray:
        """Dibuja la pantalla de espera mientras se calcula la solución.

        Args:
            frame: Fotograma BGR sobre el que se dibuja.
            up_color: Color del centro superior de referencia.
            front_color: Color del centro frontal de referencia.

        Returns:
            El mismo fotograma con la interfaz superpuesta.
        """
        self._buttons.clear()
        layout = _Layout.from_frame(frame)
        self._dim(frame, 0.55)
        center_y = layout.height // 2
        panel_width = min(layout.px(760), layout.width - 2 * layout.margin)
        panel = Rect(
            layout.width // 2 - panel_width // 2,
            center_y - layout.px(100),
            panel_width,
            layout.px(190),
        )
        self._panel(frame, panel, alpha=0.96)
        self._put_text(
            frame,
            "Calculando la solucion...",
            (layout.width // 2, center_y),
            layout.font(0.9),
            _ACCENT,
            thickness=2,
            anchor="center",
        )
        hint = (
            f"Referencia: centro {self._color_name(up_color)} arriba y "
            f"centro {self._color_name(front_color)} hacia ti"
        )
        self._put_text(
            frame,
            to_ascii(hint),
            (layout.width // 2, center_y + layout.px(44)),
            layout.font(0.5),
            _MUTED,
            anchor="center",
        )
        self._controls(
            frame,
            layout,
            (("Cancelar", KeyAction.RESET), ("Salir", KeyAction.QUIT)),
            layout.height - layout.px(76),
        )
        return frame

    def draw_guiding(self, frame: np.ndarray, view: GuidingView) -> np.ndarray:
        """Dibuja el movimiento actual y el progreso de la solución.

        Args:
            frame: Fotograma BGR sobre el que se dibuja.
            view: Solución y posición actual.

        Returns:
            El mismo fotograma con la interfaz superpuesta.
        """
        self._buttons.clear()
        layout = _Layout.from_frame(frame)
        total = view.solution.move_count
        current = view.solution.moves[view.index]
        top = layout.px(128)
        bottom = layout.height - layout.px(198)
        left = Rect(layout.margin, top, int(layout.width * 0.43) - layout.margin, bottom - top)
        # Conserva una miniatura real de la cámara antes de pintar el lienzo.
        live_width = layout.px(186)
        live_height = layout.px(106)
        ratio = min(live_width / frame.shape[1], live_height / frame.shape[0])
        live = cv2.resize(
            frame,
            (max(1, round(frame.shape[1] * ratio)), max(1, round(frame.shape[0] * ratio))),
            interpolation=cv2.INTER_AREA,
        )
        frame[:] = _BG
        self._panel(frame, left, 1.0)
        self._draw_header(
            frame,
            layout,
            "Resolucion guiada",
            f"Paso {view.index + 1:02d} de {total:02d} / Mira el giro, hazlo en tu cubo y confirma",
        )
        self._put_text(
            frame,
            "DEMOSTRACION 3D",
            (left.x + layout.px(16), top + layout.px(28)),
            layout.font(0.4),
            _ACCENT,
        )
        cube_rect = Rect(
            left.x + layout.px(8),
            top + layout.px(46),
            left.width - layout.px(16),
            left.height - layout.px(118),
        )
        picture = self._animator.render(
            view.cube or CubeModel.solved(),
            current,
            view.progress,
            cube_rect.width,
            cube_rect.height,
            view.viewpoint,
        )
        frame[cube_rect.as_slice()] = picture
        view_name = VIEW_NAMES[effective_view(current.face, view.viewpoint)]
        self._put_text(
            frame,
            f"Vista: {view_name}",
            (left.x + layout.px(16), left.y2 - layout.px(48)),
            layout.font(0.43),
            _VIOLET,
        )
        reference = "La vista cambia; NO gires todo tu cubo."
        self._draw_paragraph(
            frame,
            reference,
            (left.x + layout.px(16), left.y2 - layout.px(22)),
            left.width - layout.px(32),
            layout.font(0.44),
            _TEXT,
            max_lines=2,
        )

        panel_x = left.x2 + layout.px(18)
        panel = Rect(panel_x, top, layout.width - layout.margin - panel_x, left.height)
        self._panel(frame, panel, 1.0)
        x = panel.x + layout.px(24)
        self._put_text(
            frame,
            "GIRA SOLO LA " + current.hint.upper(),
            (x, top + layout.px(34)),
            layout.font(0.46),
            _VIOLET,
        )
        self._put_text(
            frame,
            current.notation,
            (x, top + layout.px(116)),
            layout.font(2.2),
            _TEXT,
            thickness=max(2, layout.px(3)),
        )
        turn = (
            "180 grados / media vuelta"
            if current.is_double
            else "90 grados / antihorario"
            if current.is_prime
            else "90 grados / horario"
        )
        y = self._draw_paragraph(
            frame,
            turn,
            (x, top + layout.px(158)),
            panel.width - layout.px(48),
            layout.font(0.63),
            _TEXT,
            max_lines=2,
        )
        self._draw_paragraph(
            frame,
            f"Mirando de frente la cara {current.face_name}. Mira como se mueve la capa resaltada.",
            (x, y + layout.px(12)),
            panel.width - layout.px(48),
            layout.font(0.48),
            _MUTED,
            max_lines=3,
        )
        live_x, live_y = (
            panel.x2 - live.shape[1] - layout.px(16),
            panel.y2 - live.shape[0] - layout.px(18),
        )
        frame[live_y : live_y + live.shape[0], live_x : live_x + live.shape[1]] = live
        self._put_text(
            frame,
            "DEMO / SIN CAMARA" if view.demo else "TU CAMARA",
            (live_x, live_y - layout.px(8)),
            layout.font(0.36),
            _MUTED,
        )
        self._draw_paragraph(
            frame,
            f"Arriba: {self._color_name(view.up_color)}. "
            f"Frente: {self._color_name(view.front_color)}.",
            (x, live_y + layout.px(22)),
            live_x - x - layout.px(12),
            layout.font(0.46),
            _ACCENT,
            max_lines=3,
        )
        self._controls(
            frame,
            layout,
            (
                ("Hecho", KeyAction.NEXT),
                ("Anterior", KeyAction.PREVIOUS),
                ("Repetir", KeyAction.REPLAY),
                ("Reanudar" if view.paused else "Pausar", KeyAction.PAUSE),
                (f"Ritmo {view.speed:g}x", KeyAction.SPEED),
                ("Cambiar vista", KeyAction.VIEW),
            ),
            bottom + layout.px(16),
        )
        list_y = bottom + layout.px(80)
        self._put_text(frame, "A CONTINUACION", (layout.margin, list_y), layout.font(0.4), _MUTED)
        remaining = view.solution.moves[view.index + 1 : view.index + 7]
        for index, move in enumerate(remaining):
            chip = Rect(
                layout.margin + index * layout.px(78),
                list_y + layout.px(12),
                layout.px(64),
                layout.px(32),
            )
            self._panel(frame, chip, 1.0)
            self._put_text(
                frame,
                move.notation,
                (chip.center[0], chip.y + layout.px(23)),
                layout.font(0.62),
                _TEXT,
                anchor="center",
            )
        if view.message:
            self._draw_paragraph(
                frame,
                view.message,
                (layout.width // 2, list_y + layout.px(22)),
                layout.width // 2 - layout.margin,
                layout.font(0.4),
                _WARNING,
                max_lines=2,
            )
        if not remaining:
            self._put_text(
                frame,
                "Ultimo giro. Comprueba las seis caras.",
                (layout.margin, list_y + layout.px(38)),
                layout.font(0.48),
                _ACCENT,
            )
        self._progress_bar(
            frame,
            Rect(
                layout.margin,
                layout.height - layout.px(50),
                layout.width - 2 * layout.margin,
                layout.px(4),
            ),
            view.index / max(total, 1),
        )
        self._draw_key_hints(
            frame,
            layout,
            "ESPACIO Hecho | B Atras | A Repetir | P Pausa | "
            "S Ritmo | V Vista | R Reiniciar | Q Salir",
        )
        return frame

    def draw_finished(self, frame: np.ndarray, solution: Solution) -> np.ndarray:
        """Dibuja la pantalla final cuando el cubo está resuelto.

        Args:
            frame: Fotograma BGR sobre el que se dibuja.
            solution: Solución aplicada.

        Returns:
            El mismo fotograma con la interfaz superpuesta.
        """
        self._buttons.clear()
        layout = _Layout.from_frame(frame)
        self._dim(frame, 0.55)
        center_x = layout.width // 2
        center_y = layout.height // 2
        panel_width = min(layout.px(760), layout.width - 2 * layout.margin)
        panel = Rect(
            center_x - panel_width // 2,
            center_y - layout.px(120),
            panel_width,
            layout.px(240),
        )
        self._panel(frame, panel, alpha=0.96)
        self._put_text(
            frame,
            "Secuencia completada" if solution.move_count else "Cubo resuelto",
            (center_x, center_y - layout.px(30)),
            layout.font(0.95),
            _OK,
            thickness=max(2, layout.px(2)),
            anchor="center",
        )
        if solution.move_count:
            elapsed = (
                f"{solution.elapsed_ms:.0f} ms"
                if solution.elapsed_ms < 1000.0
                else f"{solution.elapsed_ms / 1000.0:.1f} s"
            )
            detail = f"{solution.move_count} movimientos / calculo: {elapsed}"
        else:
            detail = "El cubo ya estaba resuelto"
        self._put_text(
            frame,
            to_ascii(detail),
            (center_x, center_y + layout.px(26)),
            layout.font(0.55),
            _TEXT,
            anchor="center",
        )
        self._put_text(
            frame,
            "Pulsa R para escanear otro cubo o Q para salir",
            (center_x, center_y + layout.px(70)),
            layout.font(0.48),
            _MUTED,
            anchor="center",
        )
        self._controls(
            frame,
            layout,
            (
                ("Nuevo cubo", KeyAction.RESET),
                ("Ultimo giro", KeyAction.PREVIOUS),
                ("Salir", KeyAction.QUIT),
            ),
            layout.height - layout.px(76),
        )
        return frame

    def draw_error(self, frame: np.ndarray, title: str, detail: str) -> np.ndarray:
        """Dibuja una pantalla de error bloqueante.

        Args:
            frame: Fotograma BGR sobre el que se dibuja.
            title: Título del error.
            detail: Explicación y posibles soluciones.

        Returns:
            El mismo fotograma con la interfaz superpuesta.
        """
        self._buttons.clear()
        layout = _Layout.from_frame(frame)
        self._dim(frame, 0.6)
        center_x = layout.width // 2
        center_y = layout.height // 2
        panel_width = min(layout.px(980), layout.width - 2 * layout.margin)
        self._panel(
            frame,
            Rect(
                center_x - panel_width // 2,
                center_y - layout.px(120),
                panel_width,
                layout.px(260),
            ),
            alpha=0.96,
        )
        self._put_text(
            frame,
            title,
            (center_x, center_y - layout.px(54)),
            layout.font(0.9),
            _ERROR,
            thickness=2,
            anchor="center",
        )
        self._draw_paragraph(
            frame,
            detail,
            (center_x, center_y - layout.px(6)),
            panel_width - layout.px(80),
            layout.font(0.52),
            _TEXT,
            max_lines=3,
            anchor="center",
        )
        self._put_text(
            frame,
            "Pulsa R para reintentar la camara o Q para salir",
            (center_x, center_y + layout.px(100)),
            layout.font(0.48),
            _MUTED,
            anchor="center",
        )
        self._controls(
            frame,
            layout,
            (("Reintentar", KeyAction.RESET), ("Salir", KeyAction.QUIT)),
            layout.height - layout.px(76),
        )
        return frame

    # -- Componentes -------------------------------------------------------

    def _draw_header(self, frame: np.ndarray, layout: _Layout, title: str, subtitle: str) -> None:
        """Dibuja la cabecera con el título y el progreso."""
        panel = Rect(0, 0, layout.width, layout.px(96))
        self._blend_rect(frame, panel, _BG, 1.0)
        self._put_text(
            frame,
            "RUBIK / VISION",
            (layout.margin, layout.px(28)),
            layout.font(0.42),
            _ACCENT,
        )
        self._put_text(
            frame,
            title,
            (layout.margin, layout.px(60)),
            layout.font(0.72),
            _TEXT,
        )
        self._put_text(
            frame,
            to_ascii(subtitle),
            (layout.margin, layout.px(82)),
            layout.font(0.42),
            _MUTED,
        )
        steps = ("01 ESCANEAR", "02 VALIDAR", "03 RESOLVER")
        active = 0 if "Escaneo" in title else 1 if "Verificacion" in title else 2
        x = layout.width - layout.margin - layout.px(420)
        if x > layout.px(400):
            for index, label in enumerate(steps):
                rect = Rect(
                    x + index * layout.px(140), layout.px(30), layout.px(130), layout.px(34)
                )
                self._blend_rect(frame, rect, _DARK, 1.0)
                self._put_text(
                    frame,
                    label,
                    (rect.x + layout.px(10), rect.y + layout.px(22)),
                    layout.font(0.4),
                    _ACCENT if index == active else _MUTED,
                )
                if index == active:
                    cv2.line(frame, (rect.x, rect.y2), (rect.x2, rect.y2), _ACCENT, 2)

    def _draw_grid(self, frame: np.ndarray, layout: _Layout, view: ScanView) -> None:
        """Dibuja la cuadrícula 3x3 con el color detectado en cada celda."""
        for rect, sample in zip(view.cells, view.samples, strict=False):
            border = _OK if sample.is_confident else _WARNING
            cv2.rectangle(
                frame,
                (rect.x, rect.y),
                (rect.x2 - 1, rect.y2 - 1),
                border,
                1,
            )
            if sample.color is not None:
                chip = Rect(
                    rect.x + layout.px(5), rect.y2 - layout.px(24), layout.px(48), layout.px(19)
                )
                self._blend_rect(frame, chip, _BG, 0.9)
                cv2.rectangle(
                    frame,
                    (chip.x, chip.y),
                    (chip.x + layout.px(4), chip.y2),
                    STICKER_BGR[sample.color],
                    -1,
                )
                label = to_ascii(sample.color.name_es[:3].upper())
                self._put_text(
                    frame,
                    label,
                    (chip.x + layout.px(10), chip.y2 - layout.px(4)),
                    layout.font(0.36),
                    _TEXT,
                    thickness=1,
                )
        if not view.cells:
            return
        grid = view.cells[0]
        grid_rect = Rect(
            grid.x,
            grid.y,
            view.cells[2].x2 - grid.x,
            view.cells[6].y2 - grid.y,
        )
        cv2.rectangle(
            frame,
            (grid_rect.x, grid_rect.y),
            (grid_rect.x2 - 1, grid_rect.y2 - 1),
            _ACCENT,
            1,
        )
        arm = layout.px(22)
        for x, dx in ((grid_rect.x, arm), (grid_rect.x2, -arm)):
            for y, dy in ((grid_rect.y, arm), (grid_rect.y2, -arm)):
                cv2.line(frame, (x, y), (x + dx, y), _ACCENT, max(2, layout.px(3)))
                cv2.line(frame, (x, y), (x, y + dy), _ACCENT, max(2, layout.px(3)))

    def _draw_face_checklist(self, frame: np.ndarray, layout: _Layout, view: ScanView) -> None:
        """Dibuja la lista de caras pendientes y completadas."""
        if not view.cells:
            return
        scanned = dict(view.scanned)
        row_height = layout.px(34)
        panel_width = layout.px(224)
        x = layout.width - layout.margin - panel_width
        grid = view.cells[0]
        if x < view.cells[2].x2 + layout.px(12):
            # En encuadres estrechos, seis fichas horizontales sustituyen la lista.
            for index, face in enumerate(SCAN_ORDER):
                cx = layout.width // 2 + (index * 2 - 5) * layout.px(23)
                self._put_text(
                    frame,
                    face.value,
                    (cx, layout.px(126)),
                    layout.font(0.5),
                    _ACCENT if face in scanned else _MUTED,
                    anchor="center",
                )
            return
        panel = Rect(x, grid.y, panel_width, row_height * 6 + layout.px(34))
        self._panel(frame, panel, alpha=0.96)
        self._put_text(
            frame,
            "TUS SEIS CARAS",
            (panel.x + layout.px(12), panel.y + layout.px(22)),
            layout.font(0.46),
            _MUTED,
        )

        y = panel.y + layout.px(34)
        for face in SCAN_ORDER:
            color = scanned.get(face)
            done = color is not None
            active = face is view.current_face
            if active:
                self._blend_rect(
                    frame,
                    Rect(
                        panel.x + layout.px(6),
                        y,
                        panel.width - layout.px(12),
                        row_height - layout.px(6),
                    ),
                    _ACCENT,
                    0.16,
                )
            marker_color = _OK if done else (_ACCENT if active else _MUTED)
            marker = f"{face.value}  {face.name_es}"
            self._put_text(
                frame,
                to_ascii(marker),
                (panel.x + layout.px(14), y + layout.px(20)),
                layout.font(0.48),
                marker_color,
                thickness=2 if active else 1,
            )
            if done and color is not None:
                swatch = Rect(
                    panel.x + panel.width - layout.px(26),
                    y + layout.px(6),
                    layout.px(16),
                    layout.px(16),
                )
                cv2.rectangle(
                    frame,
                    (swatch.x, swatch.y),
                    (swatch.x2, swatch.y2),
                    STICKER_BGR[color],
                    -1,
                )
                cv2.rectangle(
                    frame,
                    (swatch.x, swatch.y),
                    (swatch.x2, swatch.y2),
                    _BORDER,
                    1,
                )
            y += row_height

    def _draw_scan_status(self, frame: np.ndarray, layout: _Layout, view: ScanView) -> None:
        """Muestra calidad de lectura sin cubrir la cuadrícula de captura."""
        if not view.cells or view.cells[0].x < layout.px(232) + 2 * layout.margin:
            return
        panel = Rect(layout.margin, view.cells[0].y, layout.px(224), layout.px(230))
        self._panel(frame, panel, 0.96)
        x, y = panel.x + layout.px(16), panel.y + layout.px(28)
        self._put_text(frame, "LECTURA EN VIVO", (x, y), layout.font(0.42), _MUTED)
        ready = sum(sample.is_confident for sample in view.samples)
        self._put_text(
            frame,
            f"{ready} / 9",
            (x, y + layout.px(52)),
            layout.font(1.1),
            _ACCENT if ready == 9 else _WARNING,
        )
        self._put_text(
            frame, "celdas reconocidas", (x, y + layout.px(78)), layout.font(0.42), _MUTED
        )
        self._progress_bar(
            frame, Rect(x, y + layout.px(100), panel.width - layout.px(32), layout.px(5)), ready / 9
        )
        self._draw_paragraph(
            frame,
            "Listo para capturar" if ready == 9 else "Ajusta la luz y el encuadre",
            (x, y + layout.px(134)),
            panel.width - layout.px(32),
            layout.font(0.5),
            _TEXT,
            max_lines=2,
        )
        self._put_text(
            frame, "ESPACIO  Guardar cara", (x, panel.y2 - layout.px(18)), layout.font(0.4), _ACCENT
        )

    def _draw_footer(
        self,
        frame: np.ndarray,
        layout: _Layout,
        instruction: str,
        message: str,
        level: MessageLevel,
    ) -> None:
        """Dibuja el panel inferior con la instrucción y el estado."""
        height = layout.px(120)
        panel = Rect(
            layout.margin,
            layout.height - height - layout.px(38),
            layout.width - 2 * layout.margin,
            height,
        )
        self._panel(frame, panel, alpha=0.97)
        text_x = panel.x + layout.px(16)
        text_y = panel.y + layout.px(28)
        text_y = self._draw_paragraph(
            frame,
            instruction,
            (text_x, text_y),
            panel.width - layout.px(32),
            layout.font(0.58),
            _TEXT,
            max_lines=2,
        )
        if message:
            self._draw_paragraph(
                frame,
                message,
                (text_x, text_y + layout.px(4)),
                panel.width - layout.px(32),
                layout.font(0.48),
                _LEVEL_BGR[level],
                max_lines=2,
            )

    def _draw_key_hints(self, frame: np.ndarray, layout: _Layout, hints: str) -> None:
        """Dibuja la línea de atajos en la parte inferior."""
        self._blend_rect(
            frame, Rect(0, layout.height - layout.px(34), layout.width, layout.px(34)), _BG, 1.0
        )
        self._put_text(
            frame,
            to_ascii(hints),
            (layout.width // 2, layout.height - layout.px(14)),
            layout.font(0.44),
            _MUTED,
            anchor="center",
        )

    def _draw_mask_inset(self, frame: np.ndarray, layout: _Layout, mask: np.ndarray) -> None:
        """Dibuja la máscara de color de depuración en una esquina."""
        size = layout.px(100)
        x = layout.width - size - layout.margin
        y = layout.height - layout.px(280)
        small = cv2.resize(mask, (size, size), interpolation=cv2.INTER_AREA)
        region = frame[y : y + size, x : x + size]
        if region.shape[:2] == small.shape[:2]:
            cv2.addWeighted(small, 0.85, region, 0.15, 0, dst=region)
        cv2.rectangle(frame, (x, y), (x + size, y + size), _BORDER, 1)
        self._put_text(
            frame,
            "mascara HSV",
            (x, y + size + layout.px(16)),
            layout.font(0.4),
            _MUTED,
        )

    def _draw_net(self, frame: np.ndarray, model: CubeModel, x: int, y: int, cell: int) -> None:
        """Dibuja el desarrollo plano 2D de las seis caras."""
        positions: Mapping[Face, tuple[int, int]] = {
            Face.U: (1, 0),
            Face.L: (0, 1),
            Face.F: (1, 1),
            Face.R: (2, 1),
            Face.B: (3, 1),
            Face.D: (1, 2),
        }
        for face, (col, row) in positions.items():
            origin_x = x + col * 3 * cell
            origin_y = y + row * 3 * cell
            grid = model.face(face)
            for grid_row, row_cells in enumerate(grid):
                for grid_col, color in enumerate(row_cells):
                    x0 = origin_x + grid_col * cell
                    y0 = origin_y + grid_row * cell
                    fill = STICKER_BGR[color] if color else _DARK
                    cv2.rectangle(frame, (x0, y0), (x0 + cell, y0 + cell), fill, -1)
                    cv2.rectangle(frame, (x0, y0), (x0 + cell, y0 + cell), _BG, 1)
            chip = max(10, int(cell * 0.62))
            chip_x = origin_x + cell // 2 - chip // 2
            chip_y = origin_y + cell // 2 - chip // 2
            self._blend_rect(frame, Rect(chip_x, chip_y, chip, chip), _BG, 0.72)
            self._put_text(
                frame,
                face.value,
                (origin_x + cell // 2, origin_y + cell // 2 + max(4, cell // 6)),
                max(0.32, cell / 42.0),
                _TEXT,
                anchor="center",
            )

    # -- Utilidades de dibujo ---------------------------------------------

    @staticmethod
    def _color_name(color: Color | None) -> str:
        """Nombre legible de un color, tolerante a ``None``."""
        return color.name_es if color is not None else "sin definir"

    def _panel(self, frame: np.ndarray, rect: Rect, alpha: float = 0.6) -> None:
        """Dibuja un rectángulo oscuro semitransparente."""
        self._blend_rect(frame, rect, _DARK, alpha)
        cv2.rectangle(frame, (rect.x, rect.y), (rect.x2 - 1, rect.y2 - 1), _BORDER, 1)

    @staticmethod
    def _blend_rect(
        frame: np.ndarray, rect: Rect, color: tuple[int, int, int], alpha: float
    ) -> None:
        """Mezcla un color plano con la región indicada del fotograma."""
        if rect.width <= 0 or rect.height <= 0:
            return
        region = frame[max(0, rect.y) : max(0, rect.y2), max(0, rect.x) : max(0, rect.x2)]
        if region.size == 0:
            return
        if alpha >= 1.0:
            region[:] = color
            return
        overlay = _solid(region.shape[0], region.shape[1], color)
        cv2.addWeighted(overlay, alpha, region, 1.0 - alpha, 0, dst=region)

    def _dim(self, frame: np.ndarray, alpha: float) -> None:
        """Oscurece todo el fotograma para resaltar un mensaje."""
        self._blend_rect(frame, Rect(0, 0, frame.shape[1], frame.shape[0]), _BG, alpha)

    def _progress_bar(self, frame: np.ndarray, rect: Rect, fraction: float) -> None:
        """Dibuja una barra de progreso rellena."""
        fraction = max(0.0, min(1.0, fraction))
        cv2.rectangle(frame, (rect.x, rect.y), (rect.x2, rect.y2), _DARK, -1)
        filled = int(rect.width * fraction)
        if filled > 0:
            cv2.rectangle(
                frame,
                (rect.x, rect.y),
                (rect.x + filled, rect.y2),
                _ACCENT,
                -1,
            )
        cv2.rectangle(frame, (rect.x, rect.y), (rect.x2, rect.y2), _MUTED, 1)

    def _put_text(
        self,
        frame: np.ndarray,
        text: str,
        origin: tuple[int, int],
        scale: float,
        color: tuple[int, int, int],
        *,
        thickness: int = 1,
        anchor: str = "left",
    ) -> tuple[int, int]:
        """Dibuja texto con sombra y alineación opcional.

        Args:
            frame: Fotograma destino.
            text: Texto a dibujar (se normaliza a ASCII).
            origin: Posición de la línea base.
            scale: Escala de la fuente.
            color: Color BGR del texto.
            thickness: Grosor del trazo.
            anchor: ``"left"``, ``"center"`` o ``"right"``.

        Returns:
            Tamaño ``(ancho, alto)`` del texto dibujado.
        """
        safe = to_ascii(text)
        font = cv2.FONT_HERSHEY_DUPLEX
        width, height = _text_size(safe, scale, thickness)
        x, y = origin
        if anchor == "center":
            x -= width // 2
        elif anchor == "right":
            x -= width
        cv2.putText(
            frame,
            safe,
            (x + 1, y + 1),
            font,
            scale,
            (0, 0, 0),
            thickness,
            cv2.LINE_AA,
        )
        cv2.putText(frame, safe, (x, y), font, scale, color, thickness, cv2.LINE_AA)
        return width, height

    def _draw_paragraph(
        self,
        frame: np.ndarray,
        text: str,
        origin: tuple[int, int],
        max_width: int,
        scale: float,
        color: tuple[int, int, int],
        *,
        max_lines: int = 4,
        anchor: str = "left",
    ) -> int:
        """Dibuja un párrafo ajustado al ancho disponible.

        Args:
            frame: Fotograma destino.
            text: Texto del párrafo.
            origin: Esquina superior izquierda de la primera línea.
            max_width: Ancho máximo en píxeles.
            scale: Escala de la fuente.
            color: Color BGR.
            max_lines: Número máximo de líneas.
            anchor: Alineación horizontal.

        Returns:
            Coordenada ``y`` de la línea base de la línea siguiente, para poder
            encadenar párrafos sin solaparlos.
        """
        lines = self._wrap(text, scale, max(max_width, 1), max_lines)
        line_height = max(1, round(32 * scale))
        x, y = origin
        for index, line in enumerate(lines):
            self._put_text(
                frame,
                line,
                (x, y + index * line_height),
                scale,
                color,
                anchor=anchor,
            )
        return y + len(lines) * line_height

    @staticmethod
    def _wrap(text: str, scale: float, max_width: int, max_lines: int) -> list[str]:
        """Divide un texto en líneas que caben en el ancho indicado.

        Args:
            text: Texto original.
            scale: Escala de la fuente.
            max_width: Ancho máximo en píxeles.
            max_lines: Número máximo de líneas; la última se recorta con
                puntos suspensivos.

        Returns:
            Lista de líneas listas para dibujar.
        """
        safe = to_ascii(text)
        words = safe.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            width = _text_size(candidate, scale)[0]
            if width <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and _text_size(last + "...", scale)[0] > max_width:
                last = last[:-1]
            lines[-1] = last + "..."
        return lines

    @staticmethod
    def _progress_text(view: ScanView) -> str:
        """Genera el texto de progreso de la cabecera."""
        total = len(view.scanned)
        return f"Caras escaneadas: {total}/6   |   Cara actual: {view.current_face.value}"
