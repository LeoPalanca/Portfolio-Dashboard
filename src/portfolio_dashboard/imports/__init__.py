"""Statement format detection and raw import placement."""

from .detection import (
    ALLOWED_EXTENSIONS,
    SOURCE_LABELS,
    detect_statement_source,
    import_destination,
)

__all__ = ["ALLOWED_EXTENSIONS", "SOURCE_LABELS", "detect_statement_source", "import_destination"]
