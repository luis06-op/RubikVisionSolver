"""Modelo de estado y validación lógica de un cubo de Rubik 3x3x3.

El módulo implementa la representación interna del cubo mediante las seis caras
estándar (``U``, ``R``, ``F``, ``D``, ``L``, ``B``), la conversión a la cadena de
54 *facelets* que consume el algoritmo de Kociemba y un validador completo de la
física del cubo.

La geometría se genera a partir de coordenadas 3D enteras, de modo que las
permutaciones de los movimientos no se escriben a mano: se derivan rotando los
puntos de las pegatinas. Esto elimina los errores de transcripción típicos de
las tablas de *facelets* y permite verificar la coherencia del modelo con
pruebas de ida y vuelta.

Convención de la cadena de Kociemba
-----------------------------------
El orden de las caras es ``U``, ``R``, ``F``, ``D``, ``L``, ``B`` y cada cara se
lee fila por fila (de arriba abajo, de izquierda a derecha) tal y como se ve
desde fuera del cubo, con la cara ``U`` arriba. La cadena resultante tiene 54
caracteres con los valores ``U``, ``R``, ``F``, ``D``, ``L``, ``B``.

Examples:
    >>> from src.cube_state import CubeModel
    >>> cubo = CubeModel.solved()
    >>> cubo.is_solved()
    True
    >>> len(cubo.to_kociemba_string())
    54
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

__all__ = [
    "FACES",
    "SCAN_ORDER",
    "Color",
    "CubeModel",
    "CubeStateError",
    "Face",
    "Facelet",
    "ValidationIssue",
    "ValidationReport",
]


class CubeStateError(RuntimeError):
    """Error de uso del modelo del cubo (estado incompleto o inválido)."""


class Face(str, Enum):
    """Caras del cubo en el orden estándar de la notación de Singmaster."""

    U = "U"
    R = "R"
    F = "F"
    D = "D"
    L = "L"
    B = "B"

    @property
    def name_es(self) -> str:
        """Nombre de la cara en español.

        Returns:
            Nombre en minúsculas, por ejemplo ``"derecha"`` para ``Face.R``.
        """
        return _FACE_NAME_ES[self]


class Color(str, Enum):
    """Colores estándar de las pegatinas de un cubo de Rubik."""

    WHITE = "blanco"
    YELLOW = "amarillo"
    RED = "rojo"
    ORANGE = "naranja"
    BLUE = "azul"
    GREEN = "verde"

    @property
    def name_es(self) -> str:
        """Nombre del color en español (el propio valor del enumerado)."""
        return self.value


#: Orden canónico de las caras, idéntico al que exige la cadena de Kociemba.
FACES: Final[tuple[Face, ...]] = (Face.U, Face.R, Face.F, Face.D, Face.L, Face.B)

#: Orden de escaneo recomendado al usuario (``U`` -> ``L`` -> ``F`` -> ``R`` -> ``B`` -> ``D``).
SCAN_ORDER: Final[tuple[Face, ...]] = (
    Face.U,
    Face.L,
    Face.F,
    Face.R,
    Face.B,
    Face.D,
)

_FACE_NAME_ES: Final[dict[Face, str]] = {
    Face.U: "superior",
    Face.R: "derecha",
    Face.F: "frontal",
    Face.D: "inferior",
    Face.L: "izquierda",
    Face.B: "trasera",
}

#: Nombres cortos usados en los mensajes de validación.
_FACE_LETTER_ES: Final[dict[Face, str]] = {
    Face.U: "U (superior)",
    Face.R: "R (derecha)",
    Face.F: "F (frontal)",
    Face.D: "D (inferior)",
    Face.L: "L (izquierda)",
    Face.B: "B (trasera)",
}

Sticker = Color | None
Point = tuple[int, int, int]
Orientation = tuple[int, int]  # (eje, signo) del vector normal de la cara


@dataclass(frozen=True)
class Facelet:
    """Identifica una pegatina concreta dentro de una cara.

    Attributes:
        face: Cara a la que pertenece la pegatina.
        row: Fila dentro de la cuadrícula 3x3 (0 = arriba).
        col: Columna dentro de la cuadrícula 3x3 (0 = izquierda).
    """

    face: Face
    row: int
    col: int

    @property
    def index(self) -> int:
        """Índice de la pegatina en la cadena de Kociemba (0-53)."""
        return FACES.index(self.face) * 9 + self.row * 3 + self.col


def iter_facelets() -> Iterator[Facelet]:
    """Recorre las 54 pegatinas en el orden de la cadena de Kociemba.

    Yields:
        Cada :class:`Facelet` del cubo.
    """
    for face in FACES:
        for row in range(3):
            for col in range(3):
                yield Facelet(face, row, col)


# ---------------------------------------------------------------------------
# Geometría del cubo
# ---------------------------------------------------------------------------

#: Eje y signo del vector normal de cada cara. Los ejes son X (derecha),
#: Y (arriba) y Z (frente).
_ORIENT: Final[dict[Face, Orientation]] = {
    Face.U: (1, 1),
    Face.D: (1, -1),
    Face.R: (0, 1),
    Face.L: (0, -1),
    Face.F: (2, 1),
    Face.B: (2, -1),
}

_ORIENT_TO_FACE: Final[dict[Orientation, Face]] = {v: k for k, v in _ORIENT.items()}

#: Matrices de rotación de +90 grados respecto de X, Y y Z (coordenadas enteras).
_QUARTER_TURN: Final[dict[int, tuple[Point, Point, Point]]] = {
    0: ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    1: ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
    2: ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
}

#: ``(eje, capa, cuartos_de_giro)`` de cada movimiento en sentido horario.
#: Los cuartos de giro son 1 (90 grados) o 3 (-90 grados) respecto del eje.
_MOVE_GEOMETRY: Final[dict[Face, tuple[int, int, int]]] = {
    Face.U: (1, 1, 3),
    Face.D: (1, -1, 1),
    Face.R: (0, 1, 3),
    Face.L: (0, -1, 1),
    Face.F: (2, 1, 3),
    Face.B: (2, -1, 1),
}

#: Orden de las caras de cada esquina: ``(cara U/D, siguiente, siguiente)``
#: formando una base levógira, tal y como exige la convención estándar de
#: orientación de esquinas.


def _sticker_point(face: Face, row: int, col: int) -> Point:
    """Coordenada 3D discreta del centro de una pegatina.

    Las coordenadas pertenecen a ``{-1, 0, 1}``. En las esquinas tres
    pegatinas comparten el mismo punto y se distinguen por su normal.

    Args:
        face: Cara de la pegatina.
        row: Fila (0-2).
        col: Columna (0-2).

    Returns:
        Punto ``(x, y, z)`` con la coordenada normal fija en ``+-1``.
    """
    if face is Face.F:
        return (col - 1, 1 - row, 1)
    if face is Face.R:
        return (1, 1 - row, 1 - col)
    if face is Face.L:
        return (-1, 1 - row, col - 1)
    if face is Face.B:
        return (1 - col, 1 - row, -1)
    if face is Face.U:
        return (col - 1, 1, row - 1)
    return (col - 1, -1, 1 - row)  # Face.D


def _normal(face: Face) -> Point:
    """Vector normal unitario (entero) de una cara."""
    axis, sign = _ORIENT[face]
    vector = [0, 0, 0]
    vector[axis] = sign
    return (vector[0], vector[1], vector[2])


def _rotate_point(matrix: Sequence[Sequence[int]], point: Point) -> Point:
    """Multiplica una matriz 3x3 entera por un punto."""
    return (
        matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2] * point[2],
        matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2] * point[2],
        matrix[2][0] * point[0] + matrix[2][1] * point[1] + matrix[2][2] * point[2],
    )


def _matmul(
    left: Sequence[Sequence[int]], right: Sequence[Sequence[int]]
) -> tuple[Point, Point, Point]:
    """Multiplica dos matrices 3x3 enteras."""
    return tuple(  # type: ignore[return-value]
        tuple(
            sum(left[i][k] * right[k][j] for k in range(3))
            for j in range(3)
        )
        for i in range(3)
    )


def _rotation(axis: int, quarter_turns: int) -> tuple[Point, Point, Point]:
    """Matriz de rotación entera de ``quarter_turns`` cuartos de giro."""
    result: tuple[Point, Point, Point] = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    step = _QUARTER_TURN[axis]
    for _ in range(quarter_turns % 4):
        result = _matmul(step, result)
    return result


def _build_facelet_lookup() -> dict[tuple[Point, Point], Facelet]:
    """Indexa cada pegatina por la pareja ``(punto, normal)``.

    Returns:
        Diccionario con 54 entradas únicas.

    Raises:
        CubeStateError: Si la geometría generada no es biyectiva.
    """
    lookup: dict[tuple[Point, Point], Facelet] = {}
    for face in FACES:
        normal = _normal(face)
        for row in range(3):
            for col in range(3):
                key = (_sticker_point(face, row, col), normal)
                if key in lookup:
                    raise CubeStateError(
                        f"Geometria ambigua para la pegatina {face.value}{row}{col}"
                    )
                lookup[key] = Facelet(face, row, col)
    return lookup


def _build_move_permutations() -> dict[tuple[Face, int], tuple[int, ...]]:
    """Calcula las permutaciones de una cara para 1, 2 y 3 cuartos de giro.

    La convención es ``nueva[indice] = vieja[permutacion[indice]]``.

    Returns:
        Diccionario ``(cara, cuartos) -> permutacion`` de 54 enteros.
    """
    lookup = _build_facelet_lookup()
    permutations: dict[tuple[Face, int], tuple[int, ...]] = {}
    for face in FACES:
        axis, layer, base_turns = _MOVE_GEOMETRY[face]
        for quarters in (1, 2, 3):
            matrix = _rotation(axis, base_turns * quarters)
            indices = list(range(54))
            for source in iter_facelets():
                point = _sticker_point(source.face, source.row, source.col)
                if point[axis] != layer:
                    continue
                rotated_point = _rotate_point(matrix, point)
                rotated_normal = _rotate_point(matrix, _normal(source.face))
                target = lookup[(rotated_point, rotated_normal)]
                indices[target.index] = source.index
            permutations[(face, quarters)] = tuple(indices)
    return permutations


_FACELET_LOOKUP: Final[dict[tuple[Point, Point], Facelet]] = _build_facelet_lookup()
_MOVE_PERMUTATIONS: Final[dict[tuple[Face, int], tuple[int, ...]]] = (
    _build_move_permutations()
)

_MOVE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<face>[URFDLB])(?P<suffix>['’2]?)$"  # noqa: RUF001 - comilla tipográfica
)


def _parse_move(move: str) -> tuple[Face, int]:
    """Traduce una notación de movimiento a ``(cara, cuartos de giro)``.

    Args:
        move: Movimiento en notación de Singmaster, por ejemplo ``"R"``, ``"U'"``
            o ``"F2"``.

    Returns:
        Cara afectada y número de cuartos de giro en sentido horario (1-3).

    Raises:
        CubeStateError: Si la notación no es válida.
    """
    match = _MOVE_PATTERN.match(
        move.strip().upper().replace("’", "'")  # noqa: RUF001 - comilla tipográfica
    )
    if match is None:
        raise CubeStateError(f"Movimiento no valido: {move!r}")
    face = Face(match.group("face"))
    suffix = match.group("suffix")
    quarters = {"": 1, "'": 3, "2": 2}[suffix]
    return face, quarters


def _apply_permutation(stickers: list[Sticker], permutation: Sequence[int]) -> list[Sticker]:
    """Reordena una lista de pegatinas aplicando una permutación."""
    return [stickers[index] for index in permutation]


# ---------------------------------------------------------------------------
# Esquinas y aristas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CornerSlot:
    """Esquina física del cubo: posición 3D y sus tres pegatinas.

    El orden de ``facelets`` es el de la convención de orientación: primero la
    cara ``U``/``D`` y después las otras dos de forma que el triedro sea
    levógiro. Con ese orden, el giro de una esquina es el índice de la pegatina
    que contiene su color ``U``/``D``.
    """

    position: Point
    facelets: tuple[Facelet, Facelet, Facelet]


def _determinant(a: Face, b: Face, c: Face) -> int:
    """Determinante del triedro formado por las normales de tres caras."""
    vectors = [_normal(face) for face in (a, b, c)]
    return (
        vectors[0][0] * (vectors[1][1] * vectors[2][2] - vectors[1][2] * vectors[2][1])
        - vectors[0][1] * (vectors[1][0] * vectors[2][2] - vectors[1][2] * vectors[2][0])
        + vectors[0][2] * (vectors[1][0] * vectors[2][1] - vectors[1][1] * vectors[2][0])
    )


def _order_corner_facelets(facelets: Sequence[Facelet]) -> tuple[Facelet, Facelet, Facelet]:
    """Ordena las tres pegatinas de una esquina según la convención estándar.

    Args:
        facelets: Las tres pegatinas de la esquina, en cualquier orden.

    Returns:
        Tupla ``(pegatina U/D, segunda, tercera)`` cuyo triedro de normales es
        levógiro.

    Raises:
        CubeStateError: Si las pegatinas no forman una esquina válida.
    """
    ud = [facelet for facelet in facelets if facelet.face in (Face.U, Face.D)]
    if len(ud) != 1:
        raise CubeStateError("Una esquina debe tener exactamente una cara U o D")
    others = [facelet for facelet in facelets if facelet is not ud[0]]
    if len(others) != 2:  # pragma: no cover - geometria garantizada
        raise CubeStateError("Una esquina debe tener tres pegatinas")
    first, second = others
    if _determinant(ud[0].face, first.face, second.face) > 0:
        first, second = second, first
    return ud[0], first, second


def _is_primary_edge_face(face: Face, position: Point) -> bool:
    """Indica si una cara es la primaria de un hueco de arista.

    En la capa ``U``/``D`` la cara primaria es la ``U``/``D``; en la capa
    intermedia es la ``F``/``B``.

    Args:
        face: Cara del hueco.
        position: Posición 3D del hueco.

    Returns:
        ``True`` si la cara es la referencia de orientación del hueco.
    """
    if position[1] != 0:
        return face in (Face.U, Face.D)
    return face in (Face.F, Face.B)


def _order_edge_facelets(facelets: Sequence[Facelet], position: Point) -> tuple[Facelet, Facelet]:
    """Ordena las pegatinas de una arista dejando primero la cara primaria."""
    primary = [fl for fl in facelets if _is_primary_edge_face(fl.face, position)]
    secondary = [fl for fl in facelets if not _is_primary_edge_face(fl.face, position)]
    if len(primary) != 1 or len(secondary) != 1:  # pragma: no cover - geometria
        raise CubeStateError("Una arista debe tener una cara primaria")
    return primary[0], secondary[0]


@dataclass(frozen=True)
class _EdgeSlot:
    """Arista física del cubo: posición 3D y sus dos pegatinas."""

    position: Point
    facelets: tuple[Facelet, Facelet]


def _build_cubie_slots() -> tuple[tuple[_CornerSlot, ...], tuple[_EdgeSlot, ...]]:
    """Construye las 8 esquinas y las 12 aristas a partir de la geometría.

    Returns:
        Pareja ``(esquinas, aristas)`` ordenada de forma determinista.
    """
    by_point: dict[Point, list[Facelet]] = {}
    for face in FACES:
        for row in range(3):
            for col in range(3):
                by_point.setdefault(_sticker_point(face, row, col), []).append(
                    Facelet(face, row, col)
                )

    def sort_key(facelet: Facelet) -> int:
        return FACES.index(facelet.face)

    corners: list[_CornerSlot] = []
    edges: list[_EdgeSlot] = []
    for point in sorted(by_point, key=lambda p: (p[1], p[0], p[2]), reverse=True):
        facelets = sorted(by_point[point], key=sort_key)
        non_zero = sum(1 for coordinate in point if coordinate != 0)
        if non_zero == 3 and len(facelets) == 3:
            corners.append(_CornerSlot(point, _order_corner_facelets(facelets)))
        elif non_zero == 2 and len(facelets) == 2:
            edges.append(_EdgeSlot(point, _order_edge_facelets(facelets, point)))

    if len(corners) != 8 or len(edges) != 12:
        raise CubeStateError(
            f"Geometria inconsistente: {len(corners)} esquinas y {len(edges)} aristas"
        )
    return tuple(corners), tuple(edges)


_CORNERS: tuple[_CornerSlot, ...]
_EDGES: tuple[_EdgeSlot, ...]
_CORNERS, _EDGES = _build_cubie_slots()

_CORNER_SIGNATURES: Final[dict[frozenset[Face], int]] = {
    frozenset(facelet.face for facelet in slot.facelets): index
    for index, slot in enumerate(_CORNERS)
}
_EDGE_SIGNATURES: Final[dict[frozenset[Face], int]] = {
    frozenset(facelet.face for facelet in slot.facelets): index
    for index, slot in enumerate(_EDGES)
}


def _corner_twist(slot: _CornerSlot, facelets: Mapping[Facelet, Face]) -> int:
    """Calcula el giro (0, 1 o 2) de la esquina de un hueco.

    El giro es el índice que ocupa la pegatina con color ``U``/``D`` dentro del
    orden estándar de la esquina. Ese orden hace que la suma de los ocho giros
    sea siempre múltiplo de tres en estados alcanzables.

    Args:
        slot: Esquina inspeccionada.
        facelets: Letra de cara asignada a cada pegatina.

    Returns:
        Giro en el rango ``0..2``.
    """
    for twist, facelet in enumerate(slot.facelets):
        if facelets[facelet] in (Face.U, Face.D):
            return twist
    raise CubeStateError("Esquina sin color U/D")  # pragma: no cover


def _permutation_parity(permutation: Sequence[int]) -> int:
    """Calcula la paridad de una permutación (0 = par, 1 = impar)."""
    inversions = 0
    values = list(permutation)
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            if values[i] > values[j]:
                inversions += 1
    return inversions % 2


# ---------------------------------------------------------------------------
# Informes de validación
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    """Incidencia detectada al validar el estado del cubo.

    Attributes:
        code: Identificador estable de la categoría del problema.
        message: Descripción legible en español.
    """

    code: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    """Resultado completo de la validación de un cubo.

    Attributes:
        issues: Incidencias encontradas; vacío si el cubo es resoluble.
    """

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Indica si el estado puede resolverse físicamente."""
        return not self.issues

    @property
    def messages(self) -> tuple[str, ...]:
        """Mensajes de todas las incidencias."""
        return tuple(issue.message for issue in self.issues)

    def summary(self, limit: int = 3) -> str:
        """Resume las incidencias en una sola línea.

        Args:
            limit: Número máximo de mensajes incluidos.

        Returns:
            Texto apto para mostrar en pantalla.
        """
        if not self.issues:
            return "Cubo valido"
        shown = self.messages[:limit]
        remaining = len(self.messages) - len(shown)
        text = "; ".join(shown)
        if remaining > 0:
            text += f"; y {remaining} problema(s) mas"
        return text


