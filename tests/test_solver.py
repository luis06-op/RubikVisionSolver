"""Pruebas del adaptador de Kociemba y de la traducción al español.

Las pruebas de integración se marcan como omitidas si la librería ``kociemba``
no está instalada (por ejemplo, en un entorno mínimo de integración continua);
el resto de la suite no depende de ella.

Ejecutar con::

    pytest tests/test_solver.py -v
"""

from __future__ import annotations

import random

import pytest
from src.cube_state import _CORNERS, CubeModel, Face
from src.solver import (
    InvalidCubeError,
    Move,
    RubikSolver,
    Solution,
    SolverError,
    SolverUnavailableError,
    describe_sequence,
)

try:  # La suite de integración se omite si el backend no está disponible.
    import kociemba
except ImportError:  # pragma: no cover - depende del entorno
    kociemba = None

requires_kociemba = pytest.mark.skipif(
    kociemba is None, reason="La libreria kociemba no esta instalada"
)


def scramble(sequence: str) -> CubeModel:
    """Aplica una secuencia a un cubo resuelto."""
    cube = CubeModel.solved()
    cube.apply_algorithm(sequence)
    return cube


class TestMoveTranslation:
    """Traducción de la notación de Singmaster al español."""

    def test_clockwise_move(self) -> None:
        move = Move("R", Face.R, 1)
        assert "derecha" in move.description
        assert "horario" in move.description
        assert "antihorario" not in move.description
        assert move.is_prime is False
        assert move.is_double is False

    def test_counter_clockwise_move(self) -> None:
        move = Move("U'", Face.U, 3)
        assert "superior" in move.description
        assert "antihorario" in move.description
        assert move.is_prime is True

    def test_double_move(self) -> None:
        move = Move("F2", Face.F, 2)
        assert "180" in move.description
        assert move.is_double is True

    @pytest.mark.parametrize(
        ("face", "name"),
        [
            (Face.U, "superior"),
            (Face.D, "inferior"),
            (Face.L, "izquierda"),
            (Face.R, "derecha"),
            (Face.F, "frontal"),
            (Face.B, "trasera"),
        ],
    )
    def test_all_faces_are_named(self, face: Face, name: str) -> None:
        assert name in Move(face.value, face, 1).description

    def test_hint_mentions_the_face(self) -> None:
        assert "derecha" in Move("R", Face.R, 1).hint

    def test_describe_sequence_is_numbered(self) -> None:
        lines = describe_sequence((Move("R", Face.R, 1), Move("U'", Face.U, 3)))
        assert lines[0].startswith("1. R:")
        assert lines[1].startswith("2. U':")


class TestSolutionModel:
    """Modelo de datos de la solución."""

    def test_move_count_and_trivial(self) -> None:
        assert Solution("", (), 0.0).is_trivial
        assert Solution("R", (Move("R", Face.R, 1),), 1.5).move_count == 1


class TestSolverValidation:
    """Validación de entradas del solucionador."""

    def test_max_depth_out_of_range(self) -> None:
        with pytest.raises(SolverError):
            RubikSolver(max_depth=4)
        with pytest.raises(SolverError):
            RubikSolver(max_depth=40)

    def test_incomplete_cube_is_rejected(self) -> None:
        with pytest.raises(InvalidCubeError):
            RubikSolver().solve(CubeModel())

    def test_twisted_corner_is_rejected(self) -> None:
        cube = CubeModel.solved()
        slot = _CORNERS[0]
        values = [cube.face(fl.face)[fl.row][fl.col] for fl in slot.facelets]
        for index, facelet in enumerate(slot.facelets):
            cube._stickers[facelet.face][facelet.row][facelet.col] = values[(index + 1) % 3]
        with pytest.raises(InvalidCubeError) as error:
            RubikSolver().solve(cube)
        assert error.value.report is not None
        assert not error.value.report.is_valid

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "U" * 53,
            "U" * 54,
            "U" * 50 + "XXXX",
            "R" * 9 + "U" * 45,
        ],
    )
    def test_invalid_strings_are_rejected(self, value: str) -> None:
        with pytest.raises(InvalidCubeError):
            RubikSolver().solve(value)

    def test_already_solved_cube_returns_empty_solution(self) -> None:
        solution = RubikSolver().solve(CubeModel.solved())
        assert solution.is_trivial
        assert solution.notation == ""
        assert solution.moves == ()

    def test_solved_string_returns_empty_solution(self) -> None:
        solved = CubeModel.solved().to_kociemba_string()
        assert RubikSolver().solve(solved).is_trivial


class TestBackendAdapter:
    """Comportamiento frente a respuestas del backend."""

    def test_backend_tokens_are_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        solver = RubikSolver()
        monkeypatch.setattr(solver, "_run_backend", lambda _: "R U2 F'")
        solution = solver.solve(scramble("R U F'"))
        assert [move.notation for move in solution.moves] == ["R", "U2", "F'"]
        assert [move.quarter_turns for move in solution.moves] == [1, 2, 3]

    def test_invalid_backend_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        solver = RubikSolver()
        monkeypatch.setattr(solver, "_run_backend", lambda _: "R X")
        with pytest.raises(SolverError):
            solver.solve(scramble("R"))

    def test_unavailable_backend_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "kociemba", None)
        with pytest.raises(SolverUnavailableError):
            RubikSolver().solve(scramble("R"))


@requires_kociemba
class TestSolverIntegration:
    """Integración real con la librería ``kociemba``."""

    @pytest.mark.parametrize("seed", range(4))
    def test_solution_solves_random_scramble(self, seed: int) -> None:
        generator = random.Random(seed)
        sequence = []
        previous = ""
        for _ in range(20):
            face = generator.choice([f for f in "URFDLB" if f != previous])
            previous = face
            sequence.append(face + generator.choice(["", "'", "2"]))
        cube = scramble(" ".join(sequence))

        solution = RubikSolver().solve(cube)
        assert not solution.is_trivial
        assert solution.move_count <= 30
        cube.apply_algorithm(solution.notation)
        assert cube.is_solved()

    def test_solution_notation_matches_moves(self) -> None:
        cube = scramble("F R U' R' U' R U R' F'")
        solution = RubikSolver().solve(cube)
        assert solution.notation.split() == [move.notation for move in solution.moves]

    def test_kociemba_rejects_unsolvable_state(self) -> None:
        """La librería usa ValueError; el adaptador lo convierte en dominio."""
        from src.solver import InvalidCubeError as DomainError

        cube = CubeModel.solved()
        slot = _CORNERS[0]
        values = [cube.face(fl.face)[fl.row][fl.col] for fl in slot.facelets]
        for index, facelet in enumerate(slot.facelets):
            cube._stickers[facelet.face][facelet.row][facelet.col] = values[(index + 1) % 3]
        with pytest.raises(DomainError):
            RubikSolver().solve(cube.to_kociemba_string())
