"""XML exporter — produces well-formed UTF-8 XML files."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List

from app.exporters.base import BaseExporter

logger = logging.getLogger(__name__)


def _add_dict_element(parent: ET.Element, tag: str, data: Dict[str, Any]) -> None:
    """Add a child element with sub-elements for every key/value pair."""
    item_el = ET.SubElement(parent, tag)
    for key, value in data.items():
        child = ET.SubElement(item_el, _safe_tag(key))
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    _add_dict_element(child, "item", entry)
                else:
                    sub = ET.SubElement(child, "item")
                    sub.text = _to_str(entry)
        elif isinstance(value, dict):
            _add_dict_element(child, "item", value)
        else:
            child.text = _to_str(value)


def _safe_tag(name: str) -> str:
    """Sanitise a string so it is a valid XML tag name."""
    tag = name.replace(" ", "_").replace("(", "").replace(")", "")
    # XML tags must start with a letter or underscore
    if tag and not (tag[0].isalpha() or tag[0] == "_"):
        tag = f"_{tag}"
    return tag or "_field"


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_xml(root: ET.Element, path: str) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


class XMLExporter(BaseExporter):
    """Export each data type as an XML file."""

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def export_products(
        self, products: List[Dict[str, Any]], variants: List[Dict[str, Any]]
    ) -> str:
        variants_by_product: Dict[int, List[Dict[str, Any]]] = {}
        for v in variants:
            pid = v.get("product_id")
            if pid is not None:
                variants_by_product.setdefault(pid, []).append(v)

        root = ET.Element("products")
        for product in products:
            p = dict(product)
            pid = p.get("id")
            p["variants"] = variants_by_product.get(pid, [])
            raw_images = p.pop("image_urls", None) or []
            p["images"] = [
                {"src": url, "position": idx + 1}
                for idx, url in enumerate(raw_images)
            ]
            _add_dict_element(root, "product", p)

        path = self._filepath("products", "xml")
        _write_xml(root, path)
        logger.info("Exported products XML to %s", path)
        return path

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    async def _export_items(
        self, items: List[Dict[str, Any]], root_tag: str, item_tag: str, suffix: str
    ) -> str:
        root = ET.Element(root_tag)
        for item in items:
            _add_dict_element(root, item_tag, item)
        path = self._filepath(suffix, "xml")
        _write_xml(root, path)
        logger.info("Exported %s XML to %s", suffix, path)
        return path

    # ------------------------------------------------------------------
    # Other data types
    # ------------------------------------------------------------------

    async def export_collections(self, collections: List[Dict[str, Any]]) -> str:
        return await self._export_items(
            collections, "collections", "collection", "collections"
        )

    async def export_pages(self, pages: List[Dict[str, Any]]) -> str:
        return await self._export_items(pages, "pages", "page", "pages")

    async def export_blogs(self, blogs: List[Dict[str, Any]]) -> str:
        return await self._export_items(blogs, "blog_posts", "post", "blogs")

    async def export_urls(self, urls: List[Dict[str, Any]]) -> str:
        return await self._export_items(urls, "urls", "url_record", "urls")

    async def export_redirects(self, redirects: List[Dict[str, Any]]) -> str:
        return await self._export_items(
            redirects, "redirects", "redirect", "redirects"
        )
