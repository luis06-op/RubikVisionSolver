import { normal as faceNormal, stickerPoint } from "./geometry";
import { COLORS, COLOR_NAME, FACES, colorToFace, type ColorId, type Face, type Facelets } from "./types";

export interface Validation {
  valid: boolean;
  errors: string[];
  painted: number;
}

export interface Solvability {
  /** El estado puede alcanzarse girando las caras de un cubo real. */
  solvable: boolean;
  errors: string[];
}

/** Comprueba que el dibujo esté completo y use bien los colores. */
export function validateFacelets(facelets: Facelets): Validation {
  const errors: string[] = [];
  const painted = facelets.filter(Boolean).length;
  if (painted < 54) {
    errors.push(`Faltan ${54 - painted} pegatinas por pintar.`);
    return { valid: false, errors, painted };
  }
  for (const color of COLORS) {
    const count = facelets.filter((value) => value === color).length;
    if (count !== 9) errors.push(`Hay ${count} pegatinas ${color} en lugar de 9.`);
  }
  const centers = FACES.map((_, index) => facelets[index * 9 + 4]);
  if (new Set(centers).size !== 6) errors.push("Los seis colores centrales deben ser distintos.");
  return { valid: errors.length === 0, errors, painted };
}

// ---------------------------------------------------------------------------
// Validación de solubilidad
//
// Un dibujo puede tener nueve pegatinas de cada color y, aun así, ser
// imposible: una esquina girada, una arista volteada o dos piezas
// intercambiadas. Kociemba no termina con esos estados, así que se detectan
// aquí antes de enviar nada al motor.
// ---------------------------------------------------------------------------

type Point = [number, number, number];

const faceOf = (index: number): Face => FACES[Math.floor(index / 9)];

function determinant(a: Face, b: Face, c: Face): number {
  const [ax, ay, az] = faceNormal(a);
  const [bx, by, bz] = faceNormal(b);
  const [cx, cy, cz] = faceNormal(c);
  return ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);
}

/** Ordena las tres pegatinas de una esquina: primero la cara U/D. */
function orderCorner(facelets: number[]): number[] {
  const up = facelets.find((index) => faceOf(index) === "U" || faceOf(index) === "D");
  if (up === undefined) return facelets;
  const [first, second] = facelets.filter((index) => index !== up);
  return determinant(faceOf(up), faceOf(first), faceOf(second)) > 0
    ? [up, second, first]
    : [up, first, second];
}

/** En la capa U/D la cara primaria es U/D; en la intermedia, F/B. */
function isPrimaryEdgeFace(face: Face, point: Point): boolean {
  return point[1] !== 0 ? face === "U" || face === "D" : face === "F" || face === "B";
}

function orderEdge(facelets: number[], point: Point): number[] {
  const primary = facelets.filter((index) => isPrimaryEdgeFace(faceOf(index), point));
  const secondary = facelets.filter((index) => !isPrimaryEdgeFace(faceOf(index), point));
  return primary.length === 1 && secondary.length === 1 ? [primary[0], secondary[0]] : facelets;
}

/** Agrupa las 54 pegatinas en las 8 esquinas y las 12 aristas del cubo. */
function buildSlots(): { corners: number[][]; edges: number[][] } {
  const byPoint = new Map<string, { point: Point; facelets: number[] }>();
  FACES.forEach((face, faceIndex) => {
    for (let row = 0; row < 3; row += 1) {
      for (let col = 0; col < 3; col += 1) {
        const point = stickerPoint(face, row, col);
        const key = point.join(",");
        const entry = byPoint.get(key) ?? { point, facelets: [] };
        entry.facelets.push(faceIndex * 9 + row * 3 + col);
        byPoint.set(key, entry);
      }
    }
  });

  const corners: number[][] = [];
  const edges: number[][] = [];
  const entries = [...byPoint.values()].sort(
    (a, b) => b.point[1] - a.point[1] || b.point[0] - a.point[0] || b.point[2] - a.point[2],
  );
  for (const { point, facelets } of entries) {
    const nonZero = point.filter((value) => value !== 0).length;
    const sorted = [...facelets].sort(
      (a, b) => FACES.indexOf(faceOf(a)) - FACES.indexOf(faceOf(b)),
    );
    if (nonZero === 3 && sorted.length === 3) corners.push(orderCorner(sorted));
    else if (nonZero === 2 && sorted.length === 2) edges.push(orderEdge(sorted, point));
  }
  return { corners, edges };
}

const SLOTS = buildSlots();

