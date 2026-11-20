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
  timer: ReturnType<typeof setTimeout>;
}

/**
 * Con un cubo imposible Kociemba no termina nunca, así que el cliente corta el
 * cálculo y reinicia el worker. Los estados válidos tardan mucho menos.
 */
const SOLVE_TIMEOUT_MS = 8000;

export type WorkerFactory = () => Worker;

const createModuleWorker: WorkerFactory = () =>
  new Worker(new URL("./solver.worker.ts", import.meta.url), { type: "module" });

export class SolverClient {
  private worker: Worker;
  private pending = new Map<number, Pending>();
  private nextId = 1;
  private ready = false;
  private readyWaiters: Array<() => void> = [];
  private readonly onState?: (state: "loading" | "ready") => void;
  private readonly createWorker: WorkerFactory;

  constructor(
    onState?: (state: "loading" | "ready") => void,
    createWorker: WorkerFactory = createModuleWorker,
  ) {
    this.onState = onState;
    this.createWorker = createWorker;
    this.worker = this.spawn();
  }

  solve(cubestring: string): Promise<SolveResult> {
    const id = this.nextId++;
    return this.waitReady().then(
      () =>
        new Promise<SolveResult>((resolve, reject) => {
          const timer = setTimeout(() => {
            this.pending.delete(id);
            reject(
              new Error(
                "El cálculo tardó demasiado: los colores no forman un cubo resoluble. Revisa las pegatinas.",
              ),
            );
            this.restart();
          }, SOLVE_TIMEOUT_MS);
          this.pending.set(id, { resolve, reject, timer });
          this.worker.postMessage({ type: "solve", id, cubestring });
        }),
    );
  }

  dispose(): void {
    this.pending.forEach((pending) => clearTimeout(pending.timer));
    this.pending.clear();
    this.worker.terminate();
  }

  private spawn(): Worker {
    const worker = this.createWorker();
    this.ready = false;
    this.onState?.("loading");
    worker.onmessage = (event: MessageEvent<WorkerMessage>) => this.handleMessage(event.data);
    worker.onerror = (event) => {
      event.preventDefault?.();
      this.failAll("El motor de resolución falló al iniciarse. Recarga la página.");
    };
    worker.onmessageerror = () => this.failAll("El motor devolvió una respuesta ilegible.");
    worker.postMessage({ type: "init" });
    return worker;
  }

  private handleMessage(message: WorkerMessage): void {
    if (message.type === "ready") {
      this.ready = true;
      this.onState?.("ready");
      const waiters = this.readyWaiters;
      this.readyWaiters = [];
      waiters.forEach((resolve) => resolve());
      return;
    }
    const pending = this.pending.get(message.id);
    if (!pending) return;
    this.pending.delete(message.id);
    clearTimeout(pending.timer);
    if (message.type === "error") {
      pending.reject(new Error(message.message || "No se pudo resolver el cubo"));
    } else {
      pending.resolve({ notation: message.moves, elapsed: message.elapsed });
    }
  }

  private failAll(message: string): void {
    this.pending.forEach((pending) => {
      clearTimeout(pending.timer);
      pending.reject(new Error(message));
    });
    this.pending.clear();
    this.restart();
  }

  private restart(): void {
    this.worker.terminate();
    this.worker = this.spawn();
  }

  private waitReady(): Promise<void> {
    if (this.ready) return Promise.resolve();
    return new Promise((resolve) => {
      this.readyWaiters.push(resolve);
    });
  }
}
