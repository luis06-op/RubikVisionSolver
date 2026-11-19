import { useEffect, useRef } from "react";
import { drawCube, moveFrame } from "../cube/geometry";
import type { Facelets, Move } from "../cube/types";

interface Props {
  facelets: Facelets;
  move: Move | null;
  runId: number;
  paused: boolean;
  speed: number;
  view: number;
}

/** Milisegundos de un cuarto de vuelta y extra de un medio giro. */
const TURN_MS = 1150;
const HALF_TURN_EXTRA_MS = 380;

const WIDTH = 560;
const HEIGHT = 420;

/**
 * Lienzo isométrico con animación por reloj.
 *
 * El giro se reproduce una vez y se queda en la posición final: como esa
 * posición es exactamente el estado siguiente, avanzar de paso no produce
 * ningún salto. Se repite con `runId`.
 */
export function CubeStage({ facelets, move, runId, paused, speed, view }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const latest = useRef({ facelets, move, paused, speed, view });
  latest.current = { facelets, move, paused, speed, view };

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    // Dibuja a resolución de pantalla para que los bordes queden nítidos.
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(WIDTH * dpr);
    canvas.height = Math.round(HEIGHT * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    let raf = 0;
    let elapsed = 0;
    let last = performance.now();

    const frame = (now: number) => {
      const current = latest.current;
      // Limita el delta para que volver de otra pestaña no salte el giro.
      const delta = Math.min(48, Math.max(0, now - last));
      last = now;

      const turns = current.move ? Math.abs(moveFrame(current.move).quarterTurns) : 0;
      const duration = current.move ? TURN_MS + (turns === 2 ? HALF_TURN_EXTRA_MS : 0) : 0;
      if (!current.paused && duration > 0) {
        elapsed = Math.min(duration, elapsed + delta * current.speed);
      }
      const progress = duration > 0 ? elapsed / duration : 1;

      drawCube(ctx, {
        colors: current.facelets,
        move: current.move,
        progress,
        view: current.view,
        width: WIDTH,
        height: HEIGHT,
      });
      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [runId]);

  return (
    <div className="cube-stage">
      <div className="stage-glow" />
      <canvas ref={canvasRef} aria-label="Animación 3D del cubo" />
      <div className="stage-corner top-left" />
      <div className="stage-corner top-right" />
      <div className="stage-corner bottom-left" />
      <div className="stage-corner bottom-right" />
      {move && <div className="stage-badge">{move.notation}</div>}
    </div>
  );
}
