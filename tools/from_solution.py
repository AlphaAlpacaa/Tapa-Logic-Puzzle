"""Çözümden yola çıkarak bulmacayı türetir.

    python -m tools.from_solution dataset/human/cozumler.txt

Çözüm sayfası elimizdeyken ipucu rakamlarını tek tek okumaya gerek yok:
duvar görünüyorsa her ipucu hücresinin değeri **hesaplanabilir**. Okunması
gereken tek şey, hangi hücrenin duvar olduğu ve hangi beyaz hücrelerin ipucu
taşıdığı. Rakam okumak minik ve hataya açık; siyah-beyaz ayırmak değil.

## Giriş biçimi

Her bulmaca bir başlık satırı ve ardından ızgara satırlarıyla verilir:

    # 36
    .##..o
    o#...#
    ...o##
    ##..o.

Hücre karakterleri:

    #  duvar (siyah)
    .  boş hücre (beyaz, ipucusuz)
    o  ipucu hücresi (beyaz, üstünde sayı var)

Boş satır bulmacayı bitirir. `//` ile başlayan satırlar yorumdur.

## Doğrulama

Araç her bulmaca için üç şeyi kontrol eder:

1. Okunan duvar Tapa kurallarına uyuyor mu (2x2 yok, tek parça).
2. Duvardan türetilen ipucularla bulmaca **tek çözümlü** mü.
3. Bulunan çözüm, okunan duvarla **birebir aynı** mı.

Üçü birden geçiyorsa okuma neredeyse kesinlikle doğrudur. Biri bile
geçmiyorsa ilgili görsele tekrar bakmak gerekir — ve hangi kontrolün
düştüğü, hatanın nerede olduğunu söyler.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import Board, Cell, rules, solution_to_rows, solver, to_code  # noqa: E402
from engine.board import ClueError  # noqa: E402
from engine.generator import _features  # noqa: E402
from engine.validator import validate_solution  # noqa: E402

WALL, BLANK, CLUE = "#", ".", "o"


def parse(path: Path) -> list[tuple[str, list[str]]]:
    """Dosyayı (numara, ızgara satırları) çiftlerine ayırır."""
    puzzles: list[tuple[str, list[str]]] = []
    current_id: str | None = None
    rows: list[str] = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("//"):
            continue
        if line.startswith("#") and len(line) > 1 and not set(line[1:].strip()) <= set(WALL + BLANK + CLUE):
            if current_id and rows:
                puzzles.append((current_id, rows))
            current_id = line[1:].strip()
            rows = []
            continue
        if not line:
            if current_id and rows:
                puzzles.append((current_id, rows))
                current_id, rows = None, []
            continue
        rows.append(line)

    if current_id and rows:
        puzzles.append((current_id, rows))
    return puzzles


def build(rows: list[str]) -> tuple[Board, Board, list[str]]:
    """Izgaradan bulmacayı ve çözümü kurar. Hata varsa ValueError."""
    height = len(rows)
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError(f"satırlar eşit uzunlukta değil ({[len(r) for r in rows]})")
    for row in rows:
        unknown = set(row) - set(WALL + BLANK + CLUE)
        if unknown:
            raise ValueError(f"tanınmayan karakter: {sorted(unknown)}")

    wall = {
        (r, c) for r in range(height) for c in range(width) if rows[r][c] == WALL
    }
    clue_cells = [
        (r, c) for r in range(height) for c in range(width) if rows[r][c] == CLUE
    ]
    if not clue_cells:
        raise ValueError("hiç ipucu hücresi işaretlenmemiş")

    solved = Board(height, width)
    for pos in wall:
        solved.set_cell(*pos, Cell.FILLED)

    # İpucu değerleri duvardan hesaplanır — rakamları okumaya gerek yok.
    clues = {pos: rules.runs_pattern(rules.ring_states(solved, *pos)) for pos in clue_cells}
    puzzle = Board(height, width, clues)

    reference = Board(height, width, clues)
    for pos in wall:
        reference.set_cell(*pos, Cell.FILLED)
    return puzzle, reference, solution_to_rows(reference)


def process(path: Path, source_name: str, out_path: Path, time_limit: float,
            fresh: bool) -> None:
    puzzles = parse(path)
    print(f"{len(puzzles)} bulmaca okunacak.\n")
    print(f"{'no':<8}{'boyut':>8}{'ipucu':>7}{'çözüm':>8}  durum")
    print("-" * 60)

    accepted: list[dict] = []
    rejected: list[tuple[str, str]] = []

    for puzzle_id, rows in puzzles:
        try:
            puzzle, reference, solution = build(rows)
        except (ValueError, ClueError) as exc:
            rejected.append((puzzle_id, f"ızgara kurulamadı: {exc}"))
            print(f"{puzzle_id:<8}{'-':>8}{'-':>7}{'-':>8}  IZGARA HATASI")
            continue

        size = f"{puzzle.rows}x{puzzle.cols}"
        clue_count = len(puzzle.clues)

        # 1) Okunan duvar kurallara uyuyor mu?
        check = validate_solution(reference)
        if not check.ok:
            reason = check.issues[0].message
            rejected.append((puzzle_id, f"duvar kurallara uymuyor: {reason}"))
            print(f"{puzzle_id:<8}{size:>8}{clue_count:>7}{'-':>8}  DUVAR HATALI")
            continue

        # 2) ve 3) Tek çözümlü mü, ve çözüm okunan duvarla aynı mı?
        result = solver.solve(puzzle, limit=2, time_limit=time_limit)
        if result.stats.timed_out:
            rejected.append((puzzle_id, "zaman sınırına takıldı"))
            verdict = "ZAMAN AŞIMI"
        elif result.count == 0:
            rejected.append((puzzle_id, "çözümsüz"))
            verdict = "ÇÖZÜMSÜZ"
        elif result.count > 1:
            rejected.append((puzzle_id, "birden çok çözüm — ipucu hücreleri eksik işaretlenmiş"))
            verdict = "ÇOK ÇÖZÜMLÜ"
        elif solution_to_rows(result.solutions[0]) != solution:
            rejected.append((puzzle_id, "çözüm okunan duvarla uyuşmuyor"))
            verdict = "ÇÖZÜM FARKLI"
        else:
            rating = solver.rate(puzzle)
            accepted.append({
                "id": f"human-{puzzle_id}",
                "source": source_name,
                "sourceNumber": puzzle_id,
                "rows": puzzle.rows,
                "cols": puzzle.cols,
                "code": to_code(puzzle),
                "clues": [
                    {"r": r, "c": c, "values": list(values)}
                    for (r, c), values in sorted(puzzle.clues.items())
                ],
                "solution": solution,
                "difficulty": rating.as_dict(),
                "features": _features(puzzle, reference.filled_cells()),
            })
            verdict = f"kabul ({rating.label})"

        print(f"{puzzle_id:<8}{size:>8}{clue_count:>7}{result.count:>8}  {verdict}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if out_path.is_file() and not fresh:
        existing = [
            json.loads(line)
            for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    seen = {record["code"] for record in existing}

    added = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for record in existing:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        for record in accepted:
            if record["code"] in seen:
                continue
            seen.add(record["code"])
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            added += 1

    print("\n" + "=" * 60)
    print(f"Kabul: {len(accepted)}  |  Red: {len(rejected)}  |  Yeni kaydedilen: {added}")
    if puzzles:
        print(f"İsabet oranı: %{100 * len(accepted) / len(puzzles):.0f}")
    if rejected:
        print("\nReddedilenler:")
        for puzzle_id, reason in rejected:
            print(f"  {puzzle_id}: {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Çözümden bulmaca türetme")
    parser.add_argument("source", type=str)
    parser.add_argument("--out", type=str, default="dataset/human/puzzles.jsonl")
    parser.add_argument("--name", type=str, default="kitap")
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    if not source_path.is_file():
        raise SystemExit(f"Kaynak dosya yok: {source_path}")

    process(source_path, args.name, ROOT / args.out, args.time_limit, args.fresh)


if __name__ == "__main__":
    main()
