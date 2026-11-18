"""La demostración debe coincidir con el modelo físico en los 18 giros."""

from __future__ import annotations

import numpy as np
import pytest
from src.animation import (
    CubeAnimator,
    TurnPlayback,
    effective_view,
    scan_pose,
    turn_pose,
)
from src.cube_state import CubeModel, Face, iter_facelets
from src.solver import Move


@pytest.mark.parametrize("face", list(Face))
@pytest.mark.parametrize("suffix,quarters", [("", 1), ("2", 2), ("'", 3)])
def test_animation_endpoint_matches_logical_move(face: Face, suffix: str, quarters: int) -> None:
    cube = CubeModel.solved()
    cube.apply_algorithm("R U F2 L D B' R2")
    after = cube.copy()
    after.apply_move(face.value + suffix)
    lookup = {(s.position, s.normal): s for s in iter_facelets()}
    positions, normals, _ = turn_pose(Move(face.value + suffix, face, quarters), 1.0)
    destinations = set()
    for original, position, normal in zip(iter_facelets(), positions, normals, strict=True):
        key = tuple(np.rint(position).astype(int)), tuple(np.rint(normal).astype(int))
        destination = lookup[key]
        destinations.add(destination)
        assert (
            cube.face(original.face)[original.row][original.col]
            == (after.face(destination.face)[destination.row][destination.col])
        )
    assert len(destinations) == 54


def test_partial_turn_moves_only_requested_layer() -> None:
    move = Move("F", Face.F, 1)
    before, normals, _ = turn_pose(move, 0.0)
    during, turned_normals, _ = turn_pose(move, 0.5)
    stationary = before[:, 2] < 0.5
    np.testing.assert_array_equal(before[stationary], during[stationary])
    np.testing.assert_array_equal(normals[stationary], turned_normals[stationary])
    assert not np.array_equal(before, during)


def test_pause_speed_and_replay_are_time_based() -> None:
    now = [0.0]
    clock = TurnPlayback(lambda: now[0])
    assert clock.progress() == 0.0
    now[0] = 1.3
    assert clock.progress() == pytest.approx(0.5)
    clock.toggle_pause()
    now[0] = 20.0
    assert clock.progress() == pytest.approx(0.5)
    clock.cycle_speed()
    assert clock.speed == 1.5
    clock.toggle_pause()
    assert clock.progress() == pytest.approx(0.5)
    clock.restart()
    assert clock.progress() == 0
    assert not clock.paused


@pytest.mark.parametrize("face,view", [(Face.B, 3), (Face.L, 2), (Face.D, 4)])
def test_hidden_faces_get_visible_camera_angles(face: Face, view: int) -> None:
    assert effective_view(face, 0) == view


@pytest.mark.parametrize("face", list(Face))
def test_scan_orientation_ends_with_requested_face_toward_camera(face: Face) -> None:
    _, normals, _ = scan_pose(face, 1.0)
    front = normals @ np.array((0, 0, 1))
    assert np.count_nonzero(front > 0.99) == 9
    _, middle, _ = scan_pose(face, 0.5)
    if face not in (Face.F,):
        assert not np.allclose(middle, normals)


def test_scan_orientation_render_is_cached_and_colourful() -> None:
    renderer = CubeAnimator()
    first = renderer.render_orientation(Face.L, 0.5, 200, 140)
    assert renderer.render_orientation(Face.L, 0.5, 200, 140) is first
    assert first.shape == (140, 200, 3)
    assert first.max() > first.min()
    assert not first.flags.writeable


def test_renderer_reuses_paused_image_without_mutating_cube() -> None:
    cube = CubeModel.solved()
    original = cube.to_kociemba_string()
    renderer = CubeAnimator()
    move = Move("R'", Face.R, 3)
    first = renderer.render(cube, move, 0.3, 320, 260)
    assert renderer.render(cube, move, 0.3, 320, 260) is first
    assert not first.flags.writeable
    assert not np.array_equal(first, renderer.render(cube, move, 0.7, 320, 260))
    assert cube.to_kociemba_string() == original
