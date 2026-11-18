"""Pruebas de la interfaz de dibujo sin ventana de OpenCV.

Los errores de maquetación (escalas de fuente, ajuste de líneas, paneles) no
siempre rompen la ejecución: pueden dejar texto invisible o solapado. Estas
pruebas dibujan todas las pantallas sobre fotogramas sintéticos en varias
resoluciones para detectar excepciones y regresiones básicas de composición.

Ejecutar con::

    pytest tests/test_ui_renderer.py -v
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from src.cube_state import Color, CubeModel, Face
from src.detector import ColorDetector
from src.solver import RubikSolver, Solution
from src.ui_renderer import (
    GuidingView,
    KeyAction,
    MessageLevel,
    ScanView,
    UIRenderer,
    ValidationView,
    parse_key,
    to_ascii,
)

RESOLUTIONS = [(480, 640), (720, 1280), (1080, 1920)]
SCRAMBLE = "R U R' U' F2 D"


def blank(shape: tuple[int, int]) -> np.ndarray:
    """Fotograma uniforme con el tamaño indicado."""
    return np.full((shape[0], shape[1], 3), 60, dtype=np.uint8)


def scan_view(shape: tuple[int, int]) -> ScanView:
    """Vista de escaneo con las nueve celdas ya analizadas."""
    detector = ColorDetector()
    frame = blank(shape)
    for rect in detector.cell_rects(frame.shape):
        frame[rect.as_slice()] = (0, 255, 0)
    return ScanView(
        current_face=Face.F,
        instruction=(
            "Cara F (frontal). Coloca la cara FRONTAL mirando a la camara, "
            "con la cara superior hacia arriba"
        ),
        cells=detector.cell_rects(frame.shape),
        samples=detector.sample_face(frame),
        scanned=((Face.U, Color.WHITE), (Face.L, Color.RED)),
        message="Cara U guardada. Ahora muestra la cara F",
        level=MessageLevel.OK,
        mask=detector.build_color_mask(frame),
    )


def guiding_view(index: int = 0) -> GuidingView:
    """Vista de guía para un cubo desordenado."""
    cube = CubeModel.solved()
    cube.apply_algorithm(SCRAMBLE)
    solution = RubikSolver().solve(cube)
    return GuidingView(
        solution=solution,
        index=index,
        up_color=Color.WHITE,
        front_color=Color.GREEN,
    )


class TestKeyParsing:
    """Traducción de códigos de tecla a acciones."""

    @pytest.mark.parametrize("key", [32])
    def test_space_captures(self, key: int) -> None:
        assert parse_key(key) is KeyAction.CAPTURE

    @pytest.mark.parametrize("key", [13, 10, ord("n"), ord("N"), 65363, 2555904])
    def test_next_keys(self, key: int) -> None:
        assert parse_key(key) is KeyAction.NEXT

    @pytest.mark.parametrize("key", [ord("b"), ord("B"), 65361, 2424832])
    def test_previous_keys(self, key: int) -> None:
        assert parse_key(key) is KeyAction.PREVIOUS

    @pytest.mark.parametrize("key", [ord("r"), ord("R")])
    def test_reset_keys(self, key: int) -> None:
        assert parse_key(key) is KeyAction.RESET

    @pytest.mark.parametrize("key", [ord("q"), ord("Q"), 27])
    def test_quit_keys(self, key: int) -> None:
        assert parse_key(key) is KeyAction.QUIT

    @pytest.mark.parametrize("key", [ord("m"), ord("M")])
    def test_mask_keys(self, key: int) -> None:
        assert parse_key(key) is KeyAction.TOGGLE_MASK

    def test_unknown_and_absent_keys(self) -> None:
        assert parse_key(-1) is KeyAction.NONE
        assert parse_key(ord("z")) is KeyAction.NONE


class TestAscii:
    """Normalización de texto para las fuentes Hershey."""

    def test_accents_are_removed(self) -> None:
        assert to_ascii("Manten la cara superior") == "Manten la cara superior"
        assert to_ascii("Gíralo hacia atrás") == "Giralo hacia atras"

    def test_symbols_are_replaced(self) -> None:
        assert to_ascii("90°") == "90 grados"
        assert to_ascii("A → B") == "A -> B"
        assert to_ascii("A ← B") == "A <- B"

    def test_text_without_symbols_is_unchanged(self) -> None:
        text = "R U R' U'"
        assert to_ascii(text) == text


class TestTextLayout:
    """Ajuste de líneas y escalas tipográficas."""

    def test_wrapped_lines_fit_the_width(self) -> None:
        text = "Gira la cara derecha 90 grados en sentido horario y luego continua"
        lines = UIRenderer._wrap(text, 0.8, 320, 10)
        assert len(lines) > 1
        for line in lines:
            width = cv2.getTextSize(line, cv2.FONT_HERSHEY_DUPLEX, 0.8, 1)[0][0]
            assert width <= 320 or len(line.split()) == 1

    def test_long_text_is_truncated_with_ellipsis(self) -> None:
        lines = UIRenderer._wrap("palabra " * 60, 0.7, 260, 2)
        assert len(lines) == 2
        assert lines[-1].endswith("...")

    def test_single_word_wider_than_the_panel_is_kept(self) -> None:
        assert UIRenderer._wrap("X" * 200, 1.0, 30, 1)[0]

    def test_empty_text_produces_one_empty_line(self) -> None:
        assert UIRenderer._wrap("", 0.5, 100, 2) == [""]


class TestScreens:
    """Cada pantalla se dibuja sin errores en varias resoluciones."""

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_scanning_screen(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer()
        frame = blank(shape)
        shown = renderer.draw_scanning(frame, scan_view(shape))
        assert shown is frame
        assert shown.shape == (shape[0], shape[1], 3)
        assert shown.any()

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    @pytest.mark.parametrize("face", [Face.U, Face.L, Face.B])
    @pytest.mark.parametrize("progress", [0.0, 0.5, 1.0])
    def test_scanning_shows_rotation_guide(
        self, shape: tuple[int, int], face: Face, progress: float
    ) -> None:
        view = scan_view(shape)
        guided = ScanView(
            current_face=face,
            instruction=view.instruction,
            cells=view.cells,
            samples=view.samples,
            scanned=view.scanned,
            message=view.message,
            level=view.level,
            mask=view.mask,
            orientation_face=face,
            orientation_progress=progress,
            previous_face=Face.F,
        )
        shown = UIRenderer().draw_scanning(blank(shape), guided)
        assert shown.shape == (shape[0], shape[1], 3)
        assert shown.any()

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_scanning_with_mask(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer(show_mask=True)
        shown = renderer.draw_scanning(blank(shape), scan_view(shape))
        assert shown.shape == (shape[0], shape[1], 3)

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_validation_screen(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer()
        model = CubeModel.solved()
        view = ValidationView(
            model=model,
            report=model.validate(),
            up_face=Face.U,
            front_face=Face.F,
        )
        shown = renderer.draw_validation(blank(shape), view)
        assert shown.shape == (shape[0], shape[1], 3)

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_invalid_validation_screen(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer()
        model = CubeModel()
        view = ValidationView(
            model=model,
            report=model.validate(),
            up_face=Face.U,
            front_face=Face.F,
        )
        shown = renderer.draw_validation(blank(shape), view)
        assert shown.shape == (shape[0], shape[1], 3)

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_solving_screen(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer()
        shown = renderer.draw_solving(blank(shape), Color.WHITE, Color.GREEN)
        assert shown.shape == (shape[0], shape[1], 3)

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_guiding_screen_first_and_last(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer()
        view = guiding_view()
        assert view.solution.move_count > 1
        for index in (0, view.solution.move_count - 1):
            shown = renderer.draw_guiding(
                blank(shape),
                GuidingView(
                    solution=view.solution,
                    index=index,
                    up_color=view.up_color,
                    front_color=view.front_color,
                ),
            )
            assert shown.shape == (shape[0], shape[1], 3)

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_finished_screen_with_and_without_moves(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer()
        solution = guiding_view().solution
        for candidate in (solution, Solution("", (), 0.0)):
            shown = renderer.draw_finished(blank(shape), candidate)
            assert shown.shape == (shape[0], shape[1], 3)

    @pytest.mark.parametrize("shape", RESOLUTIONS)
    def test_error_screen(self, shape: tuple[int, int]) -> None:
        renderer = UIRenderer()
        shown = renderer.draw_error(
            blank(shape),
            "No se puede analizar la imagen",
            "El fotograma es demasiado pequeno. Comprueba la camara y reintenta",
        )
        assert shown.shape == (shape[0], shape[1], 3)

    def test_mask_toggle_is_reflected(self) -> None:
        renderer = UIRenderer()
        assert renderer.show_mask is False
        renderer.show_mask = True
        assert renderer.show_mask is True

    def test_window_name_is_configurable(self) -> None:
        renderer = UIRenderer("Otra ventana")
        assert renderer.window_name == "Otra ventana"
