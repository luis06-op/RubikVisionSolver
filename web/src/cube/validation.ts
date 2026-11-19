import { COLORS, FACES, type ColorId, type Facelets } from "./types";

export interface Validation {
  valid: boolean;
  errors: string[];
  painted: number;
}

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

export function emptyFacelets(): Facelets {
  return Array.from({ length: 54 }, () => "" as ColorId);
}
