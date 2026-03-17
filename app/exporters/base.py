"""Abstract base class for all data exporters."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseExporter(ABC):
    """Base exporter that every format-specific exporter inherits from."""

    def __init__(self, export_dir: str, project_name: str) -> None:
        self.export_dir = export_dir
        self.project_name = project_name
        os.makedirs(self.export_dir, exist_ok=True)

    def _filepath(self, suffix: str, ext: str) -> str:
        """Build a deterministic output file path."""
        safe_name = self.project_name.replace(" ", "_").lower()
        return os.path.join(self.export_dir, f"{safe_name}_{suffix}.{ext}")

    # ------------------------------------------------------------------
    # Abstract export methods
    # ------------------------------------------------------------------

    @abstractmethod
    async def export_products(
        self, products: List[Dict[str, Any]], variants: List[Dict[str, Any]]
    ) -> str:
        """Export products + variants and return the file path."""
        ...

    @abstractmethod
    async def export_collections(self, collections: List[Dict[str, Any]]) -> str:
        """Export collections and return the file path."""
        ...

    @abstractmethod
    async def export_pages(self, pages: List[Dict[str, Any]]) -> str:
        """Export pages and return the file path."""
        ...

    @abstractmethod
    async def export_blogs(self, blogs: List[Dict[str, Any]]) -> str:
        """Export blog posts and return the file path."""
        ...

    @abstractmethod
    async def export_urls(self, urls: List[Dict[str, Any]]) -> str:
        """Export URL records and return the file path."""
        ...

    @abstractmethod
    async def export_redirects(self, redirects: List[Dict[str, Any]]) -> str:
        """Export redirect mappings and return the file path."""
        ...

    # ------------------------------------------------------------------
    # Convenience batch export
    # ------------------------------------------------------------------

    async def export_all(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Export every data type present in *data* and return a mapping of
        data-type -> output file path.

        Expected keys in *data*: ``products``, ``variants``, ``collections``,
        ``pages``, ``blogs``, ``urls``, ``redirects``.  Missing keys are
        silently skipped.
        """
        results: Dict[str, str] = {}

        if data.get("products") is not None:
            results["products"] = await self.export_products(
                data["products"], data.get("variants", [])
            )

        if data.get("collections") is not None:
            results["collections"] = await self.export_collections(data["collections"])

        if data.get("pages") is not None:
            results["pages"] = await self.export_pages(data["pages"])

        if data.get("blogs") is not None:
            results["blogs"] = await self.export_blogs(data["blogs"])

        if data.get("urls") is not None:
            results["urls"] = await self.export_urls(data["urls"])

        if data.get("redirects") is not None:
            results["redirects"] = await self.export_redirects(data["redirects"])

        return results
