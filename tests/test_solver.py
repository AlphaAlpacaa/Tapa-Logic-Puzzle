"""Çözücü testleri. Çalıştırmak için: python -m tests.test_solver

En önemlisi `test_deductions_are_sound`. Hatalı bir teknik, çelişki üretmek
yerine sessizce yanlış hücre yerleştirir ve bu hata üreticiye, oradan da
bulmaca kütüphanesine sızar. Bu yüzden her çıkarım, bilinen gerçek çözümle
karşılaştırılıyor.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import Board, Cell, from_dict, rules, validate_solution  # noqa: E402
from engine import solver  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"BAŞARISIZ: {label}")
    PASSED += 1


def random_wall(rows: int, cols: int, rng: random.Random) -> set[tuple[int, int]]:
    board = Board(rows, cols)
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    rng.shuffle(cells)
    for (r, c) in cells:
        board.set_cell(r, c, Cell.FILLED)
        if rules.square_violations(board):
            board.set_cell(r, c, Cell.EMPTY)
    groups = rules.wall_components(board)
    return max(groups, key=len) if groups else set()


def puzzle_from_wall(rows: int, cols: int, wall: set[tuple[int, int]],
                     clue_cells: list[tuple[int, int]]) -> Board:
    solved = Board(rows, cols)
    for pos in wall:
        solved.set_cell(*pos, Cell.FILLED)
    clues = {pos: rules.runs_pattern(rules.ring_states(solved, *pos)) for pos in clue_cells}
    return Board(rows, cols, clues)


# ---------------------------------------------------------------------- #
# Sağlamlık: hiçbir teknik yanlış hücre yerleştirmemeli
# ---------------------------------------------------------------------- #

def test_deductions_are_sound() -> None:
    """Her çıkarım, bulmacanın türetildiği gerçek çözümle uyuşmalı.

    Bu, bulmaca birden çok çözümlü olsa bile geçerli bir ölçüt: kesin bir
    çıkarım TÜM çözümlerde doğru olmak zorundadır, dolayısıyla üretimde
    kullandığımız çözümde de doğru olmalıdır.
    """
    rng = random.Random(1907)
    checked = 0
    for _ in range(30):
        rows, cols = rng.randint(5, 8), rng.randint(5, 8)
        wall = random_wall(rows, cols, rng)
        free = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in wall]
        if len(wall) < 5 or len(free) < 4:
            continue

        clue_cells = rng.sample(free, k=max(2, len(free) // 2))
        puzzle = puzzle_from_wall(rows, cols, wall, clue_cells)

        work, stats = solver.solve_logically(puzzle)
        for pos in work.positions():
            if puzzle.is_clue(*pos):
                continue
            state = work.get_cell(*pos)
            if state is Cell.UNKNOWN:
                continue
            expected = Cell.FILLED if pos in wall else Cell.EMPTY
            check(state is expected, f"{pos} hücresi yanlış çıkarıldı ({stats.technique_use})")
        checked += 1
    check(checked >= 10, f"yeterli örnek üretilemedi ({checked})")


# ---------------------------------------------------------------------- #
# Tekil teknikler
# ---------------------------------------------------------------------- #

def test_square_rule() -> None:
    board = Board(4, 4)
    for pos in [(0, 0), (0, 1), (1, 0)]:
        board.set_cell(*pos, Cell.FILLED)
    found = solver.square_rule(board)
    check(found.get((1, 1)) is Cell.EMPTY, "2x2'nin dördüncü hücresi boşa zorlanır")


def test_unreachable_cells() -> None:
    board = Board(5, 5)
    board.set_cell(0, 0, Cell.FILLED)
    # Sağ alt köşeyi duvardan tamamen ayır.
    for pos in [(3, 3), (3, 4), (4, 3)]:
        board.set_cell(*pos, Cell.EMPTY)
    found = solver.unreachable_cells(board)
    check(found.get((4, 4)) is Cell.EMPTY, "çevresi kapalı hücre duvara bağlanamaz")


def test_connection_bottleneck() -> None:
    board = Board(3, 3)
    board.set_cell(0, 0, Cell.FILLED)
    board.set_cell(0, 2, Cell.FILLED)
    for pos in [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]:
        board.set_cell(*pos, Cell.EMPTY)
    found = solver.connection_bottleneck(board)
    check(found.get((0, 1)) is Cell.FILLED, "tek bağlantı yolu dolu olmak zorunda")


# ---------------------------------------------------------------------- #
# Çözüm ve teklik
# ---------------------------------------------------------------------- #

def test_contradiction_reasoning_is_sound() -> None:
    """Varsayım tekniği yalnızca gerçekten kanıtlanmış hücreleri döndürmeli."""
    rng = random.Random(2024)
    checked = 0
    for _ in range(40):
        rows, cols = rng.randint(5, 8), rng.randint(5, 8)
        wall = random_wall(rows, cols, rng)
        free = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in wall]
        if len(wall) < 5 or len(free) < 4:
            continue
        clue_cells = rng.sample(free, k=max(2, len(free) // 2))
        puzzle = puzzle_from_wall(rows, cols, wall, clue_cells)

        # Kısmen çözülmüş bir tahtada teknik devreye girsin.
        work = puzzle.copy()
        solver.propagate(work, solver.SolveStats(), max_level=2)
        for pos, state in solver.contradiction_reasoning(work).items():
            expected = Cell.FILLED if pos in wall else Cell.EMPTY
            check(state is expected, f"{pos} için varsayım tekniği yanlış sonuç verdi")
        checked += 1
    check(checked >= 10, f"yeterli örnek üretilemedi ({checked})")


def test_library_puzzles() -> None:
    for path in sorted((ROOT / "puzzles").glob("*.json")):
        board = from_dict(json.loads(path.read_text(encoding="utf-8")))
        result = solver.solve(board, limit=2)
        check(result.count == 1, f"{path.stem} tek çözümlü olmalı ({result.count} bulundu)")
        check(validate_solution(result.solutions[0]).ok, f"{path.stem} çözümü kurallara uymalı")


def test_no_solution_detected() -> None:
    # (2,2) tüm sekiz komşusunun dolu olmasını istiyor, ama komşularından biri
    # olan (1,1) bir ipucu hücresi ve ipucu hücreleri boyanamaz.
    board = Board(4, 4)
    board.set_clue(1, 1, [0])
    board.set_clue(2, 2, [8])
    result = solver.solve(board, limit=2)
    check(result.count == 0, "sağlanamayan ipucu çözümsüz olmalı")


def test_rating() -> None:
    board = from_dict(json.loads((ROOT / "puzzles" / "kolay-6x6.json").read_text(encoding="utf-8")))
    rating = solver.rate(board)
    check(rating.unique, "kütüphane bulmacası tek çözümlü")
    check(rating.logic_only, "varsayım gerekmemeli")
    check(rating.label in solver.LEVEL_LABELS.values(), "etiket tanımlı olmalı")


def test_next_step_explains() -> None:
    board = Board(5, 5)
    board.set_clue(2, 2, [0])
    step = solver.next_step(board)
    check(step is not None, "0 ipucusu bir adım üretmeli")
    assert step is not None
    check(step.state is Cell.EMPTY, "adım boş hücre göstermeli")
    check(step.technique.level == 1, "en ucuz teknik kullanılmalı")


def main() -> None:
    tests = [
        test_deductions_are_sound,
        test_contradiction_reasoning_is_sound,
        test_square_rule,
        test_unreachable_cells,
        test_connection_bottleneck,
        test_library_puzzles,
        test_no_solution_detected,
        test_rating,
        test_next_step_explains,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")
    print(f"\n{len(tests)} test grubu, {PASSED} kontrol başarılı.")


if __name__ == "__main__":
    main()
