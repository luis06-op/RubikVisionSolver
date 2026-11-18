"""Pruebas del modelo de estado y del validador de cubos.

Cubren la representación interna, la serialización a la cadena de Kociemba, la
aplicación de movimientos y los tres invariantes del grupo del cubo (giro de
esquinas, volteo de aristas y paridad). Los estados imposibles se construyen
partiendo de un cubo resuelto y alterando piezas concretas.

Ejecutar con::

    pytest tests/test_cube_state.py -v
"""

from __future__ import annotations

import random

import pytest
from src.cube_state import (
    _CORNERS,
    _EDGES,
    SCAN_ORDER,
    Color,
    CubeModel,
    CubeStateError,
    Face,
    ValidationReport,
)

SOLVED_STRING = "U" * 9 + "R" * 9 + "F" * 9 + "D" * 9 + "L" * 9 + "B" * 9


def scramble(sequence: str) -> CubeModel:
    """Crea un cubo resuelto y le aplica una secuencia."""
    cube = CubeModel.solved()
    cube.apply_algorithm(sequence)
    return cube


def swap_stickers(cube: CubeModel, first, second) -> None:
    """Intercambia las pegatinas de dos posiciones concretas."""
    a_face, a_row, a_col = first
    b_face, b_row, b_col = second
    left = cube.face(a_face)[a_row][a_col]
    right = cube.face(b_face)[b_row][b_col]
    cube._stickers[a_face][a_row][a_col] = right
    cube._stickers[b_face][b_row][b_col] = left


class TestSolvedCube:
    """Propiedades del cubo resuelto."""

    def test_solved_cube_is_complete_and_solved(self) -> None:
        cube = CubeModel.solved()
        assert cube.is_complete()
        assert cube.is_solved()
        assert cube.missing_faces() == ()
        assert len(cube.completed_faces()) == 6

    def test_solved_cube_string(self) -> None:
        assert CubeModel.solved().to_kociemba_string() == SOLVED_STRING

    def test_solved_cube_is_valid(self) -> None:
        report = CubeModel.solved().validate()
        assert isinstance(report, ValidationReport)
        assert report.is_valid
        assert report.messages == ()

    def test_serialization_uses_centers_not_color_names(self) -> None:
        cube = CubeModel.solved()
        scheme = {
            Face.U: Color.GREEN,
            Face.R: Color.ORANGE,
            Face.F: Color.WHITE,
            Face.D: Color.BLUE,
            Face.L: Color.RED,
            Face.B: Color.YELLOW,
        }
        for face, color in scheme.items():
            cube.set_face(face, [[color] * 3 for _ in range(3)])
        assert cube.to_kociemba_string() == SOLVED_STRING

    def test_empty_cube_reports_missing_faces(self) -> None:
        cube = CubeModel()
        report = cube.validate()
        assert not report.is_valid
        assert "Faltan caras" in report.summary()


class TestConstruction:
    """Construcción y mutación controlada del modelo."""

    def test_from_kociemba_string_round_trip(self) -> None:
        cube = CubeModel.from_kociemba_string(SOLVED_STRING)
        assert cube.to_kociemba_string() == SOLVED_STRING

    @pytest.mark.parametrize("value", ["U" * 53, "U" * 55, "X" * 54, ""])
    def test_invalid_strings_are_rejected(self, value: str) -> None:
        with pytest.raises(CubeStateError):
            CubeModel.from_kociemba_string(value)

    def test_set_face_requires_three_by_three(self) -> None:
        cube = CubeModel()
        with pytest.raises(CubeStateError):
            cube.set_face(Face.U, [[Color.WHITE] * 3] * 2)

    def test_set_face_rejects_non_colors(self) -> None:
        cube = CubeModel()
        with pytest.raises(CubeStateError):
            cube.set_face(Face.U, [["blanco"] * 3 for _ in range(3)])  # type: ignore[list-item]

    def test_set_face_colors_requires_nine(self) -> None:
        cube = CubeModel()
        with pytest.raises(CubeStateError):
            cube.set_face_colors(Face.U, [Color.WHITE] * 8)

    def test_copy_is_independent(self) -> None:
        original = CubeModel.solved()
        clone = original.copy()
        clone.apply_move("R")
        assert original.is_solved()
        assert not clone.is_solved()

    def test_incomplete_cube_cannot_be_serialized(self) -> None:
        cube = CubeModel()
        with pytest.raises(CubeStateError):
            cube.to_kociemba_string()

    def test_duplicate_centers_are_rejected(self) -> None:
        cube = CubeModel.solved()
        cube.set_face(Face.U, [[Color.RED] * 3 for _ in range(3)])
        with pytest.raises(CubeStateError):
            cube.color_to_face_map()

    def test_copy_semantics_of_face(self) -> None:
        cube = CubeModel.solved()
        grid = cube.face(Face.U)
        assert len(grid) == 3 and len(grid[0]) == 3


