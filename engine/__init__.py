"""Tapa kural motoru — arayüzden ve yapay zeka katmanından tamamen bağımsız."""

from .board import (
    Board,
    Cell,
    Clue,
    ClueError,
    Position,
    RING_OFFSETS,
    normalize_clue,
)
from .rules import (
    clue_candidates,
    clue_is_possible,
    clue_satisfied,
    forced_cells,
    ring_states,
    runs_pattern,
    square_violations,
    wall_can_still_connect,
    wall_components,
    wall_is_connected,
)
from .serialize import (
    apply_solution_rows,
    from_code,
    from_dict,
    load_json,
    save_json,
    solution_to_rows,
    to_code,
    to_dict,
)
from .solver import (
    Difficulty,
    SolveResult,
    SolveStats,
    Step,
    TECHNIQUES,
    Technique,
    count_solutions,
    is_unique,
    next_step,
    propagate,
    rate,
    solve,
    solve_logically,
)
from .validator import (
    IssueCode,
    ValidationIssue,
    ValidationResult,
    is_solved,
    validate_partial,
    validate_solution,
)

__all__ = [
    "Board", "Cell", "Clue", "ClueError", "Position", "RING_OFFSETS", "normalize_clue",
    "ring_states", "runs_pattern", "clue_satisfied", "clue_candidates",
    "clue_is_possible", "forced_cells", "square_violations",
    "wall_components", "wall_is_connected", "wall_can_still_connect",
    "IssueCode", "ValidationIssue", "ValidationResult",
    "validate_solution", "validate_partial", "is_solved",
    "to_dict", "from_dict", "save_json", "load_json", "to_code", "from_code",
    "solution_to_rows", "apply_solution_rows",
    "solve", "solve_logically", "count_solutions", "is_unique", "rate", "next_step",
    "propagate", "Technique", "TECHNIQUES", "SolveResult", "SolveStats", "Step", "Difficulty",
]
