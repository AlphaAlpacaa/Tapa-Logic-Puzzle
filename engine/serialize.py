"""Bulmacaların saklanması ve paylaşılması.

İki biçim desteklenir:

JSON (kanonik)
    Kalıcı saklama formatı. Meta veri (başlık, yazar, zorluk) ve isteğe bağlı
    çözüm taşır. Bulmaca kütüphanesi bu dosyalardan oluşur.

Kısa kod (tek satır)
    Hızlı giriş, paylaşım ve toplu test için. Biçim:

        10x10/..3.../.(12)../...

    `.`        ipucusuz hücre
    `3`        tek sayılı ipucu
    `(1 2)`    çok sayılı ipucu — parantez, sayılar araya boşluk konmadan da
               yazılabilir: `(12)`
    `/`        satır ayracı
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .board import Board, Cell, Clue, Position, normalize_clue

FORMAT_NAME = "tapa-puzzle"
FORMAT_VERSION = 1


# ---------------------------------------------------------------------- #
# JSON
# ---------------------------------------------------------------------- #

def to_dict(board: Board, *, meta: Mapping[str, Any] | None = None,
            include_solution: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "rows": board.rows,
        "cols": board.cols,
        "clues": [
            {"r": r, "c": c, "values": list(clue)}
            for (r, c), clue in sorted(board.clues.items())
        ],
        "meta": dict(meta or {}),
    }
    if include_solution:
        data["solution"] = board.grid_snapshot()
    return data


def from_dict(data: Mapping[str, Any]) -> Board:
    if data.get("format") not in (None, FORMAT_NAME):
        raise ValueError(f"Bilinmeyen format: {data.get('format')!r}")
    board = Board(int(data["rows"]), int(data["cols"]))
    for entry in data.get("clues", []):
        board.set_clue(int(entry["r"]), int(entry["c"]), entry["values"])
    if data.get("solution"):
        board.apply_grid(data["solution"])
    return board


def save_json(board: Board, path: str | Path, *, meta: Mapping[str, Any] | None = None,
              include_solution: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = to_dict(board, meta=meta, include_solution=include_solution)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_json(path: str | Path) -> Board:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------- #
# Kısa kod
# ---------------------------------------------------------------------- #

_CODE_HEADER = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*/(.*)$", re.DOTALL)


def to_code(board: Board) -> str:
    rows_out = []
    for r in range(board.rows):
        cells = []
        for c in range(board.cols):
            clue = board.clue_at(r, c)
            if clue is None:
                cells.append(".")
            elif len(clue) == 1:
                cells.append(str(clue[0]))
            else:
                cells.append("(" + "".join(str(n) for n in clue) + ")")
        rows_out.append("".join(cells))
    return f"{board.rows}x{board.cols}/" + "/".join(rows_out)


def from_code(code: str) -> Board:
    match = _CODE_HEADER.match(code.strip())
    if not match:
        raise ValueError("Kısa kod 'satırxsütun/...' biçiminde olmalıdır.")
    rows, cols = int(match.group(1)), int(match.group(2))
    body = match.group(3).replace("\n", "").replace(" ", "")
    lines = body.split("/")
    if len(lines) != rows:
        raise ValueError(f"{rows} satır bekleniyordu, {len(lines)} bulundu.")

    board = Board(rows, cols)
    for r, line in enumerate(lines):
        c = 0
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == ".":
                i += 1
            elif ch.isdigit():
                board.set_clue(r, c, [int(ch)])
                i += 1
            elif ch == "(":
                end = line.find(")", i)
                if end == -1:
                    raise ValueError(f"{r}. satırda kapanmamış parantez.")
                inner = line[i + 1:end]
                if not inner.isdigit():
                    raise ValueError(f"{r}. satırda geçersiz ipucu: ({inner})")
                board.set_clue(r, c, [int(ch) for ch in inner])
                i = end + 1
            else:
                raise ValueError(f"{r}. satırda beklenmeyen karakter: {ch!r}")
            c += 1
            if c > cols:
                raise ValueError(f"{r}. satır {cols} sütundan uzun.")
        if c != cols:
            raise ValueError(f"{r}. satırda {cols} hücre bekleniyordu, {c} bulundu.")
    return board


# ---------------------------------------------------------------------- #
# Çözüm katmanı (üretici ve AI eğitimi için)
# ---------------------------------------------------------------------- #

def solution_to_rows(board: Board) -> list[str]:
    """Boyamayı '#' ve '.' karakterlerinden oluşan satırlara çevirir."""
    return [
        "".join("#" if board.get_cell(r, c) is Cell.FILLED else "." for c in range(board.cols))
        for r in range(board.rows)
    ]


def apply_solution_rows(board: Board, rows: list[str]) -> None:
    if len(rows) != board.rows or any(len(row) != board.cols for row in rows):
        raise ValueError("Çözüm boyutu tahtayla uyuşmuyor.")
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            if board.is_clue(r, c):
                continue
            board.set_cell(r, c, Cell.FILLED if ch == "#" else Cell.EMPTY)
