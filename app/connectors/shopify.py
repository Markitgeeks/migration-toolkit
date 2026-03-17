"""Shopify Admin REST API connector (API version 2024-10)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import httpx

from .base import BaseConnector

logger = logging.getLogger(__name__)

API_VERSION = "2024-10"
PAGE_LIMIT = 250
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2.0


class ShopifyConnector(BaseConnector):
    """Extract data from a Shopify store via the Admin REST API."""

    def __init__(
        self,
        store_url: str,
        api_key: str = "",
        api_secret: str = "",
        access_token: str = "",
    ):
        super().__init__(store_url, api_key, api_secret, access_token)
        self._base = f"{self.store_url}/admin/api/{API_VERSION}"
        self._headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
        )

    async def _request(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Issue a GET with automatic retry on 429 and transient errors."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "2"))
                    logger.warning(
                        "Shopify 429 rate-limited on %s — retrying in %.1fs (attempt %d/%d)",
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
        # Should not reach here, but satisfy type checker
        raise RuntimeError("Max retries exceeded")

    async def _paginate(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        root_key: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Follow Shopify cursor-based pagination via the Link header."""
        url = f"{self._base}/{endpoint}"
        req_params = {"limit": PAGE_LIMIT}
        if params:
            req_params.update(params)

        results: List[Dict[str, Any]] = []

        while url:
            resp = await self._request(client, url, params=req_params)
            data = resp.json()
            results.extend(data.get(root_key, []))

            # After the first request use the next cursor URL directly
            url = self._next_page_url(resp)
            req_params = None  # params are embedded in the Link URL

        return results

    @staticmethod
    def _next_page_url(resp: httpx.Response) -> Optional[str]:
        link = resp.headers.get("link", "")
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        return match.group(1) if match else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        try:
            async with self._client() as client:
                resp = await self._request(client, f"{self._base}/shop.json")
                return "shop" in resp.json()
        except Exception as exc:
            logger.error("Shopify connection test failed: %s", exc)
            return False

    async def fetch_products(self) -> List[Dict[str, Any]]:
        logger.info("Fetching products from Shopify store %s", self.store_url)
        async with self._client() as client:
            raw_products = await self._paginate(
                client, "products.json", "products", {"status": "any"}
            )
            products: List[Dict[str, Any]] = []
            for rp in raw_products:
                # Fetch metafields for this product
                metafields = await self._fetch_metafields(client, rp["id"])
                products.append(self._normalize_product(rp, metafields))
            logger.info("Fetched %d products", len(products))
            return products

    async def _fetch_metafields(
        self, client: httpx.AsyncClient, product_id: int
    ) -> List[Dict[str, Any]]:
        try:
            resp = await self._request(
                client,
                f"{self._base}/products/{product_id}/metafields.json",
            )
            return resp.json().get("metafields", [])
        except Exception as exc:
            logger.warning("Failed to fetch metafields for product %d: %s", product_id, exc)
            return []

    async def fetch_collections(self) -> List[Dict[str, Any]]:
        logger.info("Fetching collections from Shopify store %s", self.store_url)
        async with self._client() as client:
            custom = await self._paginate(
                client, "custom_collections.json", "custom_collections"
            )
            smart = await self._paginate(
                client, "smart_collections.json", "smart_collections"
            )
            raw_collections = custom + smart

            collections: List[Dict[str, Any]] = []
            for rc in raw_collections:
                product_handles = await self._fetch_collection_products(
                    client, rc["id"]
                )
                collections.append(
                    self._normalize_collection(rc, product_handles)
                )
            logger.info("Fetched %d collections", len(collections))
            return collections

    async def _fetch_collection_products(
        self, client: httpx.AsyncClient, collection_id: int
    ) -> List[str]:
        try:
            products = await self._paginate(
                client,
                f"collections/{collection_id}/products.json",
                "products",
            )
            return [p.get("handle", "") for p in products if p.get("handle")]
        except Exception as exc:
            logger.warning(
                "Failed to fetch products for collection %d: %s",
                collection_id,
                exc,
            )
            return []

    async def fetch_pages(self) -> List[Dict[str, Any]]:
        logger.info("Fetching pages from Shopify store %s", self.store_url)
        async with self._client() as client:
            raw = await self._paginate(client, "pages.json", "pages")
            pages = [self._normalize_page(p) for p in raw]
            logger.info("Fetched %d pages", len(pages))
            return pages

    async def fetch_blogs(self) -> List[Dict[str, Any]]:
        logger.info("Fetching blog posts from Shopify store %s", self.store_url)
        async with self._client() as client:
            blogs = await self._paginate(client, "blogs.json", "blogs")
            articles: List[Dict[str, Any]] = []
            for blog in blogs:
                blog_title = blog.get("title", "")
                raw_articles = await self._paginate(
                    client,
                    f"blogs/{blog['id']}/articles.json",
                    "articles",
                )
                for art in raw_articles:
                    articles.append(self._normalize_article(art, blog_title))
            logger.info("Fetched %d blog articles", len(articles))
            return articles

    async def fetch_redirects(self) -> List[Dict[str, Any]]:
        logger.info("Fetching redirects from Shopify store %s", self.store_url)
        async with self._client() as client:
            raw = await self._paginate(client, "redirects.json", "redirects")
            redirects = [self._normalize_redirect(r) for r in raw]
            logger.info("Fetched %d redirects", len(redirects))
            return redirects

    # ------------------------------------------------------------------
    # Normalizers — map Shopify JSON to our DB-model dicts
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_product(
        rp: Dict[str, Any], metafields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        images = rp.get("images", [])
        first_variant = rp.get("variants", [{}])[0] if rp.get("variants") else {}

        seo_title = None
        seo_description = None
        for mf in metafields:
            if mf.get("namespace") == "global" and mf.get("key") == "title_tag":
                seo_title = mf.get("value")
            if mf.get("namespace") == "global" and mf.get("key") == "description_tag":
                seo_description = mf.get("value")

        variants = []
        options = rp.get("options", [])
        for v in rp.get("variants", []):
            variant: Dict[str, Any] = {
                "title": v.get("title"),
                "sku": v.get("sku"),
                "barcode": v.get("barcode"),
                "price": _safe_float(v.get("price")),
                "compare_at_price": _safe_float(v.get("compare_at_price")),
                "inventory_qty": v.get("inventory_quantity"),
                "weight": _safe_float(v.get("weight")),
                "weight_unit": v.get("weight_unit"),
                "image_url": None,
                "position": v.get("position"),
            }
            # Map option values
            for idx, opt in enumerate(options, 1):
                variant[f"option{idx}_name"] = opt.get("name")
                variant[f"option{idx}_value"] = v.get(f"option{idx}")
            # Resolve variant image
            if v.get("image_id"):
                for img in images:
                    if img.get("id") == v["image_id"]:
                        variant["image_url"] = img.get("src")
                        break
            variants.append(variant)

        return {
            "title": rp.get("title", ""),
            "handle": rp.get("handle"),
            "description_html": rp.get("body_html"),
            "vendor": rp.get("vendor"),
            "product_type": rp.get("product_type"),
            "tags": rp.get("tags"),
            "status": rp.get("status"),
            "sku": first_variant.get("sku"),
            "barcode": first_variant.get("barcode"),
            "price": _safe_float(first_variant.get("price")),
            "compare_at_price": _safe_float(first_variant.get("compare_at_price")),
            "cost_per_item": None,
            "source_url": None,
            "image_urls": [img.get("src") for img in images if img.get("src")],
            "seo_title": seo_title,
            "seo_description": seo_description,
            "metafields": {
                mf.get("key"): mf.get("value") for mf in metafields
            },
            "variants": variants,
        }

    @staticmethod
    def _normalize_collection(
        rc: Dict[str, Any], product_handles: List[str]
    ) -> Dict[str, Any]:
        image = rc.get("image", {}) or {}
        return {
            "title": rc.get("title", ""),
            "handle": rc.get("handle"),
            "description_html": rc.get("body_html"),
            "image_url": image.get("src"),
            "seo_title": rc.get("title"),
            "seo_description": rc.get("body_html", "")[:1024] if rc.get("body_html") else None,
            "sort_order": rc.get("sort_order"),
            "product_handles": product_handles,
        }

    @staticmethod
    def _normalize_page(rp: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": rp.get("title", ""),
            "handle": rp.get("handle"),
            "body_html": rp.get("body_html"),
            "seo_title": rp.get("title"),
            "seo_description": rp.get("body_html", "")[:1024] if rp.get("body_html") else None,
            "published": rp.get("published_at") is not None,
            "source_url": None,
        }

    @staticmethod
    def _normalize_article(
        art: Dict[str, Any], blog_title: str
    ) -> Dict[str, Any]:
        return {
            "blog_title": blog_title,
            "title": art.get("title", ""),
            "handle": art.get("handle"),
            "author": art.get("author"),
            "body_html": art.get("body_html"),
            "tags": art.get("tags"),
            "featured_image": (art.get("image", {}) or {}).get("src"),
            "seo_title": art.get("title"),
            "seo_description": art.get("summary_html"),
            "published_at": art.get("published_at"),
            "source_url": None,
        }

    @staticmethod
    def _normalize_redirect(r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": r.get("path", ""),
            "target": r.get("target", ""),
        }


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
