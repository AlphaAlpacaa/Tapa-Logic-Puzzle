import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  CellState,
  Difficulty,
  HintResponse,
  Puzzle,
  PuzzleSummary,
  ValidateResponse,
} from "./api";
import { Board, key } from "./components/Board";
import { Editor } from "./components/Editor";
import { Sidebar } from "./components/Sidebar";

/** Her hamlenin zaman damgası. Zorluk ayarı ve ileride insan çözücü
 *  modellemesi için tek toplanabilir veri bu; sonradan geri kazanılamaz. */
interface Move {
  t: number;
  r: number;
  c: number;
  from: CellState;
  to: CellState;
}

const blankGrid = (puzzle: Puzzle): CellState[][] =>
  Array.from({ length: puzzle.rows }, () => Array<CellState>(puzzle.cols).fill(0));

export default function App() {
  const [library, setLibrary] = useState<PuzzleSummary[]>([]);
  const [puzzle, setPuzzle] = useState<Puzzle | null>(null);
  const [grid, setGrid] = useState<CellState[][]>([]);
  const [history, setHistory] = useState<CellState[][][]>([]);
  const [validation, setValidation] = useState<ValidateResponse | null>(null);
  const [hint, setHint] = useState<HintResponse | null>(null);
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null);
  const [live, setLive] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"play" | "edit">("play");

  const moves = useRef<Move[]>([]);
  const startedAt = useRef<number>(Date.now());

  // --- yükleme -------------------------------------------------------- //

  useEffect(() => {
    api
      .listPuzzles()
      .then((items) => {
        setLibrary(items);
        if (items.length) void openPuzzle(items[0].id);
      })
      .catch((error: Error) =>
        setNotice(`Sunucuya ulaşılamadı. uvicorn çalışıyor mu? (${error.message})`),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const install = (next: Puzzle) => {
    setPuzzle(next);
    setGrid(blankGrid(next));
    setHistory([]);
    setValidation(null);
    setHint(null);
    setNotice(null);
    moves.current = [];
    startedAt.current = Date.now();

    // Zorluk ölçümü çözücüyü çalıştırır; arayüzü bekletmemek için arka planda.
    setDifficulty(null);
    api.difficulty(next).then(setDifficulty).catch(() => undefined);
  };

  const openPuzzle = async (id: string) => {
    try {
      install(await api.getPuzzle(id));
    } catch (error) {
      setNotice((error as Error).message);
    }
  };

  const openCode = async (code: string) => {
    try {
      install(await api.fromCode(code));
    } catch (error) {
      setNotice((error as Error).message);
    }
  };

  // --- hamleler ------------------------------------------------------- //

  const paint = useCallback(
    (r: number, c: number, state: CellState) => {
      setGrid((current) => {
        if (current[r][c] === state) return current;
        setHistory((stack) => [...stack.slice(-199), current]);
        moves.current.push({
          t: Date.now() - startedAt.current,
          r,
          c,
          from: current[r][c],
          to: state,
        });
        const next = current.map((row) => row.slice());
        next[r][c] = state;
        return next;
      });
      setHint(null);
    },
    [],
  );

  const undo = () => {
    setHistory((stack) => {
      if (!stack.length) return stack;
      setGrid(stack[stack.length - 1]);
      return stack.slice(0, -1);
    });
  };

  const clear = () => {
    if (!puzzle) return;
    setHistory((stack) => [...stack, grid]);
    setGrid(blankGrid(puzzle));
    setValidation(null);
    setHint(null);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // --- doğrulama ------------------------------------------------------ //

  useEffect(() => {
    if (!puzzle || !live || !grid.length) return;
    const timer = setTimeout(() => {
      api
        .validate(puzzle, grid, "partial")
        .then(setValidation)
        .catch(() => undefined);
    }, 220);
    return () => clearTimeout(timer);
  }, [puzzle, grid, live]);

  const check = async () => {
    if (!puzzle) return;
    setBusy(true);
    try {
      setValidation(await api.validate(puzzle, grid, "solution"));
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const askHint = async () => {
    if (!puzzle) return;
    setBusy(true);
    try {
      const response = await api.hint(puzzle, grid);
      setHint(response);
      if (response.found && response.cell && response.state !== undefined) {
        paint(response.cell[0], response.cell[1], response.state);
        setHint(response); // paint ipucuyu siliyor, geri koy
      }
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const revealSolution = async () => {
    if (!puzzle) return;
    setBusy(true);
    try {
      const response = await api.solve(puzzle);
      if (response.grid) {
        setHistory((stack) => [...stack, grid]);
        setGrid(response.grid);
        setHint(null);
      } else {
        setNotice("Bu bulmacanın çözümü yok.");
      }
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const downloadLog = () => {
    if (!puzzle) return;
    const payload = {
      puzzle: puzzle.id ?? puzzle.code,
      rows: puzzle.rows,
      cols: puzzle.cols,
      code: puzzle.code,
      startedAt: new Date(startedAt.current).toISOString(),
      durationMs: Date.now() - startedAt.current,
      solved: validation?.solved ?? false,
      moves: moves.current,
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `tapa-kayit-${Date.now()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const errorCells = useMemo(() => {
    const cells = new Set<string>();
    for (const issue of validation?.issues ?? []) {
      for (const [r, c] of issue.cells) cells.add(key(r, c));
    }
    return cells;
  }, [validation]);

  const solved = validation?.solved ?? false;

  return (
    <div className="shell">
      <header className="bar">
        <h1 className="wordmark">tapa</h1>
        <div className="bar__modes">
          <button
            className={mode === "play" ? "is-open" : ""}
            onClick={() => setMode("play")}
          >
            Oyna
          </button>
          <button
            className={mode === "edit" ? "is-open" : ""}
            onClick={() => setMode("edit")}
          >
            Düzenle
          </button>
        </div>
        <div className="bar__actions">
          <button onClick={check} disabled={mode !== "play" || !puzzle || busy}>
            Kontrol et
          </button>
          <button onClick={askHint} disabled={mode !== "play" || !puzzle || busy}>
            Bir hücre göster
          </button>
          <button onClick={undo} disabled={mode !== "play" || !history.length}>
            Geri al
          </button>
          <button onClick={clear} disabled={mode !== "play" || !puzzle}>
            Tahtayı boşalt
          </button>
          <button onClick={revealSolution} disabled={mode !== "play" || !puzzle || busy}>
            Çözümü göster
          </button>
        </div>
      </header>

      {mode === "edit" ? <Editor /> : (
      <main className="stage">
        <div className="stage__board">
          {puzzle ? (
            <Board
              puzzle={puzzle}
              grid={grid}
              errorCells={errorCells}
              hintCell={hint?.found && hint.cell ? hint.cell : null}
              onPaint={paint}
            />
          ) : (
            <p className="placeholder">Bulmaca yükleniyor…</p>
          )}
          {solved && <p className="solved">Çözüldü. Duvar tek parça, bütün ipuçları tutuyor.</p>}
        </div>

        <Sidebar
          library={library}
          puzzle={puzzle}
          validation={validation}
          hint={hint}
          difficulty={difficulty}
          live={live}
          notice={notice}
          moveCount={moves.current.length}
          onOpen={openPuzzle}
          onCode={openCode}
          onToggleLive={() => setLive((value) => !value)}
          onDownloadLog={downloadLog}
        />
      </main>
      )}
    </div>
  );
}
