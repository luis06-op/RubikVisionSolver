import { afterEach, describe, expect, it, vi } from "vitest";
import { SolverClient } from "./solver";

/** Worker falso: permite simular respuestas, errores y terminaciones. */
class FakeWorker {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;
  onmessageerror: (() => void) | null = null;
  messages: unknown[] = [];
  terminated = false;

  postMessage(message: unknown): void {
    this.messages.push(message);
  }

  terminate(): void {
    this.terminated = true;
  }

  emit(data: unknown): void {
    this.onmessage?.({ data } as MessageEvent);
  }
}

function setup() {
  const workers: FakeWorker[] = [];
  const client = new SolverClient(undefined, () => {
    const worker = new FakeWorker();
    workers.push(worker);
    return worker as unknown as Worker;
  });
  return { client, workers };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("SolverClient", () => {
  it("resuelve cuando el worker responde", async () => {
    const { client, workers } = setup();
    workers[0].emit({ type: "ready" });
    const result = client.solve("UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB");
    await Promise.resolve();
    workers[0].emit({ type: "result", id: 1, moves: "R U", elapsed: 12 });
    await expect(result).resolves.toEqual({ notation: "R U", elapsed: 12 });
  });

  it("corta el cálculo y reinicia el worker si tarda demasiado", async () => {
    vi.useFakeTimers();
    const { client, workers } = setup();
    workers[0].emit({ type: "ready" });
    const result = client.solve("estado-imposible");
    const expectation = expect(result).rejects.toThrow(/tardó demasiado/);
    await vi.advanceTimersByTimeAsync(8000);
    await expectation;
    expect(workers[0].terminated).toBe(true);
    expect(workers).toHaveLength(2);
  });

  it("rechaza el cálculo suelto si el worker falla", async () => {
    const { client, workers } = setup();
    workers[0].emit({ type: "ready" });
    const result = client.solve("estado-imposible");
    await Promise.resolve();
    workers[0].onerror?.({ preventDefault: () => undefined } as ErrorEvent);
    await expect(result).rejects.toThrow(/falló/);
    expect(workers).toHaveLength(2);
  });

  it("rechaza el cálculo suelto si el motor devuelve un error", async () => {
    const { client, workers } = setup();
    workers[0].emit({ type: "ready" });
    const result = client.solve("estado-imposible");
    await Promise.resolve();
    workers[0].emit({ type: "error", id: 1, message: "Cadena no válida" });
    await expect(result).rejects.toThrow("Cadena no válida");
  });
});
