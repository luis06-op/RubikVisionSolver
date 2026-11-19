import type { CSSProperties } from "react";
import { COLOR_HEX, COLOR_NAME, COLORS, FACES, type ColorId, type Face, type Facelets } from "../cube/types";

interface Props {
  facelets: Facelets;
  selected: ColorId;
  onSelect: (color: ColorId) => void;
  onPaint: (index: number) => void;
  disabled?: boolean;
}

/** Desarrollo plano clicable: U / L F R B / D en orden de Kociemba. */
export function NetInput({ facelets, selected, onSelect, onPaint, disabled = false }: Props) {
  const layout: Face[][] = [
    [],
    ["U"],
    ["L", "F", "R", "B"],
    ["D"],
  ];

  const cell = (face: Face, row: number, col: number) => {
    const index = FACES.indexOf(face) * 9 + row * 3 + col;
    const color = facelets[index];
    return (
      <button
        key={`${face}-${row}-${col}`}
        type="button"
        className={`sticker ${color ? "is-painted" : ""}`}
        style={color ? { background: COLOR_HEX[color] } : undefined}
        onClick={() => !disabled && onPaint(index)}
        aria-label={`Cara ${face}, fila ${row + 1}, columna ${col + 1}, ${color ? COLOR_NAME[color] : "sin pintar"}`}
        disabled={disabled}
      >
        {color ? <span className="sticker-gloss" /> : <span className="sticker-plus">+</span>}
      </button>
    );
  };

  const faceBlock = (face: Face) => (
    <div className="face-block" key={face}>
      <div className="face-title">
        <span className="face-letter">{face}</span>
        <span>{face === "U" ? "superior" : face === "L" ? "izquierda" : face === "F" ? "frontal" : face === "R" ? "derecha" : face === "B" ? "trasera" : "inferior"}</span>
      </div>
      <div className="face-grid">
        {[0, 1, 2].map((row) =>
          [0, 1, 2].map((col) => cell(face, row, col)),
        )}
      </div>
    </div>
  );

  return (
    <div className="net-editor">
      <div className="palette" role="group" aria-label="Selecciona un color">
        {COLORS.map((color) => (
          <button
            key={color}
            type="button"
            className={`swatch ${selected === color ? "is-active" : ""}`}
            style={{ "--swatch": COLOR_HEX[color] } as CSSProperties}
            onClick={() => onSelect(color)}
            disabled={disabled}
            title={COLOR_NAME[color]}
          >
            <span />
            <small>{COLOR_NAME[color]}</small>
          </button>
        ))}
      </div>

      <div className="cube-net">
        <div className="net-row net-top">{layout[1].map(faceBlock)}</div>
        <div className="net-row net-middle">{layout[2].map(faceBlock)}</div>
        <div className="net-row net-bottom">{layout[3].map(faceBlock)}</div>
      </div>

      <p className="net-hint">
        Elige un color arriba y haz clic en cada pegatina. El centro de cada cara
        define su color; respeta los colores de tu cubo real.
      </p>
    </div>
  );
}
