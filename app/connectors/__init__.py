"""Platform connectors for the Shopify Migration Toolkit.

Usage:
    from app.connectors import get_connector

    connector = get_connector("shopify", store_url="https://my-store.myshopify.com", access_token="shpat_...")
    products = await connector.fetch_products()
"""

from .base import BaseConnector
from .shopify import ShopifyConnector
from .woocommerce import WooCommerceConnector
from .web_crawler import WebCrawlerConnector

__all__ = [
    "BaseConnector",
    "ShopifyConnector",
    "WooCommerceConnector",
    "WebCrawlerConnector",
    "get_connector",
]

_REGISTRY = {
    "shopify": ShopifyConnector,
    "woocommerce": WooCommerceConnector,
    "wordpress": WooCommerceConnector,
    "custom": WebCrawlerConnector,
    "crawl": WebCrawlerConnector,
}


def get_connector(platform: str, **kwargs) -> BaseConnector:
    """Factory: return the appropriate connector for *platform*.

    Parameters
    ----------
    platform : str
        One of ``shopify``, ``woocommerce``, ``wordpress``, ``custom``, or ``crawl``.
    **kwargs
        Forwarded to the connector constructor (``store_url``, ``api_key``, etc.).

    Raises
    ------
    ValueError
        If *platform* is not recognised.
    """
    key = platform.lower().strip()
    cls = _REGISTRY.get(key)
    if cls is None:
        supported = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown platform {platform!r}. Supported: {supported}"
        )
    return cls(**kwargs)
