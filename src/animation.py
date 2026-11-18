"""Demostración 3D de giros con NumPy y OpenCV, sin GPU ni motor externo.

La geometría procede del modelo lógico. Solo gira la capa indicada y los
colores corresponden al estado anterior al paso, no a un cubo genérico.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from functools import lru_cache

import cv2
import numpy as np

from .cube_state import Color, CubeModel, Face, Facelet, iter_facelets
from .solver import Move

_COLORS = {
    Color.WHITE: (243, 243, 243),
    Color.YELLOW: (0, 230, 230),
    Color.RED: (40, 40, 225),
    Color.ORANGE: (0, 138, 250),
    Color.BLUE: (230, 88, 40),
    Color.GREEN: (62, 196, 62),
}
VIEW_NAMES = ("Automatico", "Frente / derecha", "Frente / izquierda", "Detras", "Desde abajo")
_VIEWS = ((6, 5, 8), (6, 5, 8), (-6, 5, 8), (-6, 5, -8), (6, -5, 8))


class TurnPlayback:
    """Reloj de una demostración repetida; nunca avanza el paso por sí solo.

    Args:
        clock: Fuente de tiempo monotónico inyectable para pruebas.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last = clock()
        self._elapsed = 0.0
        self.paused = False
        self.speed = 1.0

    def _tick(self) -> None:
        now = self._clock()
        if not self.paused:
            self._elapsed += max(0.0, now - self._last) * self.speed
        self._last = now

    def progress(self, double: bool = False) -> float:
        """Fracción suavizada del giro con pausas antes y después."""
        self._tick()
        duration = 2.4 if double else 1.6
        position = self._elapsed % (duration + 1.3)
        fraction = min(1.0, max(0.0, (position - 0.5) / duration))
        return fraction * fraction * (3.0 - 2.0 * fraction)

    def restart(self) -> None:
        """Repite desde el inicio y reanuda la demostración."""
        self._last = self._clock()
        self._elapsed = 0.0
        self.paused = False

    def toggle_pause(self) -> None:
        """Congela o reanuda sin saltos de posición."""
        self._tick()
        self.paused = not self.paused

    def cycle_speed(self) -> None:
        """Alterna velocidad normal, rápida y lenta conservando la posición."""
        self._tick()
        speeds = (0.5, 1.0, 1.5)
        self.speed = speeds[(speeds.index(self.speed) + 1) % len(speeds)]


@lru_cache(maxsize=1)
def _geometry() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Precalcula los 54 centros, normales y polígonos de las pegatinas."""
    stickers = tuple(iter_facelets())
    positions = np.array([sticker.position for sticker in stickers], dtype=np.float64)
    normals = np.array([sticker.normal for sticker in stickers], dtype=np.float64)
    polygons = []
    for index, sticker in enumerate(stickers):
        origin = np.array(Facelet(sticker.face, 0, 0).position)
        right = np.array(Facelet(sticker.face, 0, 1).position) - origin
        down = np.array(Facelet(sticker.face, 1, 0).position) - origin
        center = positions[index] + normals[index] * 0.5
        polygons.append(
            [
                center + 0.45 * (x * right + y * down)
                for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))
            ]
        )
    vertices = np.asarray(polygons)
    for array in (positions, normals, vertices):
        array.flags.writeable = False
    return positions, normals, vertices


def turn_pose(move: Move, progress: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve centros, normales y vértices al girar una capa.

    Args:
        move: Movimiento físico, horario visto desde fuera de su cara.
        progress: Fracción en [0, 1].

    Returns:
        Tres matrices nuevas; nunca modifica la geometría compartida.
    """
    positions, normals, vertices = (array.copy() for array in _geometry())
    axis = np.array(Facelet(move.face, 1, 1).normal, dtype=np.float64)
    moving = positions @ axis > 0.5
    quarters = -1 if move.is_prime else move.quarter_turns
    angle = -quarters * math.pi / 2 * min(1.0, max(0.0, progress))
    c, s = math.cos(angle), math.sin(angle)
    x, y, z = axis
    cross = np.array(((0, -z, y), (z, 0, -x), (-y, x, 0)))
    rotation = c * np.eye(3) + s * cross + (1 - c) * np.outer(axis, axis)
    for array in (positions, normals, vertices):
        array[moving] = array[moving] @ rotation.T
    return positions, normals, vertices


@lru_cache(maxsize=128)
def _project(move: Move, step: int, view: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Proyecta la geometría cuantizada, reutilizable entre fotogramas."""
    _, normals, vertices = turn_pose(move, step / 60)
    camera = np.asarray(_VIEWS[view], dtype=np.float64)
    camera /= np.linalg.norm(camera)
    right = np.cross((0, 1, 0), camera)
    right /= np.linalg.norm(right)
    up = np.cross(camera, right)
    basis = np.stack((right, -up, camera))
    projected = vertices @ basis.T
    visible = normals @ camera > 0.01
    order = np.argsort(projected[:, :, 2].mean(axis=1))
    return projected, visible, order


def effective_view(face: Face, view: int) -> int:
    """Elige una vista que permita ver la capa posterior, izquierda o inferior."""
    if view:
        return view % len(VIEW_NAMES)
    return {Face.L: 2, Face.B: 3, Face.D: 4}.get(face, 1)


class CubeAnimator:
    """Rasterizador de polígonos con caché del último fotograma."""

    def __init__(self) -> None:
        self._key: tuple[object, ...] | None = None
        self._image: np.ndarray | None = None

    def render(
        self, cube: CubeModel, move: Move, progress: float, width: int, height: int, view: int = 0
    ) -> np.ndarray:
        """Dibuja el estado anterior al paso con la capa activa resaltada.

        Returns:
            Imagen BGR de solo lectura; el llamante puede copiarla al lienzo.
        """
        colors = tuple(cube.face(s.face)[s.row][s.col] for s in iter_facelets())
        step = round(min(1.0, max(0.0, progress)) * 60)
        viewpoint = effective_view(move.face, view)
        key = (colors, move, step, width, height, viewpoint)
        if key == self._key and self._image is not None:
            return self._image
        image = np.full((height, width, 3), (43, 32, 25), dtype=np.uint8)
        projected, visible, order = _project(move, step, viewpoint)
        scale = min(width, height) / 5.4
        polygons = np.rint(projected[:, :, :2] * scale + (width / 2, height / 2)).astype(np.int32)
        positions, _, _ = _geometry()
        axis = np.asarray(Facelet(move.face, 1, 1).normal)
        moving = positions @ axis > 0.5
        for index in order:
            if not visible[index]:
                continue
            color = _COLORS.get(colors[index], (90, 90, 90))
            cv2.fillConvexPoly(image, polygons[index], color, cv2.LINE_AA)
            border = (193, 232, 91) if moving[index] else (18, 18, 18)
            cv2.polylines(image, [polygons[index]], True, border, 2, cv2.LINE_AA)
            if index % 9 == 4:
                center = np.rint(polygons[index].mean(axis=0)).astype(int)
                label = tuple(Face)[index // 9].value
                font_scale = max(0.35, min(width, height) / 650)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, font_scale, 1)
                at = (int(center[0] - tw // 2), int(center[1] + th // 2))
                cv2.putText(
                    image,
                    label,
                    at,
                    cv2.FONT_HERSHEY_DUPLEX,
                    font_scale,
                    (15, 15, 15),
                    2,
                    cv2.LINE_AA,
                )
        image.flags.writeable = False
        self._key, self._image = key, image
        return image
