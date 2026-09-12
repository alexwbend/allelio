"""Validation shared by frequency display and ranking."""
import math


def valid_frequency(value) -> bool:
    """Accept finite numeric proportions, never booleans or coerced strings."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)
