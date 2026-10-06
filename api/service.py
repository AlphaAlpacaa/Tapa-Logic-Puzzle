"""API'nin iş mantığı — FastAPI'ye hiç bağımlı değil.

Bu ayrım kasıtlı: aynı fonksiyonlar hem web sunucusundan hem de ileride
eğitim döngüsünden çağrılabilsin, ayrıca web çatısı kurulu olmadan test
edilebilsin diye.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from engine.board import ClueError
from engine import (
    Board,
    Cell,
    apply_solution_rows,
    from_code,
    from_dict,
    generator,
    rules,
    solution_to_rows,
    solver,
    to_code,
    validate_partial,
    validate_solution,
)

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


# ---------------------------------------------------------------------- #
# İnsan tasarımı bulmaca kütüphanesi
# ---------------------------------------------------------------------- #

HUMAN_PATH = Path(__file__).resolve().parents[1] / "dataset" / "human" / "puzzles.jsonl"


def _load_human() -> list[dict[str, Any]]:
    if not HUMAN_PATH.is_file():
        return []
    return [
        json.loads(line)
        for line in HUMAN_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def verify_entry(rows: int, cols: int, clues: Iterable[dict[str, Any]],
                 time_limit: float = 20.0) -> dict[str, Any]:
    """Girilen bulmacanın kaydedilmeye uygun olup olmadığını söyler.

    Kabul ölçütü tek çözümlülük. Elle girilen bir bulmacada tek bir rakam
    hatası neredeyse her zaman bulmacayı çözümsüz ya da çok çözümlü yapar;
    bu yüzden kayıt öncesi denetim, yazım hatalarının büyük çoğunluğunu
    yakalar.
    """
    clue_list = list(clues)
    if not clue_list:
        return {"ok": False, "status": "bos", "message": "Henüz ipucu girilmedi.", "code": ""}

    board = board_from_payload(rows, cols, clue_list)
    code = to_code(board)
    result = solver.solve(board, limit=2, time_limit=time_limit)

    if result.stats.timed_out:
        return {"ok": False, "status": "zaman", "code": code,
                "message": "Çözüm süresi aşıldı; bulmaca çok büyük ya da fazla serbest."}
    if result.count == 0:
        return {"ok": False, "status": "cozumsuz", "code": code,
                "message": "Çözümsüz. İpuçlarından biri yanlış girilmiş olmalı."}
    if result.count > 1:
        return {"ok": False, "status": "coklu", "code": code,
                "message": "Birden çok çözüm var. Bir ipucu eksik ya da yanlış."}

    rating = solver.rate(board)
    return {
        "ok": True,
        "status": "tek",
        "code": code,
        "message": f"Tek çözümlü. Zorluk: {rating.label}.",
        "difficulty": rating.as_dict(),
        "solution": solution_to_rows(result.solutions[0]),
    }


def save_human(rows: int, cols: int, clues: Iterable[dict[str, Any]],
               number: str, source: str) -> dict[str, Any]:
    """Doğrulanan bulmacayı insan veri kümesine ekler."""
    clue_list = list(clues)
    check = verify_entry(rows, cols, clue_list)
    if not check["ok"]:
        return {**check, "saved": False, "total": len(_load_human())}

    records = _load_human()
    if any(record["code"] == check["code"] for record in records):
        return {**check, "saved": False, "total": len(records),
                "message": "Bu bulmaca zaten kayıtlı."}

    board = board_from_payload(rows, cols, clue_list)
    solved = board.copy()
    apply_solution_rows(solved, check["solution"])

    record = {
        "id": f"human-{number or len(records)}",
        "source": source or "elle girilen",
        "sourceNumber": number,
        "rows": rows,
        "cols": cols,
        "code": check["code"],
        "clues": [
            {"r": r, "c": c, "values": list(values)}
            for (r, c), values in sorted(board.clues.items())
        ],
        "solution": check["solution"],
        "difficulty": check["difficulty"],
        "features": generator._features(board, solved.filled_cells()),
    }

    HUMAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HUMAN_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {**check, "saved": True, "total": len(records) + 1,
            "message": f"Kaydedildi. Toplam {len(records) + 1} bulmaca."}


# ---------------------------------------------------------------------- #
# Çözümden giriş: duvar çizilir, ipucu değerleri hesaplanır
# ---------------------------------------------------------------------- #

WALL_CHAR, BLANK_CHAR, CLUE_CHAR = "#", ".", "o"


def _board_from_solution(rows: int, cols: int, grid: Sequence[str]) -> tuple[Board, Board]:
    """Duvar çiziminden bulmacayı ve referans çözümü kurar.

    İpucu değerleri duvardan hesaplanır; kullanıcının rakam girmesine gerek
    yoktur. Okunması gereken tek şey hangi hücrenin duvar olduğu ve hangi
    beyaz hücrelerin üstünde sayı bulunduğu.
    """
    if len(grid) != rows or any(len(row) != cols for row in grid):
        raise ValueError("Izgara boyutu satır/sütun sayısıyla uyuşmuyor.")

    wall = {(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == WALL_CHAR}
    clue_cells = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == CLUE_CHAR]
    if not clue_cells:
        raise ValueError("Hiç ipucu hücresi işaretlenmedi.")

    solved = Board(rows, cols)
    for pos in wall:
        solved.set_cell(*pos, Cell.FILLED)

    clues = {pos: rules.runs_pattern(rules.ring_states(solved, *pos)) for pos in clue_cells}
    puzzle = Board(rows, cols, clues)

    reference = Board(rows, cols, clues)
    for pos in wall:
        reference.set_cell(*pos, Cell.FILLED)
    return puzzle, reference


def verify_solution_entry(rows: int, cols: int, grid: Sequence[str],
                          time_limit: float = 20.0) -> dict[str, Any]:
    """Çizilen duvarı denetler ve ondan türetilen bulmacayı doğrular.

    Üç ayrı kontrol: duvar Tapa kurallarına uyuyor mu, türetilen bulmaca tek
    çözümlü mü, ve bulunan çözüm çizilen duvarla aynı mı. Hangisinin düştüğü,
    hatanın nerede olduğunu söyler.
    """
    try:
        puzzle, reference = _board_from_solution(rows, cols, grid)
    except (ValueError, ClueError) as exc:
        return {"ok": False, "status": "izgara", "message": str(exc), "code": ""}

    wall_check = validate_solution(reference)
    if not wall_check.ok:
        return {
            "ok": False,
            "status": "duvar",
            "code": to_code(puzzle),
            "message": f"Çizilen duvar kurallara uymuyor: {wall_check.issues[0].message}",
        }

    expected = solution_to_rows(reference)
    result = solver.solve(puzzle, limit=2, time_limit=time_limit)
    payload = {
        "code": to_code(puzzle),
        "clues": [
            {"r": r, "c": c, "values": list(values)}
            for (r, c), values in sorted(puzzle.clues.items())
        ],
    }

    if result.stats.timed_out:
        return {**payload, "ok": False, "status": "zaman",
                "message": "Çözüm süresi aşıldı."}
    if result.count == 0:
        return {**payload, "ok": False, "status": "cozumsuz",
                "message": "Türetilen bulmaca çözümsüz çıktı."}
    if result.count > 1:
        return {**payload, "ok": False, "status": "coklu",
                "message": "Birden çok çözüm var. Daha fazla ipucu hücresi işaretlenmeli."}
    if solution_to_rows(result.solutions[0]) != expected:
        return {**payload, "ok": False, "status": "farkli",
                "message": "Bulunan çözüm çizilen duvarla uyuşmuyor; duvarda okuma hatası var."}

    rating = solver.rate(puzzle)
    return {
        **payload,
        "ok": True,
        "status": "tek",
        "message": f"Tek çözümlü. Zorluk: {rating.label}.",
        "difficulty": rating.as_dict(),
        "solution": expected,
    }


def save_solution_entry(rows: int, cols: int, grid: Sequence[str],
                        number: str, source: str) -> dict[str, Any]:
    check = verify_solution_entry(rows, cols, grid)
    if not check["ok"]:
        return {**check, "saved": False, "total": len(_load_human())}
    saved = save_human(rows, cols, check["clues"], number, source)
    # Türetilen sayılar yanıtta kalsın: kullanıcı kitaptakiyle karşılaştırabilsin.
    return {**saved, "clues": check["clues"]}


def list_human() -> list[dict[str, Any]]:
    return [
        {
            "id": record["id"],
            "number": record.get("sourceNumber", ""),
            "rows": record["rows"],
            "cols": record["cols"],
            "label": record["difficulty"]["label"],
        }
        for record in _load_human()
    ]
