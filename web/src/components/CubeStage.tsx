import { useEffect, useRef } from "react";
import { drawCube } from "../cube/geometry";
import type { Facelets, Move } from "../cube/types";

interface Props {
  facelets: Facelets;
  move: Move | null;
  runId: number;
  paused: boolean;
  speed: number;
  view: number;
}

/** Lienzo isométrico con animación continua controlada por reloj. */
export function CubeStage({ facelets, move, runId, paused, speed, view }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const latest = useRef({ facelets, move, paused, speed, view });
  latest.current = { facelets, move, paused, speed, view };

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let raf = 0;
    let elapsed = 0;
    let last = performance.now();

    const frame = (now: number) => {
      const current = latest.current;
      if (!current.paused) elapsed += Math.min(80, now - last) * current.speed;
      last = now;
      const phase = elapsed % 2600;
      const raw = Math.max(0, Math.min(1, (phase - 300) / 1800));
      drawCube(ctx, {
        colors: current.facelets,
        move: current.move,
        progress: raw * raw * (3 - 2 * raw),
        view: current.view,
        width: canvas.width,
        height: canvas.height,
      });
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [runId]);

  return (
    <div className="cube-stage">
      <div className="stage-glow" />
      <canvas ref={canvasRef} width={560} height={420} aria-label="Animación 3D del cubo" />
      <div className="stage-corner top-left" />
      <div className="stage-corner top-right" />
      <div className="stage-corner bottom-left" />
      <div className="stage-corner bottom-right" />
      {move && <div className="stage-badge">{move.notation}</div>}
    </div>
  );
}
