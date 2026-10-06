"""Domain layer: scores criteria profiles (O-1A, EB-1A, ...) over approved evidence.

``lighthouse_gc.core`` never imports from here; tests enforce that split.
"""

from lighthouse_gc.criteria.case import Case

__all__ = ["Case"]
