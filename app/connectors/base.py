"""Abstract base class for all platform connectors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseConnector(ABC):
    """Base connector defining the interface for all platform data extractors."""

    def __init__(
        self,
        store_url: str,
        api_key: str = "",
        api_secret: str = "",
        access_token: str = "",
    ):
        self.store_url = store_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token

    @abstractmethod
    async def test_connection(self) -> bool:
        """Verify the connection credentials are valid."""
        ...

    @abstractmethod
    async def fetch_products(self) -> List[Dict[str, Any]]:
        """Fetch all products with variants, images, and metafields."""
        ...

    @abstractmethod
    async def fetch_collections(self) -> List[Dict[str, Any]]:
        """Fetch all collections with associated product handles."""
        ...

    @abstractmethod
    async def fetch_pages(self) -> List[Dict[str, Any]]:
        """Fetch all static/CMS pages."""
        ...

    @abstractmethod
    async def fetch_blogs(self) -> List[Dict[str, Any]]:
        """Fetch all blog posts."""
        ...

    @abstractmethod
    async def fetch_redirects(self) -> List[Dict[str, Any]]:
        """Fetch all URL redirects."""
        ...

    async def fetch_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch every resource type and return a unified dict."""
        return {
            "products": await self.fetch_products(),
            "collections": await self.fetch_collections(),
            "pages": await self.fetch_pages(),
            "blogs": await self.fetch_blogs(),
            "redirects": await self.fetch_redirects(),
        }
