"""Pruebas de extremo a extremo de la máquina de estados.

La aplicación se ejecuta sin cámara ni ventana: se le entregan fotogramas
sintéticos con la cuadrícula del detector ya pintada y acciones de teclado
abstractas. Así se recorre el flujo completo ``SCANNING -> VALIDATING ->
SOLVING -> GUIDING -> FINISHED`` y se comprueban los caminos de error.

Ejecutar con::

    pytest tests/test_application.py -v
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from src import main as main_module
from src.camera import CameraConfig, CameraError, CameraHandler, ROIConfig
from src.cube_state import SCAN_ORDER, Color, CubeModel, Face
from src.detector import ColorDetector
from src.main import Application, AppState, build_parser, main
from src.solver import RubikSolver
from src.ui_renderer import KeyAction, UIRenderer

FRAME_SHAPE = (480, 640, 3)
BACKGROUND = (80, 80, 80)

#: Colores BGR sintéticos que el detector clasifica sin ambigüedad.
STICKER_BGR = {
    Color.WHITE: (255, 255, 255),
    Color.YELLOW: (0, 255, 255),
    Color.RED: (0, 0, 255),
    Color.ORANGE: (0, 110, 255),
    Color.BLUE: (255, 0, 0),
    Color.GREEN: (0, 255, 0),
}

SOLVED_STRING = "U" * 9 + "R" * 9 + "F" * 9 + "D" * 9 + "L" * 9 + "B" * 9
SCRAMBLE = "R U R' U' F2 D"


class FakeCapture:
    """Doble de ``cv2.VideoCapture`` controlable desde las pruebas."""

    def __init__(self, frame: np.ndarray, *, available: bool = True) -> None:
        self.frame = frame
        self.available = available
        self.released = False
        self.reads = 0
        self.properties: dict[int, float] = {}

    def isOpened(self) -> bool:
        return self.available and not self.released

    def set(self, prop: int, value: float) -> bool:
        self.properties[prop] = value
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        self.reads += 1
        return True, self.frame

    def release(self) -> None:
        self.released = True


def paint_frame(colors: list[Color]) -> np.ndarray:
    """Crea un fotograma con las nueve celdas pintadas en orden de lectura."""
    frame = np.full(FRAME_SHAPE, BACKGROUND, dtype=np.uint8)
    detector = ColorDetector()
    for index, color in enumerate(colors):
        rect = detector.cell_rects(FRAME_SHAPE)[index]
        frame[rect.as_slice()] = STICKER_BGR[color]
    return frame


def model_frame(model: CubeModel, face: Face) -> np.ndarray:
    """Genera el fotograma que produce el cubo al presentar una cara."""
    grid = model.face(face)
    return paint_frame([grid[row][col] for row in range(3) for col in range(3)])


def build_application(
    frame: np.ndarray | None = None,
) -> tuple[Application, FakeCapture]:
    """Construye una aplicación con cámara simulada y sin ventana."""
    source = frame if frame is not None else paint_frame([Color.WHITE] * 9)
    capture = FakeCapture(source)
    camera = CameraHandler(
        CameraConfig(width=FRAME_SHAPE[1], height=FRAME_SHAPE[0], warmup_frames=0),
        capture_factory=lambda _index: capture,
    )
    application = Application(
        camera=camera,
        detector=ColorDetector(),
        renderer=UIRenderer(),
        solver=RubikSolver(max_depth=24),
    )
    return application, capture


def scan_cube(application: Application, model: CubeModel) -> None:
    """Escanea las seis caras de un modelo en el orden documentado."""
    assert application.state is AppState.SCANNING
    for face in SCAN_ORDER:
        assert application.current_face is face
        application.process(model_frame(model, face), KeyAction.CAPTURE)


def scramble() -> CubeModel:
    """Devuelve un cubo resoluble pero desordenado."""
    cube = CubeModel.solved()
    cube.apply_algorithm(SCRAMBLE)
    return cube


def guide(application: Application, model: CubeModel) -> None:
    """Completa el escaneo y llega hasta la pantalla de guía."""
    scan_cube(application, model)
    assert application.state is AppState.VALIDATING
    frame = model_frame(model, Face.U)
    application.process(frame, KeyAction.CAPTURE)
    assert application.state is AppState.SOLVING
    application.process(frame, KeyAction.NONE)
    assert application.state in {AppState.GUIDING, AppState.FINISHED}


class TestScanning:
    """Fase de captura de las seis caras."""

    def test_starts_empty_and_asking_for_u(self) -> None:
        application, _ = build_application()
        assert application.state is AppState.SCANNING
        assert application.current_face is Face.U
        assert application.solution is None
        assert application.report is None
        assert len(application.model.missing_faces()) == 6

    def test_each_capture_advances_the_requested_face(self) -> None:
        application, _ = build_application()
        solved = CubeModel.solved()
        for position, face in enumerate(SCAN_ORDER):
            assert application.current_face is face
            application.process(model_frame(solved, face), KeyAction.CAPTURE)
            expected_state = (
                AppState.VALIDATING if position == len(SCAN_ORDER) - 1 else AppState.SCANNING
            )
            assert application.state is expected_state

    def test_unreadable_cell_does_not_advance(self) -> None:
        application, _ = build_application()
        empty = np.full(FRAME_SHAPE, BACKGROUND, dtype=np.uint8)
        application.process(empty, KeyAction.CAPTURE)
        assert application.state is AppState.SCANNING
        assert application.current_face is Face.U
        assert len(application.model.missing_faces()) == 6

    def test_rendered_frame_keeps_the_capture_size(self) -> None:
        application, _ = build_application()
        shown = application.process(model_frame(CubeModel.solved(), Face.U), KeyAction.NONE)
        assert shown.shape == FRAME_SHAPE
        assert shown.dtype == np.uint8

    def test_reset_discards_partial_scan(self) -> None:
        application, _ = build_application()
        solved = CubeModel.solved()
        application.process(model_frame(solved, Face.U), KeyAction.CAPTURE)
        application.process(model_frame(solved, Face.L), KeyAction.CAPTURE)
        application.process(model_frame(solved, Face.L), KeyAction.RESET)
        assert application.state is AppState.SCANNING
        assert application.current_face is Face.U
        assert len(application.model.missing_faces()) == 6


class TestValidation:
    """Confirmación del desarrollo plano y rechazo de estados imposibles."""

    def test_solved_cube_is_valid(self) -> None:
        application, _ = build_application()
        scan_cube(application, CubeModel.solved())
        assert application.state is AppState.VALIDATING
        assert application.report is not None
        assert application.report.is_valid
        assert application.model.to_kociemba_string() == SOLVED_STRING

    def test_scrambled_cube_keeps_its_facelets(self) -> None:
        scrambled = scramble()
        application, _ = build_application()
        scan_cube(application, scrambled)
        assert application.report is not None and application.report.is_valid
        assert application.model.to_kociemba_string() == scrambled.to_kociemba_string()

    def test_impossible_cube_is_rejected_and_cannot_be_solved(self) -> None:
        application, _ = build_application()
        white = paint_frame([Color.WHITE] * 9)
        for _ in range(len(SCAN_ORDER)):
            application.process(white, KeyAction.CAPTURE)
        assert application.state is AppState.VALIDATING
        assert application.report is not None and not application.report.is_valid

        application.process(white, KeyAction.CAPTURE)
        assert application.state is AppState.VALIDATING
        assert application.solution is None

        application.process(white, KeyAction.RESET)
        assert application.state is AppState.SCANNING
        assert application.report is None

    def test_validation_can_be_repeated_after_a_reset(self) -> None:
        application, _ = build_application()
        scan_cube(application, CubeModel.solved())
        application.process(model_frame(CubeModel.solved(), Face.U), KeyAction.RESET)
        scan_cube(application, CubeModel.solved())
        assert application.state is AppState.VALIDATING
        assert application.report is not None and application.report.is_valid


class TestSolving:
    """Cálculo de la solución en dos fotogramas."""

    def test_solving_announces_before_computing(self) -> None:
        application, _ = build_application()
        scan_cube(application, scramble())
        application.process(paint_frame([Color.WHITE] * 9), KeyAction.CAPTURE)
        assert application.state is AppState.SOLVING
        assert application.solution is None

    def test_solved_cube_finishes_without_moves(self) -> None:
        application, _ = build_application()
        scan_cube(application, CubeModel.solved())
        frame = paint_frame([Color.WHITE] * 9)
        application.process(frame, KeyAction.CAPTURE)
        application.process(frame, KeyAction.NONE)
        assert application.state is AppState.FINISHED
        assert application.solution is not None
        assert application.solution.is_trivial
        assert application.solution.move_count == 0

    def test_scrambled_cube_is_solved_by_the_guided_sequence(self) -> None:
        scrambled = scramble()
        application, _ = build_application()
        guide(application, scrambled)
        assert application.state is AppState.GUIDING
        assert application.solution is not None
        assert application.solution.move_count > 0
        assert application.solution.notation

        cube = application.model.copy()
        for move in application.solution.moves:
            cube.apply_move(move.notation)
        assert cube.is_solved()

    def test_finished_screen_offers_a_new_scan(self) -> None:
        application, _ = build_application()
        scan_cube(application, CubeModel.solved())
        frame = paint_frame([Color.WHITE] * 9)
        application.process(frame, KeyAction.CAPTURE)
        application.process(frame, KeyAction.NONE)
        assert application.state is AppState.FINISHED
        application.process(frame, KeyAction.RESET)
        assert application.state is AppState.SCANNING
        assert application.solution is None


class TestGuiding:
    """Navegación paso a paso por la solución."""

    def test_next_and_previous_move(self) -> None:
        application, _ = build_application()
        guide(application, scramble())
        assert application.solution is not None
        assert application.guide_index == 0
        assert application.solution.move_count > 1

        frame = paint_frame([Color.WHITE] * 9)
        application.process(frame, KeyAction.NEXT)
        assert application.guide_index == 1
        application.process(frame, KeyAction.PREVIOUS)
        assert application.guide_index == 0
        application.process(frame, KeyAction.PREVIOUS)
        assert application.guide_index == 0

    def test_advancing_to_the_last_move_finishes(self) -> None:
        application, _ = build_application()
        guide(application, scramble())
        assert application.solution is not None
        frame = paint_frame([Color.WHITE] * 9)
        for _ in range(application.solution.move_count):
            application.process(frame, KeyAction.NEXT)
        assert application.state is AppState.FINISHED

    def test_reset_during_guidance_returns_to_scanning(self) -> None:
        application, _ = build_application()
        guide(application, scramble())
        application.process(paint_frame([Color.WHITE] * 9), KeyAction.RESET)
        assert application.state is AppState.SCANNING
        assert application.current_face is Face.U
        assert application.solution is None
        assert application.guide_index == 0
        assert len(application.model.missing_faces()) == 6


class TestGlobalActions:
    """Acciones válidas en cualquier estado."""

    def test_quit_stops_the_application(self) -> None:
        application, _ = build_application()
        application.process(paint_frame([Color.WHITE] * 9), KeyAction.QUIT)
        assert application.state is AppState.QUIT

    def test_mask_toggle_changes_the_renderer(self) -> None:
        application, _ = build_application()
        frame = paint_frame([Color.WHITE] * 9)
        assert application.renderer.show_mask is False
        application.process(frame, KeyAction.TOGGLE_MASK)
        assert application.renderer.show_mask is True
        application.process(frame, KeyAction.TOGGLE_MASK)
        assert application.renderer.show_mask is False

    def test_mask_view_is_rendered_without_errors(self) -> None:
        application, _ = build_application()
        application.process(paint_frame([Color.WHITE] * 9), KeyAction.TOGGLE_MASK)
        shown = application.process(paint_frame([Color.RED] * 9), KeyAction.NONE)
        assert shown.shape == FRAME_SHAPE


class TestErrorHandling:
    """Recuperación ante fallos de imagen y de cámara."""

    def test_invalid_frame_opens_the_error_screen(self) -> None:
        application, _ = build_application()
        broken = np.zeros((30, 30, 3), dtype=np.uint8)
        shown = application.process(broken, KeyAction.NONE)
        assert application.state is AppState.ERROR
        assert shown.shape == FRAME_SHAPE

    def test_reset_retries_the_camera_and_restarts(self) -> None:
        application, _ = build_application()
        application.process(np.zeros((30, 30, 3), dtype=np.uint8), KeyAction.NONE)
        assert application.state is AppState.ERROR

        shown = application.process(model_frame(CubeModel.solved(), Face.U), KeyAction.RESET)
        assert application.state is AppState.SCANNING
        assert application.current_face is Face.U
        assert shown.shape == FRAME_SHAPE

    def test_failed_reopen_keeps_the_error_screen(self) -> None:
        application, capture = build_application()
        application.process(np.zeros((30, 30, 3), dtype=np.uint8), KeyAction.NONE)
        assert application.state is AppState.ERROR

        capture.available = False
        shown = application.process(model_frame(CubeModel.solved(), Face.U), KeyAction.RESET)
        assert application.state is AppState.ERROR
        assert shown.shape == FRAME_SHAPE


class TestCommandLine:
    """Opciones de línea de comandos."""

    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.camera == 0
        assert args.width == 1280
        assert args.height == 720
        assert args.fps == 30
        assert args.max_depth == 24
        assert args.roi is None
        assert args.debug_mask is False
        assert args.probe_camera is False
        assert args.threads == 1
        assert args.backend == "auto"
        assert args.demo is False

    def test_roi_is_parsed_as_fractions(self) -> None:
        args = build_parser().parse_args(["--roi", "0.1,0.2,0.5,0.6"])
        assert isinstance(args.roi, ROIConfig)
        assert args.roi == ROIConfig(0.1, 0.2, 0.5, 0.6)

    @pytest.mark.parametrize("value", ["0.1,0.2,0.5", "a,b,c,d", "0.5,0.5,0.8,0.8"])
    def test_invalid_roi_is_rejected(self, value: str) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--roi", value])

    @pytest.mark.parametrize("depth", ["5", "9", "31"])
    def test_out_of_range_depth_returns_an_error(self, depth: str) -> None:
        assert main(["--max-depth", depth]) == 2

    def test_unknown_option_is_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--no-existe"])

    def test_camera_configuration_errors_are_reported(self) -> None:
        assert main(["--width", "0"]) == 2
        assert main(["--fps", "0"]) == 2
        assert main(["--threads", "-1"]) == 2

    def test_gui_failure_is_reported(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def explode(_self: Application) -> None:
            raise cv2.error("La funcion no esta implementada")

        monkeypatch.setattr(Application, "run", explode)
        assert main([]) == 3
        assert "interfaz grafica" in capsys.readouterr().err

    def test_probe_camera_failure_is_reported(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def explode(_config: CameraConfig) -> int:
            raise cv2.error("No se pudo abrir el dispositivo")

        monkeypatch.setattr(main_module, "probe_camera", explode)
        assert main(["--probe-camera"]) == 3
        assert "OpenCV" in capsys.readouterr().err


class TestCameraDependency:
    """Comprobaciones mínimas de la integración con la cámara."""

    def test_invalid_camera_config_raises(self) -> None:
        with pytest.raises(CameraError):
            CameraConfig(width=-1)

    def test_parser_accepts_camera_index(self) -> None:
        args = build_parser().parse_args(["--camera", "2"])
        assert args.camera == 2
