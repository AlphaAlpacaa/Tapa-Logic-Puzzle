"""Tapa çözücüsü.

İki parçadan oluşur:

* **Yayılım** — kesin çıkarım teknikleri, ucuzdan pahalıya sırayla uygulanır.
  Her teknik bir *seviye* taşır; çözücü bir bulmacayı hangi seviyeye kadar
  çıkarak bitirdiğini kaydeder ve zorluk ölçüsü buradan türetilir.
* **Arama** — yayılım tıkandığında en kısıtlı hücreden dallanma.

Teknikler `TECHNIQUES` listesinde kayıtlıdır. Yeni bir çıkarım eklemek, bu
listeye bir satır yazmaktan ibarettir; çözücünün geri kalanı değişmez. Zorluk
ölçeği de teknik listesi zenginleştikçe kendiliğinden incelir.

Her tekniğin tek bir sözü vardır: döndürdüğü her hücre, **mevcut bilgiyle
kesin olarak** o durumda olmak zorundadır. Tahmin yoktur; tahmin aramanın işi.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .board import Board, Cell, Position
from . import rules
from .validator import validate_partial, validate_solution

Deductions = dict[Position, Cell]


# ---------------------------------------------------------------------- #
# Yardımcılar
# ---------------------------------------------------------------------- #

def _squares_touching(board: Board, cells: Iterable[Position]) -> set[Position]:
    """Verilen hücrelerden en az birini içeren 2x2 blokların sol üst köşeleri."""
    corners: set[Position] = set()
    for (r, c) in cells:
        for dr in (-1, 0):
            for dc in (-1, 0):
                tr, tc = r + dr, c + dc
                if 0 <= tr < board.rows - 1 and 0 <= tc < board.cols - 1:
                    corners.add((tr, tc))
    return corners


def _breaks_square(board: Board, assignment: dict[Position, Cell]) -> bool:
    """Verilen atama uygulanırsa tamamen dolu bir 2x2 oluşur mu."""
    for (r, c) in _squares_touching(board, assignment):
        quad = ((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1))
        if all(assignment.get(p, board.get_cell(*p)) is Cell.FILLED for p in quad):
            return True
    return False


def _reachable_components(board: Board) -> list[set[Position]]:
    """Dolu ve belirsiz hücrelerin birlikte oluşturduğu bileşenler.

    Duvar yalnızca bu bileşenlerden birinin içinde büyüyebilir.
    """
    pool = board.filled_cells() | board.unknown_cells()
    groups: list[set[Position]] = []
    remaining = set(pool)
    while remaining:
        seed = remaining.pop()
        group = {seed}
        queue = deque([seed])
        while queue:
            r, c = queue.popleft()
            for nb in board.orthogonal_neighbors(r, c):
                if nb in remaining:
                    remaining.remove(nb)
                    group.add(nb)
                    queue.append(nb)
        groups.append(group)
    return groups


# ---------------------------------------------------------------------- #
# Teknik 1 — ipucu okuma
# ---------------------------------------------------------------------- #

def clue_reading(board: Board) -> Deductions:
    """Bir ipucunun kalan tüm olasılıklarında aynı olan komşular zorunludur."""
    found: Deductions = {}
    for (r, c) in board.clues:
        positions, candidates = rules.clue_candidates(board, r, c)
        if not candidates:
            continue  # çelişki; ayrı kontrol yakalar
        for idx, pos in enumerate(positions):
            if pos is None or board.get_cell(*pos) is not Cell.UNKNOWN:
                continue
            states = {cand[idx] for cand in candidates}
            if len(states) == 1:
                found[pos] = next(iter(states))
    return found


# ---------------------------------------------------------------------- #
# Teknik 2 — 2x2 yasağıyla birlikte ipucu okuma
# ---------------------------------------------------------------------- #

def square_rule(board: Board) -> Deductions:
    """Bir 2x2 bloğun üçü doluysa dördüncüsü boş olmak zorundadır."""
    found: Deductions = {}
    for r in range(board.rows - 1):
        for c in range(board.cols - 1):
            quad = ((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1))
            states = [board.get_cell(*p) for p in quad]
            if states.count(Cell.FILLED) == 3 and states.count(Cell.UNKNOWN) == 1:
                found[quad[states.index(Cell.UNKNOWN)]] = Cell.EMPTY
    return found


def clue_reading_with_squares(board: Board) -> Deductions:
    """İpucu olasılıklarından 2x2 oluşturanları eleyip yeniden bakar.

    Teknik 1'den güçlüdür: tek başına ipucu kuralını sağlayan bir boyama,
    2x2 yasağını çiğnediği için elenebilir ve geriye tek seçenek kalabilir.
    """
    found: Deductions = {}
    for (r, c) in board.clues:
        positions, candidates = rules.clue_candidates(board, r, c)
        viable = []
        for cand in candidates:
            assignment = {
                pos: cand[idx]
                for idx, pos in enumerate(positions)
                if pos is not None and board.get_cell(*pos) is Cell.UNKNOWN
            }
            if not _breaks_square(board, assignment):
                viable.append(cand)
        if not viable:
            continue
        for idx, pos in enumerate(positions):
            if pos is None or board.get_cell(*pos) is not Cell.UNKNOWN:
                continue
            states = {cand[idx] for cand in viable}
            if len(states) == 1:
                found[pos] = next(iter(states))
    return found


# ---------------------------------------------------------------------- #
# Teknik 3 — bağlantılılık
# ---------------------------------------------------------------------- #

def unreachable_cells(board: Board) -> Deductions:
    """Duvara hiçbir zaman bağlanamayacak hücreler boş olmak zorundadır.

    Bir belirsiz hücre, dolu-veya-belirsiz hücrelerden oluşan bileşeninde hiç
    dolu hücre yoksa ve tahtada başka yerde dolu hücre varsa, doldurulduğunda
    duvardan kopuk kalırdı.
    """
    filled = board.filled_cells()
    if not filled:
        return {}
    found: Deductions = {}
    for group in _reachable_components(board):
        if group & filled:
            continue
        for pos in group:
            if board.get_cell(*pos) is Cell.UNKNOWN:
                found[pos] = Cell.EMPTY
    return found


def connection_bottleneck(board: Board) -> Deductions:
    """Boşaltıldığında duvarı kopartacak hücreler dolu olmak zorundadır.

    Aranan şey, dolu-veya-belirsiz hücre grafiğinde iki dolu hücreyi birbirinden
    ayıran kesme noktalarıdır (cut vertex). Naif yol her hücreyi tek tek boş
    varsayıp grafiği yeniden taramaktır; bu O(hücre²) olur ve büyük tahtalarda
    üreticiyi dizlerinin üstüne çökertir. Burada Tarjan'ın kesme noktası
    taraması tek geçişte yapılıyor: her düğümün alt ağacındaki dolu hücre
    sayısı da taşınarak, ayrılan parçanın gerçekten dolu hücre içerip içermediği
    aynı anda anlaşılıyor.
    """
    filled = board.filled_cells()
    if len(filled) < 2:
        return {}

    pool = filled | board.unknown_cells()
    root = min(filled)

    disc: dict[Position, int] = {}
    low: dict[Position, int] = {}
    subtree_filled: dict[Position, int] = {}
    parent: dict[Position, Position | None] = {root: None}
    required: set[Position] = set()
    timer = 0

    # Yinelemeli yerine döngüsel DFS: büyük tahtalarda yığın derinliği sorun olur.
    stack: list[tuple[Position, list[Position]]] = [
        (root, [nb for nb in board.orthogonal_neighbors(*root) if nb in pool])
    ]
    disc[root] = low[root] = timer
    subtree_filled[root] = 1 if root in filled else 0
    timer += 1

    while stack:
        node, pending = stack[-1]
        if pending:
            nxt = pending.pop()
            if nxt in disc:
                if nxt is not parent[node]:
                    low[node] = min(low[node], disc[nxt])
                continue
            parent[nxt] = node
            disc[nxt] = low[nxt] = timer
            subtree_filled[nxt] = 1 if nxt in filled else 0
            timer += 1
            stack.append((nxt, [nb for nb in board.orthogonal_neighbors(*nxt) if nb in pool]))
        else:
            stack.pop()
            upper = parent[node]
            if upper is not None:
                low[upper] = min(low[upper], low[node])
                subtree_filled[upper] += subtree_filled[node]
                # `upper` silinirse `node`'un alt ağacı kopar. Kopan parçada da,
                # geri kalanda da dolu hücre varsa `upper` zorunlu olarak duvarın
                # parçasıdır.
                if (
                    low[node] >= disc[upper]
                    and board.get_cell(*upper) is Cell.UNKNOWN
                    and 0 < subtree_filled[node] < len(filled)
                ):
                    required.add(upper)

    # Dolu hücrelerin hepsi aynı bileşende değilse tahta zaten çelişkili;
    # çıkarım üretmek yerine çelişki kontrolüne bırakılır.
    if sum(1 for pos in filled if pos in disc) != len(filled):
        return {}

    return {pos: Cell.FILLED for pos in required}


# ---------------------------------------------------------------------- #
# Teknik 4 — çelişkiyle çıkarım (varsayım kurup çürütme)
# ---------------------------------------------------------------------- #

def contradiction_reasoning(board: Board) -> Deductions:
    """Bir hücre için varsayım kurup çelişkiye varıldığında tersini kanıtlar.

    "Bu hücre dolu olsaydı ne olurdu?" diye varsayılır, ucuz teknikler sonuna
    kadar yayılır; çelişki çıkarsa hücrenin boş olduğu **kesin** olarak bilinir.
    Bu kör tahmin değildir: sonuç belirlenmiştir ve bulmaca tek çözümlü kalır.
    İnsan çözücülerin zor bulmacalarda yaptığı şeyin karşılığı.

    Yalnızca birinci derece varsayım kurulur (varsayım içinde varsayım yok) ve
    ilk kanıt bulunduğunda durulur; yayılım zaten en ucuz tekniğe geri dönecek.
    """
    unknown = board.unknown_cells()
    if not unknown:
        return {}

    # Bilgiye yakın hücreler önce denenir: ipucu komşuları ve duvara bitişikler.
    near_clue = {
        pos for (r, c) in board.clues for pos in board.ring(r, c)
        if pos is not None and pos in unknown
    }
    near_wall = {
        nb for (r, c) in board.filled_cells()
        for nb in board.orthogonal_neighbors(r, c) if nb in unknown
    }
    candidates = sorted(near_clue | near_wall) or sorted(unknown)

    for pos in candidates:
        for assumed, proven in ((Cell.FILLED, Cell.EMPTY), (Cell.EMPTY, Cell.FILLED)):
            trial = board.copy()
            trial.set_cell(*pos, assumed)
            # Varsayımın içinde yalnızca daha ucuz teknikler çalışır; bu hem
            # sonsuz özyinelemeyi engeller hem de maliyeti sınırlar.
            if not propagate(trial, SolveStats(), max_level=DEDUCTION_LEVEL):
                return {pos: proven}
    return {}


# ---------------------------------------------------------------------- #
# Teknik kaydı
# ---------------------------------------------------------------------- #

@dataclass(frozen=True)
class Technique:
    name: str
    level: int
    apply: Callable[[Board], Deductions]
    description: str


#: Ucuzdan pahalıya sıralı. Yeni teknikler buraya eklenir.
TECHNIQUES: tuple[Technique, ...] = (
    Technique(
        "ipucu okuma", 1, clue_reading,
        "İpucunun kalan tüm olasılıklarında aynı kalan komşular.",
    ),
    Technique(
        "2x2 kuralı", 2, square_rule,
        "Bir 2x2 bloğun üçü doluysa dördüncüsü boştur.",
    ),
    Technique(
        "ipucu + 2x2", 2, clue_reading_with_squares,
        "2x2 oluşturan olasılıklar elendikten sonra kalan zorunluluklar.",
    ),
    Technique(
        "ulaşılmaz bölge", 3, unreachable_cells,
        "Duvara hiçbir yoldan bağlanamayacak hücreler boştur.",
    ),
    Technique(
        "bağlantı boğazı", 3, connection_bottleneck,
        "Boşaltılırsa duvarı kopartacak hücreler doludur.",
    ),
    Technique(
        "çelişkiyle çıkarım", 4, contradiction_reasoning,
        "Varsayım kurulup çelişkiye varıldığı için tersi kanıtlanan hücreler.",
    ),
)

MAX_LEVEL = max(t.level for t in TECHNIQUES)

#: Varsayım tekniğinin *içinde* kullanılabilecek en pahalı seviye. Varsayım
#: içinde varsayım kurulmaz: hem sonsuz özyineleme engellenir hem maliyet
#: sınırlanır.
DEDUCTION_LEVEL = 3

#: Aramanın düğümlerinde kullanılan seviye. Arama zaten dallandığı için pahalı
#: varsayım tekniğini orada tekrar çalıştırmak gereksiz iş olur.
SEARCH_LEVEL = 3

#: Bir seviyenin "gerçekten gerekti" sayılması için o seviyedeki tekniklerin
#: en az kaç hücre açması gerektiği. Tek bir hücre için çelişki kuran bulmaca,
#: yirmi hücre için kuranla aynı etiketi almamalı: oyuncu birincisini fark bile
#: etmeden çözer.
MIN_USES = {1: 1, 2: 1, 3: 2, 4: 3}

LEVEL_LABELS = {
    0: "boş",
    1: "kolay",
    2: "orta",
    3: "zor",
    4: "çok zor",
    5: "adil değil",
}


# ---------------------------------------------------------------------- #
# Yayılım
# ---------------------------------------------------------------------- #

@dataclass
class SolveStats:
    """Çözüm sürecinin izi — zorluk ölçüsü buradan çıkar."""

    nodes: int = 0                 # arama düğümü sayısı
    guesses: int = 0               # varsayım sayısı
    deductions: int = 0            # kesin olarak yerleştirilen hücre
    max_level: int = 0             # kullanılan en pahalı teknik seviyesi
    technique_use: dict[str, int] = field(default_factory=dict)
    level_use: dict[int, int] = field(default_factory=dict)
    elapsed: float = 0.0
    logic_only: bool = True        # kör tahmine hiç gerek kalmadı mı
    timed_out: bool = False        # zaman sınırına takıldı mı

    @property
    def effective_level(self) -> int:
        """Etiketlemede kullanılan seviye: asgari kullanım şartını geçen en üst seviye.

        Pahalı bir teknik yalnızca bir iki hücre açtıysa bulmaca o seviyeden
        sayılmaz; oyuncu o adımı fark etmeden de çözebilir.
        """
        best = 0
        for level, used in self.level_use.items():
            if used >= MIN_USES.get(level, 1):
                best = max(best, level)
        return best

    @property
    def label(self) -> str:
        if not self.logic_only:
            return LEVEL_LABELS[5]
        return LEVEL_LABELS.get(self.effective_level, LEVEL_LABELS[0])

    def record(self, technique: Technique, count: int) -> None:
        self.technique_use[technique.name] = self.technique_use.get(technique.name, 0) + count
        self.level_use[technique.level] = self.level_use.get(technique.level, 0) + count
        self.deductions += count
        self.max_level = max(self.max_level, technique.level)


@dataclass
class Step:
    """Tek bir çıkarım — "ipucu ver" özelliği ve açıklanabilirlik için."""

    cell: Position
    state: Cell
    technique: Technique


def contradicted(board: Board) -> bool:
    return not validate_partial(board).ok


def next_step(board: Board, max_level: int = MAX_LEVEL) -> Step | None:
    """En ucuz teknikle bulunabilen ilk kesin hücreyi döndürür."""
    for technique in TECHNIQUES:
        if technique.level > max_level:
            break
        for pos, state in sorted(technique.apply(board).items()):
            if board.get_cell(*pos) is Cell.UNKNOWN:
                return Step(pos, state, technique)
    return None


def propagate(board: Board, stats: SolveStats, max_level: int = MAX_LEVEL) -> bool:
    """Kesin çıkarımları doyuma kadar uygular. Çelişki bulursa False.

    Her turda en ucuz tekniğe geri döner: pahalı bir teknik bir hücre açtıysa,
    sonrasında ucuz teknikler yeniden iş görebilir. Bu sıra hem performans
    hem de zorluk ölçümü için önemli — bir bulmaca ancak gerçekten gerekiyorsa
    üst seviye olarak işaretlenir.
    """
    while True:
        if contradicted(board):
            return False

        progressed = False
        for technique in TECHNIQUES:
            if technique.level > max_level:
                break  # bu ve sonrası izin verilen seviyenin üstünde
            found = {
                pos: state
                for pos, state in technique.apply(board).items()
                if board.get_cell(*pos) is Cell.UNKNOWN
            }
            if found:
                for pos, state in found.items():
                    board.set_cell(*pos, state)
                stats.record(technique, len(found))
                progressed = True
                break  # en ucuz tekniğe geri dön

        if not progressed:
            return True


# ---------------------------------------------------------------------- #
# Arama
# ---------------------------------------------------------------------- #

def _branch_cell(board: Board) -> Position | None:
    """Dallanılacak hücre: en az olasılığı kalan ipucunun komşuları önce."""
    unknown = board.unknown_cells()
    if not unknown:
        return None
    best: tuple[int, Position] | None = None
    for (r, c) in board.clues:
        positions, candidates = rules.clue_candidates(board, r, c)
        if not candidates:
            continue
        for pos in positions:
            if pos in unknown:
                score = len(candidates)
                if best is None or score < best[0]:
                    best = (score, pos)
    if best:
        return best[1]
    # İpucuya komşu hücre kalmadıysa duvara bitişik olandan devam et.
    filled = board.filled_cells()
    adjacent = {
        nb for (r, c) in filled for nb in board.orthogonal_neighbors(r, c) if nb in unknown
    }
    return min(adjacent) if adjacent else min(unknown)


@dataclass
class SolveResult:
    solutions: list[Board]
    count: int
    stats: SolveStats

    @property
    def unique(self) -> bool:
        return self.count == 1

    @property
    def solvable(self) -> bool:
        return self.count > 0


def solve(board: Board, limit: int = 1, max_level: int = SEARCH_LEVEL,
          time_limit: float | None = None) -> SolveResult:
    """Bulmacayı çözer. `limit=2` ile teklik kontrolü yapılır.

    `time_limit` verilirse arama o süreyi aşınca durur ve `stats.timed_out`
    işaretlenir. Kıyaslamalarda ve zor örneklerde donmayı engeller; sonuç o
    durumda eksik olabilir.
    """
    stats = SolveStats()
    started = time.perf_counter()
    solutions: list[Board] = []
    deadline = None if time_limit is None else started + time_limit
    _search(board.copy(), limit, max_level, stats, solutions, deadline)
    stats.elapsed = time.perf_counter() - started
    return SolveResult(solutions=solutions, count=len(solutions), stats=stats)


def _search(board: Board, limit: int, max_level: int, stats: SolveStats,
            out: list[Board], deadline: float | None = None) -> None:
    if deadline is not None and time.perf_counter() > deadline:
        stats.timed_out = True
        return

    stats.nodes += 1
    if not propagate(board, stats, max_level):
        return

    cell = _branch_cell(board)
    if cell is None:
        if validate_solution(board).ok:
            out.append(board)
        return

    stats.guesses += 1
    stats.logic_only = False
    for state in (Cell.FILLED, Cell.EMPTY):
        if len(out) >= limit or stats.timed_out:
            return
        trial = board.copy()
        trial.set_cell(*cell, state)
        _search(trial, limit, max_level, stats, out, deadline)


def solve_logically(board: Board, max_level: int = MAX_LEVEL) -> tuple[Board, SolveStats]:
    """Yalnızca kesin çıkarımlarla ilerler, varsayım yapmaz.

    Dönen tahta tamamlanmamış olabilir: `is_complete()` False ise bulmaca saf
    mantıkla bitmiyor demektir.
    """
    work = board.copy()
    stats = SolveStats()
    started = time.perf_counter()
    propagate(work, stats, max_level)
    stats.elapsed = time.perf_counter() - started
    return work, stats


def count_solutions(board: Board, limit: int = 2) -> int:
    return solve(board, limit=limit).count


def is_unique(board: Board) -> bool:
    return count_solutions(board, limit=2) == 1


# ---------------------------------------------------------------------- #
# Zorluk
# ---------------------------------------------------------------------- #

@dataclass
class Difficulty:
    label: str
    max_level: int
    effective_level: int
    logic_only: bool
    guesses: int
    deductions: int
    technique_use: dict[str, int]
    unique: bool
    elapsed: float

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "maxLevel": self.max_level,
            "effectiveLevel": self.effective_level,
            "logicOnly": self.logic_only,
            "guesses": self.guesses,
            "deductions": self.deductions,
            "techniques": self.technique_use,
            "unique": self.unique,
            "elapsed": round(self.elapsed, 4),
        }


def rate(board: Board) -> Difficulty:
    """Bulmacanın zorluğunu, çözmek için gereken en pahalı tekniğe göre ölçer.

    Ölçek bilinçli olarak kaba: teknik listesi zenginleştikçe incelecek.
    İnsan çözüm süreleriyle kalibre edilmediği sürece bu bir sıralama
    ölçüsüdür, mutlak bir zorluk değeri değil.
    """
    work = board.copy()
    work.clear_marks()

    logical, logic_stats = solve_logically(work)
    if logical.is_complete() and validate_solution(logical).ok:
        full = solve(work, limit=2)
        return Difficulty(
            label=logic_stats.label,
            max_level=logic_stats.max_level,
            effective_level=logic_stats.effective_level,
            logic_only=True,
            guesses=0,
            deductions=logic_stats.deductions,
            technique_use=dict(logic_stats.technique_use),
            unique=full.unique,
            elapsed=logic_stats.elapsed,
        )

    full = solve(work, limit=2)
    return Difficulty(
        label=LEVEL_LABELS[5],
        max_level=MAX_LEVEL + 1,
        effective_level=MAX_LEVEL + 1,
        logic_only=False,
        guesses=full.stats.guesses,
        deductions=full.stats.deductions,
        technique_use=dict(full.stats.technique_use),
        unique=full.unique,
        elapsed=full.stats.elapsed,
    )
