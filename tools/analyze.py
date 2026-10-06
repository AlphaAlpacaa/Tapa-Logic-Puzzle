"""İnsan tasarımı ve üretilmiş bulmacaları karşılaştırır.

    python -m tools.analyze

Amaç, üreticinin insan tasarımından nerede ayrıldığını tahminle değil ölçümle
belirlemek. Şu an üretici hakkında bildiklerimizin bir kısmı varsayım: ipucu
değeri sınırını 5 yaptık ama doğru sayının ne olduğunu bilmiyoruz, ipucuları
rastgele yerleştiriyoruz ama insan tasarımında simetri olup olmadığını
ölçmedik.

Raporlanan boyutlar:

* **ipucu değeri dağılımı** — hangi sayılar ne sıklıkta
* **çok sayılı ipucu oranı** ve en sık kullanılan kombinasyonlar
* **ipucu yoğunluğu** — hücre başına ipucu
* **duvar yoğunluğu** — çözümdeki dolu hücre oranı
* **simetri** — ipucu yerleşimi 180 derece dönmeye göre bakışımlı mı

Simetri özellikle önemli: insan yapımı bulmacalarda ipucu yerleşimi genellikle
dönme simetrisine sahiptir, bizim üreticimiz ise tamamen rastgele yerleştirir.
Fark buradaysa, görsel kalite açısından en büyük açığımız budur.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------- #
# Ölçütler
# ---------------------------------------------------------------------- #

def rotational_symmetry(record: dict) -> bool:
    """İpucu yerleşimi 180 derece dönmeye göre bakışımlı mı.

    Yalnızca konumlara bakılır, değerlere değil: Tapa'da simetri geleneği
    ipucuların *nerede* olduğuyla ilgilidir, hangi sayıyı taşıdıklarıyla değil.
    """
    rows, cols = record["rows"], record["cols"]
    positions = {(clue["r"], clue["c"]) for clue in record["clues"]}
    mirrored = {(rows - 1 - r, cols - 1 - c) for (r, c) in positions}
    return positions == mirrored


def symmetry_ratio(record: dict) -> float:
    """İpucuların kaçının 180 derece dönme eşi var."""
    rows, cols = record["rows"], record["cols"]
    positions = {(clue["r"], clue["c"]) for clue in record["clues"]}
    if not positions:
        return 0.0
    matched = sum(1 for (r, c) in positions if (rows - 1 - r, cols - 1 - c) in positions)
    return matched / len(positions)


def describe(name: str, records: list[dict]) -> dict:
    if not records:
        print(f"\n{name}: veri yok.")
        return {}

    values = Counter()
    combos = Counter()
    for record in records:
        for clue in record["clues"]:
            combos[tuple(sorted(clue["values"], reverse=True))] += 1
            for value in clue["values"]:
                values[value] += 1

    total_numbers = sum(values.values())
    total_clues = sum(combos.values())
    multi = sum(count for combo, count in combos.items() if len(combo) > 1)

    clue_density = [len(r["clues"]) / (r["rows"] * r["cols"]) for r in records]
    wall_density = [
        sum(row.count("#") for row in r["solution"]) / (r["rows"] * r["cols"])
        for r in records if r.get("solution")
    ]
    symmetric = [rotational_symmetry(r) for r in records]
    sym_ratios = [symmetry_ratio(r) for r in records]
    sizes = Counter(f"{r['rows']}x{r['cols']}" for r in records)

    print(f"\n{'=' * 60}\n{name}  ({len(records)} bulmaca)\n{'=' * 60}")
    print(f"boyutlar: {dict(sorted(sizes.items()))}")
    print(f"ipucu sayısı: {total_clues} | rakam sayısı: {total_numbers}")

    print("\nipucu değeri dağılımı:")
    for value in sorted(values):
        share = 100 * values[value] / total_numbers
        bar = "#" * round(share / 2)
        print(f"  {value}: {values[value]:>5}  %{share:>5.1f}  {bar}")

    print(f"\nçok sayılı ipucu oranı: %{100 * multi / total_clues:.1f}")
    print("en sık kombinasyonlar:")
    for combo, count in combos.most_common(8):
        label = " ".join(str(n) for n in combo)
        print(f"  {label:<8} {count:>5}  %{100 * count / total_clues:.1f}")

    print(f"\nipucu yoğunluğu: ortalama {statistics.mean(clue_density):.3f} "
          f"(en az {min(clue_density):.3f}, en çok {max(clue_density):.3f})")
    if wall_density:
        print(f"duvar yoğunluğu: ortalama {statistics.mean(wall_density):.3f} "
              f"(en az {min(wall_density):.3f}, en çok {max(wall_density):.3f})")

    print(f"\ntam 180° simetrik bulmaca: {sum(symmetric)}/{len(records)} "
          f"(%{100 * sum(symmetric) / len(records):.0f})")
    print(f"simetrik eşi olan ipucu oranı: ortalama %{100 * statistics.mean(sym_ratios):.0f}")

    return {
        "count": len(records),
        "valueShare": {str(v): values[v] / total_numbers for v in sorted(values)},
        "multiRatio": multi / total_clues,
        "clueDensity": statistics.mean(clue_density),
        "wallDensity": statistics.mean(wall_density) if wall_density else None,
        "fullySymmetric": sum(symmetric) / len(records),
        "symmetryRatio": statistics.mean(sym_ratios),
    }


def compare(human: dict, generated: dict) -> None:
    if not human or not generated:
        print("\nKarşılaştırma için iki veri kümesi de gerekli.")
        return

    print(f"\n{'=' * 60}\nFARKLAR (insan - üretilmiş)\n{'=' * 60}")
    print(f"{'ölçüt':<28}{'insan':>12}{'üretilmiş':>12}")
    print("-" * 52)

    def row(label: str, a, b, fmt: str = "{:.3f}") -> None:
        left = fmt.format(a) if a is not None else "-"
        right = fmt.format(b) if b is not None else "-"
        print(f"{label:<28}{left:>12}{right:>12}")

    row("çok sayılı ipucu oranı", human["multiRatio"], generated["multiRatio"])
    row("ipucu yoğunluğu", human["clueDensity"], generated["clueDensity"])
    row("duvar yoğunluğu", human["wallDensity"], generated["wallDensity"])
    row("tam simetrik oranı", human["fullySymmetric"], generated["fullySymmetric"])
    row("simetrik eş oranı", human["symmetryRatio"], generated["symmetryRatio"])

    print("\nipucu değeri payları:")
    keys = sorted(set(human["valueShare"]) | set(generated["valueShare"]), key=int)
    print(f"{'değer':<28}{'insan':>12}{'üretilmiş':>12}")
    print("-" * 52)
    for key in keys:
        row(f"  {key}", human["valueShare"].get(key, 0.0), generated["valueShare"].get(key, 0.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulmaca dağılımı karşılaştırması")
    parser.add_argument("--human", type=str, default="dataset/human/puzzles.jsonl")
    parser.add_argument("--generated", type=str, default="dataset/puzzles.jsonl")
    args = parser.parse_args()

    human_records = load(ROOT / args.human)
    generated_records = load(ROOT / args.generated)

    human_stats = describe("İNSAN TASARIMI", human_records)
    generated_stats = describe("ÜRETİLMİŞ", generated_records)
    compare(human_stats, generated_stats)


if __name__ == "__main__":
    main()
