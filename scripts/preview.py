"""Exporta las pantallas reales con un cubo sintético, sin abrir la cámara."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
from src.animation import VIEW_NAMES
from src.camera import CameraConfig, CameraHandler
from src.cube_state import SCAN_ORDER, Color, CubeModel, Face
from src.detector import ColorDetector
from src.main import Application, AppState
from src.solver import RubikSolver
from src.ui_renderer import GuidingView, KeyAction, UIRenderer

COLORS = {
    Color.WHITE: (245, 245, 245),
    Color.YELLOW: (0, 235, 255),
    Color.RED: (40, 40, 210),
    Color.ORANGE: (0, 110, 250),
    Color.BLUE: (200, 80, 0),
    Color.GREEN: (60, 170, 40),
}


def main() -> None:
    """Genera PNG reproducibles para documentación y revisión visual."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/assets"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    if args.width < 480 or args.height < 360:
        parser.error("Usa al menos 480 x 360 píxeles")
    args.output.mkdir(parents=True, exist_ok=True)
    shape = (args.height, args.width, 3)
    cube = CubeModel.solved()
    cube.apply_algorithm("R U R' U' F2 D B L2")
    detector = ColorDetector()
    renderer = UIRenderer()
    app = Application(
        CameraHandler(CameraConfig(width=args.width, height=args.height)),
        detector,
        renderer,
        RubikSolver(),
    )

    def source(face: Face) -> np.ndarray:
        image = np.full(shape, (62, 53, 45), dtype=np.uint8)
        for index, rect in enumerate(detector.cell_rects(shape)):
            inner = rect.inset(0.04)
            color = cube.face(face)[index // 3][index % 3]
            image[inner.as_slice()] = COLORS[color]
        return image

    def save(name: str, image: np.ndarray) -> None:
        target = args.output / f"{name}.png"
        if not cv2.imwrite(str(target), image):
            raise OSError(f"No se pudo escribir {target}")
        print(target)

    for face in SCAN_ORDER[:3]:
        app.process(source(face), KeyAction.CAPTURE)
    save("scanning", app.process(source(Face.R)))
    for index, progress in enumerate((0.0, 0.34, 0.67, 1.0)):
        app._scan_face_started = time.monotonic() - progress * 1.6
        save(f"scan_rotate_{index}", app.process(source(Face.R)))
    app._scan_face_started = time.monotonic()
    save("mask", app.process(source(Face.R), KeyAction.TOGGLE_MASK))
    app.process(source(Face.R), KeyAction.TOGGLE_MASK)
    for face in SCAN_ORDER[3:]:
        app.process(source(face), KeyAction.CAPTURE)
    save("validation", app.process(source(Face.F)))
    save("solving", app.process(source(Face.F), KeyAction.CAPTURE))
    save("guiding", app.process(source(Face.F)))
    if app.state is not AppState.GUIDING or app.solution is None:
        raise RuntimeError("El cubo sintético no llegó a la guía")

    view = GuidingView(
        solution=app.solution,
        index=0,
        up_color=app.model.center(Face.U),
        front_color=app.model.center(Face.F),
        cube=app._guide_states[0],
        progress=0.0,
    )
    for frame_number, progress in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
        view = GuidingView(
            solution=view.solution,
            index=0,
            up_color=view.up_color,
            front_color=view.front_color,
            cube=view.cube,
            progress=progress,
        )
        save(f"anim_{frame_number}", renderer.draw_guiding(source(Face.F).copy(), view))
    view = GuidingView(
        solution=view.solution,
        index=0,
        up_color=view.up_color,
        front_color=view.front_color,
        cube=view.cube,
        progress=0.5,
        viewpoint=3,
    )
    save("view_back", renderer.draw_guiding(source(Face.F).copy(), view))
    assert VIEW_NAMES[view.viewpoint] == "Detras"

    for _ in app.solution.moves:
        image = app.process(source(Face.F), KeyAction.NEXT)
    save("finished", image)
    save(
        "error",
        renderer.draw_error(
            source(Face.F),
            "No se detecta la camara",
            "Comprueba la conexion y cierra otras aplicaciones que esten usando el dispositivo.",
        ),
    )


if __name__ == "__main__":
    main()
