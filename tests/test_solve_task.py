"""El solver corre en un proceso independiente y se puede cancelar."""

from __future__ import annotations

import time

import pytest
from src.cube_state import CubeModel
from src.solve_task import SolveTask
from src.solver import SolverError

from tests.test_application import SCRAMBLE


def scramble_string() -> str:
    cube = CubeModel.solved()
    cube.apply_algorithm(SCRAMBLE)
    return cube.to_kociemba_string()


def test_solve_task_returns_a_solution_in_a_separate_process() -> None:
    task = SolveTask(scramble_string(), 24, timeout=60)
    try:
        solution = None
        deadline = time.monotonic() + 60
        while solution is None and time.monotonic() < deadline:
            solution = task.poll()
            if solution is None:
                time.sleep(0.02)
        assert solution is not None
        assert solution.move_count > 0
    finally:
        task.close()
    cube = CubeModel.from_kociemba_string(scramble_string())
    cube.apply_algorithm(solution.notation)
    assert cube.is_solved()


def test_solve_task_rejects_an_invalid_cube() -> None:
    task = SolveTask("U" * 54, 24, timeout=60)
    try:
        with pytest.raises(SolverError):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                task.poll()
                time.sleep(0.02)
            raise AssertionError("El motor no respondio")
    finally:
        task.close()


def test_close_is_idempotent() -> None:
    task = SolveTask(scramble_string(), 24, timeout=60)
    task.close()
    task.close()
    with pytest.raises(SolverError):
        task.poll()
