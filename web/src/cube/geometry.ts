/**
 * Geometría del cubo y animación 2D con proyección isométrica.
 * Es el mismo modelo entero que usa la aplicación de escritorio.
 */

import { COLOR_HEX, FACES, type ColorId, type Face, type Facelets, type Move, type Vec3 } from "./types";

const ORIENT: Record<Face, [number, 1 | -1]> = {
  U: [1, 1], D: [1, -1], R: [0, 1], L: [0, -1], F: [2, 1], B: [2, -1],
};

const AXIS_OF: Record<Face, number> = { U: 1, D: 1, R: 0, L: 0, F: 2, B: 2 };

const QUARTER: Record<number, [Vec3, Vec3, Vec3]> = {
  0: [[1, 0, 0], [0, 0, -1], [0, 1, 0]],
  1: [[0, 0, 1], [0, 1, 0], [-1, 0, 0]],
  2: [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
};

/** (eje, capa, cuartos del giro horario) por cara. */
const MOVE_GEOMETRY: Record<Face, [number, number, number]> = {
  U: [1, 1, 3], D: [1, -1, 1], R: [0, 1, 3], L: [0, -1, 1],
  F: [2, 1, 3], B: [2, -1, 1],
};

function stickerPoint(face: Face, row: number, col: number): Vec3 {
  switch (face) {
    case "F": return [col - 1, 1 - row, 1];
    case "R": return [1, 1 - row, 1 - col];
    case "L": return [-1, 1 - row, col - 1];
    case "B": return [1 - col, 1 - row, -1];
    case "U": return [col - 1, 1, row - 1];
    case "D": return [col - 1, -1, 1 - row];
  }
}

function normal(face: Face): Vec3 {
  const [axis, sign] = ORIENT[face];
  const vector: Vec3 = [0, 0, 0];
  vector[axis] = sign;
  return vector;
}

function rotatePoint(matrix: [Vec3, Vec3, Vec3], point: Vec3): Vec3 {
  return [
    matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2] * point[2],
    matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2] * point[2],
    matrix[2][0] * point[0] + matrix[2][1] * point[1] + matrix[2][2] * point[2],
  ];
}

function rotation(axis: number, quarters: number): [Vec3, Vec3, Vec3] {
  let result: [Vec3, Vec3, Vec3] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  const steps = ((Math.round(quarters) % 4) + 4) % 4;
  for (let i = 0; i < steps; i += 1) {
    const step = QUARTER[axis];
    const next: Vec3[] = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    for (let row = 0; row < 3; row += 1) {
      for (let col = 0; col < 3; col += 1) {
        next[row][col] = step[row][0] * result[0][col]
          + step[row][1] * result[1][col]
          + step[row][2] * result[2][col];
      }
    }
    result = next as [Vec3, Vec3, Vec3];
  }
  return result;
}

