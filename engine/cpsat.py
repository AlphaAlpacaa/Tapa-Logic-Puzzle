"""Tapa'nın CP-SAT ile çözümü (Google OR-Tools).

Bu, `solver.py`'nin rakibi değil tamamlayıcısıdır. Oradaki çözücü Tapa'yı
*nasıl* çözeceğini adım adım bilir; buradaki ise yalnızca kuralları bildirir ve
aramayı CP-SAT'a bırakır. Üç işe yarar:

1. **Bağımsız doğrulama.** Tamamen farklı iki yöntemin aynı cevapta buluşması,
   doğruluk için elimizdeki en güçlü kanıt.
2. **Ölçeklenme.** Büyük tahtalarda mantıksal çözücü yavaşlıyor; CP-SAT'ın
   öğrenen araması oralarda daha iyi dayanır.
3. **Karşılaştırma tabanı.** İleride öğrenilmiş bir modelin işe yarayıp
   yaramadığı, ancak güçlü bir klasik rakibe karşı anlamlı biçimde ölçülebilir.

Bağımlılık isteğe bağlıdır: `ortools` kurulu değilse bu modül içe aktarılabilir
ama `available()` False döner ve çağrılar `CpSatUnavailable` yükseltir. Motorun
geri kalanı etkilenmez.

    pip install ortools
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .board import Board, Cell, Position
from . import rules
from .validator import validate_solution

try:  # ortools isteğe bağlı
    from ortools.sat.python import cp_model
    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - kurulu olmadığında
    cp_model = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


Connectivity = Literal["reach", "cuts", "none"]


class CpSatUnavailable(RuntimeError):
    """ortools kurulu değil."""


def available() -> bool:
    return cp_model is not None


def _require() -> None:
    if cp_model is None:
        raise CpSatUnavailable(
            "ortools kurulu değil. Kurmak için: pip install ortools"
        ) from _IMPORT_ERROR


# ---------------------------------------------------------------------- #
# Model kurulumu
# ---------------------------------------------------------------------- #

@dataclass
class Model:
    """Kurulmuş CP-SAT modeli ve hücre değişkenleri."""

    model: "cp_model.CpModel"
    cells: dict[Position, "cp_model.IntVar"]
    board: Board


def build_model(board: Board, connectivity: Connectivity = "cuts") -> Model:
    """Tapa kurallarını CP-SAT kısıtlarına çevirir.

    Tahtanın mevcut boyaması da modele sabit olarak girer; böylece aynı model
    hem sıfırdan çözmek hem de yarım bırakılmış bir tahtayı tamamlamak için
    kullanılabilir.
    """
    _require()
    model = cp_model.CpModel()

    cells: dict[Position, cp_model.IntVar] = {
        (r, c): model.NewBoolVar(f"x_{r}_{c}") for (r, c) in board.positions()
    }

    # K1 — ipucu hücreleri boyanmaz.
    for pos in board.clues:
        model.Add(cells[pos] == 0)

    # Oyuncunun / çözücünün şimdiye kadar kesinleştirdiği hücreler sabitlenir.
    for pos in board.positions():
        if board.is_clue(*pos):
            continue
        state = board.get_cell(*pos)
        if state is Cell.FILLED:
            model.Add(cells[pos] == 1)
        elif state is Cell.EMPTY:
            model.Add(cells[pos] == 0)

    _add_clue_constraints(model, cells, board)
    _add_square_constraints(model, cells, board)

    if connectivity == "reach":
        _add_reachability(model, cells, board)

    return Model(model=model, cells=cells, board=board)


def _add_clue_constraints(model, cells, board: Board) -> None:
    """Her ipucu için komşu sekizlisinin alabileceği desenleri tablo olarak verir.

    Geçerli desenleri zaten `rules.clue_candidates` hesaplıyor (en fazla 256
    olasılık). CP-SAT'ın tablo kısıtı bu listeyi doğrudan kabul ettiği için
    ipucu kuralı aritmetiğe çevrilmeden, olduğu gibi aktarılabiliyor.
    """
    blank = board.copy()
    blank.clear_marks()  # tablolar tahtanın mevcut durumundan bağımsız kurulur

    for (r, c) in board.clues:
        positions, candidates = rules.clue_candidates(blank, r, c)
        free = [
            (idx, pos) for idx, pos in enumerate(positions)
            if pos is not None and blank.get_cell(*pos) is Cell.UNKNOWN
        ]
        if not free:
            # Serbest komşu yok: ipucu ya zaten sağlanıyor ya da sağlanamaz.
            if not candidates:
                model.Add(cells[(r, c)] == 1)  # ipucu hücresi dolu olamaz → çözümsüz
            continue

        table = []
        for candidate in candidates:
            table.append(tuple(1 if candidate[idx] is Cell.FILLED else 0 for idx, _ in free))
        variables = [cells[pos] for _, pos in free]

        if not table:
            # Hiçbir desen ipucuyu sağlamıyor: model çözümsüz olmalı. Boş bir
            # AddBoolOr sürüme göre farklı davranabildiği için açık bir çelişki
            # kuruluyor.
            impossible = model.NewBoolVar(f"impossible_{r}_{c}")
            model.Add(impossible == 0)
            model.Add(impossible == 1)
        else:
            model.AddAllowedAssignments(variables, sorted(set(table)))


def _add_square_constraints(model, cells, board: Board) -> None:
    """K3 — hiçbir 2x2 blok tamamen dolu olamaz."""
    for r in range(board.rows - 1):
        for c in range(board.cols - 1):
            quad = [cells[(r, c)], cells[(r, c + 1)], cells[(r + 1, c)], cells[(r + 1, c + 1)]]
            model.Add(sum(quad) <= 3)


def _add_reachability(model, cells, board: Board) -> None:
    """K4 — bağlantılılık, erişilebilirlik etiketleriyle.

    Her dolu hücreye bir derinlik etiketi verilir. Tam olarak bir dolu hücre
    kök olur (etiket 0); diğer her dolu hücrenin, etiketi bir eksik olan dolu
    bir ortogonal komşuyu "öncül" seçmesi şart koşulur. Böylece her dolu
    hücreden köke azalan bir zincir uzanır ve duvar tek parça kalır.

    Akış tabanlı kodlamaya tercih edildi: büyük-M çarpımları gerektirmiyor,
    yalnızca ima kısıtları kullanıyor ve hücre başına dört boole değişkeniyle
    sınırlı kalıyor.
    """
    size = board.rows * board.cols
    depth = {
        pos: model.NewIntVar(0, size, f"d_{pos[0]}_{pos[1]}")
        for pos in board.positions()
    }
    root = {pos: model.NewBoolVar(f"root_{pos[0]}_{pos[1]}") for pos in board.positions()}

    has_wall = model.NewBoolVar("has_wall")
    model.Add(sum(cells.values()) >= 1).OnlyEnforceIf(has_wall)
    model.Add(sum(cells.values()) == 0).OnlyEnforceIf(has_wall.Not())
    model.Add(sum(root.values()) == 1).OnlyEnforceIf(has_wall)
    model.Add(sum(root.values()) == 0).OnlyEnforceIf(has_wall.Not())

    for pos in board.positions():
        model.AddImplication(root[pos], cells[pos])
        model.Add(depth[pos] == 0).OnlyEnforceIf(root[pos])

        preds = []
        for nb in board.orthogonal_neighbors(*pos):
            chosen = model.NewBoolVar(f"p_{pos[0]}_{pos[1]}_{nb[0]}_{nb[1]}")
            model.AddImplication(chosen, cells[nb])
            model.AddImplication(chosen, cells[pos])
            model.Add(depth[pos] == depth[nb] + 1).OnlyEnforceIf(chosen)
            preds.append(chosen)

        # Kök olmayan her dolu hücre tam olarak bir öncül seçer; boş hücre seçmez.
        model.Add(cp_model.LinearExpr.Sum(preds) == cells[pos] - root[pos])


# ---------------------------------------------------------------------- #
# Çözüm
# ---------------------------------------------------------------------- #

@dataclass
class CpSatResult:
    solutions: list[Board]
    count: int
    status: str
    elapsed: float = 0.0
    branches: int = 0
    conflicts: int = 0
    cut_rounds: int = 0          # yalnızca "cuts" kodlamasında
    hit_limit: bool = False      # zaman sınırına takıldı mı
    connectivity: str = "cuts"

    @property
    def unique(self) -> bool:
        return self.count == 1 and not self.hit_limit

    @property
    def solvable(self) -> bool:
        return self.count > 0

    def as_dict(self) -> dict:
        return {
            "count": self.count,
            "status": self.status,
            "elapsed": round(self.elapsed, 4),
            "branches": self.branches,
            "conflicts": self.conflicts,
            "cutRounds": self.cut_rounds,
            "hitLimit": self.hit_limit,
            "connectivity": self.connectivity,
        }


def _read_solution(board: Board, cells, solver) -> Board:
    out = board.copy()
    for pos in board.positions():
        if out.is_clue(*pos):
            continue
        out.set_cell(*pos, Cell.FILLED if solver.Value(cells[pos]) == 1 else Cell.EMPTY)
    return out


def _nogood(model, cells, board: Board, assignment: dict[Position, int]) -> None:
    """Bulunan çözümü bir daha üretmemesi için modele yasak ekler.

    Yalnızca oynanabilir hücreler kullanılır; ipucu hücreleri zaten sabit
    olduğu için yasağa katkıları olmaz.
    """
    literals = []
    for pos, value in assignment.items():
        if board.is_clue(*pos):
            continue
        literals.append(cells[pos].Not() if value == 1 else cells[pos])
    if literals:
        model.AddBoolOr(literals)


def _components(board: Board, filled: set[Position]) -> list[set[Position]]:
    remaining = set(filled)
    groups = []
    while remaining:
        seed = remaining.pop()
        group = {seed}
        queue = deque([seed])
        while queue:
            cur = queue.popleft()
            for nb in board.orthogonal_neighbors(*cur):
                if nb in remaining:
                    remaining.remove(nb)
                    group.add(nb)
                    queue.append(nb)
        groups.append(group)
    return groups


def _add_connectivity_cut(model, cells, board: Board, group: set[Position]) -> None:
    """Bir parçanın yalıtılmış kalmasını yasaklar.

    "Bu grubun tamamı dolu ve çevresi tamamen boş" durumu yasaklanır: ya
    gruptan bir hücre boşalır ya da sınırdan bir hücre dolar.
    """
    boundary = {
        nb for pos in group for nb in board.orthogonal_neighbors(*pos)
        if nb not in group
    }
    literals = [cells[pos].Not() for pos in sorted(group)]
    literals += [cells[pos] for pos in sorted(boundary)]
    model.AddBoolOr(literals)


def solve(board: Board, limit: int = 1, *, connectivity: Connectivity = "cuts",
          time_limit: float | None = 60.0, workers: int = 8) -> CpSatResult:
    """Bulmacayı CP-SAT ile çözer.

    `limit=2` teklik kontrolü için yeterlidir. Çözümler, bulunan her çözümü
    yasaklayıp yeniden çözerek sayılır; bu, yardımcı değişkenlerin aynı
    boyamayı birden çok kez saydırmasını engeller.

    `connectivity="cuts"` (varsayılan) önce bağlantılılık kısıtı olmadan çözer;
    sonuç parçalıysa o parçayı yasaklayıp yeniden dener. `"reach"` ise
    bağlantılılığı modelin içine gömer.

    Varsayılanın `cuts` olmasının sebebi ölçüm: ipucu ve 2x2 kısıtları
    bağlantılılığı pratikte zaten zorluyor, dolayısıyla kesme turu neredeyse
    hiç gerekmiyor ve `reach` kodlamasının eklediği değişkenler saf maliyete
    dönüşüyor. Ölçülen fark dört ila beş kat.
    """
    _require()
    started = time.perf_counter()

    work = board.copy()
    built = build_model(work, connectivity=connectivity)
    model, cells = built.model, built.cells

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = time_limit

    solutions: list[Board] = []
    branches = conflicts = cut_rounds = 0
    status_name = "UNKNOWN"
    hit_limit = False

    while len(solutions) < limit:
        if time_limit is not None:
            remaining = time_limit - (time.perf_counter() - started)
            if remaining <= 0:
                hit_limit = True
                break
            solver.parameters.max_time_in_seconds = remaining

        status = solver.Solve(model)
        status_name = solver.StatusName(status)
        branches += solver.NumBranches()
        conflicts += solver.NumConflicts()

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if status == cp_model.UNKNOWN:
                hit_limit = True
            break

        assignment = {pos: solver.Value(var) for pos, var in cells.items()}
        filled = {pos for pos, value in assignment.items() if value == 1}

        if connectivity == "cuts":
            groups = _components(work, filled)
            if len(groups) > 1:
                # Parçalı çözüm: en küçük parçayı yasakla, çözüm olarak sayma.
                _add_connectivity_cut(model, cells, work, min(groups, key=len))
                cut_rounds += 1
                continue

        candidate = _read_solution(work, cells, solver)
        if validate_solution(candidate).ok:
            solutions.append(candidate)
        _nogood(model, cells, work, assignment)

    return CpSatResult(
        solutions=solutions,
        count=len(solutions),
        status=status_name,
        elapsed=time.perf_counter() - started,
        branches=branches,
        conflicts=conflicts,
        cut_rounds=cut_rounds,
        hit_limit=hit_limit,
        connectivity=connectivity,
    )


def count_solutions(board: Board, limit: int = 2, **kwargs) -> int:
    return solve(board, limit=limit, **kwargs).count


def is_unique(board: Board, **kwargs) -> bool:
    return solve(board, limit=2, **kwargs).unique
