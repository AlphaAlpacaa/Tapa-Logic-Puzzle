"""Tapa tahtasının veri yapısı.

Tahta iki katmandan oluşur:
  1. İpucu katmanı  : hangi hücrede hangi sayı(lar) var. Oyun boyunca değişmez.
  2. Boyama katmanı : her hücrenin durumu (bilinmiyor / dolu / boş). Oyuncu veya
                      çözücü bu katmanı değiştirir.

İpucu hücreleri Tapa kuralı gereği asla boyanmaz; bu sınıf bunu zorunlu kılar.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Iterator, Mapping, Sequence

Position = tuple[int, int]
Clue = tuple[int, ...]

#: Bir hücrenin 8 komşusu, saat yönünde, sol üst köşeden başlayarak.
#: Tapa'da ipucu sayıları bu halka üzerinde okunduğu için sıra kritiktir.
RING_OFFSETS: tuple[Position, ...] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
    (1, 0),
    (1, -1),
    (0, -1),
)

MAX_CLUE_NUMBERS = 4  # bir hücrede en fazla 4 sayı bulunabilir


class Cell(IntEnum):
    """Boyama katmanındaki hücre durumları."""

    UNKNOWN = 0  # henüz karar verilmemiş
    FILLED = 1   # duvarın parçası (boyalı)
    EMPTY = 2    # kesin boş (oyuncunun nokta koyduğu hücre)


class ClueError(ValueError):
    """Geometrik olarak imkânsız veya biçimsel olarak hatalı ipucu."""


def normalize_clue(values: Sequence[int]) -> Clue:
    """İpucu sayılarını kanonik biçime çevirir: büyükten küçüğe sıralı demet.

    Tapa'da halka döngüsel okunduğu için sayıların yazılış sırası anlamsızdır;
    karşılaştırmaları kolaylaştırmak adına her ipucu sıralı tutulur.
    """
    nums = list(values)
    if not nums:
        raise ClueError("İpucu en az bir sayı içermelidir.")
    if len(nums) > MAX_CLUE_NUMBERS:
        raise ClueError(f"Bir hücrede en fazla {MAX_CLUE_NUMBERS} sayı olabilir.")
    for n in nums:
        if not isinstance(n, int) or isinstance(n, bool):
            raise ClueError(f"İpucu sayıları tam sayı olmalıdır: {n!r}")
        if not 0 <= n <= 8:
            raise ClueError(f"İpucu sayıları 0-8 aralığında olmalıdır: {n}")
    if 0 in nums and len(nums) > 1:
        raise ClueError("0 ipucusu tek başına kullanılır.")
    return tuple(sorted(nums, reverse=True))


class Board:
    """Değişken boyutlu Tapa tahtası."""

    __slots__ = ("rows", "cols", "_clues", "_cells")

    def __init__(
        self,
        rows: int,
        cols: int,
        clues: Mapping[Position, Sequence[int]] | None = None,
    ) -> None:
        if rows < 1 or cols < 1:
            raise ValueError("Izgara en az 1x1 olmalıdır.")
        self.rows = rows
        self.cols = cols
        self._clues: dict[Position, Clue] = {}
        self._cells: list[list[Cell]] = [
            [Cell.UNKNOWN] * cols for _ in range(rows)
        ]
        for (r, c), values in (clues or {}).items():
            self.set_clue(r, c, values)

    # ------------------------------------------------------------------ #
    # Konum yardımcıları
    # ------------------------------------------------------------------ #

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def _require_bounds(self, r: int, c: int) -> None:
        if not self.in_bounds(r, c):
            raise IndexError(f"({r}, {c}) ızgara dışında (boyut {self.rows}x{self.cols}).")

    def positions(self) -> Iterator[Position]:
        for r in range(self.rows):
            for c in range(self.cols):
                yield (r, c)

    def ring(self, r: int, c: int) -> list[Position | None]:
        """Hücrenin 8 komşusunu saat yönünde verir; ızgara dışı için None."""
        out: list[Position | None] = []
        for dr, dc in RING_OFFSETS:
            nr, nc = r + dr, c + dc
            out.append((nr, nc) if self.in_bounds(nr, nc) else None)
        return out

    def orthogonal_neighbors(self, r: int, c: int) -> list[Position]:
        """Duvar bağlantısı için kullanılan 4 komşu (çapraz sayılmaz)."""
        out = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if self.in_bounds(nr, nc):
                out.append((nr, nc))
        return out

    # ------------------------------------------------------------------ #
    # İpucu katmanı
    # ------------------------------------------------------------------ #

    @property
    def clues(self) -> dict[Position, Clue]:
        return dict(self._clues)

    def clue_at(self, r: int, c: int) -> Clue | None:
        return self._clues.get((r, c))

    def is_clue(self, r: int, c: int) -> bool:
        return (r, c) in self._clues

    def set_clue(self, r: int, c: int, values: Sequence[int]) -> None:
        """Hücreye ipucu yerleştirir ve geometrik olarak mümkün olduğunu doğrular."""
        self._require_bounds(r, c)
        clue = normalize_clue(values)
        available = sum(1 for p in self.ring(r, c) if p is not None)
        if not clue_fits_geometry(clue, available):
            raise ClueError(
                f"({r}, {c}) hücresine {clue} ipucusu sığmaz: "
                f"bu konumda yalnızca {available} komşu var."
            )
        self._clues[(r, c)] = clue
        # İpucu hücreleri asla boyanmaz.
        self._cells[r][c] = Cell.EMPTY

    def remove_clue(self, r: int, c: int) -> None:
        self._require_bounds(r, c)
        if self._clues.pop((r, c), None) is not None:
            self._cells[r][c] = Cell.UNKNOWN

    # ------------------------------------------------------------------ #
    # Boyama katmanı
    # ------------------------------------------------------------------ #

    def get_cell(self, r: int, c: int) -> Cell:
        self._require_bounds(r, c)
        return self._cells[r][c]

    def set_cell(self, r: int, c: int, state: Cell) -> None:
        self._require_bounds(r, c)
        if self.is_clue(r, c):
            raise ValueError(f"({r}, {c}) bir ipucu hücresi; boyanamaz.")
        self._cells[r][c] = Cell(state)

    def toggle(self, r: int, c: int) -> Cell:
        """Arayüz için: bilinmiyor -> dolu -> boş -> bilinmiyor döngüsü."""
        order = {
            Cell.UNKNOWN: Cell.FILLED,
            Cell.FILLED: Cell.EMPTY,
            Cell.EMPTY: Cell.UNKNOWN,
        }
        new_state = order[self.get_cell(r, c)]
        self.set_cell(r, c, new_state)
        return new_state

    def clear_marks(self) -> None:
        """Tüm boyamayı siler; ipucular korunur."""
        for r, c in self.positions():
            if not self.is_clue(r, c):
                self._cells[r][c] = Cell.UNKNOWN

    def filled_cells(self) -> set[Position]:
        return {p for p in self.positions() if self._cells[p[0]][p[1]] is Cell.FILLED}

    def unknown_cells(self) -> set[Position]:
        return {p for p in self.positions() if self._cells[p[0]][p[1]] is Cell.UNKNOWN}

    def is_complete(self) -> bool:
        """Boyanmamış (kararsız) hücre kalmamışsa True."""
        return not self.unknown_cells()

    # ------------------------------------------------------------------ #
    # Kopyalama ve gösterim
    # ------------------------------------------------------------------ #

    def copy(self) -> "Board":
        clone = Board(self.rows, self.cols)
        clone._clues = dict(self._clues)
        clone._cells = [row[:] for row in self._cells]
        return clone

    def grid_snapshot(self) -> list[list[int]]:
        """Boyama katmanının düz int matrisi (AI modelleri ve API için)."""
        return [[int(s) for s in row] for row in self._cells]

    def apply_grid(self, grid: Sequence[Sequence[int]]) -> None:
        """Düz int matrisini boyama katmanına uygular."""
        if len(grid) != self.rows or any(len(row) != self.cols for row in grid):
            raise ValueError("Matris boyutu tahtayla uyuşmuyor.")
        for r, c in self.positions():
            if self.is_clue(r, c):
                continue
            self._cells[r][c] = Cell(grid[r][c])

    def to_text(self) -> str:
        """Terminalde hızlı gözle kontrol için okunabilir çıktı."""
        lines = []
        for r in range(self.rows):
            row = []
            for c in range(self.cols):
                clue = self.clue_at(r, c)
                if clue is not None:
                    row.append("".join(str(n) for n in clue).rjust(4))
                elif self._cells[r][c] is Cell.FILLED:
                    row.append("   #")
                elif self._cells[r][c] is Cell.EMPTY:
                    row.append("   .")
                else:
                    row.append("    ")
            lines.append("|" + "|".join(row) + "|")
        return "\n".join(lines)

    def __repr__(self) -> str:  # pragma: no cover - sadece hata ayıklama
        return f"<Board {self.rows}x{self.cols} ipucu={len(self._clues)}>"


def clue_fits_geometry(clue: Clue, available: int) -> bool:
    """İpucunun, komşu sayısı `available` olan bir hücreye sığıp sığmadığı.

    Kenar ve köşe hücrelerinde ızgara dışı komşular her zaman bitişik bir yay
    oluşturduğu için, kalan komşular doğrusal bir dizi gibi davranır:
    k blok arasına en az k-1 boşluk gerekir. İç hücrelerde (8 komşu) halka
    döngüsel olduğundan k blok için k boşluk gerekir; tek istisna tüm halkanın
    dolu olduğu (8,) durumudur.
    """
    if clue == (0,):
        return True
    total = sum(clue)
    k = len(clue)
    if available == 8:
        if k == 1 and total == 8:
            return True
        return total + k <= 8
    return total + (k - 1) <= available
