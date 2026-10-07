"""Domain layer: scores criteria profiles (O-1A, EB-1A, ...) over approved evidence.

``areao1.core`` never imports from here; tests enforce that split.
"""

from areao1.criteria.case import Case

__all__ = ["Case"]
