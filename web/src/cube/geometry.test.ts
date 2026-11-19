import { describe, expect, it } from "vitest";

import {
  applyAlgorithm,
  applyMatrix,
  applyMove,
  frameIndex,
  isInLayer,
  layerMatrix,
  moveFrame,
  movePermutation,
  stickerFrame,
} from "./geometry";
import { FACES, type ColorId, type Facelets, type Move, type Vec3 } from "./types";

const SOLVED: Facelets = FACES.flatMap((face) =>
  Array.from(
    { length: 9 },
    () => ({ U: "W", R: "R", F: "G", D: "Y", L: "O", B: "B" })[face] as ColorId,
  ),
);

const ALL_MOVES: Move[] = FACES.flatMap((face) =>
  ([1, 2, 3] as const).map((quarters) => ({
    face,
    quarters,
    notation: `${face}${quarters === 2 ? "2" : quarters === 3 ? "'" : ""}`,
  })),
);

function parse(algorithm: string): Move[] {
  return algorithm
    .trim()
    .split(/\s+/)
    .map((token) => {
      const suffix = token.slice(1);
      return {
        face: token[0] as Move["face"],
        quarters: (suffix === "2" ? 2 : suffix === "'" ? 3 : 1) as 1 | 2 | 3,
        notation: token,
      };
    });
}

const snap = (vector: Vec3): Vec3 => vector.map((value) => Math.round(value)) as Vec3;

describe("modelo de giros", () => {
  it("un giro solo afecta a las 21 pegatinas de su capa", () => {
    for (const move of ALL_MOVES) {
      const touched = Array.from({ length: 54 }, (_, index) => isInLayer(move, index));
      expect(touched.filter(Boolean)).toHaveLength(21);
    }
  });

  it("las pegatinas fuera de la capa se quedan quietas", () => {
    for (const move of ALL_MOVES) {
      const permutation = movePermutation(move);
      for (let target = 0; target < 54; target += 1) {
        if (!isInLayer(move, target)) expect(permutation[target]).toBe(target);
      }
    }
  });

  it("la rotación visual de la capa coincide con la permutación", () => {
    for (const move of ALL_MOVES) {
      const permutation = movePermutation(move);
      const matrix = layerMatrix(move, 1);
      for (let target = 0; target < 54; target += 1) {
        const source = permutation[target];
        // Solo comparamos la capa móvil: el resto no se transforma al dibujar.
        expect(isInLayer(move, source)).toBe(isInLayer(move, target));
        if (!isInLayer(move, target)) continue;
        const frame = stickerFrame(source);
        const landed = frameIndex(
          snap(applyMatrix(matrix, frame.point)),
          snap(applyMatrix(matrix, frame.normal)),
        );
        expect(landed).toBe(target);
      }
    }
  });

  it("en progreso 0 no hay giro y el progreso interpola una rotación limpia", () => {
    for (const move of ALL_MOVES) {
      layerMatrix(move, 0).forEach((row, rowIndex) => {
        row.forEach((value, colIndex) => {
          expect(value).toBeCloseTo(rowIndex === colIndex ? 1 : 0, 12);
        });
      });

      const { axis, layer } = moveFrame(move);
      const sample: Vec3 = [0, 0, 0];
      sample[(axis + 1) % 3] = layer;
      sample[(axis + 2) % 3] = layer;
      const length = Math.hypot(...sample);
      for (const progress of [0, 0.25, 0.5, 0.75, 1]) {
        expect(Math.hypot(...applyMatrix(layerMatrix(move, progress), sample)))
          .toBeCloseTo(length, 10);
      }
    }
  });

  it("la solución de referencia devuelve el cubo a su estado resuelto", () => {
    const scramble = "R U R' U' F2 D B L2";
    const solution = "L2 B' D' F2 U R U' R'";
    const moved = applyAlgorithm(applyAlgorithm(SOLVED, parse(scramble)), parse(solution));
    expect(moved).toEqual(SOLVED);
  });

  it("repetir un giro cuatro veces restaura el cubo", () => {
    for (const face of FACES) {
      const move: Move = { face, quarters: 1, notation: face };
      let state = [...SOLVED];
      for (let index = 0; index < 4; index += 1) state = applyMove(state, move);
      expect(state).toEqual(SOLVED);
    }
  });
});
