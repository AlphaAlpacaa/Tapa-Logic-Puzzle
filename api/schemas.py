"""API istek/yanıt şemaları."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ClueModel(BaseModel):
    r: int
    c: int
    values: list[int]


class PuzzleSummary(BaseModel):
    id: str
    rows: int
    cols: int
    clueCount: int
    meta: dict[str, Any] = Field(default_factory=dict)


class PuzzleResponse(BaseModel):
    id: str | None = None
    rows: int
    cols: int
    clues: list[ClueModel]
    code: str
    meta: dict[str, Any] = Field(default_factory=dict)


class CodeRequest(BaseModel):
    code: str = Field(..., examples=["6x6/....../.3..(11)./....../....../..0.../......"])


class BlankRequest(BaseModel):
    rows: int = Field(..., ge=1, le=40)
    cols: int = Field(..., ge=1, le=40)


class ValidateRequest(BaseModel):
    rows: int
    cols: int
    clues: list[ClueModel]
    grid: list[list[int]] = Field(..., description="0 bilinmiyor, 1 dolu, 2 boş")
    mode: Literal["partial", "solution"] = "partial"


class IssueModel(BaseModel):
    code: str
    message: str
    cells: list[list[int]]


class ValidateResponse(BaseModel):
    ok: bool
    mode: str
    solved: bool
    issues: list[IssueModel]


class HintResponse(BaseModel):
    found: bool
    reason: str
    cell: list[int] | None = None
    state: int | None = None
    technique: str | None = None


class PuzzleRequest(BaseModel):
    """Yalnızca bulmaca; oyuncunun boyaması gerekmeyen işler için."""

    rows: int
    cols: int
    clues: list[ClueModel]


class SolveStatsModel(BaseModel):
    nodes: int
    guesses: int
    deductions: int
    elapsed: float


class SolveResponse(BaseModel):
    solved: bool
    unique: bool
    count: int
    grid: list[list[int]] | None = None
    stats: SolveStatsModel


class DifficultyResponse(BaseModel):
    label: str
    maxLevel: int
    logicOnly: bool
    guesses: int
    deductions: int
    techniques: dict[str, int]
    unique: bool
    elapsed: float


class EntryRequest(BaseModel):
    """Düzenleyiciden gelen bulmaca."""

    rows: int = Field(..., ge=3, le=40)
    cols: int = Field(..., ge=3, le=40)
    clues: list[ClueModel]


class SaveRequest(EntryRequest):
    number: str = ""
    source: str = ""


class SolutionEntryRequest(BaseModel):
    """Çözüm çiziminden giriş: '#' duvar, '.' boş, 'o' ipucu hücresi."""

    rows: int = Field(..., ge=3, le=40)
    cols: int = Field(..., ge=3, le=40)
    grid: list[str]


class SolutionSaveRequest(SolutionEntryRequest):
    number: str = ""
    source: str = ""


class VerifyResponse(BaseModel):
    ok: bool
    status: str
    message: str
    code: str = ""
    difficulty: dict[str, Any] | None = None
    solution: list[str] | None = None
    clues: list[ClueModel] | None = None
    saved: bool | None = None
    total: int | None = None


class HumanEntry(BaseModel):
    id: str
    number: str
    rows: int
    cols: int
    label: str
