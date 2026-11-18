"""Controles de guía, clics, estados esperados y modo sin cámara."""

from __future__ import annotations

import cv2
import pytest
from src.cube_state import Color
from src.main import AppState, build_parser
from src.ui_renderer import KeyAction, parse_key

from tests.test_application import build_application, guide, paint_frame, scramble


@pytest.mark.parametrize(
    "key,action",
    [
        ("a", KeyAction.REPLAY),
        ("p", KeyAction.PAUSE),
        ("s", KeyAction.SPEED),
        ("v", KeyAction.VIEW),
    ],
)
def test_new_shortcuts_and_uppercase(key: str, action: KeyAction) -> None:
    assert parse_key(ord(key)) is action
    assert parse_key(ord(key.upper())) is action


def test_controls_do_not_confirm_moves_and_snapshots_follow_solution() -> None:
    app, _ = build_application()
    guide(app, scramble())
    frame = paint_frame([Color.WHITE] * 9)
    assert app._guide_states[-1].is_solved()
    for action in (KeyAction.PAUSE, KeyAction.REPLAY, KeyAction.SPEED, KeyAction.VIEW):
        app.process(frame, action)
        assert app.guide_index == 0
    expected = app.model.copy()
    expected.apply_move(app.solution.moves[0].notation)
    app.process(frame, KeyAction.NEXT)
    assert app._guide_states[app.guide_index].to_kociemba_string() == expected.to_kociemba_string()
    app.process(frame, KeyAction.PREVIOUS)
    assert app._guide_states[app.guide_index].to_kociemba_string() == app.model.to_kociemba_string()


def test_click_uses_current_buttons_and_ignores_double_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = build_application()
    frame = paint_frame([Color.WHITE] * 9)
    app.process(frame)
    x, y = next(
        rect.center for rect, action in app.renderer._buttons if action is KeyAction.CAPTURE
    )
    monkeypatch.setattr("src.main.time.monotonic", lambda: 5.0)
    app._on_mouse(cv2.EVENT_LBUTTONUP, x, y, 0, None)
    assert app._mouse_action is KeyAction.CAPTURE
    app._mouse_action = KeyAction.NONE
    app._on_mouse(cv2.EVENT_LBUTTONUP, x, y, 0, None)
    assert app._mouse_action is KeyAction.NONE
    assert app.renderer.hit_test(-1, -1) is KeyAction.NONE


def test_can_review_last_step_after_finishing() -> None:
    app, _ = build_application()
    guide(app, scramble())
    frame = paint_frame([Color.WHITE] * 9)
    for _ in app.solution.moves:
        app.process(frame, KeyAction.NEXT)
    app.process(frame, KeyAction.PREVIOUS)
    assert app.state is AppState.GUIDING
    assert app.guide_index == app.solution.move_count - 1


def test_demo_reset_keeps_a_valid_cube_and_cli_accepts_backends() -> None:
    app, _ = build_application()
    app.demo = True
    app.load_demo()
    app.process(paint_frame([Color.WHITE] * 9), KeyAction.RESET)
    assert app.state is AppState.VALIDATING
    assert app.model.validate().is_valid
    for backend in ("auto", "dshow", "msmf", "v4l2"):
        args = build_parser().parse_args(["--demo", "--backend", backend])
        assert args.demo and args.backend == backend
