"""Shopify-specific data validation for migration data."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationError:
    """A single validation issue."""

    field: str
    message: str
    item_identifier: str  # e.g. SKU, handle, or URL
    severity: str  # "error" or "warning"


@dataclass
class ValidationReport:
    """Result of validating one data type."""

    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def add_error(
        self, field: str, message: str, item_identifier: str = ""
    ) -> None:
        self.errors.append(
            ValidationError(
                field=field,
                message=message,
                item_identifier=item_identifier,
                severity="error",
            )
        )

    def add_warning(
        self, field: str, message: str, item_identifier: str = ""
    ) -> None:
        self.warnings.append(
            ValidationError(
                field=field,
                message=message,
                item_identifier=item_identifier,
                severity="warning",
            )
        )

    def build_summary(self, total_items: int) -> None:
        self.summary = {
            "total_items": total_items,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "is_valid": len(self.errors) == 0,
        }


# Pre-compiled patterns
_HANDLE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SCRIPT_RE = re.compile(r"<\s*script", re.IGNORECASE)


class ShopifyValidator:
    """Validates migration data against Shopify's requirements and best practices."""

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def validate_products(
        self,
        products: List[Dict[str, Any]],
        variants: List[Dict[str, Any]],
    ) -> ValidationReport:
        report = ValidationReport()

        # Index variants by product_id
        variants_by_product: Dict[int, List[Dict[str, Any]]] = {}
        for v in variants:
            pid = v.get("product_id")
            if pid is not None:
                variants_by_product.setdefault(pid, []).append(v)

        # --- Duplicate SKU check (across all variants + product-level SKUs) ---
        all_skus: list[str] = []
        for p in products:
            sku = p.get("sku")
            if sku:
                all_skus.append(str(sku))
        for v in variants:
            sku = v.get("sku")
            if sku:
                all_skus.append(str(sku))

        sku_counts = Counter(all_skus)
        for sku, count in sku_counts.items():
            if count > 1:
                report.add_error(
                    "sku",
                    f"Duplicate SKU '{sku}' found {count} times",
                    item_identifier=sku,
                )

        # --- Per-product checks ---
        for product in products:
            pid = product.get("id", "")
            handle = product.get("handle", "") or ""
            title = product.get("title", "") or ""
            identifier = handle or title or str(pid)

            # Required: title
            if not title.strip():
                report.add_error("title", "Product title is missing", identifier)

            # Title length
            if len(title) > 255:
                report.add_error(
                    "title",
                    f"Title exceeds 255 characters ({len(title)})",
                    identifier,
                )

            # Handle format
            if handle and not _HANDLE_RE.match(handle):
                report.add_warning(
                    "handle",
                    f"Handle '{handle}' is not lowercase-hyphenated — Shopify will auto-correct it",
                    identifier,
                )

            # Price (product-level)
            price = product.get("price")
            if price is not None:
                self._check_price(report, price, "price", identifier)
            else:
                # Only warn if there are no variants providing a price
                pvars = variants_by_product.get(product.get("id"), [])
                if not pvars:
                    report.add_warning(
                        "price",
                        "Product has no price and no variants",
                        identifier,
                    )

            # Images
            image_urls = product.get("image_urls") or []
            if not image_urls:
                report.add_warning(
                    "image_urls",
                    "Product has no images",
                    identifier,
                )

            # HTML security
            body = product.get("description_html") or ""
            if _SCRIPT_RE.search(body):
                report.add_error(
                    "description_html",
                    "Product description contains <script> tags",
                    identifier,
                )

            # Variant constraints
            pvars = variants_by_product.get(product.get("id"), [])
            if len(pvars) > 100:
                report.add_error(
                    "variants",
                    f"Product has {len(pvars)} variants (Shopify max is 100)",
                    identifier,
                )

            # Option consistency — collect unique option names
            option_names: set[str] = set()
            for v in pvars:
                for opt_key in ("option1_name", "option2_name", "option3_name"):
                    name = v.get(opt_key)
                    if name:
                        option_names.add(name)
            if len(option_names) > 3:
                report.add_error(
                    "options",
                    f"Product uses {len(option_names)} option names (Shopify max is 3)",
                    identifier,
                )

        # --- Per-variant checks ---
        for v in variants:
            v_sku = v.get("sku") or ""
            v_id = v_sku or str(v.get("id", ""))
            price = v.get("price")
            if price is not None:
                self._check_price(report, price, "variant_price", v_id)

        report.build_summary(len(products))
        return report

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def validate_collections(
        self, collections: List[Dict[str, Any]]
    ) -> ValidationReport:
        report = ValidationReport()

        handles_seen: Counter[str] = Counter()
        for col in collections:
            handle = col.get("handle", "") or ""
            title = col.get("title", "") or ""
            identifier = handle or title

            if not title.strip():
                report.add_error("title", "Collection title is missing", identifier)

            if handle:
                handles_seen[handle] += 1

            body = col.get("description_html") or ""
            if _SCRIPT_RE.search(body):
                report.add_error(
                    "description_html",
                    "Collection description contains <script> tags",
                    identifier,
                )

        for h, count in handles_seen.items():
            if count > 1:
                report.add_error(
                    "handle",
                    f"Duplicate collection handle '{h}' found {count} times",
                    item_identifier=h,
                )

        report.build_summary(len(collections))
        return report

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def validate_pages(self, pages: List[Dict[str, Any]]) -> ValidationReport:
        report = ValidationReport()

        handles_seen: Counter[str] = Counter()
        for page in pages:
            handle = page.get("handle", "") or ""
            title = page.get("title", "") or ""
            identifier = handle or title

            if not title.strip():
                report.add_error("title", "Page title is missing", identifier)

            body = page.get("body_html") or ""
            if not body.strip():
                report.add_warning("body_html", "Page has no content", identifier)

            if _SCRIPT_RE.search(body):
                report.add_error(
                    "body_html",
                    "Page content contains <script> tags",
                    identifier,
                )

            if handle:
                handles_seen[handle] += 1

        for h, count in handles_seen.items():
            if count > 1:
                report.add_error(
                    "handle",
                    f"Duplicate page handle '{h}' found {count} times",
                    item_identifier=h,
                )

        report.build_summary(len(pages))
        return report

    # ------------------------------------------------------------------
    # Blogs
    # ------------------------------------------------------------------

    def validate_blogs(self, blogs: List[Dict[str, Any]]) -> ValidationReport:
        report = ValidationReport()

        for blog in blogs:
            handle = blog.get("handle", "") or ""
            title = blog.get("title", "") or ""
            identifier = handle or title

            if not title.strip():
                report.add_error("title", "Blog post title is missing", identifier)

            author = blog.get("author", "") or ""
            if not author.strip():
                report.add_warning(
                    "author", "Blog post has no author", identifier
                )

            body = blog.get("body_html") or ""
            if _SCRIPT_RE.search(body):
                report.add_error(
                    "body_html",
                    "Blog post content contains <script> tags",
                    identifier,
                )

        report.build_summary(len(blogs))
        return report

    # ------------------------------------------------------------------
    # URLs
    # ------------------------------------------------------------------

    def validate_urls(self, urls: List[Dict[str, Any]]) -> ValidationReport:
        report = ValidationReport()

        seen_urls: Counter[str] = Counter()
        for u in urls:
            url = u.get("url", "") or ""
            status = u.get("status_code")
            identifier = url

            if url:
                seen_urls[url] += 1

            # Broken links
            if status is not None:
                try:
                    code = int(status)
                except (TypeError, ValueError):
                    code = 0
                if 400 <= code < 500:
                    report.add_error(
                        "status_code",
                        f"Client error {code} on {url}",
                        identifier,
                    )
                elif 500 <= code < 600:
                    report.add_error(
                        "status_code",
                        f"Server error {code} on {url}",
                        identifier,
                    )

            # Missing canonical
            canonical = u.get("canonical_url", "") or ""
            if not canonical.strip():
                report.add_warning(
                    "canonical_url",
                    "URL has no canonical tag",
                    identifier,
                )

            # Missing meta description
            meta_desc = u.get("meta_description", "") or ""
            if not meta_desc.strip():
                report.add_warning(
                    "meta_description",
                    "URL has no meta description",
                    identifier,
                )

        # Duplicate URLs
        for url_str, count in seen_urls.items():
            if count > 1:
                report.add_warning(
                    "url",
                    f"Duplicate URL '{url_str}' found {count} times",
                    item_identifier=url_str,
                )

        report.build_summary(len(urls))
        return report

    # ------------------------------------------------------------------
    # Batch validate
    # ------------------------------------------------------------------

    def validate_all(self, data: Dict[str, Any]) -> Dict[str, ValidationReport]:
        """Validate every data type present in *data*.

        Expected keys: ``products``, ``variants``, ``collections``, ``pages``,
        ``blogs``, ``urls``.
        """
        results: Dict[str, ValidationReport] = {}

        if data.get("products") is not None:
            results["products"] = self.validate_products(
                data["products"], data.get("variants", [])
            )

        if data.get("collections") is not None:
            results["collections"] = self.validate_collections(data["collections"])

        if data.get("pages") is not None:
            results["pages"] = self.validate_pages(data["pages"])

        if data.get("blogs") is not None:
            results["blogs"] = self.validate_blogs(data["blogs"])

        if data.get("urls") is not None:
            results["urls"] = self.validate_urls(data["urls"])

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_price(
        report: ValidationReport,
        price: Any,
        field_name: str,
        identifier: str,
    ) -> None:
        try:
            val = float(price)
        except (TypeError, ValueError):
            report.add_error(
                field_name,
                f"Price '{price}' is not a valid number",
                identifier,
            )
            return
        if val < 0:
            report.add_error(
                field_name,
                f"Price '{val}' is negative",
                identifier,
            )
