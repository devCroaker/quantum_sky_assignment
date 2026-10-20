"""Input errors that name the file and the location, as R2 requires.

R2 asks for an error that names the file and the row. Only one of the two
inputs has rows, so ``InputError`` accepts either a CSV row number or an XML
line number and renders whichever it was given. A field name is included when
the problem is attributable to one column, because "row 4" alone sends a
reader hunting.

Errors are raised on the first problem rather than collected. A malformed
input is a reason to stop, not something to work around, and a single precise
message is easier to act on than a list in which later entries may be
consequences of the first.
"""

from __future__ import annotations

__all__ = ["InputError", "NetscopeError"]


class NetscopeError(Exception):
    """Base class for every error this package raises deliberately."""


class InputError(NetscopeError):
    """A rejected input, located precisely enough to go and fix it.

    Exactly one of ``row`` or ``line`` should be given. ``row`` is a
    one-based CSV data row, counted the way a spreadsheet counts it, so the
    header is row 1 and the first site is row 2. ``line`` is a one-based line
    in a text or XML file.
    """

    def __init__(
        self,
        file: str,
        message: str,
        *,
        row: int | None = None,
        line: int | None = None,
        field: str | None = None,
    ) -> None:
        if row is not None and line is not None:
            raise ValueError("give either row or line, not both")
        self.file = file
        self.message = message
        self.row = row
        self.line = line
        self.field = field
        super().__init__(str(self))

    def __str__(self) -> str:
        where = [self.file]
        if self.row is not None:
            where.append(f"row {self.row}")
        if self.line is not None:
            where.append(f"line {self.line}")
        if self.field is not None:
            where.append(f"column {self.field!r}")
        return f"{', '.join(where)}: {self.message}"
