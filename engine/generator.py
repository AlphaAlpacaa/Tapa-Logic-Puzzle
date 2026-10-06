"""Tapa bulmaca üreticisi.

Yöntem "oymacılık": önce geçerli bir çözüm (duvar) inşa edilir, ipucular ondan
türetilir, sonra tekliği bozmayan ipucular tek tek elenir. Tersi yön — rastgele
ipucu serpip çözüm aramak — neredeyse hep çözümsüz tahta üretir.

Duvar, tek hücreden başlatılıp komşuluk üzerinden büyütülür. Bu sayede
bağlantılılık (K4) ve 2x2 yasağı (K3) inşa sırasında zaten sağlanır; sonradan
düzeltme gerekmez ve duvar yoğunluğu hedeflenebilir. Yoğunluk kontrolü
çeşitlilik için şart: hep aynı doluluktaki bulmacalar, üstünde eğitilen modeli
olduğundan iyi gösterir.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from .board import Board, Cell, Position
from . import rules, solver
from .validator import validate_solution
from .serialize import solution_to_rows, to_code


# ---------------------------------------------------------------------- #
# Duvar inşası
# ---------------------------------------------------------------------- #

def _creates_square(wall: set[Position], pos: Position) -> bool:
    """`pos` eklenirse tamamen dolu bir 2x2 oluşur mu."""
    r, c = pos
    for dr in (-1, 0):
        for dc in (-1, 0):
            quad = {(r + dr, c + dc), (r + dr, c + dc + 1),
                    (r + dr + 1, c + dc), (r + dr + 1, c + dc + 1)}
            if quad - {pos} <= wall:
                return True
    return False


def grow_wall(rows: int, cols: int, target: int, rng: random.Random) -> set[Position]:
    """Hedef büyüklükte, bağlı ve 2x2 içermeyen bir duvar büyütür.

    Tohumdan başlayıp her adımda duvara ortogonal komşu bir hücre ekler.
    Eklenebilecek hücre kalmazsa olduğu yerde durur — bu yüzden dönen kümenin
    boyutu hedeften küçük olabilir.
    """
    start = (rng.randrange(rows), rng.randrange(cols))
    wall = {start}
    frontier = set()

    def refresh(pos: Position) -> None:
        r, c = pos
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in wall:
                frontier.add((nr, nc))

    refresh(start)
    while len(wall) < target and frontier:
        pos = rng.choice(sorted(frontier))
        frontier.discard(pos)
        if _creates_square(wall, pos):
            continue
        wall.add(pos)
        refresh(pos)
    return wall


# ---------------------------------------------------------------------- #
# İpucu yerleştirme
# ---------------------------------------------------------------------- #

def covering_clues(solved: Board, wall: set[Position], rng: random.Random, *,
                   max_clue_value: int = 5) -> dict[Position, tuple[int, ...]] | None:
    """Her hücreyi en az bir ipucunun görüş alanına sokan ipucu kümesi.

    Görülmeyen bir hücre hiçbir kısıta tabi olmaz; doldurulup boşaltılabildiği
    için bulmaca tek çözümlü olamaz. Bu yüzden kapsama şart.

    `max_clue_value` büyük ipucu değerlerini eler. Bunun zorluk üzerindeki
    etkisi doğrudan: `8` ipucusu sekiz komşunun da dolu olduğunu söyler ve
    görüldüğü anda sekiz hücre birden kapanır. Büyük değerler bulmacayı anında
    açar, dolayısıyla sınırlamak hem görünümü insan tasarımına yaklaştırır hem
    bulmacayı gerçekten zorlaştırır.

    Aday ipucular önce bilgi değeri düşük olanlardan seçilir: küçük sayılar ve
    çok sayılı ipucular önde gelir.
    """
    candidates = []
    for pos in solved.positions():
        if pos in wall:
            continue
        values = rules.runs_pattern(rules.ring_states(solved, *pos))
        if max(values) > max_clue_value:
            continue
        candidates.append((pos, values))
    if not candidates:
        return None

    rng.shuffle(candidates)
    # Küçük en büyük değer önce; eşitlikte çok sayılı ipucu tercih edilir.
    candidates.sort(key=lambda item: (max(item[1]), -len(item[1])))

    uncovered = set(solved.positions())
    chosen: dict[Position, tuple[int, ...]] = {}
    for pos, values in candidates:
        covers = {p for p in solved.ring(*pos) if p is not None} & uncovered
        if covers or pos in uncovered:
            chosen[pos] = values
            uncovered -= covers
            uncovered.discard(pos)
    if uncovered:
        return None

    return chosen


def solvable_by_logic(board: Board, max_level: int) -> bool:
    """Bulmaca, verilen seviyeye kadarki tekniklerle sonuna dek çözülüyor mu.

    Bu aynı zamanda teklik kanıtıdır: yayılımın attığı her adım zorunlu
    olduğundan, tahtayı mantıkla bitirebiliyorsak başka çözüm olamaz. Teklik
    için ayrıca arama yapmaya gerek kalmaz — hem çok daha hızlı, hem de
    oyuncuyu tahmine zorlamayan bulmaca garantisi.
    """
    work = board.copy()
    work.clear_marks()
    stats = solver.SolveStats()
    if not solver.propagate(work, stats, max_level):
        return False
    return work.is_complete() and validate_solution(work).ok


def trim_clues(rows: int, cols: int, clues: dict[Position, tuple[int, ...]],
               rng: random.Random, *, max_level: int = solver.MAX_LEVEL,
               aggressiveness: float = 1.0) -> dict[Position, tuple[int, ...]]:
    """Bulmacayı mantıkla çözülebilir bırakan her ipucuyu eler.

    İki ayar zorluğu birlikte belirler:

    `max_level` oyuncunun kullanmasına izin verilen en pahalı teknik. 1 ise
    yalnızca ipucu okumayla çözülmesi gerekir, dolayısıyla çok ipucu kalır ve
    bulmaca kolay olur; 3 ise bağlantılılık akıl yürütmesine izin verildiği
    için çok daha fazla ipucu elenebilir.

    `aggressiveness` kaç ipucunun elenmeye *denendiğini* belirler. 1.0 en aza
    yaklaşır; düşük değerler fazladan ipucu bırakır.
    """
    kept = dict(clues)

    # Doyuma kadar tekrarlanır: bir ipucu elendikten sonra, daha önce
    # elenemeyen bir başkası elenebilir hale gelebilir. Tek geçiş gereğinden
    # fazla ipucu bırakıyordu.
    while True:
        order = sorted(kept)
        rng.shuffle(order)
        attempts = order[: max(1, round(len(order) * aggressiveness))]

        removed = False
        for pos in attempts:
            if len(kept) <= 1:
                break
            if pos not in kept:
                continue
            trial = Board(rows, cols, {p: v for p, v in kept.items() if p != pos})
            if solvable_by_logic(trial, max_level):
                del kept[pos]
                removed = True
        if not removed:
            return kept


# ---------------------------------------------------------------------- #
# Üretim
# ---------------------------------------------------------------------- #

@dataclass
class Generated:
    board: Board
    solution: list[str]
    difficulty: solver.Difficulty
    features: dict[str, Any] = field(default_factory=dict)

    def as_record(self, puzzle_id: str) -> dict[str, Any]:
        """Veri kümesi satırı: bulmaca, çözüm, zorluk ve öznitelikler bir arada."""
        return {
            "id": puzzle_id,
            "rows": self.board.rows,
            "cols": self.board.cols,
            "code": to_code(self.board),
            "clues": [
                {"r": r, "c": c, "values": list(values)}
                for (r, c), values in sorted(self.board.clues.items())
            ],
            "solution": self.solution,
            "difficulty": self.difficulty.as_dict(),
            "features": self.features,
        }


def _features(board: Board, wall: set[Position]) -> dict[str, Any]:
    cells = board.rows * board.cols
    clue_values = [v for values in board.clues.values() for v in values]
    return {
        "cells": cells,
        "clueCount": len(board.clues),
        "clueDensity": round(len(board.clues) / cells, 4),
        "wallSize": len(wall),
        "wallDensity": round(len(wall) / cells, 4),
        "clueNumbers": len(clue_values),
        "maxClueValue": max(clue_values) if clue_values else 0,
        "multiNumberClues": sum(1 for v in board.clues.values() if len(v) > 1),
        "zeroClues": sum(1 for v in board.clues.values() if v == (0,)),
    }


def generate(rows: int, cols: int, rng: random.Random, *,
             wall_density: float = 0.5, aggressiveness: float = 1.0,
             max_level: int = solver.MAX_LEVEL, exact_level: bool = False,
             max_clue_value: int = 5, attempts: int = 60) -> Generated | None:
    """Mantıkla çözülebilen, tek çözümlü bir bulmaca üretir.

    `max_level` oyuncunun kullanmasına **izin verilen** en pahalı tekniktir:
    1 kolay, 2 orta, 3 zor, 4 çok zor (çelişkiyle çıkarım). Üretilen bulmaca
    daha ucuz tekniklerle de çözülebiliyorsa etiketi düşük kalır.

    `exact_level` açıkken yalnızca gerçekten o seviyeyi gerektiren bulmacalar
    kabul edilir. İstenen zorluğu garanti eder ama daha çok deneme ister.

    Başaramazsa None döner.
    """
    target = max(2, round(rows * cols * wall_density))

    for _ in range(attempts):
        wall = grow_wall(rows, cols, target, rng)
        if len(wall) < target * 0.75:
            continue  # büyüme erken tıkandı, yoğunluk hedefi tutmadı

        solved = Board(rows, cols)
        for pos in wall:
            solved.set_cell(*pos, Cell.FILLED)

        clues = covering_clues(solved, wall, rng, max_clue_value=max_clue_value)
        if clues is None:
            continue

        try:
            full = Board(rows, cols, clues)
        except Exception:
            continue
        # Kapsayan ipucu kümesi bile mantıkla çözülemiyorsa bu duvar uygun değil.
        if not solvable_by_logic(full, max_level):
            continue

        kept = trim_clues(rows, cols, clues, rng,
                          max_level=max_level, aggressiveness=aggressiveness)
        board = Board(rows, cols, kept)

        rating = solver.rate(board)
        if not (rating.unique and rating.logic_only):
            continue
        if exact_level and rating.effective_level != max_level:
            continue

        return Generated(
            board=board,
            solution=solution_to_rows(solved),
            difficulty=rating,
            features=_features(board, wall),
        )
    return None


@dataclass(frozen=True)
class Spec:
    """Tek bir üretim isteği."""

    rows: int
    cols: int
    wall_density: float = 0.5
    aggressiveness: float = 1.0
    max_level: int = solver.MAX_LEVEL
    exact_level: bool = False
    max_clue_value: int = 5


def generate_batch(specs: Iterable[Spec], rng: random.Random) -> list[Generated]:
    """İstek listesinden bulmaca üretir, aynısını iki kez üretmez."""
    out: list[Generated] = []
    seen: set[str] = set()
    for spec in specs:
        item = generate(spec.rows, spec.cols, rng,
                        wall_density=spec.wall_density,
                        aggressiveness=spec.aggressiveness,
                        max_level=spec.max_level,
                        exact_level=spec.exact_level,
                        max_clue_value=spec.max_clue_value)
        if item is None:
            continue
        code = to_code(item.board)
        if code in seen:
            continue  # aynı bulmacanın eğitim ve test kümesine birlikte düşmesini engeller
        seen.add(code)
        out.append(item)
    return out
