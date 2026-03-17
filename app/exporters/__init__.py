"""Exporters for converting migration data to various file formats."""

from app.exporters.base import BaseExporter
from app.exporters.csv_exporter import CSVExporter
from app.exporters.json_exporter import JSONExporter
from app.exporters.xml_exporter import XMLExporter
from app.exporters.xlsx_exporter import XLSXExporter

__all__ = [
    "BaseExporter",
    "CSVExporter",
    "JSONExporter",
    "XMLExporter",
    "XLSXExporter",
    "get_exporter",
]

_EXPORTERS: dict[str, type[BaseExporter]] = {
    "csv": CSVExporter,
    "json": JSONExporter,
    "xml": XMLExporter,
    "xlsx": XLSXExporter,
}


def get_exporter(format: str, export_dir: str, project_name: str) -> BaseExporter:
    """Return an exporter instance for the given format.

    Args:
        format: One of ``csv``, ``json``, ``xml``, ``xlsx``.
        export_dir: Directory where exported files are written.
        project_name: Human-readable project name used in filenames.

    Raises:
        ValueError: If *format* is not recognised.
    """
    format_lower = format.lower().strip()
    cls = _EXPORTERS.get(format_lower)
    if cls is None:
        supported = ", ".join(sorted(_EXPORTERS))
        raise ValueError(
            f"Unsupported export format '{format}'. Supported: {supported}"
        )
    return cls(export_dir=export_dir, project_name=project_name)
