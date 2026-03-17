"""Generic web crawler connector using Playwright + BeautifulSoup.

Extracts products, collections, pages, and blog posts from any ecommerce site
by parsing structured data (JSON-LD, Open Graph) and falling back to HTML analysis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseConnector

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 1000
DEFAULT_CRAWL_DELAY = 0.5  # seconds between requests
REQUEST_TIMEOUT = 20.0

# URL patterns for page-type classification
_PRODUCT_PATTERNS = re.compile(
    r"/(products?|shop|item|p)/|/dp/|product_id=|/catalog/",
    re.IGNORECASE,
)
_COLLECTION_PATTERNS = re.compile(
    r"/(collections?|categories?|category|shop|department)/",
    re.IGNORECASE,
)
_BLOG_PATTERNS = re.compile(
    r"/(blogs?|articles?|news|journal|posts?)/",
    re.IGNORECASE,
)
_SKIP_EXTENSIONS = re.compile(
    r"\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|css|js|xml|json|woff2?|ttf|eot|ico|mp4|webm)$",
    re.IGNORECASE,
)


class WebCrawlerConnector(BaseConnector):
    """Crawl an arbitrary website and extract ecommerce data."""

    def __init__(
        self,
        store_url: str,
        api_key: str = "",
        api_secret: str = "",
        access_token: str = "",
        max_pages: int = DEFAULT_MAX_PAGES,
        crawl_delay: float = DEFAULT_CRAWL_DELAY,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ):
        super().__init__(store_url, api_key, api_secret, access_token)
        self.max_pages = max_pages
        self.crawl_delay = crawl_delay
        self.progress_callback = progress_callback

        parsed = urlparse(self.store_url)
        self._domain = parsed.netloc
        self._scheme = parsed.scheme or "https"
        self._origin = f"{self._scheme}://{self._domain}"

        # State
        self._visited: Set[str] = set()
        self._url_records: List[Dict[str, Any]] = []
        self._products: List[Dict[str, Any]] = []
        self._collections: List[Dict[str, Any]] = []
        self._pages: List[Dict[str, Any]] = []
        self._blogs: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT), follow_redirects=True
            ) as client:
                resp = await client.get(self.store_url)
                return resp.status_code < 400
        except Exception as exc:
            logger.error("Connection test failed for %s: %s", self.store_url, exc)
            return False

    async def fetch_products(self) -> List[Dict[str, Any]]:
        if not self._visited:
            await self._crawl()
        return self._products

    async def fetch_collections(self) -> List[Dict[str, Any]]:
        if not self._visited:
            await self._crawl()
        return self._collections

    async def fetch_pages(self) -> List[Dict[str, Any]]:
        if not self._visited:
            await self._crawl()
        return self._pages

    async def fetch_blogs(self) -> List[Dict[str, Any]]:
        if not self._visited:
            await self._crawl()
        return self._blogs

    async def fetch_redirects(self) -> List[Dict[str, Any]]:
        if not self._visited:
            await self._crawl()
        redirects = []
        for rec in self._url_records:
            if rec.get("redirect_to"):
                redirects.append(
                    {"source": rec["url"], "target": rec["redirect_to"]}
                )
        return redirects

    async def fetch_all(self) -> Dict[str, List[Dict[str, Any]]]:
        await self._crawl()
        return {
            "products": self._products,
            "collections": self._collections,
            "pages": self._pages,
            "blogs": self._blogs,
            "redirects": await self.fetch_redirects(),
        }

    # ------------------------------------------------------------------
    # Crawler core
    # ------------------------------------------------------------------

    async def _crawl(self) -> None:
        """Run the full crawl pipeline using httpx (serverless-compatible)."""
        logger.info("Starting crawl of %s (max %d pages)", self.store_url, self.max_pages)

        # Discover URLs from sitemap first
        sitemap_urls = await self._parse_sitemap(f"{self._origin}/sitemap.xml")
        queue: List[str] = list(sitemap_urls)
        if self.store_url not in sitemap_urls:
            queue.insert(0, self.store_url)

        logger.info("Sitemap discovery found %d URLs", len(sitemap_urls))

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT),
            follow_redirects=True,
            headers=headers,
        ) as client:
            while queue and len(self._visited) < self.max_pages:
                url = queue.pop(0)
                url = self._normalize_url(url)

                if url in self._visited:
                    continue
                if not self._is_same_domain(url):
                    continue
                if _SKIP_EXTENSIONS.search(url):
                    continue

                self._visited.add(url)
                self._report_progress(len(self._visited), len(queue) + len(self._visited), url)

                try:
                    resp = await client.get(url)
                    status_code = resp.status_code
                    final_url = str(resp.url)

                    # Detect redirect
                    redirect_to = None
                    if self._normalize_url(final_url) != url:
                        redirect_to = final_url

                    # Skip non-HTML responses
                    content_type = resp.headers.get("content-type", "")
                    if "text/html" not in content_type:
                        self._url_records.append({
                            "url": url, "status_code": status_code,
                            "page_type": "other", "redirect_to": redirect_to,
                            "content_type": content_type,
                        })
                        continue

                    html = resp.text
                except Exception as exc:
                    logger.warning("Failed to load %s: %s", url, exc)
                    self._url_records.append(
                        {"url": url, "status_code": 0, "page_type": "error", "redirect_to": None}
                    )
                    continue

                soup = BeautifulSoup(html, "lxml")
                page_data = self._extract_page_metadata(soup, url)
                page_data["status_code"] = status_code
                page_data["redirect_to"] = redirect_to

                # Classify and extract
                page_type = self._classify_page(url, soup)
                page_data["page_type"] = page_type

                self._url_records.append(page_data)
                self._dispatch_page(page_type, soup, url, page_data)

                # Discover new links
                new_links = self._extract_links(soup, url)
                for link in new_links:
                    if link not in self._visited:
                        queue.append(link)

                if self.crawl_delay > 0:
                    await asyncio.sleep(self.crawl_delay)

        logger.info(
            "Crawl complete: %d pages visited, %d products, %d collections, %d pages, %d blogs",
            len(self._visited),
            len(self._products),
            len(self._collections),
            len(self._pages),
            len(self._blogs),
        )

    # ------------------------------------------------------------------
    # Sitemap parser
    # ------------------------------------------------------------------

    async def _parse_sitemap(self, url: str) -> Set[str]:
        """Recursively parse sitemap.xml and sitemap index files."""
        urls: Set[str] = set()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT), follow_redirects=True
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return urls
        except Exception as exc:
            logger.debug("Could not fetch sitemap at %s: %s", url, exc)
            return urls

        soup = BeautifulSoup(resp.text, "lxml")

        # Sitemap index — recurse into child sitemaps
        for sitemap_tag in soup.find_all("sitemap"):
            loc = sitemap_tag.find("loc")
            if loc and loc.text.strip():
                child_urls = await self._parse_sitemap(loc.text.strip())
                urls.update(child_urls)

        # Regular sitemap — collect URLs
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if loc and loc.text.strip():
                candidate = loc.text.strip()
                if self._is_same_domain(candidate):
                    urls.add(self._normalize_url(candidate))

        return urls

    # ------------------------------------------------------------------
    # Page metadata extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_page_metadata(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract meta tags, canonical, OG data from a page."""
        title_tag = soup.find("title")
        meta_title = title_tag.get_text(strip=True) if title_tag else None

        meta_desc = None
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag and isinstance(desc_tag, Tag):
            meta_desc = desc_tag.get("content")

        canonical = None
        canon_tag = soup.find("link", attrs={"rel": "canonical"})
        if canon_tag and isinstance(canon_tag, Tag):
            canonical = canon_tag.get("href")

        og: Dict[str, str] = {}
        for tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:")}):
            if isinstance(tag, Tag):
                prop = tag.get("property", "")
                content = tag.get("content", "")
                if isinstance(prop, str) and isinstance(content, str):
                    og[prop] = content

        return {
            "url": url,
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "canonical_url": canonical,
            "og": og,
            "content_type": "text/html",
        }

    # ------------------------------------------------------------------
    # Structured data extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract all JSON-LD blocks from a page."""
        results: List[Dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    results.extend(data)
                elif isinstance(data, dict):
                    # Handle @graph wrapper
                    if "@graph" in data:
                        results.extend(data["@graph"])
                    else:
                        results.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return results

    # ------------------------------------------------------------------
    # Page classification
    # ------------------------------------------------------------------

    def _classify_page(self, url: str, soup: BeautifulSoup) -> str:
        """Determine if a page is product, collection, page, or blog."""
        # Check JSON-LD first
        json_ld = self._extract_json_ld(soup)
        for item in json_ld:
            ld_type = item.get("@type", "")
            if isinstance(ld_type, list):
                ld_type = " ".join(ld_type)
            ld_type_lower = ld_type.lower()
            if "product" in ld_type_lower:
                return "product"
            if "article" in ld_type_lower or "blogposting" in ld_type_lower or "newsarticle" in ld_type_lower:
                return "blog"
            if "collectionpage" in ld_type_lower or "itemlist" in ld_type_lower:
                return "collection"

        # Check OG type
        og_type_tag = soup.find("meta", attrs={"property": "og:type"})
        if og_type_tag and isinstance(og_type_tag, Tag):
            og_type = (og_type_tag.get("content") or "").lower()
            if og_type == "product":
                return "product"
            if og_type == "article":
                return "blog"

        # URL pattern fallback
        path = urlparse(url).path
        if _PRODUCT_PATTERNS.search(path):
            return "product"
        if _COLLECTION_PATTERNS.search(path):
            return "collection"
        if _BLOG_PATTERNS.search(path):
            return "blog"

        return "page"

    # ------------------------------------------------------------------
    # Dispatch extraction by page type
    # ------------------------------------------------------------------

    def _dispatch_page(
        self,
        page_type: str,
        soup: BeautifulSoup,
        url: str,
        page_data: Dict[str, Any],
    ) -> None:
        if page_type == "product":
            product = self._extract_product(soup, url, page_data)
            if product:
                self._products.append(product)
        elif page_type == "collection":
            collection = self._extract_collection(soup, url, page_data)
            if collection:
                self._collections.append(collection)
        elif page_type == "blog":
            post = self._extract_blog_post(soup, url, page_data)
            if post:
                self._blogs.append(post)
        else:
            page = self._extract_static_page(soup, url, page_data)
            if page:
                self._pages.append(page)

    # ------------------------------------------------------------------
    # Product extraction
    # ------------------------------------------------------------------

    def _extract_product(
        self,
        soup: BeautifulSoup,
        url: str,
        page_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        json_ld = self._extract_json_ld(soup)
        ld_product = None
        for item in json_ld:
            t = item.get("@type", "")
            if isinstance(t, list):
                t = " ".join(t)
            if "product" in t.lower():
                ld_product = item
                break

        title = None
        description = None
        price = None
        sku = None
        images: List[str] = []
        variants: List[Dict[str, Any]] = []

        if ld_product:
            title = ld_product.get("name")
            description = ld_product.get("description")
            sku = ld_product.get("sku")
            img = ld_product.get("image")
            if isinstance(img, str):
                images.append(img)
            elif isinstance(img, list):
                images.extend(i if isinstance(i, str) else i.get("url", "") for i in img)
            elif isinstance(img, dict):
                images.append(img.get("url", ""))

            offers = ld_product.get("offers") or {}
            if isinstance(offers, dict):
                offers = [offers]
            if isinstance(offers, list):
                for off in offers:
                    if isinstance(off, dict):
                        if price is None:
                            price = _safe_float(off.get("price"))
                        if len(offers) > 1:
                            variants.append({
                                "title": off.get("name") or off.get("sku") or "Variant",
                                "sku": off.get("sku"),
                                "price": _safe_float(off.get("price")),
                                "compare_at_price": None,
                                "inventory_qty": None,
                                "weight": None,
                                "weight_unit": None,
                                "image_url": None,
                                "position": len(variants) + 1,
                                "barcode": None,
                                "option1_name": None,
                                "option1_value": off.get("name"),
                                "option2_name": None,
                                "option2_value": None,
                                "option3_name": None,
                                "option3_value": None,
                            })

        # HTML fallback
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else page_data.get("meta_title", "Untitled")

        if not description:
            description = page_data.get("meta_description")

        if not images:
            og_img = page_data.get("og", {}).get("og:image")
            if og_img:
                images.append(og_img)

        if not price:
            price_tag = soup.find(class_=re.compile(r"price", re.I))
            if price_tag:
                price = _extract_price_from_text(price_tag.get_text())

        # Default single variant
        if not variants:
            variants.append({
                "title": "Default",
                "sku": sku,
                "price": price,
                "compare_at_price": None,
                "inventory_qty": None,
                "weight": None,
                "weight_unit": None,
                "image_url": images[0] if images else None,
                "position": 1,
                "barcode": None,
                "option1_name": None,
                "option1_value": None,
                "option2_name": None,
                "option2_value": None,
                "option3_name": None,
                "option3_value": None,
            })

        return {
            "title": title or "Untitled Product",
            "handle": _handle_from_url(url),
            "description_html": description,
            "vendor": None,
            "product_type": None,
            "tags": "",
            "status": "active",
            "sku": sku,
            "barcode": None,
            "price": price,
            "compare_at_price": None,
            "cost_per_item": None,
            "source_url": url,
            "image_urls": images,
            "seo_title": page_data.get("meta_title"),
            "seo_description": page_data.get("meta_description"),
            "variants": variants,
        }

    # ------------------------------------------------------------------
    # Collection extraction
    # ------------------------------------------------------------------

    def _extract_collection(
        self,
        soup: BeautifulSoup,
        url: str,
        page_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else page_data.get("meta_title", "Untitled")

        # Find product links within collection
        product_handles: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(url, href)
            if _PRODUCT_PATTERNS.search(full_url):
                handle = _handle_from_url(full_url)
                if handle and handle not in product_handles:
                    product_handles.append(handle)

        return {
            "title": title or "Untitled Collection",
            "handle": _handle_from_url(url),
            "description_html": page_data.get("meta_description"),
            "image_url": page_data.get("og", {}).get("og:image"),
            "seo_title": page_data.get("meta_title"),
            "seo_description": page_data.get("meta_description"),
            "sort_order": None,
            "product_handles": product_handles,
        }

    # ------------------------------------------------------------------
    # Blog post extraction
    # ------------------------------------------------------------------

    def _extract_blog_post(
        self,
        soup: BeautifulSoup,
        url: str,
        page_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        json_ld = self._extract_json_ld(soup)
        ld_article = None
        for item in json_ld:
            t = item.get("@type", "")
            if isinstance(t, list):
                t = " ".join(t)
            if "article" in t.lower() or "blogposting" in t.lower():
                ld_article = item
                break

        title = None
        author = None
        published_at = None
        body_html = None
        featured_image = None

        if ld_article:
            title = ld_article.get("headline") or ld_article.get("name")
            author_data = ld_article.get("author")
            if isinstance(author_data, dict):
                author = author_data.get("name")
            elif isinstance(author_data, str):
                author = author_data
            published_at = ld_article.get("datePublished")
            img = ld_article.get("image")
            if isinstance(img, str):
                featured_image = img
            elif isinstance(img, dict):
                featured_image = img.get("url")
            elif isinstance(img, list) and img:
                first = img[0]
                featured_image = first if isinstance(first, str) else first.get("url", "")

        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else page_data.get("meta_title", "Untitled")

        # Extract article body
        article_tag = soup.find("article") or soup.find(class_=re.compile(r"(post|article|entry)-?(content|body)", re.I))
        if article_tag:
            body_html = str(article_tag)
        else:
            main_tag = soup.find("main")
            if main_tag:
                body_html = str(main_tag)

        if not featured_image:
            featured_image = page_data.get("og", {}).get("og:image")

        return {
            "blog_title": "Blog",
            "title": title or "Untitled Post",
            "handle": _handle_from_url(url),
            "author": author,
            "body_html": body_html,
            "tags": "",
            "featured_image": featured_image,
            "seo_title": page_data.get("meta_title"),
            "seo_description": page_data.get("meta_description"),
            "published_at": published_at,
            "source_url": url,
        }

    # ------------------------------------------------------------------
    # Static page extraction
    # ------------------------------------------------------------------

    def _extract_static_page(
        self,
        soup: BeautifulSoup,
        url: str,
        page_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else page_data.get("meta_title", "Untitled")

        main = soup.find("main") or soup.find("article") or soup.find(id="content")
        body_html = str(main) if main else None

        return {
            "title": title or "Untitled Page",
            "handle": _handle_from_url(url),
            "body_html": body_html,
            "seo_title": page_data.get("meta_title"),
            "seo_description": page_data.get("meta_description"),
            "published": True,
            "source_url": url,
        }

    # ------------------------------------------------------------------
    # Link discovery
    # ------------------------------------------------------------------

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        links: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full = urljoin(base_url, href)
            normalized = self._normalize_url(full)
            if self._is_same_domain(normalized) and not _SKIP_EXTENSIONS.search(normalized):
                links.append(normalized)
        return links

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        # Strip fragment, keep path and query
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def _is_same_domain(self, url: str) -> bool:
        return urlparse(url).netloc == self._domain

    def _report_progress(self, done: int, total: int, url: str) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(done, total, url)
            except Exception:
                pass
        if done % 50 == 0 or done == 1:
            logger.info("Crawl progress: %d/%d — %s", done, total, url)


# ------------------------------------------------------------------
# Module-level utilities
# ------------------------------------------------------------------


def _handle_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] if path else ""


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _extract_price_from_text(text: str) -> Optional[float]:
    """Pull the first number that looks like a price from a text string."""
    match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if match:
        return _safe_float(match.group(0))
    return None
