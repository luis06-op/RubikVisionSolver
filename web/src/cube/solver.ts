/** Cliente del worker que calcula la solución sin bloquear la interfaz. */

export interface SolveResult {
  notation: string;
  elapsed: number;
}

type WorkerMessage =
  | { type: "ready" }
  | { type: "result"; id: number; moves: string; elapsed: number }
  | { type: "error"; id: number; message: string };

interface Pending {
  resolve: (result: SolveResult) => void;
  reject: (error: Error) => void;
}

export class SolverClient {
  private worker: Worker;
  private pending = new Map<number, Pending>();
  private nextId = 1;
  private readyResolve: () => void;
  readonly ready: Promise<void>;

  constructor(onState?: (state: "loading" | "ready") => void) {
    this.worker = new Worker(new URL("./solver.worker.ts", import.meta.url), { type: "module" });
    this.readyResolve = () => undefined;
    this.ready = new Promise<void>((resolve) => {
      this.readyResolve = resolve;
    });
    this.worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
      const message = event.data;
      if (message.type === "ready") {
        this.readyResolve();
        onState?.("ready");
        return;
      }
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.type === "error") {
        pending.reject(new Error(message.message || "No se pudo resolver el cubo"));
      } else {
        pending.resolve({ notation: message.moves, elapsed: message.elapsed });
      }
    };
    this.worker.postMessage({ type: "init" });
  }

  solve(cubestring: string): Promise<SolveResult> {
    const id = this.nextId++;
    return this.ready.then(
      () =>
        new Promise<SolveResult>((resolve, reject) => {
          this.pending.set(id, { resolve, reject });
          this.worker.postMessage({ type: "solve", id, cubestring });
        }),
    );
  }

  dispose(): void {
    this.worker.terminate();
    this.pending.clear();
  }
}
