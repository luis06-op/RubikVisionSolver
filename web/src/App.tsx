import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CubeStage } from "./components/CubeStage";
import { NetInput } from "./components/NetInput";
import { applyAlgorithm, applyMove } from "./cube/geometry";
import { SolverClient } from "./cube/solver";
import {
  COLOR_HEX,
  colorToFace,
  describeMove,
  faceletString,
  FACES,
  parseMoves,
  type ColorId,
  type Facelets,
  type Move,
} from "./cube/types";
import { emptyFacelets, validateFacelets } from "./cube/validation";

const VIEW_NAMES = ["Frontal / derecha", "Frontal / izquierda", "Trasera", "Inferior"];
const SOLVED: Facelets = FACES.flatMap((face) =>
  Array.from({ length: 9 }, () =>
    ({ U: "W", R: "R", F: "G", D: "Y", L: "O", B: "B" })[face] as ColorId,
  ),
);
const DEMO_SCRAMBLE = "R U R' U' F2 D B L2";

type Phase = "input" | "guide";

export default function App() {
  const [facelets, setFacelets] = useState<Facelets>(emptyFacelets);
  const [selected, setSelected] = useState<ColorId>("W");
  const [phase, setPhase] = useState<Phase>("input");
  const [solverReady, setSolverReady] = useState(false);
  const [solving, setSolving] = useState(false);
  const [error, setError] = useState("");
  const [moves, setMoves] = useState<Move[]>([]);
  const [states, setStates] = useState<Facelets[]>([]);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [view, setView] = useState(0);
  const [runId, setRunId] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const clientRef = useRef<SolverClient | null>(null);

  useEffect(() => {
    const client = new SolverClient((state) => setSolverReady(state === "ready"));
    clientRef.current = client;
    return () => {
      client.dispose();
      clientRef.current = null;
    };
  }, []);

  const validation = useMemo(() => validateFacelets(facelets), [facelets]);
  const painted = validation.painted;

  const paint = useCallback((position: number) => {
    setFacelets((current) => {
      const next = [...current];
      next[position] = selected;
      return next;
    });
  }, [selected]);

  const loadDemo = () => {
    setFacelets(applyAlgorithm(SOLVED, parseMoves(DEMO_SCRAMBLE)));
    setError("");
  };

  const solve = async () => {
    if (!validation.valid || !clientRef.current) {
      setError(validation.errors[0] ?? "El solucionador no está listo.");
      return;
    }
    setSolving(true);
    setError("");
    const cubestring = faceletString(facelets, colorToFace(facelets));
    try {
      const result = await clientRef.current.solve(cubestring);
      const parsed = parseMoves(result.notation);
      const timeline = [facelets];
      let current = facelets;
      for (const move of parsed) {
        current = applyMove(current, move);
        timeline.push(current);
      }
      setMoves(parsed);
      setStates(timeline);
      setElapsed(result.elapsed);
      setIndex(0);
      setPaused(false);
      setRunId((value) => value + 1);
      setPhase("guide");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSolving(false);
    }
  };

  const advance = useCallback((delta: number) => {
    setIndex((current) => Math.max(0, Math.min(moves.length, current + delta)));
    setRunId((value) => value + 1);
  }, [moves.length]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (phase !== "guide") return;
      if (event.key === " " || event.key === "ArrowRight") {
        event.preventDefault();
        advance(1);
      } else if (event.key === "ArrowLeft") {
        advance(-1);
      } else if (event.key.toLowerCase() === "r") {
        setRunId((value) => value + 1);
      } else if (event.key.toLowerCase() === "p") {
        setPaused((value) => !value);
      } else if (event.key.toLowerCase() === "v") {
        setView((value) => (value + 1) % VIEW_NAMES.length);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, advance]);

  const finished = phase === "guide" && index >= moves.length;
  const currentMove = !finished && index < moves.length ? moves[index] : null;
  const currentState = states[Math.min(index, states.length - 1)] ?? facelets;
  const nextMoves = moves.slice(index + 1, index + 6);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#inicio">
          <span className="brand-mark">R<span>V</span></span>
          <span className="brand-copy"><strong>RubikVision</strong><small>Studio · Guía 3D</small></span>
        </a>
        <nav>
          <span className={`engine-pill ${solverReady ? "is-ready" : ""}`}>
            <i /> {solverReady ? "Motor Kociemba listo" : "Preparando motor…"}
          </span>
          <a href="https://github.com/luis06-op/RubikVisionSolver" target="_blank" rel="noreferrer">GitHub ↗</a>
        </nav>
      </header>

      <main id="inicio">
        <section className="hero">
          <p className="eyebrow">ESTUDIO DE RESOLUCIÓN · SIN CÁMARA</p>
          <h1>Pinta tu cubo.<br /><em>Mira cómo resolverlo.</em></h1>
          <p className="hero-copy">
            Marca los 54 colores de tu cubo y sigue una solución corta tipo
            Kociemba con una animación 3D para cada giro, como Cyber Solver.
          </p>
          <div className="hero-stats">
            <span><strong>54</strong> pegatinas</span>
            <span><strong>~20</strong> movimientos</span>
            <span><strong>100%</strong> en tu navegador</span>
          </div>
        </section>

        {phase === "input" ? (
          <section className="workspace">
            <div className="panel editor-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">PASO 01</p>
                  <h2>Dibuja tu cubo</h2>
                </div>
                <span className={`counter ${validation.valid ? "is-valid" : ""}`}>{painted}/54</span>
              </div>

              <NetInput
                facelets={facelets}
                selected={selected}
                onSelect={setSelected}
                onPaint={paint}
              />

              {error && <p className="error-box" role="alert">{error}</p>}

              <div className="actions">
                <button className="btn primary" onClick={solve} disabled={!solverReady || solving}>
                  {solving ? "Calculando…" : "Resolver mi cubo →"}
                </button>
                <button className="btn ghost" onClick={loadDemo}>Cargar ejemplo</button>
                <button className="btn ghost" onClick={() => setFacelets(emptyFacelets())}>Limpiar</button>
              </div>
              {!validation.valid && painted === 54 && (
                <ul className="error-list">
                  {validation.errors.map((message) => <li key={message}>{message}</li>)}
                </ul>
              )}
              <p className="fine-print">
                Los datos no salen de tu equipo: la resolución ocurre en un Web Worker.
              </p>
            </div>

            <aside className="panel preview-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">VISTA PREVIA</p>
                  <h2>Tu cubo</h2>
                </div>
              </div>
              <CubeStage
                facelets={currentState}
                move={null}
                runId={runId}
                paused={false}
                speed={1}
                view={view}
              />
              <div className="legend">
                {FACES.map((face, index) => (
                  <span key={face}>
                    <i style={{ background: COLOR_HEX[facelets[index * 9 + 4]] ?? "#475569" }} />
                    {face}
                  </span>
                ))}
              </div>
              <button className="btn subtle" onClick={() => setView((value) => (value + 1) % VIEW_NAMES.length)}>
                Vista: {VIEW_NAMES[view]}
              </button>
            </aside>
          </section>
        ) : (
          <section className="workspace guide-layout">
            <div className="panel stage-panel">
              <div className="panel-heading compact">
                <div>
                  <p className="eyebrow">PASO 02 · GUÍA 3D</p>
                  <h2>{finished ? "Cubo resuelto" : `Movimiento ${index + 1} de ${moves.length}`}</h2>
                </div>
                <span className="counter is-valid">{elapsed} ms</span>
              </div>
              <CubeStage
                facelets={currentState}
                move={currentMove}
                runId={runId}
                paused={paused}
                speed={speed}
                view={view}
              />
              <div className="progress-track">
                <div style={{ width: `${moves.length ? (index / moves.length) * 100 : 0}%` }} />
              </div>
              <div className="guide-controls">
                <button className="btn ghost" onClick={() => advance(-1)} disabled={index === 0}>← Anterior</button>
                <button className="btn primary" onClick={() => advance(1)} disabled={finished}>Ya lo hice →</button>
                <button className="btn ghost" onClick={() => setRunId((value) => value + 1)}>↻ Repetir</button>
                <button className="btn ghost" onClick={() => setPaused((value) => !value)}>{paused ? "▶ Reanudar" : "❚❚ Pausa"}</button>
                <button className="btn ghost" onClick={() => setSpeed((value) => value === 1 ? 1.5 : value === 1.5 ? 0.5 : 1)}>Velocidad {speed}×</button>
                <button className="btn ghost" onClick={() => setView((value) => (value + 1) % VIEW_NAMES.length)}>Cambiar vista</button>
              </div>
            </div>

            <aside className="panel instruction-panel">
              {finished ? (
                <>
                  <p className="eyebrow">SECUENCIÓN COMPLETADA</p>
                  <h2 className="success-title">¡Listo!</h2>
                  <p>Comprueba las seis caras de tu cubo. La animación no verifica los giros: confía en tu vista.</p>
                  <button className="btn primary" onClick={() => setPhase("input")}>Resolver otro cubo</button>
                  <button className="btn ghost" onClick={() => setIndex(0)}>Ver desde el inicio</button>
                </>
              ) : currentMove ? (
                <>
                  <p className="eyebrow">AHORA · MIRANDO LA CARA {currentMove.face}</p>
                  <div className="move-notation">{currentMove.notation}</div>
                  <h2>{describeMove(currentMove)}</h2>
                  <p className="instruction-note">
                    Gira solo esa capa. La animación muestra el sentido desde la
                    cara indicada, no desde la cámara frontal.
                  </p>
                  <div className="next-moves">
                    <p className="eyebrow">A CONTINUACIÓN</p>
                    <div className="chip-row">
                      {nextMoves.map((move, position) => (
                        <span className="chip" key={`${position}-${move.notation}`}>{move.notation}</span>
                      ))}
                    </div>
                  </div>
                  <div className="shortcut-note">
                    Atajos: <kbd>ESPACIO</kbd> siguiente · <kbd>←</kbd> atrás · <kbd>R</kbd> repetir · <kbd>P</kbd> pausa · <kbd>V</kbd> vista
                  </div>
                </>
              ) : null}
              <button className="btn subtle" onClick={() => setPhase("input")}>← Editar colores</button>
            </aside>
          </section>
        )}
      </main>

      <footer>
        <span>RubikVision Studio · Hecho por <a href="https://github.com/luis06-op">luis06-op</a></span>
        <span>Kociemba vía cubejs (MIT) · React + TypeScript</span>
      </footer>
    </div>
  );
}