function axisAngle(axis: Vec3, angle: number): [Vec3, Vec3, Vec3] {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const [x, y, z] = axis;
  return [
    [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
    [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
    [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
  ];
}

const key = (point: Vec3, faceNormal: Vec3) => `${point.join(",")}|${faceNormal.join(",")}`;

const LOOKUP = new Map<string, number>();
FACES.forEach((face, faceIndex) => {
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      LOOKUP.set(key(stickerPoint(face, row, col), normal(face)), faceIndex * 9 + row * 3 + col);
    }
  }
});

const PERMUTATIONS = new Map<string, number[]>();
FACES.forEach((face) => {
  const [axis, layer, base] = MOVE_GEOMETRY[face];
  for (let quarters = 1; quarters <= 3; quarters += 1) {
    const matrix = rotation(axis, base * quarters);
    const indices = Array.from({ length: 54 }, (_, index) => index);
    FACES.forEach((currentFace, faceIndex) => {
      for (let row = 0; row < 3; row += 1) {
        for (let col = 0; col < 3; col += 1) {
          const point = stickerPoint(currentFace, row, col);
          if (point[axis] !== layer) continue;
          const target = LOOKUP.get(key(
            rotatePoint(matrix, point),
            rotatePoint(matrix, normal(currentFace)),
          ));
          if (target !== undefined) indices[target] = faceIndex * 9 + row * 3 + col;
        }
      }
    });
    PERMUTATIONS.set(`${face}${quarters}`, indices);
  }
});

/** Aplica un movimiento a 54 pegatinas en orden URFDLB. */
export function applyMove(facelets: Facelets, move: Move): Facelets {
  const permutation = PERMUTATIONS.get(`${move.face}${move.quarters}`);
  return permutation ? permutation.map((index) => facelets[index]) : [...facelets];
}

export function applyAlgorithm(facelets: Facelets, moves: Move[]): Facelets {
  return moves.reduce((state, move) => applyMove(state, move), [...facelets]);
}

interface Geometry {
  points: Vec3[];
  normals: Vec3[];
  polygons: Vec3[][];
}

const BASE: Geometry = (() => {
  const points: Vec3[] = [];
  const normals: Vec3[] = [];
  const polygons: Vec3[][] = [];
  FACES.forEach((face) => {
    for (let row = 0; row < 3; row += 1) {
      for (let col = 0; col < 3; col += 1) {
        const point = stickerPoint(face, row, col);
        const faceNormal = normal(face);
        const origin = stickerPoint(face, 0, 0);
        const right = stickerPoint(face, 0, 1).map((value, index) => value - origin[index]) as Vec3;
        const down = stickerPoint(face, 1, 0).map((value, index) => value - origin[index]) as Vec3;
        points.push(point);
        normals.push(faceNormal);
        polygons.push(([[-1, -1], [1, -1], [1, 1], [-1, 1]] as const).map(([x, y]) => [
          point[0] + faceNormal[0] * 0.5 + 0.45 * (x * right[0] + y * down[0]),
          point[1] + faceNormal[1] * 0.5 + 0.45 * (x * right[1] + y * down[1]),
          point[2] + faceNormal[2] * 0.5 + 0.45 * (x * right[2] + y * down[2]),
        ]));
      }
    }
  });
  return { points, normals, polygons };
})();

function smoothstep(value: number): number {
  const t = Math.max(0, Math.min(1, value));
  return t * t * (3 - 2 * t);
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

function matrixFor(move: Move | null, progress: number): [Vec3, Vec3, Vec3] {
  if (!move) return [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  const base = MOVE_GEOMETRY[move.face][2];
  const turns = move.quarters === 2 ? 2 : move.quarters === 3 ? -1 : 1;
  const angle = -turns * base * (Math.PI / 2) * smoothstep(progress);
  return axisAngle(normal(move.face), angle);
}

const VIEWS: Vec3[] = [[6, 5, 8], [-6, 5, 8], [-6, 5, -8], [6, -5, 8]];

export interface DrawOptions {
  colors: Facelets;
  move: Move | null;
  progress: number;
  view: number;
  width: number;
  height: number;
}

function hexToRgba(hex: string): string {
  const value = hex.slice(1);
  return `rgba(${parseInt(value.slice(0, 2), 16)}, ${parseInt(value.slice(2, 4), 16)}, ${parseInt(value.slice(4, 6), 16)}, 1)`;
}

/** Dibuja el cubo en un canvas 2D con proyección isométrica. */
export function drawCube(ctx: CanvasRenderingContext2D, options: DrawOptions): void {
  const { width, height } = options;
  ctx.clearRect(0, 0, width, height);
  const raw = VIEWS[options.view % VIEWS.length];
  const length = Math.hypot(...raw);
  const camera: Vec3 = [raw[0] / length, raw[1] / length, raw[2] / length];
  let right = cross([0, 1, 0], camera);
  const rightLength = Math.hypot(...right);
  right = right.map((value) => value / rightLength) as Vec3;
  const up = cross(camera, right);
  const matrix = matrixFor(options.move, options.progress);
  const axisIndex = options.move ? AXIS_OF[options.move.face] : -1;
  const layer = options.move ? MOVE_GEOMETRY[options.move.face][1] : -99;

  const stickers = BASE.polygons.map((polygon, index) => {
    const transformed = polygon.map((vertex) => rotatePoint(matrix, vertex));
    const faceNormal = rotatePoint(matrix, BASE.normals[index]);
    const depth = transformed.reduce((sum, vertex) => sum + dot(vertex, camera), 0) / 4;
    return {
      x: transformed.map((vertex) => dot(vertex, right)),
      y: transformed.map((vertex) => -dot(vertex, up)),
      depth,
      visible: dot(faceNormal, camera) > 0.01,
      index,
      moving: axisIndex >= 0 && BASE.points[index][axisIndex] === layer,
    };
  }).filter((sticker) => sticker.visible).sort((a, b) => a.depth - b.depth);

  const scale = Math.min(width, height) / 5.4;
  ctx.lineJoin = "round";
  for (const sticker of stickers) {
    ctx.beginPath();
    sticker.x.forEach((value, index) => {
      const px = width / 2 + value * scale;
      const py = height / 2 + sticker.y[index] * scale;
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fillStyle = hexToRgba(COLOR_HEX[options.colors[sticker.index] as ColorId] ?? "#334155");
    ctx.fill();
    ctx.lineWidth = sticker.moving ? 3 : 1.5;
    ctx.strokeStyle = sticker.moving ? "#5eead4" : "rgba(8, 15, 30, 0.9)";
    ctx.stroke();
  }
}
