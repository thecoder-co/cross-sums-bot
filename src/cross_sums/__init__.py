"""Cross Sums solver and macOS automation."""

from .model import Puzzle, Solution
from .solver import MultipleSolutionsError, NoSolutionError, solve_unique

__all__ = [
    "MultipleSolutionsError",
    "NoSolutionError",
    "Puzzle",
    "Solution",
    "solve_unique",
]

