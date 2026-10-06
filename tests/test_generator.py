"""Üretici testleri. Çalıştırmak için: python -m tests.test_generator

Veri kümesinin tamamı denetlenir. Bozuk bir bulmaca sessizce eğitim verisine
karışırsa, modelin neden öğrenemediğini aylarca aramak mümkündür.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import Board, Cell, apply_solution_rows, from_code, solver  # noqa: E402
from engine import generator, validate_solution  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"BAŞARISIZ: {label}")
    PASSED += 1


# ---------------------------------------------------------------------- #
# Duvar inşası
# ---------------------------------------------------------------------- #

def test_grown_walls_are_legal() -> None:
    from engine.rules import square_violations, wall_components

    rng = random.Random(5)
    for _ in range(60):
        rows, cols = rng.randint(4, 12), rng.randint(4, 12)
        target = round(rows * cols * rng.choice([0.35, 0.5, 0.65]))
        wall = generator.grow_wall(rows, cols, target, rng)
        board = Board(rows, cols)
        for pos in wall:
            board.set_cell(*pos, Cell.FILLED)
        check(not square_violations(board), "büyütülen duvarda 2x2 olmamalı")
        check(len(wall_components(board)) <= 1, "büyütülen duvar tek parça olmalı")


# ---------------------------------------------------------------------- #
# Zorluk hedefi tutuyor mu
# ---------------------------------------------------------------------- #

def test_difficulty_target() -> None:
    """İzin verilen seviye aşılmamalı; `exact_level` ise tam tutmalı."""
    rng = random.Random(77)
    for level in (1, 2, 3, 4):
        item = generator.generate(7, 7, rng, wall_density=0.5, max_level=level, attempts=30)
        check(item is not None, f"seviye {level} için bulmaca üretilmeli")
        assert item is not None
        check(item.difficulty.logic_only, "üretilen bulmaca kör tahmin gerektirmemeli")
        check(item.difficulty.unique, "üretilen bulmaca tek çözümlü olmalı")
        check(
            item.difficulty.max_level <= level,
            f"seviye {level} istendi, {item.difficulty.max_level} gerekti",
        )

    for level in (1, 2, 3, 4):
        item = generator.generate(7, 7, rng, wall_density=0.5, max_level=level,
                                  exact_level=True, attempts=60)
        if item is None:
            continue  # kesin seviye her denemede tutmayabilir
        check(
            item.difficulty.max_level == level,
            f"kesin seviye {level} istendi, {item.difficulty.max_level} çıktı",
        )


# ---------------------------------------------------------------------- #
# Veri kümesinin tamamı
# ---------------------------------------------------------------------- #

def test_dataset_integrity() -> None:
    path = ROOT / "dataset" / "puzzles.jsonl"
    if not path.is_file():
        print("    (veri kümesi yok, atlandı — python -m tools.build_dataset)")
        return

    codes: set[str] = set()
    walls: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            record = json.loads(line)
            board = from_code(record["code"])
            check(board.rows == record["rows"] and board.cols == record["cols"],
                  f"{line_no}. satır: kısa kod boyutla uyuşmalı")

            # Kayıtlı çözüm gerçekten geçerli mi?
            solved = board.copy()
            apply_solution_rows(solved, record["solution"])
            check(validate_solution(solved).ok, f"{line_no}. satır: kayıtlı çözüm kurallara uymalı")

            # Mantıkla çözülebilmeli ve bulunan çözüm kayıtlıyla aynı olmalı.
            logical, _ = solver.solve_logically(board)
            check(logical.is_complete(), f"{line_no}. satır: mantıkla çözülebilmeli")
            check(
                logical.grid_snapshot() == solved.grid_snapshot(),
                f"{line_no}. satır: mantıksal çözüm kayıtlı çözümle aynı olmalı",
            )

            wall_key = "|".join(record["solution"])
            check(record["code"] not in codes, f"{line_no}. satır: bulmaca tekrarı")
            check(wall_key not in walls, f"{line_no}. satır: çözüm tekrarı (sızıntı riski)")
            codes.add(record["code"])
            walls.add(wall_key)


def test_library_matches_dataset() -> None:
    for path in sorted((ROOT / "puzzles").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        board = Board(data["rows"], data["cols"])
        for clue in data["clues"]:
            board.set_clue(clue["r"], clue["c"], clue["values"])
        rating = solver.rate(board)
        check(rating.unique, f"{path.stem}: tek çözümlü olmalı")
        check(rating.logic_only, f"{path.stem}: varsayım gerektirmemeli")
        check(
            rating.label == data["meta"].get("zorluk", rating.label),
            f"{path.stem}: etiket ölçümle uyuşmalı",
        )


def main() -> None:
    tests = [
        test_grown_walls_are_legal,
        test_difficulty_target,
        test_dataset_integrity,
        test_library_matches_dataset,
    ]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")
    print(f"\n{len(tests)} test grubu, {PASSED} kontrol başarılı.")


if __name__ == "__main__":
    main()