# ---------------------------------------------------------------------------
# Modelo del cubo
# ---------------------------------------------------------------------------


class CubeModel:
    """Estado de un cubo de Rubik de 3x3x3.

    Cada cara se almacena como una matriz 3x3 de colores; una pegatina sin
    escanear se representa con ``None``. El modelo no contiene cámara ni
    interfaz: es un objeto de dominio puro, lo que permite probarlo de forma
    aislada.

    Examples:
        >>> cubo = CubeModel()
        >>> cubo.is_complete()
        False
        >>> cubo.set_face(Face.U, [[Color.WHITE] * 3 for _ in range(3)])
        >>> len(cubo.completed_faces())
        1
    """

    def __init__(self) -> None:
        """Crea un cubo vacío, sin ninguna pegatina escaneada."""
        self._stickers: dict[Face, list[list[Sticker]]] = {
            face: [[None] * 3 for _ in range(3)] for face in FACES
        }

    # -- Construcción ------------------------------------------------------

    @classmethod
    def solved(cls) -> CubeModel:
        """Crea un cubo resuelto con el esquema de colores estándar.

        El esquema es blanco arriba, rojo a la derecha, verde delante, amarillo
        abajo, naranja a la izquierda y azul detrás.

        Returns:
            Modelo completamente escaneado y resuelto.
        """
        scheme: dict[Face, Color] = {
            Face.U: Color.WHITE,
            Face.R: Color.RED,
            Face.F: Color.GREEN,
            Face.D: Color.YELLOW,
            Face.L: Color.ORANGE,
            Face.B: Color.BLUE,
        }
        model = cls()
        for face, color in scheme.items():
            model.set_face(face, [[color] * 3 for _ in range(3)])
        return model

    @classmethod
    def from_kociemba_string(cls, cubestring: str) -> CubeModel:
        """Construye un modelo a partir de una cadena de 54 *facelets*.

        Args:
            cubestring: Cadena de 54 caracteres ``URFDLB`` en el orden estándar.

        Returns:
            Modelo equivalente con los colores estándar del cubo físico.

        Raises:
            CubeStateError: Si la cadena no tiene la longitud o el alfabeto
                esperados.
        """
        normalized = cubestring.strip().upper()
        if len(normalized) != 54:
            raise CubeStateError(
                f"La cadena de Kociemba debe tener 54 caracteres, no {len(normalized)}"
            )
        invalid = sorted(set(normalized) - {face.value for face in FACES})
        if invalid:
            raise CubeStateError(f"Caracteres no validos en la cadena: {invalid}")

        model = cls()
        for face in FACES:
            offset = FACES.index(face) * 9
            grid: list[list[Sticker]] = []
            for row in range(3):
                grid.append(
                    [
                        _DEFAULT_SCHEME[Face(normalized[offset + row * 3 + col])]
                        for col in range(3)
                    ]
                )
            model._stickers[face] = grid
        return model

    def copy(self) -> CubeModel:
        """Devuelve una copia independiente del modelo."""
        clone = CubeModel()
        clone._stickers = {
            face: [row[:] for row in grid] for face, grid in self._stickers.items()
        }
        return clone

    # -- Acceso a las caras ------------------------------------------------

    def set_face(self, face: Face, grid: Sequence[Sequence[Color]]) -> None:
        """Asigna la cuadrícula 3x3 de una cara.

        Args:
            face: Cara que se actualiza.
            grid: Tres filas de tres colores.

        Raises:
            CubeStateError: Si la cuadrícula no es 3x3 o contiene valores que no
                son instancias de :class:`Color`.
        """
        if len(grid) != 3 or any(len(row) != 3 for row in grid):
            raise CubeStateError("Cada cara debe ser una cuadricula de 3x3")
        for row in grid:
            for color in row:
                if not isinstance(color, Color):
                    raise CubeStateError(
                        "Las pegatinas deben ser instancias de Color, "
                        f"no {color!r}"
                    )
        self._stickers[face] = [[Color(cell) for cell in row] for row in grid]

    def set_face_colors(self, face: Face, colors: Sequence[Color]) -> None:
        """Asigna una cara plana (9 colores en orden de lectura).

        Args:
            face: Cara que se actualiza.
            colors: Nueve colores en orden fila por fila.

        Raises:
            CubeStateError: Si la secuencia no contiene exactamente 9 colores.
        """
        if len(colors) != 9:
            raise CubeStateError("Se esperaban 9 colores para la cara")
        self.set_face(face, [colors[0:3], colors[3:6], colors[6:9]])

    def clear_face(self, face: Face) -> None:
        """Elimina las pegatinas escaneadas de una cara."""
        self._stickers[face] = [[None] * 3 for _ in range(3)]

    def clear(self) -> None:
        """Reinicia el modelo completo, dejando las seis caras vacías."""
        for face in FACES:
            self.clear_face(face)

    def face(self, face: Face) -> tuple[tuple[Sticker, ...], ...]:
        """Devuelve la cuadrícula 3x3 de una cara como tuplas inmutables."""
        return tuple(tuple(row) for row in self._stickers[face])

    def center(self, face: Face) -> Sticker:
        """Color del centro de una cara (``None`` si no se ha escaneado)."""
        return self._stickers[face][1][1]

    def is_face_complete(self, face: Face) -> bool:
        """Indica si las nueve pegatinas de una cara están escaneadas."""
        return all(cell is not None for row in self._stickers[face] for cell in row)

    def is_complete(self) -> bool:
        """Indica si las 54 pegatinas están escaneadas."""
        return all(self.is_face_complete(face) for face in FACES)

    def completed_faces(self) -> tuple[Face, ...]:
        """Caras escaneadas, en el orden canónico ``URFDLB``."""
        return tuple(face for face in FACES if self.is_face_complete(face))

    def missing_faces(self) -> tuple[Face, ...]:
        """Caras pendientes de escaneo, en el orden canónico ``URFDLB``."""
        return tuple(face for face in FACES if not self.is_face_complete(face))

    # -- Conversión --------------------------------------------------------

    def color_to_face_map(self) -> dict[Color, Face]:
        """Asocia cada color con la cara cuyo centro lo contiene.

        Returns:
            Diccionario de seis entradas.

        Raises:
            CubeStateError: Si falta algún centro o dos caras comparten color.
        """
        mapping: dict[Color, Face] = {}
        for face in FACES:
            color = self.center(face)
            if color is None:
                raise CubeStateError(
                    f"Falta el centro de la cara {_FACE_LETTER_ES[face]}"
                )
            if color in mapping:
                raise CubeStateError(
                    "Dos caras tienen el mismo color en el centro: "
                    f"{color.name_es} en {_FACE_LETTER_ES[mapping[color]]} y "
                    f"{_FACE_LETTER_ES[face]}"
                )
            mapping[color] = face
        return mapping

    def to_kociemba_string(self) -> str:
        """Convierte el estado a la cadena de 54 *facelets* de Kociemba.

        Returns:
            Cadena con las caras en orden ``U R F D L B``, cada una fila por
            fila.

        Raises:
            CubeStateError: Si el cubo está incompleto o los centros no definen
                una asignación de colores única.
        """
        if not self.is_complete():
            missing = ", ".join(_FACE_LETTER_ES[face] for face in self.missing_faces())
            raise CubeStateError(f"No se puede serializar un cubo incompleto: {missing}")
        mapping = self.color_to_face_map()
        characters: list[str] = []
        for face in FACES:
            for row in self._stickers[face]:
                for color in row:
                    if color is None:  # pragma: no cover - defendido por is_complete
                        raise CubeStateError("Pegatina vacia durante la serializacion")
                    characters.append(mapping[color].value)
        return "".join(characters)

    # -- Movimientos -------------------------------------------------------

    def apply_move(self, move: str) -> None:
        """Aplica un movimiento en notación de Singmaster.

        Args:
            move: Movimiento como ``"R"``, ``"U'"`` o ``"F2"``.

        Raises:
            CubeStateError: Si el cubo está incompleto o la notación no es
                válida.
        """
        face, quarters = _parse_move(move)
        permutation = _MOVE_PERMUTATIONS[(face, quarters)]
        flat: list[Sticker] = []
        for current in FACES:
            for sticker_row in self._stickers[current]:
                flat.extend(sticker_row)
        flat = _apply_permutation(flat, permutation)
        for position, current in enumerate(FACES):
            for row in range(3):
                base = position * 9 + row * 3
                self._stickers[current][row] = flat[base : base + 3]

    def apply_algorithm(self, algorithm: str) -> None:
        """Aplica una secuencia de movimientos separada por espacios.

        Args:
            algorithm: Secuencia como ``"R U R' U'"``.

        Raises:
            CubeStateError: Si algún movimiento no es válido.
        """
        for move in algorithm.split():
            self.apply_move(move)

    def is_solved(self) -> bool:
        """Indica si cada cara muestra un único color.

        Raises:
            CubeStateError: Si el cubo está incompleto.
        """
        if not self.is_complete():
            raise CubeStateError("No se puede comprobar un cubo incompleto")
        for face in FACES:
            cells = {color for row in self._stickers[face] for color in row}
            if len(cells) != 1:
                return False
        return True

    # -- Validación --------------------------------------------------------

    def validate(self) -> ValidationReport:
        """Valida que el estado escaneado sea físicamente resoluble.

        Comprueba, en este orden: que el cubo esté completo, que haya nueve
        pegatinas de cada color, que los seis centros sean distintos, que todas
        las esquinas y aristas existan una sola vez y, por último, los tres
        invariantes del grupo del cubo (giro de esquinas, volteo de aristas y
        paridad de la permutación).

        Returns:
            Informe con todas las incidencias detectadas.
        """
        issues: list[ValidationIssue] = []

        if not self.is_complete():
            missing = ", ".join(_FACE_LETTER_ES[face] for face in self.missing_faces())
            issues.append(
                ValidationIssue(
                    "incompleto",
                    f"Faltan caras por escanear: {missing}. Pulsa R para reiniciar",
                )
            )
            return ValidationReport(tuple(issues))

        counts: dict[Color, int] = {color: 0 for color in Color}
        for face in FACES:
            for sticker_row in self._stickers[face]:
                for color in sticker_row:
                    if color is None:  # pragma: no cover - cubierto por is_complete
                        continue
                    counts[color] += 1
        for color, count in counts.items():
            if count != 9:
                issues.append(
                    ValidationIssue(
                        "conteo",
                        f"Hay {count} pegatinas de color {color.name_es} "
                        f"en lugar de 9. Revisa la iluminacion y vuelve a escanear",
                    )
                )

        try:
            color_faces = self.color_to_face_map()
        except CubeStateError as error:
            issues.append(ValidationIssue("centros", str(error)))
            return ValidationReport(tuple(issues))

        if issues:
            # Sin nueve pegatinas de cada color las comprobaciones de cubies no
            # aportan informacion util y generarian mensajes redundantes.
            return ValidationReport(tuple(issues))

        facelets: dict[Facelet, Face] = {}
        for face in FACES:
            for row in range(3):
                for col in range(3):
                    color = self._stickers[face][row][col]
                    if color is None:  # pragma: no cover
                        continue
                    facelets[Facelet(face, row, col)] = color_faces[color]

        structural, corner_perm, edge_perm, twists, flips = self._inspect_cubies(
            facelets
        )
        issues.extend(structural)
        if issues:
            return ValidationReport(tuple(issues))

        if sum(twists) % 3 != 0:
            issues.append(
                ValidationIssue(
                    "orientacion",
                    "Hay una esquina girada de forma imposible: revisa las caras "
                    "con esquinas de colores poco saturados",
                )
            )
        if sum(flips) % 2 != 0:
            issues.append(
                ValidationIssue(
                    "orientacion",
                    "Hay una arista volteada de forma imposible: vuelve a escanear "
                    "las caras afectadas",
                )
            )
        if _permutation_parity(corner_perm) != _permutation_parity(edge_perm):
            issues.append(
                ValidationIssue(
                    "permutacion",
                    "La permutacion del cubo es imposible (dos piezas intercambiadas): "
                    "revisa el orden de las caras escaneadas",
                )
            )

        return ValidationReport(tuple(issues))

    def _inspect_cubies(
        self, facelets: Mapping[Facelet, Face]
    ) -> tuple[
        list[ValidationIssue],
        list[int],
        list[int],
        list[int],
        list[int],
    ]:
        """Empareja las pegatinas con las esquinas y aristas de referencia.

        Args:
            facelets: Letra de cara asignada a cada pegatina.

        Returns:
            Incidencias estructurales, permutación de esquinas, permutación de
            aristas, lista de giros y lista de volteos.
        """
        issues: list[ValidationIssue] = []
        corner_perm: list[int] = []
        edge_perm: list[int] = []
        twists: list[int] = []
        flips: list[int] = []
        used_corners: dict[int, int] = {}
        used_edges: dict[int, int] = {}

        for slot in _CORNERS:
            signature = frozenset(facelets[facelet] for facelet in slot.facelets)
            cubie = _CORNER_SIGNATURES.get(signature)
            if cubie is None:
                issues.append(
                    ValidationIssue(
                        "esquina",
                        "La esquina formada por las caras "
                        f"{self._describe_faces(signature)} no existe en un cubo real",
                    )
                )
                continue
            if cubie in used_corners:
                issues.append(
                    ValidationIssue(
                        "duplicado",
                        "La esquina "
                        f"{self._describe_faces(signature)} aparece mas de una vez",
                    )
                )
                continue
            used_corners[cubie] = slot.facelets[0].index
            corner_perm.append(cubie)
            twists.append(_corner_twist(slot, facelets))

        for edge_slot in _EDGES:
            signature = frozenset(facelets[facelet] for facelet in edge_slot.facelets)
            cubie = _EDGE_SIGNATURES.get(signature)
            if cubie is None:
                issues.append(
                    ValidationIssue(
                        "arista",
                        "La arista formada por las caras "
                        f"{self._describe_faces(signature)} no existe en un cubo real",
                    )
                )
                continue
            if cubie in used_edges:
                issues.append(
                    ValidationIssue(
                        "duplicado",
                        "La arista "
                        f"{self._describe_faces(signature)} aparece mas de una vez",
                    )
                )
                continue
            used_edges[cubie] = edge_slot.facelets[0].index
            edge_perm.append(cubie)
            flips.append(self._edge_flip(edge_slot, facelets))

        return issues, corner_perm, edge_perm, twists, flips

    @staticmethod
    def _edge_flip(slot: _EdgeSlot, facelets: Mapping[Facelet, Face]) -> int:
        """Calcula el volteo de una arista según la convención estándar.

        Una arista con pegatina ``U``/``D`` está bien orientada si esa pegatina
        ocupa una cara ``U``/``D``; en las aristas de la capa intermedia se usa
        como referencia la pegatina ``F``/``B``.

        Args:
            slot: Arista física inspeccionada.
            facelets: Letra de cara asignada a cada pegatina.

        Returns:
            ``0`` si está orientada y ``1`` si está volteada.
        """
        letters = {facelets[facelet] for facelet in slot.facelets}
        if Face.U in letters:
            primary = Face.U
        elif Face.D in letters:
            primary = Face.D
        elif Face.F in letters:
            primary = Face.F
        else:
            primary = Face.B
        return 0 if facelets[slot.facelets[0]] is primary else 1

    @staticmethod
    def _describe_faces(faces: Iterable[Face]) -> str:
        """Formatea un conjunto de caras como ``"U-R-F"``."""
        return "-".join(sorted(face.value for face in faces))

    # -- Representación ----------------------------------------------------

    def __repr__(self) -> str:
        """Representación compacta con las caras escaneadas."""
        done = "".join(face.value for face in self.completed_faces())
        return f"CubeModel(caras_escaneadas={done or '-'})"


#: Esquema de colores estándar usado al importar cadenas de Kociemba.
_DEFAULT_SCHEME: Final[dict[Face, Color]] = {
    Face.U: Color.WHITE,
    Face.R: Color.RED,
    Face.F: Color.GREEN,
    Face.D: Color.YELLOW,
    Face.L: Color.ORANGE,
    Face.B: Color.BLUE,
}
