"""Kural motorunun testleri. Çalıştırmak için: python -m tests.test_engine"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import (  # noqa: E402
    Board,
    Cell,
    ClueError,
    forced_cells,
    from_code,
    from_dict,
    runs_pattern,
    to_code,
    to_dict,
    validate_partial,
    validate_solution,
)
from engine.rules import ring_states, square_violations, wall_is_connected  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"BAŞARISIZ: {label}")
    PASSED += 1


def ring(*filled_indices: int) -> list[Cell]:
    """Test kolaylığı: verilen indekslerdeki komşular dolu, kalanı boş."""
    return [Cell.FILLED if i in filled_indices else Cell.EMPTY for i in range(8)]


# ---------------------------------------------------------------------- #
# K2 — halka deseni
# ---------------------------------------------------------------------- #

def test_runs_pattern() -> None:
    check(runs_pattern(ring()) == (0,), "boş halka -> 0")
    check(runs_pattern(ring(*range(8))) == (8,), "tam dolu halka -> 8")
    check(runs_pattern(ring(0, 1, 2)) == (3,), "ardışık üçlü blok")
    check(runs_pattern(ring(0, 4)) == (1, 1), "karşılıklı iki tekli blok")
    check(runs_pattern(ring(7, 0, 1)) == (3,), "başa saran blok tek blok sayılır")
    check(runs_pattern(ring(0, 1, 3, 4, 5)) == (3, 2), "iki blok büyükten küçüğe sıralanır")
    check(runs_pattern(ring(0, 2, 4, 6)) == (1, 1, 1, 1), "dört ayrı tekli blok")
    # Sıralama önemsizdir: 1 2 ile 2 1 aynı ipucudur.
    check(runs_pattern(ring(0, 2, 3)) == runs_pattern(ring(0, 1, 3)), "sıra önemsiz")
    # Belirsiz hücreler tam değerlendirmede boş sayılır.
    states = ring(0, 1)
    states[4] = Cell.UNKNOWN
    check(runs_pattern(states) == (2,), "UNKNOWN boş kabul edilir")


# ---------------------------------------------------------------------- #
# İpucu doğrulama ve geometri
# ---------------------------------------------------------------------- #

def test_clue_validation() -> None:
    board = Board(5, 5)
    board.set_clue(2, 2, [1, 2])
    check(board.clue_at(2, 2) == (2, 1), "ipucu büyükten küçüğe normalleştirilir")

    try:
        board.set_clue(0, 0, [4])       # köşede yalnızca 3 komşu var
        check(False, "köşeye sığmayan ipucu reddedilmeli")
    except ClueError:
        check(True, "köşeye sığmayan ipucu reddedildi")

    try:
        board.set_clue(0, 0, [1, 1])    # 3 komşuya iki blok + boşluk = 3, sığar
        check(True, "köşeye sığan çok bloklu ipucu kabul edildi")
    except ClueError:
        check(False, "köşeye sığan ipucu reddedilmemeli")

    try:
        board.set_clue(2, 4, [0, 1])
        check(False, "0 başka sayıyla birlikte kullanılamaz")
    except ClueError:
        check(True, "0 + başka sayı reddedildi")

    try:
        board.set_cell(2, 2, Cell.FILLED)
        check(False, "ipucu hücresi boyanamamalı")
    except ValueError:
        check(True, "ipucu hücresi boyanamaz")


# ---------------------------------------------------------------------- #
# K3, K4 ve bütünsel doğrulama
# ---------------------------------------------------------------------- #

def test_square_and_connectivity() -> None:
    board = Board(4, 4)
    for pos in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        board.set_cell(*pos, Cell.FILLED)
    check(len(square_violations(board)) == 1, "2x2 dolu alan tespit edilir")

    board = Board(4, 4)
    board.set_cell(0, 0, Cell.FILLED)
    board.set_cell(3, 3, Cell.FILLED)
    check(not wall_is_connected(board), "ayrık iki hücre bağlı değildir")
    board = Board(4, 4)
    for pos in [(0, 0), (0, 1), (0, 2)]:
        board.set_cell(*pos, Cell.FILLED)
    check(wall_is_connected(board), "yatay şerit bağlıdır")

    board = Board(4, 4)
    board.set_cell(0, 0, Cell.FILLED)
    board.set_cell(1, 1, Cell.FILLED)
    check(not wall_is_connected(board), "çapraz komşuluk bağlantı saymaz")


def test_forced_deductions() -> None:
    board = Board(5, 5)
    board.set_clue(2, 2, [0])
    deductions = forced_cells(board)
    check(len(deductions) == 8, "0 ipucusu 8 komşuyu da boşa zorlar")
    check(all(state is Cell.EMPTY for state in deductions.values()), "hepsi boş olmalı")

    board = Board(3, 3)
    board.set_clue(1, 1, [8])
    deductions = forced_cells(board)
    check(len(deductions) == 8 and all(s is Cell.FILLED for s in deductions.values()),
          "8 ipucusu tüm komşuları doldurmaya zorlar")


# ---------------------------------------------------------------------- #
# Rastgele çözümlerden türetilmiş bulmacalarla tutarlılık
# ---------------------------------------------------------------------- #

def random_wall(rows: int, cols: int, rng: random.Random) -> set[tuple[int, int]]:
    """Kurallara uygun (2x2 yok, tek parça) rastgele bir duvar üretir."""
    board = Board(rows, cols)
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    rng.shuffle(cells)
    wall: set[tuple[int, int]] = set()
    for (r, c) in cells:
        wall.add((r, c))
        board.set_cell(r, c, Cell.FILLED)
        if square_violations(board):
            wall.discard((r, c))
            board.set_cell(r, c, Cell.EMPTY)
    # En büyük bağlı bileşeni duvar olarak al.
    from engine.rules import wall_components
    groups = wall_components(board)
    if not groups:
        return set()
    return max(groups, key=len)


def test_generated_puzzles() -> None:
    rng = random.Random(20251005)
    for trial in range(40):
        rows, cols = rng.randint(4, 8), rng.randint(4, 8)
        wall = random_wall(rows, cols, rng)
        if len(wall) < 4:
            continue
        free = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in wall]
        if not free:
            continue

        # Çözümden ipucuları türet.
        solved = Board(rows, cols)
        for pos in wall:
            solved.set_cell(*pos, Cell.FILLED)

        clue_cells = rng.sample(free, k=max(1, len(free) // 3))
        clues = {(r, c): runs_pattern(ring_states(solved, r, c)) for (r, c) in clue_cells}

        puzzle = Board(rows, cols, clues)
        for pos in wall:
            puzzle.set_cell(*pos, Cell.FILLED)
        for pos in free:
            if not puzzle.is_clue(*pos):
                puzzle.set_cell(*pos, Cell.EMPTY)

        result = validate_solution(puzzle)
        check(result.ok, f"üretilen çözüm {trial}. denemede geçerli olmalı: {result.issues}")

        # Bir ipucunun komşusu olan dolu hücreyi silmek mutlaka hata üretmeli.
        # (İpuçlarından uzaktaki bir hücreyi silmek geçerli bir başka çözüm
        # verebilir; bu yüzden kurban ipucu komşuları arasından seçilir.)
        watched = {
            p for (r, c) in clue_cells for p in puzzle.ring(r, c)
            if p is not None and p in wall
        }
        if watched:
            broken = puzzle.copy()
            victim = rng.choice(sorted(watched))
            broken.set_cell(*victim, Cell.EMPTY)
            check(not validate_solution(broken).ok, "bozulan çözüm reddedilmeli")


def test_partial_validation() -> None:
    board = Board(5, 5)
    board.set_clue(2, 2, [0])
    check(validate_partial(board).ok, "boş tahtada çelişki yok")
    board.set_cell(1, 1, Cell.FILLED)
    result = validate_partial(board)
    check(not result.ok, "0 ipucusunun yanına dolu hücre konamaz")
    check((2, 2) in result.error_cells, "hatalı hücre bildirilir")


# ---------------------------------------------------------------------- #
# Serileştirme
# ---------------------------------------------------------------------- #

def test_serialization() -> None:
    board = Board(4, 6, {(0, 1): [3], (2, 3): [1, 2], (3, 5): [1]})
    code = to_code(board)
    check(from_code(code).clues == board.clues, "kısa kod gidiş-dönüş")
    check(from_dict(to_dict(board)).clues == board.clues, "JSON gidiş-dönüş")
    check(code.startswith("4x6/"), f"kod başlığı doğru: {code}")
    check("(21)" in code, f"çok sayılı ipucu parantezle yazılır: {code}")

    rebuilt = from_code("4x6/.3..../....../...(21)../.....1")
    check(rebuilt.clues == board.clues, "elle yazılmış kod okunur")


def main() -> None:
    tests = [
        test_runs_pattern,
        test_clue_validation,
        test_square_and_connectivity,
        test_forced_deductions,
        test_generated_puzzles,
        test_partial_validation,
        test_serialization,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")
    print(f"\n{len(tests)} test grubu, {PASSED} kontrol başarılı.")


if __name__ == "__main__":
    main()
