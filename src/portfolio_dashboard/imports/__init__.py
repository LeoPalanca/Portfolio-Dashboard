"""Statement format detection and raw import placement."""

from .detection import (
    ALLOWED_EXTENSIONS,
    SOURCE_EXTENSIONS,
    SOURCE_LABELS,
    detect_statement_source,
    import_destination,
    source_format_label,
)
from .fineco import fineco_statement_kind, has_fineco_bank_headers, read_fineco_bank_movements

__all__ = [
    "ALLOWED_EXTENSIONS",
    "SOURCE_EXTENSIONS",
    "SOURCE_LABELS",
    "detect_statement_source",
    "fineco_statement_kind",
    "has_fineco_bank_headers",
    "import_destination",
    "read_fineco_bank_movements",
    "source_format_label",
]
