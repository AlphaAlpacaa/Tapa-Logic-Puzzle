"""API'nin iş mantığı — FastAPI'ye hiç bağımlı değil.

Bu ayrım kasıtlı: aynı fonksiyonlar hem web sunucusundan hem de ileride
eğitim döngüsünden çağrılabilsin, ayrıca web çatısı kurulu olmadan test
edilebilsin diye.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from engine import Board, Cell, from_code, from_dict, rules, solver, to_code, validate_partial, validate_solution

PUZZLE_DIR = Path(__file__).resolve().parents[1] / "puzzles"


# ---------------------------------------------------------------------- #
# Tahta <-> sözlük dönüşümü
# ---------------------------------------------------------------------- #

def board_to_payload(board: Board, *, puzzle_id: str | None = None,
                     meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": puzzle_id,
        "rows": board.rows,
        "cols": board.cols,
        "clues": [
            {"r": r, "c": c, "values": list(clue)}
            for (r, c), clue in sorted(board.clues.items())
        ],
        "code": to_code(board),
        "meta": meta or {},
    }


def board_from_payload(rows: int, cols: int, clues: Iterable[dict[str, Any]],
                       grid: Sequence[Sequence[int]] | None = None) -> Board:
    board = Board(rows, cols)
    for clue in clues:
        board.set_clue(int(clue["r"]), int(clue["c"]), clue["values"])
    if grid is not None:
        board.apply_grid(grid)
    return board


# ---------------------------------------------------------------------- #
# Bulmaca kütüphanesi
# ---------------------------------------------------------------------- #

def list_puzzles() -> list[dict[str, Any]]:
    """puzzles/ klasöründeki tüm .json bulmacaları başlıklarıyla listeler."""
    out = []
    for path in sorted(PUZZLE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append({
                "id": path.stem,
                "rows": data["rows"],
                "cols": data["cols"],
                "clueCount": len(data.get("clues", [])),
                "meta": data.get("meta", {}),
            })
        except (json.JSONDecodeError, KeyError):
            continue  # bozuk dosya kütüphaneyi düşürmesin
    return out


def load_puzzle(puzzle_id: str) -> dict[str, Any]:
    path = (PUZZLE_DIR / f"{puzzle_id}.json").resolve()
    if PUZZLE_DIR.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(f"Bulmaca bulunamadı: {puzzle_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    board = from_dict(data)
    board.clear_marks()  # çözüm dosyada olsa bile oyuncuya boş tahta verilir
    return board_to_payload(board, puzzle_id=puzzle_id, meta=data.get("meta", {}))


def puzzle_from_code(code: str) -> dict[str, Any]:
    return board_to_payload(from_code(code))


def blank_puzzle(rows: int, cols: int) -> dict[str, Any]:
    return board_to_payload(Board(rows, cols))


# ---------------------------------------------------------------------- #
# Doğrulama
# ---------------------------------------------------------------------- #

def validate(rows: int, cols: int, clues: Iterable[dict[str, Any]],
             grid: Sequence[Sequence[int]], mode: str = "partial") -> dict[str, Any]:
    """mode='partial' anlık geri bildirim, mode='solution' bitiş kontrolü."""
    board = board_from_payload(rows, cols, clues, grid)
    result = validate_partial(board) if mode == "partial" else validate_solution(board)
    return {
        "ok": result.ok,
        "mode": mode,
        "solved": validate_solution(board).ok,
        "issues": [
            {
                "code": issue.code.value,
                "message": issue.message,
                "cells": [[r, c] for (r, c) in issue.cells],
            }
            for issue in result.issues
        ],
    }


# ---------------------------------------------------------------------- #
# İpucu (tek adımlık mantıksal çıkarım)
# ---------------------------------------------------------------------- #

def hint(rows: int, cols: int, clues: Iterable[dict[str, Any]],
         grid: Sequence[Sequence[int]]) -> dict[str, Any]:
    """Kesin olarak çıkarılabilen tek bir hücreyi, gerekçesiyle verir.

    Çözücünün teknik zincirini kullanır ve her zaman en ucuz tekniği tercih
    eder — oyuncuya gösterilen gerekçe böylece mümkün olan en basit olanı olur.
    """
    board = board_from_payload(rows, cols, clues, grid)

    if solver.contradicted(board):
        issues = validate_partial(board).issues
        detail = issues[0].message if issues else "Tahtada bir çelişki var."
        return {"found": False, "reason": f"{detail} Önce onu düzeltmek gerekiyor."}

    step = solver.next_step(board)
    if step is None:
        if board.is_complete():
            return {"found": False, "reason": "Tahtada karar verilmemiş hücre kalmadı."}
        return {
            "found": False,
            "reason": "Elimizdeki tekniklerle çıkarılabilecek hücre kalmadı; buradan sonrası varsayım gerektiriyor.",
        }

    verb = "dolu" if step.state is Cell.FILLED else "boş"
    return {
        "found": True,
        "cell": [step.cell[0], step.cell[1]],
        "state": int(step.state),
        "technique": step.technique.name,
        "reason": f"{step.technique.description} Bu hücre {verb} olmak zorunda.",
    }


# ---------------------------------------------------------------------- #
# Çözme ve zorluk
# ---------------------------------------------------------------------- #

def solve(rows: int, cols: int, clues: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Bulmacayı sıfırdan çözer; oyuncunun mevcut işaretlerini dikkate almaz.

    Böylece oyuncu hatalı bir yoldaysa bile doğru çözüm gösterilebilir.
    """
    board = board_from_payload(rows, cols, clues)
    result = solver.solve(board, limit=2)
    return {
        "solved": result.solvable,
        "unique": result.unique,
        "count": result.count,
        "grid": result.solutions[0].grid_snapshot() if result.solutions else None,
        "stats": {
            "nodes": result.stats.nodes,
            "guesses": result.stats.guesses,
            "deductions": result.stats.deductions,
            "elapsed": round(result.stats.elapsed, 4),
        },
    }


def difficulty(rows: int, cols: int, clues: Iterable[dict[str, Any]]) -> dict[str, Any]:
    board = board_from_payload(rows, cols, clues)
    return solver.rate(board).as_dict()
