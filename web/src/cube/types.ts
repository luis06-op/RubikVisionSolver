/** Tipos compartidos del estudio de cubos. */

export const FACES = ["U", "R", "F", "D", "L", "B"] as const;
export type Face = (typeof FACES)[number];

export const COLORS = ["W", "Y", "R", "O", "B", "G"] as const;
export type ColorId = (typeof COLORS)[number];

export type Facelets = ColorId[];

export interface Move {
  notation: string;
  face: Face;
  quarters: 1 | 2 | 3;
}

export interface GuideState {
  facelets: Facelets;
  before: Move | null;
}

export type Vec3 = [number, number, number];

export const COLOR_HEX: Record<ColorId, string> = {
  W: "#f8fafc",
  Y: "#facc15",
  R: "#ef4444",
  O: "#fb923c",
  B: "#3b82f6",
  G: "#22c55e",
};

export const COLOR_NAME: Record<ColorId, string> = {
  W: "blanco",
  Y: "amarillo",
  R: "rojo",
  O: "naranja",
  B: "azul",
  G: "verde",
};

export const FACE_NAME: Record<Face, string> = {
  U: "superior",
  R: "derecha",
  F: "frontal",
  D: "inferior",
  L: "izquierda",
  B: "trasera",
};

/** Cada color se asocia a la cara cuyo centro tiene ese color. */
export function colorToFace(facelets: Facelets): Record<ColorId, Face> {
  const result = {} as Record<ColorId, Face>;
  FACES.forEach((face, index) => {
    result[facelets[index * 9 + 4]] = face;
  });
  return result;
}

export function faceletString(facelets: Facelets, mapping: Record<ColorId, Face>): string {
  return facelets.map((color) => mapping[color]).join("");
}

export function parseMoves(notation: string): Move[] {
  return notation
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => {
      if (!/^[URFDLB](?:['2])?$/.test(token)) {
        throw new Error(`Movimiento no reconocido: ${token}`);
      }
      const suffix = token.slice(1);
      return {
        notation: token,
        face: token[0] as Face,
        quarters: (suffix === "2" ? 2 : suffix === "'" ? 3 : 1) as 1 | 2 | 3,
      };
    });
}

export function describeMove(move: Move): string {
  const turn =
    move.quarters === 2
      ? "180 grados (media vuelta)"
      : move.quarters === 3
        ? "90 grados en sentido antihorario"
        : "90 grados en sentido horario";
  return `Gira la cara ${FACE_NAME[move.face]} ${turn}, mirándola de frente.`;
}
