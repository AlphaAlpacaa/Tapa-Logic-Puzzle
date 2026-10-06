"""Mantıksal çözücü ile CP-SAT'ı karşılaştırır ve birbirine karşı doğrular.

    python -m tools.benchmark                 # veri kümesi üzerinde doğrula + ölç
    python -m tools.benchmark --scale         # büyük tahtalarda ölçeklenme
    python -m tools.benchmark --limit 20      # sadece ilk 20 bulmaca

İki iş birden yapar:

**Doğrulama.** İki çözücünün bulduğu çözümler ve çözüm sayıları karşılaştırılır.
Tamamen farklı iki yöntemin aynı cevapta buluşması, doğruluk için elimizdeki en
güçlü kanıt; ayrışırlarsa en az biri hatalıdır ve bunu bilmek gerekir.

**Ölçüm.** Süre, dallanma ve çatışma sayıları raporlanır. Bu rakamlar ileride
öğrenilmiş modellerin karşılaştırılacağı taban çizgisidir.

`ortools` kurulu değilse yalnızca mantıksal çözücü ölçülür ve bu belirtilir.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import Board, cpsat, from_code, generator, solver  # noqa: E402
from engine import solution_to_rows  # noqa: E402


def load_dataset(limit: int | None) -> list[dict]:
    path = ROOT / "dataset" / "puzzles.jsonl"
    if not path.is_file():
        raise SystemExit("Veri kümesi yok. Önce: python -m tools.build_dataset")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return records[:limit] if limit else records


# ---------------------------------------------------------------------- #
# Doğrulama + ölçüm
# ---------------------------------------------------------------------- #

def compare(records: list[dict], connectivity: str, time_limit: float) -> None:
    has_cpsat = cpsat.available()
    if not has_cpsat:
        print("ortools kurulu değil; yalnızca mantıksal çözücü ölçülüyor.")
        print("Kurmak için: pip install ortools\n")

    logic_times: list[float] = []
    cp_times: list[float] = []
    mismatches: list[str] = []
    cp_failures: list[str] = []

    print(f"{'bulmaca':<14}{'boyut':>7}{'zorluk':>10}{'mantık':>10}{'cp-sat':>10}  durum")
    print("-" * 64)

    for record in records:
        board = from_code(record["code"])

        started = time.perf_counter()
        logic = solver.solve(board, limit=2)
        logic_elapsed = time.perf_counter() - started
        logic_times.append(logic_elapsed)

        row = (
            f"{record['id']:<14}"
            f"{record['rows']}x{record['cols']:>4}"
            f"{record['difficulty']['label']:>10}"
            f"{logic_elapsed:>9.3f}s"
        )

        if not has_cpsat:
            print(row + f"{'-':>10}  -")
            continue

        try:
            cp = cpsat.solve(board, limit=2, connectivity=connectivity, time_limit=time_limit)
        except Exception as exc:  # modelin kendisi patlarsa sessiz kalmasın
            cp_failures.append(f"{record['id']}: {type(exc).__name__}: {exc}")
            print(row + f"{'HATA':>10}  {type(exc).__name__}")
            continue

        cp_times.append(cp.elapsed)
        note = "uyumlu"

        if cp.hit_limit:
            note = "cp-sat zaman sınırına takıldı"
        elif cp.count != logic.count:
            note = f"ÇÖZÜM SAYISI FARKLI (mantık {logic.count}, cp-sat {cp.count})"
            mismatches.append(f"{record['id']}: {note}")
        elif logic.solutions and cp.solutions:
            a = solution_to_rows(logic.solutions[0])
            b = solution_to_rows(cp.solutions[0])
            if a != b:
                note = "ÇÖZÜMLER FARKLI"
                mismatches.append(f"{record['id']}: çözümler ayrışıyor")
        elif logic.count == 0 and cp.count == 0:
            note = "ikisi de çözümsüz buldu"

        print(row + f"{cp.elapsed:>9.3f}s  {note}")

    print("\n" + "=" * 64)
    print(f"{len(records)} bulmaca denendi.")
    if logic_times:
        print(f"Mantıksal çözücü : toplam {sum(logic_times):.2f}s | "
              f"ortalama {statistics.mean(logic_times):.3f}s | en kötü {max(logic_times):.3f}s")
    if cp_times:
        print(f"CP-SAT ({connectivity:<5})   : toplam {sum(cp_times):.2f}s | "
              f"ortalama {statistics.mean(cp_times):.3f}s | en kötü {max(cp_times):.3f}s")

    if cp_failures:
        print(f"\n{len(cp_failures)} bulmacada CP-SAT hata verdi:")
        for line in cp_failures[:10]:
            print("  " + line)
    if mismatches:
        print(f"\nUYUŞMAZLIK ({len(mismatches)}): iki çözücü ayrışıyor, en az biri hatalı.")
        for line in mismatches[:10]:
            print("  " + line)
    elif cp_times and not cp_failures:
        print("\nİki çözücü bütün bulmacalarda aynı sonuçta buluştu.")


# ---------------------------------------------------------------------- #
# Ölçeklenme
# ---------------------------------------------------------------------- #

def scale_test(sizes: list[int], time_limit: float, connectivity: str, seed: int) -> None:
    """Artan boyutlarda üretilmiş bulmacalarda iki çözücüyü karşılaştırır.

    Üretim, mantıksal çözücüye dayandığı için büyük boyutlarda yavaşlar; bu
    yüzden burada hedef zorluk şart koşulmaz, sadece geçerli bir bulmaca
    üretilir.
    """
    rng = random.Random(seed)
    has_cpsat = cpsat.available()

    print(f"{'boyut':>7}{'ipucu':>8}{'mantık':>11}{'cp-sat':>11}  not")
    print("-" * 52)

    for size in sizes:
        item = generator.generate(size, size, rng, wall_density=0.45,
                                  max_level=solver.MAX_LEVEL, attempts=40)
        if item is None:
            print(f"{size}x{size:<3}  bulmaca üretilemedi")
            continue

        board = item.board
        started = time.perf_counter()
        logic = solver.solve(board, limit=1)
        logic_elapsed = time.perf_counter() - started

        line = f"{size}x{size:>4}{item.features['clueCount']:>8}{logic_elapsed:>10.3f}s"

        if not has_cpsat:
            print(line + f"{'-':>11}  ortools yok")
            continue

        cp = cpsat.solve(board, limit=1, connectivity=connectivity, time_limit=time_limit)
        note = "uyumlu"
        if cp.hit_limit:
            note = "cp-sat zaman sınırına takıldı"
        elif logic.solutions and cp.solutions:
            if solution_to_rows(logic.solutions[0]) != solution_to_rows(cp.solutions[0]):
                note = "ÇÖZÜMLER FARKLI"
        print(line + f"{cp.elapsed:>10.3f}s  {note} (dal {cp.branches}, çatışma {cp.conflicts})")


# ---------------------------------------------------------------------- #
# Kodlama karşılaştırması
# ---------------------------------------------------------------------- #

def encoding_test(records: list[dict], time_limit: float) -> None:
    """İki bağlantılılık kodlamasını aynı bulmacalarda karşılaştırır."""
    if not cpsat.available():
        raise SystemExit("Bu karşılaştırma için ortools gerekiyor: pip install ortools")

    print(f"{'bulmaca':<14}{'etiket':>12}{'kesme':>12}  tur")
    print("-" * 44)
    totals = {"reach": 0.0, "cuts": 0.0}

    for record in records:
        board = from_code(record["code"])
        out = {}
        for mode in ("reach", "cuts"):
            result = cpsat.solve(board, limit=2, connectivity=mode, time_limit=time_limit)
            out[mode] = result
            totals[mode] += result.elapsed
        print(f"{record['id']:<14}{out['reach'].elapsed:>11.3f}s"
              f"{out['cuts'].elapsed:>11.3f}s  {out['cuts'].cut_rounds}")

    print("-" * 44)
    print(f"{'toplam':<14}{totals['reach']:>11.2f}s{totals['cuts']:>11.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tapa çözücü karşılaştırması")
    parser.add_argument("--limit", type=int, default=None, help="kaç bulmaca denensin")
    parser.add_argument("--connectivity", choices=["reach", "cuts"], default="reach",
                        help="CP-SAT bağlantılılık kodlaması")
    parser.add_argument("--time-limit", type=float, default=60.0,
                        help="CP-SAT için bulmaca başına saniye sınırı")
    parser.add_argument("--scale", action="store_true",
                        help="artan boyutlarda ölçeklenme testi")
    parser.add_argument("--sizes", type=str, default="8,10,12,14,16,18,20",
                        help="ölçeklenme testindeki boyutlar")
    parser.add_argument("--encodings", action="store_true",
                        help="iki bağlantılılık kodlamasını karşılaştır")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    if args.scale:
        sizes = [int(part) for part in args.sizes.split(",") if part.strip()]
        scale_test(sizes, args.time_limit, args.connectivity, args.seed)
        return

    records = load_dataset(args.limit)
    if args.encodings:
        encoding_test(records[: args.limit or 15], args.time_limit)
        return

    compare(records, args.connectivity, args.time_limit)


if __name__ == "__main__":
    main()
