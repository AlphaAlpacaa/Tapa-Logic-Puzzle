"""İnsan tasarımı bulmacaları doğrulayarak ayrı bir veri kümesine aktarır.

    python -m tools.import_human dataset/human/kaynak.txt

Kaynak dosya satır başına bir bulmaca içerir:

    36 | 7x5/....../...

`#` ile başlayan satırlar ve boş satırlar atlanır.

Neden ayrı bir veri kümesi: `dataset/puzzles.jsonl` üreticinin çıktısı,
`dataset/human/puzzles.jsonl` ise insan tasarımı. İkisini karıştırmak, modeli
hangisi üzerinde eğitip hangisinde sınadığımızı belirsizleştirir — ki asıl
merak edilen soru tam olarak budur: üretilmiş veriyle eğitilen bir model,
insan tasarımı bulmacalarda ne yapıyor?

## Doğrulama neden şart

Bulmacalar elle ya da görüntüden okunarak girildiğinde tek bir rakam hatası
bulmacayı sessizce bozar. Bu araç her bulmacayı çözücüden geçirir ve şu
ayrımı yapar:

* **tek çözümlü**  — okuma büyük olasılıkla doğru, kabul edilir
* **çözümsüz**     — okuma hatalı, reddedilir
* **çok çözümlü**  — bir ipucu eksik ya da yanlış okunmuş, reddedilir

Bu kusursuz bir denetim değil: hatalı bir okuma tesadüfen başka bir geçerli
bulmaca üretebilir. Ama pratikte hataların büyük çoğunluğunu yakalar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import from_code, solver, to_code  # noqa: E402
from engine.board import ClueError  # noqa: E402
from engine.generator import _features  # noqa: E402


def parse_source(path: Path) -> list[tuple[str, str]]:
    entries = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            raise SystemExit(f"{line_no}. satırda '|' yok: {line!r}")
        puzzle_id, code = (part.strip() for part in line.split("|", 1))
        entries.append((puzzle_id, code))
    return entries


def verify(entries: list[tuple[str, str]], source_name: str,
           time_limit: float) -> tuple[list[dict], list[tuple[str, str]]]:
    accepted: list[dict] = []
    rejected: list[tuple[str, str]] = []

    print(f"{'bulmaca':<10}{'boyut':>8}{'ipucu':>7}{'çözüm':>8}  durum")
    print("-" * 56)

    for puzzle_id, code in entries:
        try:
            board = from_code(code)
        except (ValueError, ClueError) as exc:
            rejected.append((puzzle_id, f"kod okunamadı: {exc}"))
            print(f"{puzzle_id:<10}{'-':>8}{'-':>7}{'-':>8}  KOD HATASI")
            continue

        result = solver.solve(board, limit=2, time_limit=time_limit)
        size = f"{board.rows}x{board.cols}"
        clue_count = len(board.clues)

        if result.stats.timed_out:
            rejected.append((puzzle_id, "zaman sınırına takıldı"))
            verdict = "ZAMAN AŞIMI"
        elif result.count == 0:
            rejected.append((puzzle_id, "çözümsüz — okuma hatalı olabilir"))
            verdict = "ÇÖZÜMSÜZ"
        elif result.count > 1:
            rejected.append((puzzle_id, "birden çok çözüm — bir ipucu eksik ya da yanlış"))
            verdict = "ÇOK ÇÖZÜMLÜ"
        else:
            rating = solver.rate(board)
            accepted.append({
                "id": f"human-{puzzle_id}",
                "source": source_name,
                "sourceNumber": puzzle_id,
                "rows": board.rows,
                "cols": board.cols,
                "code": to_code(board),
                "clues": [
                    {"r": r, "c": c, "values": list(values)}
                    for (r, c), values in sorted(board.clues.items())
                ],
                "solution": _solution_rows(result.solutions[0]),
                "difficulty": rating.as_dict(),
                "features": _features(board, result.solutions[0].filled_cells()),
            })
            verdict = f"kabul ({rating.label})"

        print(f"{puzzle_id:<10}{size:>8}{clue_count:>7}{result.count:>8}  {verdict}")

    return accepted, rejected


def _solution_rows(board) -> list[str]:
    from engine import solution_to_rows
    return solution_to_rows(board)


def main() -> None:
    parser = argparse.ArgumentParser(description="İnsan tasarımı bulmaca aktarımı")
    parser.add_argument("source", type=str, help="kaynak metin dosyası")
    parser.add_argument("--out", type=str, default="dataset/human/puzzles.jsonl")
    parser.add_argument("--name", type=str, default="elle girilen",
                        help="kaynak adı (kitap, dergi vb.)")
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--fresh", action="store_true",
                        help="mevcut insan veri kümesini sil ve sıfırdan yaz")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    if not source_path.is_file():
        raise SystemExit(f"Kaynak dosya yok: {source_path}")

    entries = parse_source(source_path)
    print(f"{len(entries)} bulmaca okunacak.\n")
    accepted, rejected = verify(entries, args.name, args.time_limit)

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if out_path.is_file() and not args.fresh:
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

    print("\n" + "=" * 56)
    print(f"Kabul: {len(accepted)}  |  Red: {len(rejected)}  |  Yeni kaydedilen: {added}")
    if entries:
        print(f"İsabet oranı: %{100 * len(accepted) / len(entries):.0f}")
    if rejected:
        print("\nReddedilenler:")
        for puzzle_id, reason in rejected:
            print(f"  {puzzle_id}: {reason}")
        print("\nReddedilen her bulmaca bir okuma hatasına işaret eder; "
              "ilgili görsele tekrar bakılmalı.")


if __name__ == "__main__":
    main()
