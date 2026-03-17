"""WooCommerce REST API v3 connector."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseConnector

logger = logging.getLogger(__name__)

PER_PAGE = 100
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2.0


class WooCommerceConnector(BaseConnector):
    """Extract data from a WooCommerce store via the REST API v3."""

    def __init__(
        self,
        store_url: str,
        api_key: str = "",
        api_secret: str = "",
        access_token: str = "",
    ):
        super().__init__(store_url, api_key, api_secret, access_token)
        self._wc_base = f"{self.store_url}/wp-json/wc/v3"
        self._wp_base = f"{self.store_url}/wp-json/wp/v2"

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _auth_params(self) -> Dict[str, str]:
        return {
            "consumer_key": self.api_key,
            "consumer_secret": self.api_secret,
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
        )

    async def _request(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "2"))
                    logger.warning(
                        "WooCommerce 429 on %s — retrying in %.1fs (attempt %d/%d)",
                        url,
                        retry_after,
                        attempt,
                        MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError:
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt == MAX_RETRIES:
                    raise
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "Transient error on %s (%s) — retrying in %.1fs (attempt %d/%d)",
                    url,
                    exc,
                    wait,
                    attempt,
                    MAX_RETRIES,
                )
                await asyncio.sleep(wait)
        raise RuntimeError("Max retries exceeded")

    async def _paginate_wc(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Paginate WooCommerce endpoints using page/per_page and X-WP-TotalPages."""
        url = f"{self._wc_base}/{endpoint}"
        params: Dict[str, Any] = {**self._auth_params(), "per_page": PER_PAGE, "page": 1}
        if extra_params:
            params.update(extra_params)

        results: List[Dict[str, Any]] = []
        total_pages = 1

        while params["page"] <= total_pages:
            resp = await self._request(client, url, params=params)
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            tp = resp.headers.get("X-WP-TotalPages")
            if tp:
                total_pages = int(tp)
            params["page"] += 1

        return results

    async def _paginate_wp(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Paginate WordPress REST API endpoints."""
        url = f"{self._wp_base}/{endpoint}"
        params: Dict[str, Any] = {"per_page": PER_PAGE, "page": 1}
        if extra_params:
            params.update(extra_params)

        results: List[Dict[str, Any]] = []
        total_pages = 1

        while params["page"] <= total_pages:
            resp = await self._request(client, url, params=params)
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            tp = resp.headers.get("X-WP-TotalPages")
            if tp:
                total_pages = int(tp)
            params["page"] += 1

        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        try:
            async with self._client() as client:
                resp = await self._request(
                    client,
                    f"{self._wc_base}/system_status",
                    params=self._auth_params(),
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.error("WooCommerce connection test failed: %s", exc)
            return False

    async def fetch_products(self) -> List[Dict[str, Any]]:
        logger.info("Fetching products from WooCommerce store %s", self.store_url)
        async with self._client() as client:
            raw = await self._paginate_wc(client, "products")
            products: List[Dict[str, Any]] = []
            for rp in raw:
                # For variable products, fetch variations separately
                variations: List[Dict[str, Any]] = []
                if rp.get("type") == "variable":
                    try:
                        variations = await self._paginate_wc(
                            client, f"products/{rp['id']}/variations"
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to fetch variations for product %d: %s",
                            rp["id"],
                            exc,
                        )
                products.append(self._normalize_product(rp, variations))
            logger.info("Fetched %d products", len(products))
            return products

    async def fetch_collections(self) -> List[Dict[str, Any]]:
        logger.info("Fetching categories from WooCommerce store %s", self.store_url)
        async with self._client() as client:
            raw = await self._paginate_wc(client, "products/categories")
            collections = [self._normalize_collection(c) for c in raw]
            logger.info("Fetched %d collections", len(collections))
            return collections

    async def fetch_pages(self) -> List[Dict[str, Any]]:
        logger.info("Fetching pages from WordPress %s", self.store_url)
        async with self._client() as client:
            raw = await self._paginate_wp(client, "pages")
            pages = [self._normalize_page(p) for p in raw]
            logger.info("Fetched %d pages", len(pages))
            return pages

    async def fetch_blogs(self) -> List[Dict[str, Any]]:
        logger.info("Fetching blog posts from WordPress %s", self.store_url)
        async with self._client() as client:
            raw = await self._paginate_wp(client, "posts")
            posts = [self._normalize_post(p) for p in raw]
            logger.info("Fetched %d blog posts", len(posts))
            return posts

    async def fetch_redirects(self) -> List[Dict[str, Any]]:
        logger.info("WooCommerce has no built-in redirects API — returning empty list")
        return []

    # ------------------------------------------------------------------
    # Normalizers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_product(
        rp: Dict[str, Any], variations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        images = rp.get("images", [])
        attrs = rp.get("attributes", [])

        variants: List[Dict[str, Any]] = []
        for v in variations:
            variant: Dict[str, Any] = {
                "title": _wc_variation_title(v),
                "sku": v.get("sku"),
                "barcode": None,
                "price": _safe_float(v.get("price")),
                "compare_at_price": _safe_float(v.get("regular_price")),
                "inventory_qty": v.get("stock_quantity"),
                "weight": _safe_float(v.get("weight")),
                "weight_unit": None,
                "image_url": (v.get("image", {}) or {}).get("src"),
                "position": v.get("menu_order"),
            }
            v_attrs = v.get("attributes", [])
            for idx in range(1, 4):
                if idx - 1 < len(v_attrs):
                    variant[f"option{idx}_name"] = v_attrs[idx - 1].get("name")
                    variant[f"option{idx}_value"] = v_attrs[idx - 1].get("option")
                else:
                    variant[f"option{idx}_name"] = None
                    variant[f"option{idx}_value"] = None
            variants.append(variant)

        # If simple product with no variations, create a single "variant"
        if not variants:
            single: Dict[str, Any] = {
                "title": "Default",
                "sku": rp.get("sku"),
                "barcode": None,
                "price": _safe_float(rp.get("price")),
                "compare_at_price": _safe_float(rp.get("regular_price")),
                "inventory_qty": rp.get("stock_quantity"),
                "weight": _safe_float(rp.get("weight")),
                "weight_unit": None,
                "image_url": images[0].get("src") if images else None,
                "position": 1,
            }
            for idx in range(1, 4):
                single[f"option{idx}_name"] = None
                single[f"option{idx}_value"] = None
            variants.append(single)

        return {
            "title": rp.get("name", ""),
            "handle": rp.get("slug"),
            "description_html": rp.get("description"),
            "vendor": None,
            "product_type": _first_category_name(rp.get("categories", [])),
            "tags": ", ".join(t.get("name", "") for t in rp.get("tags", [])),
            "status": rp.get("status"),
            "sku": rp.get("sku"),
            "barcode": None,
            "price": _safe_float(rp.get("price")),
            "compare_at_price": _safe_float(rp.get("regular_price")),
            "cost_per_item": None,
            "source_url": rp.get("permalink"),
            "image_urls": [img.get("src") for img in images if img.get("src")],
            "seo_title": rp.get("name"),
            "seo_description": rp.get("short_description"),
            "variants": variants,
        }

    @staticmethod
    def _normalize_collection(rc: Dict[str, Any]) -> Dict[str, Any]:
        image = rc.get("image", {}) or {}
        return {
            "title": rc.get("name", ""),
            "handle": rc.get("slug"),
            "description_html": rc.get("description"),
            "image_url": image.get("src"),
            "seo_title": rc.get("name"),
            "seo_description": (rc.get("description") or "")[:1024] or None,
            "sort_order": None,
            "product_handles": [],  # WooCommerce categories don't embed products
        }

    @staticmethod
    def _normalize_page(rp: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": _rendered(rp.get("title")),
            "handle": rp.get("slug"),
            "body_html": _rendered(rp.get("content")),
            "seo_title": _rendered(rp.get("title")),
            "seo_description": _rendered(rp.get("excerpt")),
            "published": rp.get("status") == "publish",
            "source_url": rp.get("link"),
        }

    @staticmethod
    def _normalize_post(rp: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "blog_title": "Blog",
            "title": _rendered(rp.get("title")),
            "handle": rp.get("slug"),
            "author": str(rp.get("author", "")),
            "body_html": _rendered(rp.get("content")),
            "tags": "",
            "featured_image": rp.get("jetpack_featured_media_url"),
            "seo_title": _rendered(rp.get("title")),
            "seo_description": _rendered(rp.get("excerpt")),
            "published_at": rp.get("date"),
            "source_url": rp.get("link"),
        }


# ------------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------------


def _rendered(val: Any) -> Optional[str]:
    """WordPress REST API wraps many strings in {rendered: ...}."""
    if isinstance(val, dict):
        return val.get("rendered")
    return val


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _first_category_name(cats: List[Dict[str, Any]]) -> Optional[str]:
    if cats:
        return cats[0].get("name")
    return None


def _wc_variation_title(v: Dict[str, Any]) -> str:
    attrs = v.get("attributes", [])
    if attrs:
        return " / ".join(a.get("option", "") for a in attrs)
    return "Default"
