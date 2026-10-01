"""X01 checkout suggestions: the shortest way to finish, preferring standard routes."""

from __future__ import annotations

from functools import lru_cache

# (label, score, multiplier) for every distinct dart, in preference order for set-up darts.
_SETUP = [(f"T{n}", 3 * n, 3) for n in (20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)] + \
         [("25", 25, 1)] + [(f"S{n}", n, 1) for n in range(20, 0, -1)] + \
         [(f"D{n}", 2 * n, 2) for n in range(20, 0, -1)] + [("BULL", 50, 2)]
# Preferred finishing doubles (most players aim D20, D16, D8 ...).
_DOUBLE_PREF = [20, 16, 8, 18, 12, 10, 4, 2, 1, 19, 17, 15, 14, 13, 11, 9, 7, 6, 5, 3]


def _finishers(rule: str) -> list[tuple[str, int]]:
    doubles = [(f"D{n}", 2 * n) for n in _DOUBLE_PREF] + [("BULL", 50)]
    if rule == "double":
        return doubles
    if rule == "master":
        return doubles + [(f"T{n}", 3 * n) for n in range(20, 0, -1)]
    return [(lbl, s) for lbl, s, _ in _SETUP] + [("BULL", 50)]


@lru_cache(maxsize=4096)
def suggest_checkout(remaining: int, darts_left: int = 3, rule: str = "double") -> list[str] | None:
    """Shortest checkout route for ``remaining`` with at most ``darts_left`` darts, or None."""
    if remaining <= 0 or darts_left <= 0 or remaining > 180:
        return None
    fin = _finishers(rule)
    for lbl, s in fin:
        if s == remaining:
            return [lbl]
    if darts_left >= 2:
        for lbl1, s1, _ in _SETUP:
            rest = remaining - s1
            if rest <= 0:
                continue
            for lbl2, s2 in fin:
                if s2 == rest:
                    return [lbl1, lbl2]
    if darts_left >= 3:
        for lbl1, s1, _ in _SETUP:
            for lbl2, s2, _ in _SETUP:
                rest = remaining - s1 - s2
                if rest <= 0:
                    continue
                for lbl3, s3 in fin:
                    if s3 == rest:
                        return [lbl1, lbl2, lbl3]
    return None
