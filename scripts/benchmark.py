"""Mide procesamiento sintético sin cámara: python -m scripts.benchmark."""

from __future__ import annotations

import argparse
import statistics
import time

import cv2
import numpy as np
from src.camera import CameraConfig, CameraHandler
from src.detector import ColorDetector
from src.main import Application
from src.solver import RubikSolver
from src.ui_renderer import UIRenderer


def main() -> None:
    """Imprime mediana y percentil 95; no mide captura ni FPS de la webcam."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    if args.frames < 10:
        parser.error("--frames debe ser al menos 10")
    cv2.setNumThreads(1)
    print(f"OpenCV {cv2.__version__}; un hilo; {args.frames} muestras; sin E/S")
    for height, width in ((480, 640), (720, 1280), (1080, 1920)):
        detector = ColorDetector()
        frame = np.random.default_rng(42).integers(0, 256, (height, width, 3), dtype=np.uint8)
        app = Application(CameraHandler(CameraConfig()), detector, UIRenderer(), RubikSolver())
        for name in ("detector", "escaneo"):
            timings = []
            for index in range(args.frames + 10):
                source = frame.copy()
                start = time.perf_counter()
                if name == "detector":
                    detector.sample_face(source)
                else:
                    app.process(source)
                elapsed = (time.perf_counter() - start) * 1000
                if index >= 10:
                    timings.append(elapsed)
            print(
                f"{width}x{height} {name:8s}: "
                f"mediana {statistics.median(timings):.2f} ms; "
                f"p95 {float(np.percentile(timings, 95)):.2f} ms"
            )


if __name__ == "__main__":
    main()
