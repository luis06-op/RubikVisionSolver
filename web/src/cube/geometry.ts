/**
 * Geometría del cubo y animación 2D con proyección isométrica.
 * Es el mismo modelo entero que usa la aplicación de escritorio.
 */

import { COLOR_HEX, FACES, type ColorId, type Face, type Facelets, type Move, type Vec3 } from "./types";

const ORIENT: Record<Face, [number, 1 | -1]> = {
  U: [1, 1], D: [1, -1], R: [0, 1], L: [0, -1], F: [2, 1], B: [2, -1],
};

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

/** Coordenada 3D discreta del centro de una pegatina (reutilizada por la validación). */
export function stickerPoint(face: Face, row: number, col: number): Vec3 {
  switch (face) {
    case "F": return [col - 1, 1 - row, 1];
    case "R": return [1, 1 - row, 1 - col];
    case "L": return [-1, 1 - row, col - 1];
    case "B": return [1 - col, 1 - row, -1];
    case "U": return [col - 1, 1, row - 1];
    case "D": return [col - 1, -1, 1 - row];
  }
}

/** Normal unitaria de una cara (reutilizada por la validación). */
export function normal(face: Face): Vec3 {
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

interface StickerGeometry {
  points: Vec3[];
  normals: Vec3[];
  polygons: Vec3[][];
}

const BASE: StickerGeometry = (() => {
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

/** Mitad del lado de cada pieza: 0,494 deja una ranura fina entre piezas. */
const CUBIE_HALF = 0.494;

interface Piece {
  vertices: Vec3[];
  normal: Vec3;
  /** Centro de la pieza: decide si gira con la capa activa. */
  center: Vec3;
  kind: "body" | "sticker";
  /** Índice de la pegatina; -1 en el cuerpo. */
  sticker: number;
}

/** Seis caras de una pieza del cubo (cuerpo oscuro bajo las pegatinas). */
function cubieFaces(center: Vec3): Piece[] {
  const pieces: Piece[] = [];
  for (let axis = 0; axis < 3; axis += 1) {
    for (const sign of [-1, 1] as const) {
      const faceNormal: Vec3 = [0, 0, 0];
      faceNormal[axis] = sign;
      const face: Vec3 = [...center] as Vec3;
      face[axis] += sign * CUBIE_HALF;
      const u = (axis + 1) % 3;
      const v = (axis + 2) % 3;
      pieces.push({
        vertices: ([[-1, -1], [1, -1], [1, 1], [-1, 1]] as const).map(([su, sv]) => {
          const corner: Vec3 = [...face] as Vec3;
          corner[u] += su * CUBIE_HALF;
          corner[v] += sv * CUBIE_HALF;
          return corner;
        }),
        normal: faceNormal,
        center,
        kind: "body",
        sticker: -1,
      });
    }
  }
  return pieces;
}

/** Las 27 piezas con su cuerpo y las 54 pegatinas, listas para dibujar. */
const PIECES: Piece[] = (() => {
  const pieces: Piece[] = [];
  for (const x of [-1, 0, 1]) {
    for (const y of [-1, 0, 1]) {
      for (const z of [-1, 0, 1]) {
        pieces.push(...cubieFaces([x, y, z]));
      }
    }
  }
  BASE.polygons.forEach((vertices, index) => {
    pieces.push({
      vertices,
      normal: BASE.normals[index],
      center: BASE.points[index],
      kind: "sticker",
      sticker: index,
    });
  });
  return pieces;
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

export type Matrix3 = [Vec3, Vec3, Vec3];

const IDENTITY: Matrix3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];

/** Capa que gira: eje (0=X, 1=Y, 2=Z), coordenada de la capa y cuartos. */
export interface TurnFrame {
  axis: number;
  layer: number;
  quarterTurns: number;
}

/**
 * Describe la capa afectada por un movimiento.
 *
 * La permutación lógica se construye girando `base * quarters` cuartos de
 * vuelta; aquí se reduce al camino corto (3 -> -1) para que la animación no
 * dé una vuelta de más y para que el final coincida con el estado siguiente.
 */
export function moveFrame(move: Move): TurnFrame {
  const [axis, layer, base] = MOVE_GEOMETRY[move.face];
  const total = (((base * move.quarters) % 4) + 4) % 4;
  return { axis, layer, quarterTurns: total === 3 ? -1 : total };
}

/** Matriz de giro de la capa en el instante `progress` (0..1). */
export function layerMatrix(move: Move, progress: number): Matrix3 {
  const { axis, quarterTurns } = moveFrame(move);
  // La permutación se genera girando sobre el eje positivo (X/Y/Z), no sobre
  // la normal de la cara: usar la normal invertía D, L y B.
  const direction: Vec3 = [0, 0, 0];
  direction[axis] = 1;
  return axisAngle(direction, quarterTurns * (Math.PI / 2) * smoothstep(progress));
}

/** Permutación destino <- origen que aplica un movimiento. */
export function movePermutation(move: Move): number[] {
  const permutation = PERMUTATIONS.get(`${move.face}${move.quarters}`);
  if (!permutation) throw new Error(`Movimiento sin permutación: ${move.notation}`);
  return permutation;
}

/** ¿La pegatina `index` pertenece a la capa que gira? */
export function isInLayer(move: Move, index: number): boolean {
  const { axis, layer } = moveFrame(move);
  return BASE.points[index][axis] === layer;
}

export interface StickerFrame {
  face: Face;
  point: Vec3;
  normal: Vec3;
}

/** Centro y normal de una pegatina; útil para verificar la animación. */
export function stickerFrame(index: number): StickerFrame {
  return {
    face: FACES[Math.floor(index / 9)],
    point: BASE.points[index],
    normal: BASE.normals[index],
  };
}

/** Índice de la pegatina que ocupa un punto con una normal dados. */
export function frameIndex(point: Vec3, stickerNormal: Vec3): number | undefined {
  return LOOKUP.get(key(point, stickerNormal));
}

/** Aplica una matriz de giro a un punto. */
export function applyMatrix(matrix: Matrix3, point: Vec3): Vec3 {
  return rotatePoint(matrix, point);
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
  const frame = options.move ? moveFrame(options.move) : null;
  const matrix = options.move ? layerMatrix(options.move, options.progress) : IDENTITY;

  const visible = PIECES.map((piece) => {
    // Solo las piezas de la capa activa giran; el resto mantiene su sitio.
    const moving = frame !== null && piece.center[frame.axis] === frame.layer;
    const local = moving ? matrix : IDENTITY;
    const vertices = piece.vertices.map((vertex) => rotatePoint(local, vertex));
    const faceNormal = rotatePoint(local, piece.normal);
    const depth = vertices.reduce((sum, vertex) => sum + dot(vertex, camera), 0) / 4;
    return {
      x: vertices.map((vertex) => dot(vertex, right)),
      y: vertices.map((vertex) => -dot(vertex, up)),
      depth,
      normal: faceNormal,
      piece,
      moving,
    };
  })
    .filter((item) => dot(item.normal, camera) > 0.01)
    .sort((a, b) => a.depth - b.depth);

  const scale = Math.min(width, height) / 5.4;
  ctx.lineJoin = "round";
  for (const item of visible) {
    ctx.beginPath();
    item.x.forEach((value, index) => {
      const px = width / 2 + value * scale;
      const py = height / 2 + item.y[index] * scale;
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.closePath();

    if (item.piece.kind === "body") {
      ctx.fillStyle = item.moving ? "#101c30" : "#0a1424";
      ctx.strokeStyle = "#050a12";
      ctx.lineWidth = 1;
      ctx.fill();
      ctx.stroke();
      continue;
    }

    const color = options.colors[item.piece.sticker];
    ctx.fillStyle = color ? hexToRgba(COLOR_HEX[color as ColorId] ?? "#334155") : "#334155";
    ctx.strokeStyle = item.moving ? "#5eead4" : "rgba(4, 9, 18, 0.85)";
    ctx.lineWidth = item.moving ? 2.4 : 1.2;
    ctx.fill();
    ctx.stroke();
  }
}
