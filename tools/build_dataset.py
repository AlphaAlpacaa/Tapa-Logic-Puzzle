"""Bulmaca veri kümesini kurar. Her çalıştırmada üstüne ekler.

Örnekler:

    # 100 bulmaca, 6x6 ile 12x12 arası, tüm zorluklar
    python -m tools.build_dataset --count 100

    # sadece büyük ve çok zor olanlardan 20 tane ekle
    python -m tools.build_dataset --count 20 --min-size 12 --max-size 16 --levels 4

    # seyrek duvarlı kolay bulmacalar
    python -m tools.build_dataset --count 30 --levels 1,2 --densities 0.35,0.45

    # belirli boyutlar
    python -m tools.build_dataset --count 40 --sizes 8,10,14

    # sıfırdan başla (mevcut veri kümesini ve kütüphaneyi siler)
    python -m tools.build_dataset --count 50 --fresh

Varsayılan davranış **eklemektir**: mevcut `dataset/puzzles.jsonl` okunur, yeni
bulmacalar sonuna yazılır, tekrarlar atlanır. Böylece araç her çalıştırıldığında
veri kümesi büyür.

İki çıktı üretilir, çünkü iki ayrı işe hizmet ederler:

* `dataset/puzzles.jsonl` — asıl veri kümesi. Satır başına bir bulmaca; çözüm,
  zorluk dökümü ve öznitelikler bir arada. Üretim sırasında anında yazılır,
  yani araç yarıda kesilse bile o ana kadarki iş durur.
* `puzzles/*.json` — arayüzün yan panelindeki vitrin. Her boyut-zorluk
  çiftinden bir örnek; yüz satırlık liste kimsenin işine yaramaz.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import Board, generator, save_json, solver  # noqa: E402


# ---------------------------------------------------------------------- #
# Üretim planı
# ---------------------------------------------------------------------- #

def plan(count: int, sizes: list[int], densities: list[float], levels: list[int],
         rng: random.Random, exact: bool = True, max_clue: int = 5) -> list[generator.Spec]:
    """Boyut × yoğunluk × zorluk kombinasyonlarını eşit dağıtan plan.

    Çeşitlilik rastgeleliğe bırakılmaz. Üretici hep kendi kolay bulduğu türü
    üretirse, o veriyle eğitilen model olduğundan iyi görünür ve bunu fark
    etmek zordur.
    """
    combos = [
        generator.Spec(size, size, density, 1.0, level, exact, max_clue)
        for size in sizes
        for density in densities
        for level in levels
    ]
    if not combos:
        raise SystemExit("Üretim planı boş: boyut, yoğunluk ve zorluk listelerini kontrol edin.")

    specs: list[generator.Spec] = []
    while len(specs) < count:
        rng.shuffle(combos)
        specs.extend(combos)
    return specs[:count]


# ---------------------------------------------------------------------- #
# Mevcut veri kümesi
# ---------------------------------------------------------------------- #

def load_existing(path: Path) -> tuple[list[dict], set[str], set[str]]:
    """Önceki çalıştırmaların ürettiklerini okur; tekrarları engellemek için."""
    if not path.is_file():
        return [], set(), set()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]
    codes = {r["code"] for r in records}
    walls = {"|".join(r["solution"]) for r in records}
    return records, codes, walls


# ---------------------------------------------------------------------- #
# Üretim
# ---------------------------------------------------------------------- #

def build(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    dataset_dir = ROOT / args.out
    dataset_dir.mkdir(parents=True, exist_ok=True)
    jsonl = dataset_dir / "puzzles.jsonl"

    if args.fresh and jsonl.exists():
        jsonl.unlink()

    existing, seen_codes, seen_walls = load_existing(jsonl)
    fresh_records: list[dict] = []
    next_index = len(existing)
    skipped = 0

    print(
        f"{args.count} bulmaca hedefleniyor | boyut {min(args.sizes)}-{max(args.sizes)} | "
        f"zorluk {','.join(str(level) for level in args.levels)} | tohum {args.seed}",
        flush=True,
    )
    if existing:
        print(f"Mevcut veri kümesinde {len(existing)} bulmaca var, üstüne eklenecek.", flush=True)
    print(flush=True)

    with jsonl.open("a", encoding="utf-8") as handle:
        for spec in plan(args.count, args.sizes, args.densities, args.levels, rng,
                         exact=not args.loose_level, max_clue=args.max_clue):
            item = generator.generate(
                spec.rows, spec.cols, rng,
                wall_density=spec.wall_density,
                aggressiveness=spec.aggressiveness,
                max_level=spec.max_level,
                exact_level=spec.exact_level,
                max_clue_value=spec.max_clue_value,
                attempts=args.attempts,
            )
            if item is None:
                skipped += 1
                continue

            record = item.as_record(f"tapa-{next_index:04d}")
            wall_key = "|".join(item.solution)
            # Aynı bulmacanın ya da aynı çözümün eğitim ve test kümesine
            # birlikte düşmesi, sızıntı yüzünden başarıyı şişirir.
            if record["code"] in seen_codes or wall_key in seen_walls:
                skipped += 1
                continue
            seen_codes.add(record["code"])
            seen_walls.add(wall_key)

            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            fresh_records.append(record)
            next_index += 1
            print(
                f"  {record['id']}  {spec.rows}x{spec.cols}  "
                f"{record['features']['clueCount']:>3} ipucu  "
                f"{record['difficulty']['label']}",
                flush=True,
            )

    print(f"\n{len(fresh_records)} yeni bulmaca eklendi, {skipped} deneme boşa gitti.")
    all_records = existing + fresh_records
    summarise(all_records, dataset_dir)
    if not args.no_library:
        export_library(all_records, fresh=args.fresh)


def summarise(records: list[dict], dataset_dir: Path) -> None:
    def spread(values: list[float]) -> dict[str, float]:
        if not values:
            return {"min": 0, "max": 0, "mean": 0}
        return {
            "min": min(values),
            "max": max(values),
            "mean": round(sum(values) / len(values), 4),
        }

    summary = {
        "count": len(records),
        "bySize": dict(sorted(Counter(f"{r['rows']}x{r['cols']}" for r in records).items())),
        "byDifficulty": dict(Counter(r["difficulty"]["label"] for r in records)),
        "clueDensity": spread([r["features"]["clueDensity"] for r in records]),
        "maxClueValue": dict(sorted(Counter(r["features"]["maxClueValue"] for r in records).items())),
        "wallDensity": spread([r["features"]["wallDensity"] for r in records]),
    }
    (dataset_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nVeri kümesi:", json.dumps(summary, ensure_ascii=False, indent=2))


#: Dosya adları ASCII tutulur: adlar URL'de geçiyor, boşluk ve Türkçe karakter
#: istemci tarafında kodlama hatasına yol açar. Görünen başlık meta'da durur.
SLUGS = {"kolay": "kolay", "orta": "orta", "zor": "zor", "çok zor": "cok-zor"}


def slugify(label: str) -> str:
    return SLUGS.get(label, label.replace(" ", "-"))


def export_library(records: list[dict], *, fresh: bool = False) -> None:
    """Her boyut-zorluk çiftinden birer örneği arayüz kütüphanesine koyar."""
    puzzles_dir = ROOT / "puzzles"
    puzzles_dir.mkdir(exist_ok=True)
    if fresh:
        for stale in puzzles_dir.glob("*.json"):
            stale.unlink()

    added = 0
    for record in records:
        label = record["difficulty"]["label"]
        name = f"{label} {record['rows']}x{record['cols']}"
        target = puzzles_dir / f"{slugify(label)}-{record['rows']}x{record['cols']}.json"
        if target.exists():
            continue
        board = Board(record["rows"], record["cols"])
        for clue in record["clues"]:
            board.set_clue(clue["r"], clue["c"], clue["values"])
        save_json(
            board,
            target,
            meta={
                "baslik": name,
                "zorluk": record["difficulty"]["label"],
                "kaynak": record["id"],
                "teknikler": record["difficulty"]["techniques"],
            },
        )
        added += 1
    total = len(list(puzzles_dir.glob("*.json")))
    print(f"Kütüphaneye {added} yeni bulmaca eklendi (toplam {total}).")


# ---------------------------------------------------------------------- #
# Komut satırı
# ---------------------------------------------------------------------- #

def int_list(text: str) -> list[int]:
    return [int(part) for part in text.replace(" ", "").split(",") if part]


def float_list(text: str) -> list[float]:
    return [float(part) for part in text.replace(" ", "").split(",") if part]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tapa veri kümesi kurucu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--count", type=int, default=50, help="üretilecek bulmaca sayısı")
    parser.add_argument("--min-size", type=int, default=6, help="en küçük kenar uzunluğu")
    parser.add_argument("--max-size", type=int, default=12, help="en büyük kenar uzunluğu")
    parser.add_argument("--sizes", type=int_list, default=None,
                        help="boyutları doğrudan ver, örn. 6,8,10 (min/max yerine geçer)")
    parser.add_argument("--levels", type=int_list, default=[1, 2, 3, 4],
                        help="hedef zorluklar: 1 kolay, 2 orta, 3 zor, 4 çok zor")
    parser.add_argument("--densities", type=float_list, default=[0.38, 0.45, 0.52],
                        help="duvar yoğunlukları")
    parser.add_argument("--max-clue", type=int, default=5,
                        help="en büyük ipucu değeri; düşürmek bulmacayı zorlaştırır")
    parser.add_argument("--seed", type=int, default=None, help="tekrarlanabilirlik için tohum")
    parser.add_argument("--attempts", type=int, default=60,
                        help="bir bulmaca için en fazla kaç duvar denensin")
    parser.add_argument("--out", type=str, default="dataset", help="çıktı klasörü")
    parser.add_argument("--fresh", action="store_true",
                        help="eklemek yerine sıfırdan başla (mevcut veriyi siler)")
    parser.add_argument("--no-library", action="store_true",
                        help="arayüz kütüphanesine kopyalama")
    parser.add_argument("--loose-level", action="store_true",
                        help="istenen zorluğu şart koşma; daha hızlı ama kolay bulmacalar da çıkar")
    args = parser.parse_args()

    if not args.sizes:
        if args.min_size > args.max_size:
            raise SystemExit("--min-size, --max-size değerinden büyük olamaz.")
        args.sizes = list(range(args.min_size, args.max_size + 1))

    if any(size < 3 for size in args.sizes):
        raise SystemExit("Boyut en az 3 olmalı.")
    for level in args.levels:
        if not 1 <= level <= solver.MAX_LEVEL:
            raise SystemExit(f"Zorluk 1 ile {solver.MAX_LEVEL} arasında olmalı.")
    if any(not 0.1 <= density <= 0.9 for density in args.densities):
        raise SystemExit("Duvar yoğunluğu 0.1 ile 0.9 arasında olmalı.")
    if not 1 <= args.max_clue <= 8:
        raise SystemExit("--max-clue 1 ile 8 arasında olmalı.")

    if args.seed is None:
        args.seed = random.randrange(1_000_000)

    build(args)


if __name__ == "__main__":
    main()
