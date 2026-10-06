"""GEÇİCİ araç — gerçek çözücü ve üretici yazılınca silinecek.

Amacı sadece arayüzü test edebilmek için tekliği kanıtlanmış birkaç bulmaca
üretmek. Yöntem kaba kuvvet: rastgele bir duvar çiz, ipucuları ondan türet,
çözüm sayısını say, tek çözüm kalana kadar ipucu ele.

Çalıştırma: python -m tools.make_puzzles
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import Board, Cell, rules, save_json, to_code, validate_partial, validate_solution


# ---------------------------------------------------------------------- #
# Çözüm sayma (kaba kuvvet + yayılım)
# ---------------------------------------------------------------------- #

def _propagate(board: Board) -> bool:
    """Zorunlu hücreleri doyuma kadar uygular. Çelişki bulursa False."""
    while True:
        if not validate_partial(board).ok:
            return False
        deductions = rules.forced_cells(board)
        new = {p: s for p, s in deductions.items() if board.get_cell(*p) is Cell.UNKNOWN}
        if not new:
            return True
        for pos, state in new.items():
            board.set_cell(*pos, state)


def _branch_cell(board: Board) -> tuple[int, int] | None:
    """En kısıtlı belirsiz hücre: önce bir ipucunun komşusu olanlar."""
    unknown = board.unknown_cells()
    if not unknown:
        return None
    near_clue = {
        p for (r, c) in board.clues for p in board.ring(r, c)
        if p is not None and p in unknown
    }
    return min(near_clue or unknown)


def count_solutions(board: Board, limit: int = 2) -> int:
    """En fazla `limit` çözüm sayar (teklik kontrolü için 2 yeter)."""
    work = board.copy()
    if not _propagate(work):
        return 0
    cell = _branch_cell(work)
    if cell is None:
        return 1 if validate_solution(work).ok else 0

    total = 0
    for state in (Cell.FILLED, Cell.EMPTY):
        trial = work.copy()
        trial.set_cell(*cell, state)
        total += count_solutions(trial, limit - total)
        if total >= limit:
            break
    return total


# ---------------------------------------------------------------------- #
# Üretim
# ---------------------------------------------------------------------- #

def random_wall(rows: int, cols: int, rng: random.Random) -> set[tuple[int, int]]:
    """2x2 içermeyen, tek parça rastgele duvar."""
    board = Board(rows, cols)
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    rng.shuffle(cells)
    for (r, c) in cells:
        board.set_cell(r, c, Cell.FILLED)
        if rules.square_violations(board):
            board.set_cell(r, c, Cell.EMPTY)
    groups = rules.wall_components(board)
    return max(groups, key=len) if groups else set()


def build_puzzle(rows: int, cols: int, rng: random.Random) -> tuple[Board, set] | None:
    wall = random_wall(rows, cols, rng)
    if not 0.35 * rows * cols < len(wall) < 0.65 * rows * cols:
        return None

    solved = Board(rows, cols)
    for pos in wall:
        solved.set_cell(*pos, Cell.FILLED)

    free = [p for p in solved.positions() if p not in wall]
    if not free:
        return None

    # Her hücrenin en az bir ipucunun görüş alanında olması gerekiyor; aksi
    # hâlde o hücre serbest kalır ve bulmaca tek çözümlü olamaz.
    uncovered = set(solved.positions())
    chosen: list[tuple[int, int]] = []
    rng.shuffle(free)
    for pos in free:
        covers = {p for p in solved.ring(*pos) if p is not None} & uncovered
        if covers or pos in uncovered:
            chosen.append(pos)
            uncovered -= covers
            uncovered.discard(pos)
    if uncovered:
        return None

    clues = {pos: rules.runs_pattern(rules.ring_states(solved, *pos)) for pos in chosen}
    try:
        puzzle = Board(rows, cols, clues)
    except Exception:
        return None

    if count_solutions(puzzle) != 1:
        return None

    # İpucu sayısını azalt: tekliği bozmayan her ipucuyu çıkar.
    order = list(chosen)
    rng.shuffle(order)
    for pos in order:
        trial = Board(rows, cols, {p: v for p, v in clues.items() if p != pos})
        if count_solutions(trial) == 1:
            del clues[pos]
    return Board(rows, cols, clues), wall


def main() -> None:
    rng = random.Random(7)
    targets = [(6, 6, "kolay-6x6"), (7, 7, "orta-7x7"), (8, 8, "zor-8x8")]
    for rows, cols, name in targets:
        for attempt in range(400):
            built = build_puzzle(rows, cols, rng)
            if built is None:
                continue
            board, wall = built
            for pos in wall:
                board.set_cell(*pos, Cell.FILLED)
            assert validate_solution(board).ok, "çözüm kurallara uymuyor"
            board.clear_marks()
            save_json(
                board,
                Path(__file__).resolve().parents[1] / "puzzles" / f"{name}.json",
                meta={"baslik": name, "kaynak": "otomatik uretim", "tekCozum": True},
            )
            print(f"{name}: {len(board.clues)} ipucu  |  {to_code(board)}")
            break
        else:
            print(f"{name}: üretilemedi")


if __name__ == "__main__":
    main()
