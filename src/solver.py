"""Adaptador del algoritmo de Kociemba y traducción de movimientos al español.

El módulo aísla la dependencia de la librería ``kociemba`` detrás de una API
propia tipada. Si el *backend* no está instalado, la aplicación puede seguir
funcionando hasta el momento de resolver y mostrar un error claro en lugar de
fallar al arrancar.

Examples:
    >>> from src.cube_state import CubeModel
    >>> from src.solver import RubikSolver
    >>> solver = RubikSolver()
    >>> solucion = solver.solve(CubeModel.solved())
    >>> solucion.is_trivial
    True
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from .cube_state import CubeModel, CubeStateError, Face, ValidationReport

__all__ = [
    "InvalidCubeError",
    "Move",
    "RubikSolver",
    "Solution",
    "SolverError",
    "SolverUnavailableError",
]


class SolverError(RuntimeError):
    """Error genérico durante el cálculo de la solución."""


class SolverUnavailableError(SolverError):
    """La librería ``kociemba`` no está instalada o no puede importarse."""


class InvalidCubeError(SolverError):
    """El estado del cubo no es resoluble.

    Attributes:
        report: Informe de validación asociado, si se disponía de él.
    """

    def __init__(self, message: str, report: ValidationReport | None = None) -> None:
        """Inicializa el error.

        Args:
            message: Descripción legible del problema.
            report: Informe de validación opcional con el detalle.
        """
        super().__init__(message)
        self.report = report


#: Nombres de las caras tal y como aparecen en las instrucciones.
_FACE_NAMES: Final[dict[Face, str]] = {
    Face.U: "superior",
    Face.R: "derecha",
    Face.F: "frontal",
    Face.D: "inferior",
    Face.L: "izquierda",
    Face.B: "trasera",
}

#: Descripción del giro según el sufijo de la notación.
_TURN_DESCRIPTION: Final[dict[str, str]] = {
    "": "90 grados en sentido horario",
    "'": "90 grados en sentido antihorario",
    "2": "180 grados (media vuelta)",
}

_MOVE_TOKEN: Final[re.Pattern[str]] = re.compile(r"^[URFDLB](?:['2])?$")


@dataclass(frozen=True)
class Move:
    """Movimiento individual de la solución.

    Attributes:
        notation: Notación de Singmaster, por ejemplo ``"R'"``.
        face: Cara afectada.
        quarter_turns: Cuartos de giro en sentido horario (1, 2 o 3).
    """

    notation: str
    face: Face
    quarter_turns: int

    @property
    def is_prime(self) -> bool:
        """Indica si el movimiento es de 90 grados antihorarios."""
        return self.quarter_turns == 3

    @property
    def is_double(self) -> bool:
        """Indica si el movimiento es de 180 grados."""
        return self.quarter_turns == 2

    @property
    def face_name(self) -> str:
        """Nombre de la cara en español."""
        return _FACE_NAMES[self.face]

    @property
    def description(self) -> str:
        """Instrucción completa para el usuario.

        Returns:
            Frase en español con la cara, el ángulo y el sentido del giro.
        """
        suffix = "" if self.quarter_turns == 1 else "'" if self.quarter_turns == 3 else "2"
        return (
            f"Gira la cara {self.face_name} "
            f"{_TURN_DESCRIPTION[suffix]} "
            f"(mirando de frente la cara {self.face_name})"
        )

    @property
    def hint(self) -> str:
        """Recordatorio corto de la cara que se debe girar."""
        return f"Cara {self.face_name}"


@dataclass(frozen=True)
class Solution:
    """Solución completa calculada por el algoritmo.

    Attributes:
        notation: Secuencia completa, por ejemplo ``"R U' F2"``.
        moves: Lista tipada de movimientos.
        elapsed_ms: Tiempo de cálculo en milisegundos.
    """

    notation: str
    moves: tuple[Move, ...]
    elapsed_ms: float

    @property
    def move_count(self) -> int:
        """Número de movimientos de la solución."""
        return len(self.moves)

    @property
    def is_trivial(self) -> bool:
        """Indica si el cubo ya estaba resuelto."""
        return not self.moves


class RubikSolver:
    """Calcula soluciones mediante el algoritmo de dos fases de Kociemba.

    Attributes:
        max_depth: Profundidad máxima de búsqueda de la primera fase. Valores
            altos exploran soluciones más cortas a costa de tiempo.
    """

    def __init__(self, max_depth: int = 24) -> None:
        """Configura el solucionador.

        Args:
            max_depth: Profundidad máxima de búsqueda (20-24 recomendado).

        Raises:
            SolverError: Si ``max_depth`` está fuera del rango admitido.
        """
        if not 10 <= max_depth <= 30:
            raise SolverError(
                "max_depth debe estar entre 10 y 30 para que la busqueda sea viable"
            )
        self.max_depth = max_depth

    def solve(self, cube: CubeModel | str) -> Solution:
        """Resuelve un cubo.

        Args:
            cube: Modelo validable o cadena de 54 *facelets*.

        Returns:
            Solución con los movimientos en notación y en español.

        Raises:
            InvalidCubeError: Si el cubo no es físicamente resoluble.
            SolverUnavailableError: Si la librería ``kociemba`` no está
                instalada.
            SolverError: Si el *backend* devuelve una respuesta inesperada.
        """
        cubestring, already_solved = self._prepare(cube)
        if already_solved:
            return Solution(notation="", moves=(), elapsed_ms=0.0)

        started = time.perf_counter()
        raw = self._run_backend(cubestring)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        moves = self._parse(raw)
        return Solution(
            notation=" ".join(move.notation for move in moves),
            moves=moves,
            elapsed_ms=elapsed_ms,
        )

    def _prepare(self, cube: CubeModel | str) -> tuple[str, bool]:
        """Normaliza la entrada y detecta el cubo ya resuelto.

        Args:
            cube: Modelo o cadena de *facelets*.

        Returns:
            Pareja ``(cadena, ya_resuelto)``.

        Raises:
            InvalidCubeError: Si el estado no es válido.
        """
        if isinstance(cube, CubeModel):
            report = cube.validate()
            if not report.is_valid:
                raise InvalidCubeError(report.summary(), report)
            try:
                cubestring = cube.to_kociemba_string()
            except CubeStateError as error:  # pragma: no cover - cubo ya validado
                raise InvalidCubeError(str(error)) from error
            return cubestring, cube.is_solved()

        normalized = cube.strip().upper().replace("\u2019", "'")
        if len(normalized) != 54:
            raise InvalidCubeError(
                "La cadena del cubo debe tener 54 caracteres URFDLB"
            )
        if set(normalized) - set("URFDLB"):
            raise InvalidCubeError("La cadena del cubo contiene caracteres no validos")
        centers = tuple(normalized[face * 9 + 4] for face in range(6))
        if centers != ("U", "R", "F", "D", "L", "B"):
            raise InvalidCubeError(
                "Los centros de la cadena no son U, R, F, D, L y B en ese orden"
            )
        return normalized, all(
            normalized[face * 9 : face * 9 + 9] == normalized[face * 9 + 4] * 9
            for face in range(6)
        )

    def _run_backend(self, cubestring: str) -> str:
        """Invoca la librería ``kociemba`` con manejo defensivo de errores.

        Args:
            cubestring: Cadena de 54 *facelets* validada.

        Returns:
            Respuesta cruda del *backend*.

        Raises:
            SolverUnavailableError: Si la dependencia no está instalada.
            InvalidCubeError: Si el *backend* considera el cubo imposible.
            SolverError: Ante cualquier otro fallo del *backend*.
        """
        try:
            import kociemba  # Importación diferida: la app arranca sin la dependencia.
        except ImportError as error:  # pragma: no cover - depende del entorno
            raise SolverUnavailableError(
                "La libreria 'kociemba' no esta instalada. "
                "Ejecuta: pip install -r requirements.txt"
            ) from error

        try:
            return str(kociemba.solve(cubestring, max_depth=self.max_depth))
        except ValueError as error:
            raise InvalidCubeError(
                "Kociemba rechaza el estado: el cubo no es fisicamente resoluble",
            ) from error
        except Exception as error:  # pragma: no cover - errores internos del backend
            raise SolverError(
                f"El motor de resolucion fallo: {type(error).__name__}: {error}"
            ) from error

    def _parse(self, raw: str) -> tuple[Move, ...]:
        """Convierte la respuesta del *backend* en movimientos tipados.

        Args:
            raw: Secuencia de movimientos separada por espacios.

        Returns:
            Tupla de :class:`Move`.

        Raises:
            SolverError: Si aparece un token desconocido.
        """
        moves: list[Move] = []
        for token in raw.split():
            if not _MOVE_TOKEN.match(token):
                raise SolverError(f"Movimiento inesperado del motor: {token!r}")
            face = Face(token[0])
            suffix = token[1:]
            quarters = 1 if suffix == "" else 3 if suffix == "'" else 2
            moves.append(Move(token, face, quarters))
        return tuple(moves)


def describe_sequence(moves: Sequence[Move]) -> tuple[str, ...]:
    """Genera las instrucciones en español de una secuencia.

    Args:
        moves: Movimientos de la solución.

    Returns:
        Una frase por movimiento, numerada.
    """
    return tuple(
        f"{index}. {move.notation}: {move.description}"
        for index, move in enumerate(moves, start=1)
    )
