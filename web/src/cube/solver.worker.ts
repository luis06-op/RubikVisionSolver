/// <reference lib="webworker" />
import Cube from "cubejs";

type Request =
  | { type: "init" }
  | { type: "solve"; id: number; cubestring: string };

let initialized = false;

function ensureSolver(): void {
  if (initialized) return;
  Cube.initSolver();
  initialized = true;
}

self.onmessage = (event: MessageEvent<Request>) => {
  const message = event.data;
  if (message.type === "init") {
    ensureSolver();
    self.postMessage({ type: "ready" });
    return;
  }
  ensureSolver();
  const started = performance.now();
  try {
    const cube = Cube.fromString(message.cubestring);
    const moves = cube.solve(22).trim();
    self.postMessage({
      type: "result",
      id: message.id,
      moves,
      elapsed: Math.round(performance.now() - started),
    });
  } catch (error) {
    self.postMessage({
      type: "error",
      id: message.id,
      message: error instanceof Error ? error.message : String(error),
    });
  }
};
