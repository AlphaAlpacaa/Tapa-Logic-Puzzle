"""FastAPI sunucusu.

Çalıştırma:  uvicorn api.main:app --reload
Dokümantasyon: http://127.0.0.1:8000/docs

Sunucu durumsuzdur: oyun durumu istemcide tutulur, her istekte tahtanın
tamamı gönderilir. Böylece aynı uç noktalar, oturum yönetimi olmadan toplu
değerlendirme ve model eğitimi için de kullanılabilir.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine.board import ClueError

from . import service
from .schemas import (
    BlankRequest,
    CodeRequest,
    DifficultyResponse,
    HintResponse,
    PuzzleRequest,
    PuzzleResponse,
    PuzzleSummary,
    SolveResponse,
    ValidateRequest,
    ValidateResponse,
)

app = FastAPI(
    title="Tapa",
    description="Tapa bulmacası için kural motoru servisi.",
    version="0.1.0",
)

# Geliştirme sırasında React, Vite'ın kendi sunucusunda (5173) çalışır.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/puzzles", response_model=list[PuzzleSummary])
def get_puzzles() -> list[dict]:
    """Kütüphanedeki bulmacaları listeler."""
    return service.list_puzzles()


@app.get("/api/puzzles/{puzzle_id}", response_model=PuzzleResponse)
def get_puzzle(puzzle_id: str) -> dict:
    try:
        return service.load_puzzle(puzzle_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/puzzles/from-code", response_model=PuzzleResponse)
def post_code(request: CodeRequest) -> dict:
    """Tek satırlık kısa koddan bulmaca oluşturur."""
    try:
        return service.puzzle_from_code(request.code)
    except (ValueError, ClueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/puzzles/blank", response_model=PuzzleResponse)
def post_blank(request: BlankRequest) -> dict:
    """Kendi bulmacanı kurmak için boş ızgara."""
    try:
        return service.blank_puzzle(request.rows, request.cols)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/validate", response_model=ValidateResponse)
def post_validate(request: ValidateRequest) -> dict:
    try:
        return service.validate(
            request.rows,
            request.cols,
            [clue.model_dump() for clue in request.clues],
            request.grid,
            request.mode,
        )
    except (ValueError, ClueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/hint", response_model=HintResponse)
def post_hint(request: ValidateRequest) -> dict:
    try:
        return service.hint(
            request.rows,
            request.cols,
            [clue.model_dump() for clue in request.clues],
            request.grid,
        )
    except (ValueError, ClueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/solve", response_model=SolveResponse)
def post_solve(request: PuzzleRequest) -> dict:
    """Bulmacayı sıfırdan çözer ve çözümün tek olup olmadığını söyler."""
    try:
        return service.solve(request.rows, request.cols,
                             [clue.model_dump() for clue in request.clues])
    except (ValueError, ClueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/difficulty", response_model=DifficultyResponse)
def post_difficulty(request: PuzzleRequest) -> dict:
    """Çözmek için gereken en pahalı tekniğe göre zorluk ölçer."""
    try:
        return service.difficulty(request.rows, request.cols,
                                  [clue.model_dump() for clue in request.clues])
    except (ValueError, ClueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------- #
# Üretim: derlenmiş React çıktısını da aynı sunucu servis eder.
# `cd web && npm run build` çalıştırıldıysa devreye girer.
# ---------------------------------------------------------------------- #

_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        return FileResponse(_DIST / "index.html")
