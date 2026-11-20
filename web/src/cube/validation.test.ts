import { describe, expect, it } from "vitest";
import { applyAlgorithm } from "./geometry";
import { FACES, parseMoves, type ColorId, type Facelets } from "./types";
import { validateFacelets, validateSolvable } from "./validation";

const SOLVED: Facelets = FACES.flatMap((face) =>
  Array.from(
    { length: 9 },
    () => ({ U: "W", R: "R", F: "G", D: "Y", L: "O", B: "B" })[face] as ColorId,
  ),
);

const swapped = (facelets: Facelets, a: number, b: number): Facelets => {
  const next = [...facelets];
  [next[a], next[b]] = [next[b], next[a]];
  return next;
};

const rotated = (facelets: Facelets, a: number, b: number, c: number): Facelets => {
  const next = [...facelets];
  next[a] = facelets[c];
  next[b] = facelets[a];
  next[c] = facelets[b];
  return next;
};

describe("validateSolvable", () => {
  it("acepta el cubo resuelto", () => {
    expect(validateFacelets(SOLVED).valid).toBe(true);
    expect(validateSolvable(SOLVED)).toEqual({ solvable: true, errors: [] });
  });

  it("acepta un cubo desordenado de verdad", () => {
    const scrambled = applyAlgorithm(SOLVED, parseMoves("R U R' U' F2 D B L2"));
    expect(validateFacelets(scrambled).valid).toBe(true);
    expect(validateSolvable(scrambled).solvable).toBe(true);
  });

  it("rechaza dos pegatinas cambiadas aunque haya nueve de cada color", () => {
    const broken = swapped(SOLVED, 0, 9);
    expect(validateFacelets(broken).valid).toBe(true);
    expect(validateSolvable(broken).solvable).toBe(false);
  });

  it("detecta una arista volteada", () => {
    // UR: pegatina de U (índice 5) y de R (índice 10).
    const flipped = swapped(SOLVED, 5, 10);
    const result = validateSolvable(flipped);
    expect(result.solvable).toBe(false);
    expect(result.errors.join(" ")).toMatch(/arista volteada/i);
  });

  it("detecta una esquina girada", () => {
    // URF: pegatinas de U (8), R (9) y F (20).
    const twisted = rotated(SOLVED, 8, 9, 20);
    const result = validateSolvable(twisted);
    expect(result.solvable).toBe(false);
    expect(result.errors.join(" ")).toMatch(/esquina girada/i);
  });

  it("detecta dos piezas intercambiadas (paridad impar)", () => {
    // Intercambia los colores laterales de las aristas UR y UF.
    const parity = swapped(SOLVED, 10, 19);
    const result = validateSolvable(parity);
    expect(result.solvable).toBe(false);
    expect(result.errors.join(" ")).toMatch(/intercambiadas/i);
  });

  it("no opina mientras faltan pegatinas", () => {
    expect(validateSolvable(Array(54).fill("") as Facelets)).toEqual({
      solvable: false,
      errors: [],
    });
  });
});
