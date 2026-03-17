"""JSON exporter — produces pretty-printed JSON files."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.exporters.base import BaseExporter

logger = logging.getLogger(__name__)


def _json_serial(obj: Any) -> Any:
    """Fallback serialiser for objects that are not JSON-native."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class JSONExporter(BaseExporter):
    """Export each data type as a standalone pretty-printed JSON file."""

    async def _write(self, data: Any, suffix: str) -> str:
        path = self._filepath(suffix, "json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=_json_serial)
        logger.info("Exported %s to %s", suffix, path)
        return path

    # ------------------------------------------------------------------
    # Products — nest variants and images inside each product
    # ------------------------------------------------------------------

    async def export_products(
        self, products: List[Dict[str, Any]], variants: List[Dict[str, Any]]
    ) -> str:
        variants_by_product: Dict[int, List[Dict[str, Any]]] = {}
        for v in variants:
            pid = v.get("product_id")
            if pid is not None:
                variants_by_product.setdefault(pid, []).append(v)

        nested: list[dict[str, Any]] = []
        for product in products:
            p = dict(product)
            pid = p.get("id")
            p["variants"] = variants_by_product.get(pid, [])

            # Normalise image_urls into an images array with src + position
            raw_images = p.pop("image_urls", None) or []
            p["images"] = [
                {"src": url, "position": idx + 1}
                for idx, url in enumerate(raw_images)
            ]
            nested.append(p)

        return await self._write(nested, "products")

    # ------------------------------------------------------------------
    # Other data types — straight pass-through
    # ------------------------------------------------------------------

    async def export_collections(self, collections: List[Dict[str, Any]]) -> str:
        return await self._write(collections, "collections")

    async def export_pages(self, pages: List[Dict[str, Any]]) -> str:
        return await self._write(pages, "pages")

    async def export_blogs(self, blogs: List[Dict[str, Any]]) -> str:
        return await self._write(blogs, "blogs")

    async def export_urls(self, urls: List[Dict[str, Any]]) -> str:
        return await self._write(urls, "urls")

    async def export_redirects(self, redirects: List[Dict[str, Any]]) -> str:
        return await self._write(redirects, "redirects")
