"""Solver and screenshot-driven automation for Offline Games Meowdoku."""

from .model import MeowdokuPuzzle, MeowdokuSolution
from .solver import (
    MultipleSolutionsError,
    NoSolutionError,
    classify_cell,
    solve_unique,
)

__all__ = [
    "MeowdokuPuzzle",
    "MeowdokuSolution",
    "MultipleSolutionsError",
    "NoSolutionError",
    "classify_cell",
    "solve_unique",
]
