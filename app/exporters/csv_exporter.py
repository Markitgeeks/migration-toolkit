"""CSV exporter — produces Shopify-compatible CSV files."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from app.exporters.base import BaseExporter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shopify product import columns (exact order required)
# ---------------------------------------------------------------------------
SHOPIFY_PRODUCT_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Type",
    "Tags",
    "Published",
    "Option1 Name",
    "Option1 Value",
    "Option2 Name",
    "Option2 Value",
    "Option3 Name",
    "Option3 Value",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Requires Shipping",
    "Variant Taxable",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "SEO Title",
    "SEO Description",
    "Status",
]

COLLECTION_COLUMNS = [
    "Title",
    "Handle",
    "Body HTML",
    "Sort Order",
    "Product Handles",
    "SEO Title",
    "SEO Description",
]

PAGE_COLUMNS = [
    "Title",
    "Handle",
    "Body HTML",
    "Published",
    "SEO Title",
    "SEO Description",
]

BLOG_COLUMNS = [
    "Blog Title",
    "Title",
    "Handle",
    "Author",
    "Body HTML",
    "Tags",
    "Featured Image",
    "Published At",
    "SEO Title",
    "SEO Description",
]

URL_COLUMNS = [
    "URL",
    "Status Code",
    "Content Type",
    "Canonical URL",
    "Meta Title",
    "Meta Description",
    "Page Type",
]

REDIRECT_COLUMNS = [
    "Old URL",
    "New URL",
]


def _grams_from_weight(weight: Any, unit: str | None) -> int:
    """Convert a weight value + unit string to grams."""
    try:
        w = float(weight)
    except (TypeError, ValueError):
        return 0
    unit = (unit or "g").lower().strip()
    multipliers = {"g": 1, "kg": 1000, "oz": 28.3495, "lb": 453.592}
    return int(round(w * multipliers.get(unit, 1)))


class CSVExporter(BaseExporter):
    """Export data as CSV files compatible with Shopify's import tools."""

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def export_products(
        self, products: List[Dict[str, Any]], variants: List[Dict[str, Any]]
    ) -> str:
        # Index variants by product_id for fast lookup
        variants_by_product: Dict[int, List[Dict[str, Any]]] = {}
        for v in variants:
            pid = v.get("product_id")
            if pid is not None:
                variants_by_product.setdefault(pid, []).append(v)

        rows: list[dict[str, Any]] = []

        for product in products:
            pid = product.get("id")
            handle = product.get("handle", "")
            image_urls: list[str] = product.get("image_urls") or []
            prod_variants = variants_by_product.get(pid, [])

            # Build base product-level dict
            base: dict[str, Any] = {
                "Handle": handle,
                "Title": product.get("title", ""),
                "Body (HTML)": product.get("description_html", ""),
                "Vendor": product.get("vendor", ""),
                "Product Category": "",
                "Type": product.get("product_type", ""),
                "Tags": product.get("tags", ""),
                "Published": "TRUE",
                "SEO Title": product.get("seo_title", ""),
                "SEO Description": product.get("seo_description", ""),
                "Status": product.get("status", "active"),
            }

            if prod_variants:
                # First variant row carries all product-level data
                for idx, var in enumerate(prod_variants):
                    row = dict(base) if idx == 0 else {"Handle": handle}
                    row.update(self._variant_fields(var))

                    # Image on first variant row (primary image)
                    if idx == 0 and image_urls:
                        row["Image Src"] = image_urls[0]
                        row["Image Position"] = 1
                        row["Image Alt Text"] = product.get("title", "")

                    rows.append(row)

                # Extra rows for additional images (no variant data)
                for img_idx, img_url in enumerate(image_urls[1:], start=2):
                    rows.append(
                        {
                            "Handle": handle,
                            "Image Src": img_url,
                            "Image Position": img_idx,
                            "Image Alt Text": product.get("title", ""),
                        }
                    )
            else:
                # Product with no variants — create a default variant row
                base.update(
                    {
                        "Option1 Name": "Title",
                        "Option1 Value": "Default Title",
                        "Variant SKU": product.get("sku", ""),
                        "Variant Grams": 0,
                        "Variant Inventory Tracker": "shopify",
                        "Variant Inventory Qty": 0,
                        "Variant Inventory Policy": "deny",
                        "Variant Fulfillment Service": "manual",
                        "Variant Price": product.get("price", "0.00"),
                        "Variant Compare At Price": product.get(
                            "compare_at_price", ""
                        ),
                        "Variant Requires Shipping": "TRUE",
                        "Variant Taxable": "TRUE",
                        "Variant Barcode": product.get("barcode", ""),
                    }
                )
                if image_urls:
                    base["Image Src"] = image_urls[0]
                    base["Image Position"] = 1
                    base["Image Alt Text"] = product.get("title", "")
                rows.append(base)

                for img_idx, img_url in enumerate(image_urls[1:], start=2):
                    rows.append(
                        {
                            "Handle": handle,
                            "Image Src": img_url,
                            "Image Position": img_idx,
                            "Image Alt Text": product.get("title", ""),
                        }
                    )

        df = pd.DataFrame(rows, columns=SHOPIFY_PRODUCT_COLUMNS)
        df.fillna("", inplace=True)
        path = self._filepath("products", "csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("Exported %d product rows to %s", len(df), path)
        return path

    @staticmethod
    def _variant_fields(var: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "Option1 Name": var.get("option1_name", ""),
            "Option1 Value": var.get("option1_value", ""),
            "Option2 Name": var.get("option2_name", ""),
            "Option2 Value": var.get("option2_value", ""),
            "Option3 Name": var.get("option3_name", ""),
            "Option3 Value": var.get("option3_value", ""),
            "Variant SKU": var.get("sku", ""),
            "Variant Grams": _grams_from_weight(
                var.get("weight"), var.get("weight_unit")
            ),
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": var.get("inventory_qty", 0),
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Variant Price": var.get("price", "0.00"),
            "Variant Compare At Price": var.get("compare_at_price", ""),
            "Variant Requires Shipping": "TRUE",
            "Variant Taxable": "TRUE",
            "Variant Barcode": var.get("barcode", ""),
        }

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    async def export_collections(self, collections: List[Dict[str, Any]]) -> str:
        rows: list[dict[str, Any]] = []
        for col in collections:
            handles = col.get("product_handles") or []
            rows.append(
                {
                    "Title": col.get("title", ""),
                    "Handle": col.get("handle", ""),
                    "Body HTML": col.get("description_html", ""),
                    "Sort Order": col.get("sort_order", ""),
                    "Product Handles": ";".join(handles)
                    if isinstance(handles, list)
                    else str(handles),
                    "SEO Title": col.get("seo_title", ""),
                    "SEO Description": col.get("seo_description", ""),
                }
            )
        df = pd.DataFrame(rows, columns=COLLECTION_COLUMNS)
        df.fillna("", inplace=True)
        path = self._filepath("collections", "csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("Exported %d collections to %s", len(df), path)
        return path

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    async def export_pages(self, pages: List[Dict[str, Any]]) -> str:
        rows: list[dict[str, Any]] = []
        for page in pages:
            rows.append(
                {
                    "Title": page.get("title", ""),
                    "Handle": page.get("handle", ""),
                    "Body HTML": page.get("body_html", ""),
                    "Published": "TRUE" if page.get("published", True) else "FALSE",
                    "SEO Title": page.get("seo_title", ""),
                    "SEO Description": page.get("seo_description", ""),
                }
            )
        df = pd.DataFrame(rows, columns=PAGE_COLUMNS)
        df.fillna("", inplace=True)
        path = self._filepath("pages", "csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("Exported %d pages to %s", len(df), path)
        return path

    # ------------------------------------------------------------------
    # Blogs
    # ------------------------------------------------------------------

    async def export_blogs(self, blogs: List[Dict[str, Any]]) -> str:
        rows: list[dict[str, Any]] = []
        for blog in blogs:
            rows.append(
                {
                    "Blog Title": blog.get("blog_title", ""),
                    "Title": blog.get("title", ""),
                    "Handle": blog.get("handle", ""),
                    "Author": blog.get("author", ""),
                    "Body HTML": blog.get("body_html", ""),
                    "Tags": blog.get("tags", ""),
                    "Featured Image": blog.get("featured_image", ""),
                    "Published At": blog.get("published_at", ""),
                    "SEO Title": blog.get("seo_title", ""),
                    "SEO Description": blog.get("seo_description", ""),
                }
            )
        df = pd.DataFrame(rows, columns=BLOG_COLUMNS)
        df.fillna("", inplace=True)
        path = self._filepath("blogs", "csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("Exported %d blog posts to %s", len(df), path)
        return path

    # ------------------------------------------------------------------
    # URLs
    # ------------------------------------------------------------------

    async def export_urls(self, urls: List[Dict[str, Any]]) -> str:
        rows: list[dict[str, Any]] = []
        for u in urls:
            rows.append(
                {
                    "URL": u.get("url", ""),
                    "Status Code": u.get("status_code", ""),
                    "Content Type": u.get("content_type", ""),
                    "Canonical URL": u.get("canonical_url", ""),
                    "Meta Title": u.get("meta_title", ""),
                    "Meta Description": u.get("meta_description", ""),
                    "Page Type": u.get("page_type", ""),
                }
            )
        df = pd.DataFrame(rows, columns=URL_COLUMNS)
        df.fillna("", inplace=True)
        path = self._filepath("urls", "csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("Exported %d URL records to %s", len(df), path)
        return path

    # ------------------------------------------------------------------
    # Redirects
    # ------------------------------------------------------------------

    async def export_redirects(self, redirects: List[Dict[str, Any]]) -> str:
        rows: list[dict[str, Any]] = []
        for r in redirects:
            rows.append(
                {
                    "Old URL": r.get("old_url", "") or r.get("url", ""),
                    "New URL": r.get("new_url", "") or r.get("redirect_to", ""),
                }
            )
        df = pd.DataFrame(rows, columns=REDIRECT_COLUMNS)
        df.fillna("", inplace=True)
        path = self._filepath("redirects", "csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("Exported %d redirects to %s", len(df), path)
        return path
