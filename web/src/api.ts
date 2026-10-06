export type CellState = 0 | 1 | 2; // 0 bilinmiyor, 1 dolu, 2 boş

export interface Clue {
  r: number;
  c: number;
  values: number[];
}

export interface Puzzle {
  id: string | null;
  rows: number;
  cols: number;
  clues: Clue[];
  code: string;
  meta: Record<string, unknown>;
}

export interface PuzzleSummary {
  id: string;
  rows: number;
  cols: number;
  clueCount: number;
  meta: Record<string, unknown>;
}

export interface Issue {
  code: string;
  message: string;
  cells: [number, number][];
}

export interface ValidateResponse {
  ok: boolean;
  mode: "partial" | "solution";
  solved: boolean;
  issues: Issue[];
}

export interface HintResponse {
  found: boolean;
  reason: string;
  cell?: [number, number];
  state?: CellState;
  technique?: string;
}

export interface SolveResponse {
  solved: boolean;
  unique: boolean;
  count: number;
  grid: CellState[][] | null;
  stats: { nodes: number; guesses: number; deductions: number; elapsed: number };
}

export interface Difficulty {
  label: string;
  maxLevel: number;
  logicOnly: boolean;
  guesses: number;
  deductions: number;
  techniques: Record<string, number>;
  unique: boolean;
  elapsed: number;
}

async function send<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Sunucu ${response.status} döndü.`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listPuzzles: () => send<PuzzleSummary[]>("/puzzles"),
  getPuzzle: (id: string) => send<Puzzle>(`/puzzles/${encodeURIComponent(id)}`),
  fromCode: (code: string) => send<Puzzle>("/puzzles/from-code", { code }),
  validate: (puzzle: Puzzle, grid: CellState[][], mode: "partial" | "solution") =>
    send<ValidateResponse>("/validate", {
      rows: puzzle.rows,
      cols: puzzle.cols,
      clues: puzzle.clues,
      grid,
      mode,
    }),
  hint: (puzzle: Puzzle, grid: CellState[][]) =>
    send<HintResponse>("/hint", {
      rows: puzzle.rows,
      cols: puzzle.cols,
      clues: puzzle.clues,
      grid,
      mode: "partial",
    }),
  solve: (puzzle: Puzzle) =>
    send<SolveResponse>("/solve", {
      rows: puzzle.rows,
      cols: puzzle.cols,
      clues: puzzle.clues,
    }),
  difficulty: (puzzle: Puzzle) =>
    send<Difficulty>("/difficulty", {
      rows: puzzle.rows,
      cols: puzzle.cols,
      clues: puzzle.clues,
    }),
};