const CORNER_INDEX = new Map<string, number>();
SLOTS.corners.forEach((slot, index) => {
  CORNER_INDEX.set(slot.map(faceOf).sort().join(""), index);
});
const EDGE_INDEX = new Map<string, number>();
SLOTS.edges.forEach((slot, index) => {
  EDGE_INDEX.set(slot.map(faceOf).sort().join(""), index);
});

/** Paridad de una permutación: 0 si es par, 1 si es impar. */
function permutationParity(values: number[]): number {
  let inversions = 0;
  for (let i = 0; i < values.length; i += 1) {
    for (let j = i + 1; j < values.length; j += 1) {
      if (values[i] > values[j]) inversions += 1;
    }
  }
  return inversions % 2;
}

/** Nombres legibles de las caras según el color real que tienen. */
function describeWith(faceToColor: Record<Face, ColorId>) {
  return (faces: Face[]): string =>
    faces.map((face) => COLOR_NAME[faceToColor[face]]).sort().join("-");
}
/**
 * Comprueba los tres invariantes del cubo: giro de esquinas, volteo de
 * aristas y paridad de la permutación. Devuelve mensajes en español para que
 * el usuario sepa qué pegatinas revisar.
 */
export function validateSolvable(facelets: Facelets): Solvability {
  if (facelets.some((color) => !color)) return { solvable: false, errors: [] };

  const counts = new Map<ColorId, number>();
  facelets.forEach((color) => counts.set(color, (counts.get(color) ?? 0) + 1));
  const centers = FACES.map((_, index) => facelets[index * 9 + 4]);
  if ([...counts.values()].some((count) => count !== 9) || new Set(centers).size !== 6) {
    // De los colores ya informa validateFacelets.
    return { solvable: false, errors: [] };
  }

  const mapping = colorToFace(facelets);
  const faces = facelets.map((color) => mapping[color]) as Face[];
  const faceToColor = {} as Record<Face, ColorId>;
  COLORS.forEach((color) => {
    faceToColor[mapping[color]] = color;
  });
  const describe = describeWith(faceToColor);

  const errors: string[] = [];
  const cornerPerm: number[] = [];
  const edgePerm: number[] = [];
  const twists: number[] = [];
  const flips: number[] = [];
  const usedCorners = new Set<number>();
  const usedEdges = new Set<number>();

  for (const slot of SLOTS.corners) {
    const present = slot.map((index) => faces[index]);
    const cubie = CORNER_INDEX.get([...present].sort().join(""));
    if (cubie === undefined) {
      errors.push(`La esquina ${describe(present)} no existe en un cubo real: revisa esas pegatinas.`);
      continue;
    }
    if (usedCorners.has(cubie)) {
      errors.push(`La esquina ${describe(present)} aparece más de una vez.`);
      continue;
    }
    usedCorners.add(cubie);
    cornerPerm.push(cubie);
    twists.push(slot.findIndex((index) => faces[index] === "U" || faces[index] === "D"));
  }

  for (const slot of SLOTS.edges) {
    const present = slot.map((index) => faces[index]);
    const cubie = EDGE_INDEX.get([...present].sort().join(""));
    if (cubie === undefined) {
      errors.push(`La arista ${describe(present)} no existe en un cubo real: revisa esas pegatinas.`);
      continue;
    }
    if (usedEdges.has(cubie)) {
      errors.push(`La arista ${describe(present)} aparece más de una vez.`);
      continue;
    }
    usedEdges.add(cubie);
    edgePerm.push(cubie);
    const letters = new Set(present);
    const primary: Face = letters.has("U") ? "U" : letters.has("D") ? "D" : letters.has("F") ? "F" : "B";
    flips.push(faces[slot[0]] === primary ? 0 : 1);
  }

  if (cornerPerm.length !== 8 || edgePerm.length !== 12) {
    return { solvable: false, errors };
  }

  if (twists.reduce((total, value) => total + value, 0) % 3 !== 0) {
    errors.push("Hay una esquina girada de forma imposible: revisa los colores de las esquinas.");
  }
  if (flips.reduce((total, value) => total + value, 0) % 2 !== 0) {
    errors.push("Hay una arista volteada de forma imposible: revisa los colores de las aristas.");
  }
  if (permutationParity(cornerPerm) !== permutationParity(edgePerm)) {
    errors.push("Dos piezas están intercambiadas: así el cubo no se puede resolver. Revisa los colores.");
  }

  return { solvable: errors.length === 0, errors };
}

export function emptyFacelets(): Facelets {
  return Array.from({ length: 54 }, () => "" as ColorId);
}
