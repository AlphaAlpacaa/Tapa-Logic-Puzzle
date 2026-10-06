"""Tapa doğrulayıcısı.

İki ayrı mod sunar:

* `validate_solution` — tahtayı bitmiş bir çözüm gibi değerlendirir. Belirsiz
  hücreler boş sayılır. Oyun sonunda "doğru mu?" sorusunu yanıtlar.
* `validate_partial` — yalnızca kesinleşmiş çelişkileri raporlar. Oyuncu hamle
  yaparken anlık geri bildirim vermek ve çözücüde dalı budamak içindir.

Her iki mod da aynı `ValidationResult` yapısını döndürür; arayüz hatalı
hücreleri doğrudan `issue.cells` üzerinden boyayabilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .board import Board, Cell, Position
from . import rules


class IssueCode(str, Enum):
    CLUE_MISMATCH = "clue_mismatch"          # ipucu sayılarıyla komşuluk uyuşmuyor
    CLUE_IMPOSSIBLE = "clue_impossible"      # ipucu artık sağlanamaz (kısmi mod)
    SQUARE_2X2 = "square_2x2"                # 2x2 dolu alan
    DISCONNECTED = "disconnected"            # duvar parçalı
    CANNOT_CONNECT = "cannot_connect"        # duvar artık birleşemez (kısmi mod)
    INCOMPLETE = "incomplete"                # karar verilmemiş hücre var (katı mod)


@dataclass(frozen=True)
class ValidationIssue:
    code: IssueCode
    message: str
    cells: tuple[Position, ...] = ()


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_cells(self) -> set[Position]:
        """Arayüzde kırmızıya boyanacak hücreler."""
        return {cell for issue in self.issues for cell in issue.cells}

    def __bool__(self) -> bool:
        return self.ok


def validate_solution(board: Board, *, strict: bool = False) -> ValidationResult:
    """Tahtayı tamamlanmış bir çözüm olarak doğrular.

    `strict=True` ise belirsiz hücre bırakılması da hata sayılır; aksi hâlde
    belirsiz hücreler boş kabul edilir (oyuncuların her boş kareyi tek tek
    işaretlemesi gerekmez).
    """
    issues: list[ValidationIssue] = []

    if strict and not board.is_complete():
        unknown = tuple(sorted(board.unknown_cells()))
        issues.append(
            ValidationIssue(
                IssueCode.INCOMPLETE,
                f"{len(unknown)} hücre için karar verilmemiş.",
                unknown,
            )
        )

    # K2 — ipucular
    for (r, c), clue in sorted(board.clues.items()):
        actual = rules.runs_pattern(rules.ring_states(board, r, c))
        if actual != clue:
            issues.append(
                ValidationIssue(
                    IssueCode.CLUE_MISMATCH,
                    f"({r}, {c}) ipucusu {_fmt(clue)} bekliyor, çevresinde {_fmt(actual)} var.",
                    ((r, c),),
                )
            )

    # K3 — 2x2
    for quad in rules.square_violations(board):
        issues.append(
            ValidationIssue(
                IssueCode.SQUARE_2X2,
                f"{quad[0]} köşesinde 2x2'lik dolu alan var.",
                quad,
            )
        )

    # K4 — bağlantılılık
    groups = rules.wall_components(board)
    if len(groups) > 1:
        cells = tuple(sorted(cell for g in groups for cell in g))
        issues.append(
            ValidationIssue(
                IssueCode.DISCONNECTED,
                f"Duvar {len(groups)} ayrı parçaya bölünmüş.",
                cells,
            )
        )

    return ValidationResult(ok=not issues, issues=issues)


def validate_partial(board: Board) -> ValidationResult:
    """Yalnızca geri dönüşü olmayan çelişkileri raporlar.

    Henüz tamamlanmamış bir tahtada "bu hamle kesin yanlış" demenin ölçütü:
    bir ipucu hiçbir boyamayla sağlanamıyor, 2x2 oluşmuş ya da duvar parçaları
    artık birleşemiyor.
    """
    issues: list[ValidationIssue] = []

    for (r, c), clue in sorted(board.clues.items()):
        if not rules.clue_is_possible(board, r, c):
            issues.append(
                ValidationIssue(
                    IssueCode.CLUE_IMPOSSIBLE,
                    f"({r}, {c}) ipucusu {_fmt(clue)} artık sağlanamaz.",
                    ((r, c),),
                )
            )

    for quad in rules.square_violations(board):
        issues.append(
            ValidationIssue(
                IssueCode.SQUARE_2X2,
                f"{quad[0]} köşesinde 2x2'lik dolu alan var.",
                quad,
            )
        )

    if not rules.wall_can_still_connect(board):
        issues.append(
            ValidationIssue(
                IssueCode.CANNOT_CONNECT,
                "Duvar parçaları birbirine bağlanamaz hâle geldi.",
                tuple(sorted(board.filled_cells())),
            )
        )

    return ValidationResult(ok=not issues, issues=issues)


def is_solved(board: Board) -> bool:
    return validate_solution(board).ok


def _fmt(clue: tuple[int, ...]) -> str:
    return " ".join(str(n) for n in clue)
