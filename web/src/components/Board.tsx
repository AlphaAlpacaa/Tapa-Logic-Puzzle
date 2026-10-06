import { useCallback, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from "react";
import type { CellState, Clue, Puzzle } from "../api";

interface Props {
  puzzle: Puzzle;
  grid: CellState[][];
  errorCells: Set<string>;
  hintCell: [number, number] | null;
  onPaint: (r: number, c: number, state: CellState) => void;
}

export const key = (r: number, c: number) => `${r},${c}`;

/** İpucu rakamlarının hücre içindeki yerleşimi — gerçek Tapa dizgisini izler. */
function clueSlots(count: number): string[] {
  switch (count) {
    case 1:
      return ["center"];
    case 2:
      return ["tl", "br"];
    case 3:
      return ["tl", "tr", "bc"];
    default:
      return ["tl", "tr", "bl", "br"];
  }
}

export function Board({ puzzle, grid, errorCells, hintCell, onPaint }: Props) {
  const clueMap = new Map<string, Clue>();
  for (const clue of puzzle.clues) clueMap.set(key(clue.r, clue.c), clue);

  const [focus, setFocus] = useState<[number, number]>([0, 0]);
  const painting = useRef<CellState | null>(null);

  const isFilled = (r: number, c: number) =>
    r >= 0 && c >= 0 && r < puzzle.rows && c < puzzle.cols && grid[r][c] === 1;

  /** Sol tık doldurur, sağ tık "kesin boş" noktası koyar; aynı hamle geri alır. */
  const nextState = (current: CellState, right: boolean): CellState => {
    if (right) return current === 2 ? 0 : 2;
    return current === 1 ? 0 : 1;
  };

  const begin = useCallback(
    (r: number, c: number, right: boolean) => {
      if (clueMap.has(key(r, c))) return;
      const target = nextState(grid[r][c], right);
      painting.current = target;
      onPaint(r, c, target);
    },
    [grid, onPaint, clueMap],
  );

  const extend = (r: number, c: number) => {
    if (painting.current === null || clueMap.has(key(r, c))) return;
    if (grid[r][c] !== painting.current) onPaint(r, c, painting.current);
  };

  const onKeyDown = (event: ReactKeyboardEvent) => {
    const [r, c] = focus;
    const moves: Record<string, [number, number]> = {
      ArrowUp: [r - 1, c],
      ArrowDown: [r + 1, c],
      ArrowLeft: [r, c - 1],
      ArrowRight: [r, c + 1],
    };
    if (moves[event.key]) {
      event.preventDefault();
      const [nr, nc] = moves[event.key];
      if (nr >= 0 && nc >= 0 && nr < puzzle.rows && nc < puzzle.cols) setFocus([nr, nc]);
      return;
    }
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      if (!clueMap.has(key(r, c))) onPaint(r, c, nextState(grid[r][c], false));
    }
    if (event.key.toLowerCase() === "x") {
      event.preventDefault();
      if (!clueMap.has(key(r, c))) onPaint(r, c, nextState(grid[r][c], true));
    }
  };

  return (
    <div
      className="board"
      role="grid"
      aria-label={`${puzzle.rows}'e ${puzzle.cols} Tapa tahtası`}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerUp={() => (painting.current = null)}
      onPointerLeave={() => (painting.current = null)}
      onContextMenu={(event) => event.preventDefault()}
      style={{ "--cols": puzzle.cols, "--rows": puzzle.rows } as CSSProperties}
    >
      {grid.map((row, r) =>
        row.map((state, c) => {
          const clue = clueMap.get(key(r, c));
          const filled = state === 1;
          const classes = ["cell"];
          if (clue) classes.push("cell--clue");
          else if (filled) classes.push("cell--filled");
          else if (state === 2) classes.push("cell--empty");
          // Bitişik dolu hücreler arasındaki çizgi duvarın rengine boyanır:
          // duvar tek bir sürekli şekil olarak görünür, bağlantılılık gözle okunur.
          if (filled && isFilled(r, c + 1)) classes.push("join-right");
          if (filled && isFilled(r + 1, c)) classes.push("join-down");
          if (errorCells.has(key(r, c))) classes.push("cell--error");
          if (hintCell && hintCell[0] === r && hintCell[1] === c) classes.push("cell--hint");
          if (focus[0] === r && focus[1] === c) classes.push("cell--focus");

          return (
            <div
              key={key(r, c)}
              className={classes.join(" ")}
              role="gridcell"
              aria-label={
                clue
                  ? `${r + 1}. satır ${c + 1}. sütun, ipucu ${clue.values.join(" ")}`
                  : `${r + 1}. satır ${c + 1}. sütun, ${
                      filled ? "dolu" : state === 2 ? "boş" : "belirsiz"
                    }`
              }
              onPointerDown={(event) => {
                setFocus([r, c]);
                begin(r, c, event.button === 2);
              }}
              onPointerEnter={() => extend(r, c)}
            >
              {clue && (
                <div className={`clue clue--${clue.values.length}`}>
                  {clue.values.map((value, index) => (
                    <span key={index} className={`clue__n clue__n--${clueSlots(clue.values.length)[index]}`}>
                      {value}
                    </span>
                  ))}
                </div>
              )}
              {state === 2 && !clue && <span className="dot" />}
            </div>
          );
        }),
      )}
    </div>
  );
}
