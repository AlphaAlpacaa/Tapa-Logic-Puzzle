"""Tapa'nın kuralları — tahtadan bağımsız, saf fonksiyonlar.

Kurallar:
  K1  İpucu hücreleri boyanmaz.
  K2  Bir ipucu hücresinin 8 komşusu saat yönünde okunduğunda oluşan ardışık
      dolu blokların uzunlukları, ipucu sayılarına eşittir. Halka döngüseldir,
      bu yüzden sayıların sırası önemsizdir; bloklar arasında en az bir boş
      hücre bulunur. Izgara dışı komşular boş sayılır.
  K3  Hiçbir yerde 2x2'lik tamamen dolu alan bulunamaz.
  K4  Tüm dolu hücreler tek bir ortogonal bağlı grup (duvar) oluşturur.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Sequence

from .board import Board, Cell, Clue, Position, normalize_clue

RingStates = tuple[Cell, ...]


# ---------------------------------------------------------------------- #
# K2 — halka okuma ve blok deseni
# ---------------------------------------------------------------------- #

def ring_states(board: Board, r: int, c: int) -> RingStates:
    """Hücrenin 8 komşusunun durumu, saat yönünde. Izgara dışı = EMPTY."""
    out: list[Cell] = []
    for pos in board.ring(r, c):
        out.append(Cell.EMPTY if pos is None else board.get_cell(*pos))
    return tuple(out)


def runs_pattern(states: Sequence[Cell]) -> Clue:
    """Halkadaki ardışık dolu blokların uzunluklarını kanonik ipucu olarak verir.

    UNKNOWN hücreler boş kabul edilir; bu fonksiyon tamamlanmış bir halkayı
    değerlendirmek içindir. Kısmi durumlar için `clue_candidates` kullanılır.
    """
    filled = [s is Cell.FILLED for s in states]
    n = len(filled)
    if all(filled):
        return (n,)
    if not any(filled):
        return (0,)
    # Boş bir hücreden başlayarak okursak hiçbir blok başa sarmaz.
    start = next(i for i in range(n) if not filled[i])
    runs: list[int] = []
    current = 0
    for k in range(n):
        if filled[(start + k) % n]:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return tuple(sorted(runs, reverse=True))


def clue_satisfied(board: Board, r: int, c: int) -> bool:
    """İpucu, tahtanın mevcut (tamamlanmış sayılan) boyamasıyla uyuşuyor mu."""
    clue = board.clue_at(r, c)
    if clue is None:
        raise ValueError(f"({r}, {c}) bir ipucu hücresi değil.")
    return runs_pattern(ring_states(board, r, c)) == clue


def clue_candidates(board: Board, r: int, c: int) -> tuple[list[Position | None], list[RingStates]]:
    """İpucunu sağlayan tüm halka boyamalarını üretir.

    Yalnızca UNKNOWN komşular serbest bırakılır; zaten karar verilmiş hücreler
    sabit tutulur. En fazla 2^8 = 256 olasılık denendiği için ucuzdur ve hem
    canlı geri bildirimde hem de çözücünün yayılım adımında kullanılır.

    Dönen liste boşsa ipucu mevcut boyamayla çelişiyor demektir.
    """
    clue = board.clue_at(r, c)
    if clue is None:
        raise ValueError(f"({r}, {c}) bir ipucu hücresi değil.")
    positions = board.ring(r, c)
    base = list(ring_states(board, r, c))
    free = [i for i, s in enumerate(base) if s is Cell.UNKNOWN]
    found: list[RingStates] = []
    for mask in range(1 << len(free)):
        trial = list(base)
        for bit, idx in enumerate(free):
            trial[idx] = Cell.FILLED if (mask >> bit) & 1 else Cell.EMPTY
        if runs_pattern(trial) == clue:
            found.append(tuple(trial))
    return positions, found


def clue_is_possible(board: Board, r: int, c: int) -> bool:
    """İpucu, kalan belirsiz hücrelerle hâlâ sağlanabilir mi."""
    _, candidates = clue_candidates(board, r, c)
    return bool(candidates)


def forced_cells(board: Board) -> dict[Position, Cell]:
    """Tek bir ipucuna bakarak kesin olarak çıkarılabilen hücreleri verir.

    Bir komşu, ipucunun tüm olası boyamalarında aynı durumdaysa o durum
    zorunludur. Çözücünün ve "ipucu ver" özelliğinin temel yayılım adımı.
    """
    deductions: dict[Position, Cell] = {}
    for (r, c) in board.clues:
        positions, candidates = clue_candidates(board, r, c)
        if not candidates:
            continue
        for idx, pos in enumerate(positions):
            if pos is None or board.get_cell(*pos) is not Cell.UNKNOWN:
                continue
            states = {cand[idx] for cand in candidates}
            if len(states) == 1:
                deductions[pos] = states.pop()
    return deductions


# ---------------------------------------------------------------------- #
# K3 — 2x2 yasağı
# ---------------------------------------------------------------------- #

def square_violations(board: Board) -> list[tuple[Position, ...]]:
    """Tamamen dolu 2x2 blokların listesi (her biri 4 konum)."""
    bad = []
    for r in range(board.rows - 1):
        for c in range(board.cols - 1):
            quad = ((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1))
            if all(board.get_cell(*p) is Cell.FILLED for p in quad):
                bad.append(quad)
    return bad


# ---------------------------------------------------------------------- #
# K4 — bağlantılılık
# ---------------------------------------------------------------------- #

def _components(board: Board, cells: set[Position]) -> list[set[Position]]:
    """Verilen hücre kümesinin ortogonal bağlı bileşenleri."""
    remaining = set(cells)
    groups: list[set[Position]] = []
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


def wall_components(board: Board) -> list[set[Position]]:
    return _components(board, board.filled_cells())


def wall_is_connected(board: Board) -> bool:
    """Tüm dolu hücreler tek parça mı. Hiç dolu hücre yoksa koşul sağlanmış sayılır."""
    return len(wall_components(board)) <= 1


def wall_can_still_connect(board: Board) -> bool:
    """Kısmi tahtada duvarın birleşme ihtimali kaldı mı.

    Dolu ve belirsiz hücreler birlikte düşünüldüğünde, dolu hücrelerin hepsi
    aynı bileşene düşüyorsa birleşme hâlâ mümkündür.
    """
    filled = board.filled_cells()
    if len(filled) <= 1:
        return True
    reachable = filled | board.unknown_cells()
    for group in _components(board, reachable):
        if filled <= group:
            return True
    return False