class TestMoves:
    """Aplicación de movimientos y consistencia del grupo."""

    @pytest.mark.parametrize("move", ["U", "D", "R", "L", "F", "B"])
    def test_quarter_turn_four_times_is_identity(self, move: str) -> None:
        cube = CubeModel.solved()
        for _ in range(4):
            cube.apply_move(move)
        assert cube.is_solved()

    @pytest.mark.parametrize("move", ["U'", "D'", "R'", "L'", "F'", "B'"])
    def test_prime_is_inverse_of_quarter_turn(self, move: str) -> None:
        cube = CubeModel.solved()
        cube.apply_move(move[0])
        cube.apply_move(move)
        assert cube.is_solved()

    def test_double_move_equals_two_quarter_turns(self) -> None:
        single = CubeModel.solved()
        single.apply_move("R")
        single.apply_move("R")
        double = CubeModel.solved()
        double.apply_move("R2")
        assert single.to_kociemba_string() == double.to_kociemba_string()

    def test_sexy_move_six_times_is_identity(self) -> None:
        cube = CubeModel.solved()
        for _ in range(6):
            cube.apply_algorithm("R U R' U'")
        assert cube.is_solved()

    def test_known_scramble_matches_reference_string(self) -> None:
        cube = scramble("R U R' U'")
        assert cube.to_kociemba_string() == (
            "UULUUFUUFRRUBRRURRFFDFFUFFFDDRDDDDDDBLLLLLLLLBRRBBBBBB"
        )

    def test_single_face_move_is_a_valid_state(self) -> None:
        assert scramble("F").validate().is_valid

    def test_algorithm_with_invalid_token_raises(self) -> None:
        with pytest.raises(CubeStateError):
            CubeModel.solved().apply_algorithm("R X")

    def test_lowercase_and_smart_quotes_are_accepted(self) -> None:
        a = scramble("R U'")
        b = CubeModel.solved()
        b.apply_move("r")
        b.apply_move("u\u2019")  # comilla tipográfica
        assert a.to_kociemba_string() == b.to_kociemba_string()

    @pytest.mark.parametrize("seed", range(5))
    def test_random_scrambles_are_valid(self, seed: int) -> None:
        generator = random.Random(seed)
        cube = CubeModel.solved()
        previous = ""
        for _ in range(25):
            face = generator.choice([f for f in "URFDLB" if f != previous])
            previous = face
            cube.apply_move(face + generator.choice(["", "'", "2"]))
        assert not cube.is_solved()
        assert cube.validate().is_valid


class TestValidator:
    """Rechazo de estados físicamente imposibles."""

    def test_twisted_corner_is_rejected(self) -> None:
        cube = CubeModel.solved()
        slot = _CORNERS[0]
        values = [cube.face(fl.face)[fl.row][fl.col] for fl in slot.facelets]
        for index, facelet in enumerate(slot.facelets):
            cube._stickers[facelet.face][facelet.row][facelet.col] = values[(index + 1) % 3]
        report = cube.validate()
        assert not report.is_valid
        assert any(issue.code == "orientacion" for issue in report.issues)

    def test_flipped_edge_is_rejected(self) -> None:
        cube = CubeModel.solved()
        first, second = _EDGES[0].facelets
        swap_stickers(
            cube,
            (first.face, first.row, first.col),
            (second.face, second.row, second.col),
        )
        report = cube.validate()
        assert not report.is_valid
        assert any(issue.code == "orientacion" for issue in report.issues)

    def test_swapped_edges_are_rejected_by_parity(self) -> None:
        cube = CubeModel.solved()
        for first, second in zip(_EDGES[0].facelets, _EDGES[1].facelets, strict=True):
            swap_stickers(
                cube,
                (first.face, first.row, first.col),
                (second.face, second.row, second.col),
            )
        report = cube.validate()
        assert not report.is_valid
        assert any(issue.code == "permutacion" for issue in report.issues)

    def test_swapped_corners_are_rejected_by_parity(self) -> None:
        cube = CubeModel.solved()
        for first, second in zip(_CORNERS[0].facelets, _CORNERS[1].facelets, strict=True):
            swap_stickers(
                cube,
                (first.face, first.row, first.col),
                (second.face, second.row, second.col),
            )
        report = cube.validate()
        assert not report.is_valid
        assert any(issue.code == "permutacion" for issue in report.issues)

    def test_wrong_color_count_is_rejected(self) -> None:
        cube = CubeModel.solved()
        cube._stickers[Face.U][0][0] = Color.RED
        report = cube.validate()
        assert not report.is_valid
        assert any(issue.code == "conteo" for issue in report.issues)

    def test_swapped_stickers_break_the_cubie_structure(self) -> None:
        cube = scramble("R U F' L2 D B'")
        grid = cube.face(Face.U)
        positions = [(row, col) for row in range(3) for col in range(3)]
        first = positions[0]
        second = next(
            (row, col)
            for row, col in positions
            if grid[row][col] is not grid[first[0]][first[1]]
        )
        swap_stickers(
            cube,
            (Face.U, first[0], first[1]),
            (Face.U, second[0], second[1]),
        )
        report = cube.validate()
        assert not report.is_valid
        assert any(
            issue.code in {"esquina", "arista", "duplicado", "orientacion", "permutacion"}
            for issue in report.issues
        )

    def test_report_summary_limits_messages(self) -> None:
        cube = CubeModel()
        report = cube.validate()
        assert report.summary(limit=1).count(";") == 0


class TestScanProtocol:
    """Verifica que el orden de escaneo sea el documentado."""

    def test_scan_order(self) -> None:
        assert SCAN_ORDER == (Face.U, Face.L, Face.F, Face.R, Face.B, Face.D)

    def test_center_lookup(self) -> None:
        cube = CubeModel.solved()
        assert cube.center(Face.U) is Color.WHITE
        assert cube.center(Face.D) is Color.YELLOW
