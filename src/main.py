"""Punto de entrada y máquina de estados de RubikVisionSolver.

La aplicación se organiza como una máquina de estados explícita:

``SCANNING``
    Se pide al usuario una cara por vez en el orden ``U, L, F, R, B, D``.
    Cada pulsación de ESPACIO captura la cuadrícula y avanza.
``VALIDATING``
    Se comprueba que el cubo escaneado sea físicamente resoluble y se muestra
    el desarrollo plano para que el usuario lo confirme.
``SOLVING``
    Se calcula la solución con Kociemba (en dos fotogramas, para poder mostrar
    el aviso de espera antes del cálculo).
``GUIDING``
    Se muestran los movimientos uno a uno con instrucciones en español.
``FINISHED``
    El cubo está resuelto; se puede empezar de nuevo con ``R``.

Examples:
    Ejecutar la aplicación con la cámara predeterminada::

        python -m src.main
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from collections.abc import Sequence
from enum import Enum
from typing import Final

import cv2
import numpy as np

from .camera import CameraConfig, CameraError, CameraHandler, ROIConfig
from .cube_state import SCAN_ORDER, CubeModel, Face, ValidationReport
from .detector import ColorDetector, DetectorError, FaceletSample
from .solver import RubikSolver, Solution, SolverError
from .ui_renderer import (
    GuidingView,
    KeyAction,
    MessageLevel,
    ScanView,
    UIRenderer,
    ValidationView,
    parse_key,
)

__all__ = ["AppState", "Application", "build_parser", "main"]


class AppState(Enum):
    """Estados del ciclo de vida de la aplicación."""

    SCANNING = "scanning"
    VALIDATING = "validating"
    SOLVING = "solving"
    GUIDING = "guiding"
    FINISHED = "finished"
    ERROR = "error"
    QUIT = "quit"


#: Orden de escaneo recomendado (mantiene la cara superior siempre arriba).
SCAN_SEQUENCE: Final[tuple[Face, ...]] = SCAN_ORDER

#: Instrucción física exacta para colocar cada cara frente a la cámara.
SCAN_INSTRUCTIONS: Final[dict[Face, str]] = {
    Face.U: (
        "Inclina el cubo hacia ti hasta que la cara SUPERIOR mire a la cámara; "
        "la cara frontal quedará abajo"
    ),
    Face.L: (
        "Gira el cubo sobre su eje vertical hasta que la cara IZQUIERDA mire a la "
        "cámara, manteniendo la cara superior hacia arriba"
    ),
    Face.F: (
        "Coloca la cara FRONTAL mirando a la cámara, con la cara superior hacia "
        "arriba"
    ),
    Face.R: (
        "Gira el cubo sobre su eje vertical hasta que la cara DERECHA mire a la "
        "cámara, manteniendo la cara superior hacia arriba"
    ),
    Face.B: (
        "Gira el cubo 180 grados hasta que la cara TRASERA mire a la cámara, "
        "manteniendo la cara superior hacia arriba"
    ),
    Face.D: (
        "Inclina el cubo hacia atrás (alejándolo de ti) hasta que la cara "
        "INFERIOR mire a la cámara; la cara frontal quedará arriba"
    ),
}

#: Límite de seguridad para el cálculo (movimientos de la primera fase).
MAX_DEPTH_LIMIT: Final[int] = 30


class Application:
    """Orquesta cámara, detector, modelo, solucionador e interfaz.

    La clase no crea la ventana ni abre la cámara en su constructor: recibe las
    dependencias ya construidas, lo que permite probar la máquina de estados con
    fotogramas sintéticos y sin hardware.

    Attributes:
        state: Estado actual de la máquina.
        model: Cubo que se está escaneando.
        solution: Solución calculada, si existe.
        report: Informe de validación, si se ha generado.
    """

    def __init__(
        self,
        camera: CameraHandler,
        detector: ColorDetector,
        renderer: UIRenderer,
        solver: RubikSolver,
    ) -> None:
        """Inicializa la aplicación.

        Args:
            camera: Fuente de vídeo.
            detector: Detector de colores.
            renderer: Motor de dibujo.
            solver: Solucionador de Kociemba.
        """
        self.camera = camera
        self.detector = detector
        self.renderer = renderer
        self.solver = solver

        self.state = AppState.SCANNING
        self.model = CubeModel()
        self.solution: Solution | None = None
        self.report: ValidationReport | None = None

        self._scan_index = 0
        self._samples: tuple[FaceletSample, ...] = ()
        self._message = ""
        self._level = MessageLevel.INFO
        self._illumination_hint = ""
        self._error_title = ""
        self._error_detail = ""
        self._solve_announced = False
        self._guide_index = 0
        self._last_frame: np.ndarray | None = None

    # -- Propiedades -------------------------------------------------------

    @property
    def current_face(self) -> Face:
        """Cara que se está pidiendo al usuario durante el escaneo."""
        return SCAN_SEQUENCE[min(self._scan_index, len(SCAN_SEQUENCE) - 1)]

    @property
    def guide_index(self) -> int:
        """Movimiento de la solución que se está mostrando en la guía."""
        return self._guide_index

    # -- Bucle principal ---------------------------------------------------

    def run(self) -> None:
        """Ejecuta el bucle de captura hasta que el usuario sale.

        Raises:
            CameraError: Si la cámara no se puede abrir al inicio.
            cv2.error: Si el entorno gráfico no permite abrir o actualizar la ventana.
        """
        pending = KeyAction.NONE
        try:
            self.camera.open()
            cv2.namedWindow(self.renderer.window_name, cv2.WINDOW_NORMAL)
            while self.state is not AppState.QUIT:
                started = time.perf_counter()
                if self.state is AppState.ERROR:
                    frame = (
                        self._last_frame
                        if self._last_frame is not None
                        else self._blank_frame()
                    )
                else:
                    try:
                        frame = self.camera.read()
                    except CameraError as error:
                        self._enter_error("Fallo de camara", str(error))
                        continue
                    self._last_frame = frame

                shown = self.process(frame, pending)
                cv2.imshow(self.renderer.window_name, shown)
                elapsed_ms = (time.perf_counter() - started) * 1000
                delay = max(1, round(self.camera.config.frame_interval_ms - elapsed_ms))
                pending = parse_key(cv2.waitKeyEx(delay))
                # Algunos backends (p. ej. Wayland nativo) no ofrecen esta propiedad.
                with contextlib.suppress(cv2.error):
                    if cv2.getWindowProperty(self.renderer.window_name, cv2.WND_PROP_VISIBLE) == 0:
                        self.state = AppState.QUIT
        finally:
            self.camera.release()
            with contextlib.suppress(cv2.error):
                cv2.destroyAllWindows()

    def process(self, frame: np.ndarray, action: KeyAction = KeyAction.NONE) -> np.ndarray:
        """Procesa un fotograma y una acción de teclado.

        Este método concentra la lógica de la máquina de estados y no depende de
        la ventana de OpenCV, por lo que puede probarse de forma automática.

        Args:
            frame: Fotograma BGR capturado.
            action: Acción del usuario para este fotograma.

        Returns:
            Copia con la interfaz dibujada; el fotograma original no se modifica.
        """
        if self.state is AppState.SCANNING:
            self._analyse(frame)
        elif self.state is AppState.ERROR and self.detector.is_valid_frame(frame):
            self._last_frame = frame

        self._handle_key(action)
        self._advance_solving()
        # El renderizador dibuja in situ; conserva la captura original para
        # reintentos, pantallas de error y llamadas repetidas desde pruebas.
        output = frame.copy() if self.detector.is_valid_frame(frame) else self._blank_frame()
        return self._render(output)

    # -- Análisis ----------------------------------------------------------

    def _analyse(self, frame: np.ndarray) -> None:
        """Analiza la cuadrícula del fotograma actual."""
        try:
            self._samples = self.detector.sample_face(frame)
            illumination = self.detector.measure_illumination(frame)
        except DetectorError as error:
            self._enter_error("No se puede analizar la imagen", str(error))
            return
        self._illumination_hint = "" if illumination.is_ok else illumination.advice

    # -- Acciones ----------------------------------------------------------

    def _handle_key(self, action: KeyAction) -> None:
        """Aplica la acción del usuario según el estado actual."""
        if action is KeyAction.NONE:
            return
        if action is KeyAction.QUIT:
            self.state = AppState.QUIT
            return
        if action is KeyAction.TOGGLE_MASK:
            self.renderer.show_mask = not self.renderer.show_mask
            return

        if self.state is AppState.SCANNING:
            if action is KeyAction.CAPTURE:
                self._capture_face()
            elif action is KeyAction.RESET:
                self._restart_scan(keep_message=False)
        elif self.state is AppState.VALIDATING:
            if (
                action in (KeyAction.NEXT, KeyAction.CAPTURE)
                and self.report is not None
                and self.report.is_valid
            ):
                self._enter_solving()
            elif action is KeyAction.RESET:
                self._restart_scan(keep_message=False)
        elif self.state is AppState.GUIDING:
            if action in (KeyAction.NEXT, KeyAction.CAPTURE):
                self._next_move()
            elif action is KeyAction.PREVIOUS:
                self._previous_move()
            elif action is KeyAction.RESET:
                self._restart_scan(keep_message=False)
        elif self.state is AppState.FINISHED and action is KeyAction.RESET:
            self._restart_scan(keep_message=False)
        elif self.state is AppState.ERROR and action is KeyAction.RESET:
            self._retry_camera()

    def _capture_face(self) -> None:
        """Guarda la cara actual y avanza en la secuencia de escaneo."""
        if not self._samples:
            self._set_message("Todavia no hay lectura de la camara", MessageLevel.WARNING)
            return

        colors = [sample.color for sample in self._samples]
        if any(color is None for color in colors):
            missing = [str(index + 1) for index, color in enumerate(colors) if color is None]
            self._set_message(
                "No se pudo leer la celda "
                + ", ".join(missing)
                + ". Ajusta la luz o el encuadre y vuelve a intentarlo",
                MessageLevel.WARNING,
            )
            return

        face = self.current_face
        palette = [color for color in colors if color is not None]
        self.model.set_face_colors(face, palette)
        self._scan_index += 1
        if self._scan_index >= len(SCAN_SEQUENCE):
            self._start_validation()
        else:
            center = self.model.center(face)
            color_name = center.name_es if center is not None else "desconocido"
            self._set_message(
                f"Cara {face.value} guardada (centro {color_name}). "
                f"Ahora muestra la cara {self.current_face.value}",
                MessageLevel.OK,
            )

    def _start_validation(self) -> None:
        """Valida el cubo completo y pasa a la pantalla de confirmación."""
        self.report = self.model.validate()
        self.state = AppState.VALIDATING
        if self.report.is_valid:
            self._set_message("Cubo completo. Revisa el esquema y pulsa ESPACIO", MessageLevel.OK)
        else:
            self._set_message(
                "Hay problemas en el escaneo. Pulsa R para repetirlo",
                MessageLevel.ERROR,
            )

    def _enter_solving(self) -> None:
        """Prepara el cálculo de la solución."""
        self.state = AppState.SOLVING
        self.solution = None
        self._solve_announced = False
        self._set_message("", MessageLevel.INFO)

    def _advance_solving(self) -> None:
        """Ejecuta el cálculo en el segundo fotograma del estado ``SOLVING``."""
        if self.state is not AppState.SOLVING or self.solution is not None:
            return
        if not self._solve_announced:
            self._solve_announced = True
            return

        started = time.perf_counter()
        try:
            solution = self.solver.solve(self.model)
        except SolverError as error:
            self.report = self.model.validate()
            self.state = AppState.VALIDATING
            self._set_message(f"No se pudo calcular la solucion: {error}", MessageLevel.ERROR)
            return

        self.solution = solution
        if solution.is_trivial:
            self.state = AppState.FINISHED
            print("El cubo ya estaba resuelto.")
        else:
            self.state = AppState.GUIDING
            self._set_message("", MessageLevel.INFO)
            elapsed = (time.perf_counter() - started) * 1000.0
            print(
                f"Solucion ({solution.move_count} movimientos, {elapsed:.0f} ms): "
                f"{solution.notation}"
            )
            for line in _describe(solution):
                print(f"  {line}")

    def _next_move(self) -> None:
        """Avanza al siguiente movimiento de la solución."""
        if self.solution is None:
            return
        if self.solution.move_count == 0:
            self.state = AppState.FINISHED
            return
        if self.solution.moves and self._guide_index >= self.solution.move_count - 1:
            self.state = AppState.FINISHED
            print("Secuencia completada: el cubo deberia estar resuelto.")
            return
        self._guide_index = min(self._guide_index + 1, self.solution.move_count - 1)

    def _previous_move(self) -> None:
        """Retrocede un movimiento en la guía."""
        self._guide_index = max(0, self._guide_index - 1)

    def _restart_scan(self, keep_message: bool) -> None:
        """Reinicia el escaneo desde cero."""
        self.model = CubeModel()
        self.report = None
        self.solution = None
        self._scan_index = 0
        self._samples = ()
        self.state = AppState.SCANNING
        self._solve_announced = False
        self._guide_index = 0
        if not keep_message:
            self._set_message(
                "Escaneo reiniciado. Muestra la cara U a la camara",
                MessageLevel.INFO,
            )

    def _retry_camera(self) -> None:
        """Intenta reabrir la cámara tras un error."""
        try:
            self.camera.release()
            self.camera.open()
        except CameraError as error:
            self._enter_error("Fallo de camara", str(error))
            return
        self._restart_scan(keep_message=False)

    def _enter_error(self, title: str, detail: str) -> None:
        """Muestra una pantalla de error bloqueante."""
        self.state = AppState.ERROR
        self._error_title = title
        self._error_detail = detail
        print(f"Error: {title}. {detail}", file=sys.stderr)

    def _set_message(self, message: str, level: MessageLevel) -> None:
        """Actualiza el mensaje mostrado en pantalla."""
        self._message = message
        self._level = level

    # -- Renderizado -------------------------------------------------------

    def _render(self, frame: np.ndarray) -> np.ndarray:
        """Dibuja la pantalla correspondiente al estado actual."""
        if not self.detector.is_valid_frame(frame):
            # Tras recuperarse de un error el fotograma recibido puede ser el
            # que provocó el fallo; se sustituye por uno neutro para poder
            # seguir mostrando la interfaz.
            frame = self._blank_frame()

        if self.state is AppState.SCANNING:
            message = self._illumination_hint or self._message
            level = MessageLevel.WARNING if self._illumination_hint else self._level
            scan_view = ScanView(
                current_face=self.current_face,
                instruction=(
                    f"Cara {self.current_face.value} "
                    f"({self.current_face.name_es}). "
                    f"{SCAN_INSTRUCTIONS[self.current_face]}"
                ),
                cells=self.detector.cell_rects(frame.shape),
                samples=self._samples,
                scanned=tuple(
                    (face, center)
                    for face in SCAN_SEQUENCE
                    if (center := self.model.center(face)) is not None
                ),
                message=message,
                level=level,
                mask=self.detector.build_color_mask(frame) if self.renderer.show_mask else None,
            )
            return self.renderer.draw_scanning(frame, scan_view)

        if self.state is AppState.VALIDATING:
            report = self.report or self.model.validate()
            validation_view = ValidationView(
                model=self.model,
                report=report,
                up_face=Face.U,
                front_face=Face.F,
                message=self._message if self._level is MessageLevel.ERROR else "",
            )
            return self.renderer.draw_validation(frame, validation_view)

        if self.state is AppState.SOLVING:
            return self.renderer.draw_solving(
                frame, self.model.center(Face.U), self.model.center(Face.F)
            )

        if self.state is AppState.GUIDING and self.solution is not None:
            guiding_view = GuidingView(
                solution=self.solution,
                index=self._guide_index,
                up_color=self.model.center(Face.U),
                front_color=self.model.center(Face.F),
            )
            return self.renderer.draw_guiding(frame, guiding_view)

        if self.state is AppState.FINISHED:
            return self.renderer.draw_finished(frame, self.solution or Solution("", (), 0.0))

        if self.state is AppState.ERROR:
            return self.renderer.draw_error(frame, self._error_title, self._error_detail)

        return frame

    def _blank_frame(self) -> np.ndarray:
        """Devuelve un fotograma negro del tamaño configurado."""
        config = self.camera.config
        return np.zeros((config.height, config.width, 3), dtype=np.uint8)


def _describe(solution: Solution) -> Sequence[str]:
    """Genera la lista de instrucciones en español de una solución."""
    return tuple(
        f"{index}. {move.notation}: {move.description}"
        for index, move in enumerate(solution.moves, start=1)
    )


# ---------------------------------------------------------------------------
# Interfaz de línea de comandos
# ---------------------------------------------------------------------------


def _parse_roi(value: str) -> ROIConfig:
    """Convierte ``"x,y,w,h"`` en una región de interés.

    Args:
        value: Cuatro fracciones separadas por comas.

    Returns:
        Configuración de ROI.

    Raises:
        argparse.ArgumentTypeError: Si el formato o los valores no son válidos.
    """
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("La ROI debe tener el formato x,y,w,h")
    try:
        x, y, width, height = (float(part) for part in parts)
        return ROIConfig(x, y, width, height)
    except (ValueError, CameraError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_parser() -> argparse.ArgumentParser:
    """Construye el analizador de argumentos de la aplicación.

    Returns:
        Parser configurado con todas las opciones de la herramienta.
    """
    parser = argparse.ArgumentParser(
        prog="rubikvision",
        description="Escanea un cubo de Rubik con la camara y guia su resolucion",
    )
    parser.add_argument(
        "--camera", type=int, default=0, help="indice del dispositivo (por defecto 0)"
    )
    parser.add_argument("--width", type=int, default=1280, help="ancho solicitado (px)")
    parser.add_argument("--height", type=int, default=720, help="alto solicitado (px)")
    parser.add_argument("--fps", type=int, default=30, help="fotogramas por segundo solicitados")
    parser.add_argument(
        "--roi",
        type=_parse_roi,
        default=None,
        metavar="X,Y,W,H",
        help="region de interes en fracciones, por ejemplo 0.1,0.1,0.8,0.8",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=24,
        help="profundidad de busqueda de Kociemba (20-24 recomendado)",
    )
    parser.add_argument(
        "--debug-mask",
        action="store_true",
        help="muestra la mascara HSV para calibrar los colores",
    )
    parser.add_argument(
        "--probe-camera",
        action="store_true",
        help="abre la camara, muestra sus datos y sale",
    )
    return parser


def probe_camera(config: CameraConfig) -> int:
    """Comprueba que la cámara funciona e imprime su resolución real.

    Args:
        config: Configuración usada para abrir la cámara.

    Returns:
        Código de salida del proceso.
    """
    with CameraHandler(config) as camera:
        frame = camera.read()
        height, width = frame.shape[:2]
        print(f"Camara {config.index} operativa: {width}x{height} px")
        print(f"Intervalo de fotogramas: {config.frame_interval_ms} ms")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la aplicación.

    Args:
        argv: Argumentos de línea de comandos; por defecto ``sys.argv[1:]``.

    Returns:
        Código de salida del proceso.
    """
    args = build_parser().parse_args(argv)
    if not 10 <= args.max_depth <= MAX_DEPTH_LIMIT:
        print(f"Error: --max-depth debe estar entre 10 y {MAX_DEPTH_LIMIT}", file=sys.stderr)
        return 2

    try:
        config = CameraConfig(
            index=args.camera,
            width=args.width,
            height=args.height,
            fps=args.fps,
            roi=args.roi or ROIConfig(),
        )
        if args.probe_camera:
            return probe_camera(config)
        solver = RubikSolver(max_depth=args.max_depth)
        detector = ColorDetector()
        renderer = UIRenderer(show_mask=args.debug_mask)
        camera = CameraHandler(config)
        application = Application(camera, detector, renderer, solver)
    except (CameraError, SolverError) as error:
        print(f"Error de configuracion: {error}", file=sys.stderr)
        return 2
    except cv2.error as error:
        print(f"Error de OpenCV: {error}", file=sys.stderr)
        return 3

    try:
        application.run()
    except CameraError as error:
        print(f"Error de camara: {error}", file=sys.stderr)
        return 2
    except cv2.error as error:
        print(
            "Error de interfaz grafica: no se pudo crear o actualizar la ventana.\n"
            "Asegurate de ejecutar con un entorno de escritorio y de tener "
            "instalado opencv-python (no la variante headless).\n"
            f"Detalle: {error}",
            file=sys.stderr,
        )
        return 3
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
