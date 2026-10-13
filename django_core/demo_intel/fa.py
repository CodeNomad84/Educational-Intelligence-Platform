# DEMO SCOPE — whole file. Persian digit / decimal-separator helpers (no dependency).
import re

_TABLE = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")


def digits(value):
    """'27% 15.4' -> '۲۷% ۱۵٫۴' (digits and decimal point between digits only)."""
    if value is None:
        return "—"
    return _DECIMAL.sub("٫", str(value)).translate(_TABLE)
