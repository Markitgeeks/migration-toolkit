from __future__ import annotations

import datetime
from typing import Optional, List

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Boolean,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False, default="custom"
    )  # shopify / woocommerce / bigcommerce / magento / custom
    auth_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="crawl"
    )  # api / crawl
    api_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    api_secret: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending / crawling / completed / failed
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relationships
    products: Mapped[List[Product]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    variants: Mapped[List[Variant]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    collections: Mapped[List[Collection]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    pages: Mapped[List[Page]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    blog_posts: Mapped[List[BlogPost]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    url_records: Mapped[List[URLRecord]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    crawl_logs: Mapped[List[CrawlLog]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    handle: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compare_at_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_per_item: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    image_urls: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    seo_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    seo_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # relationships
    project: Mapped[Project] = relationship(back_populates="products")
    variants: Mapped[List[Variant]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compare_at_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inventory_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    option1_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    option1_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    option2_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    option2_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    option3_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    option3_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # relationships
    product: Mapped[Product] = relationship(back_populates="variants")
    project: Mapped[Project] = relationship(back_populates="variants")


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    handle: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    seo_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    seo_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    sort_order: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    product_handles: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # relationships
    project: Mapped[Project] = relationship(back_populates="collections")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    handle: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seo_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    seo_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # relationships
    project: Mapped[Project] = relationship(back_populates="pages")


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    blog_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    handle: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    featured_image: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    seo_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    seo_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # relationships
    project: Mapped[Project] = relationship(back_populates="blog_posts")


class URLRecord(Base):
    __tablename__ = "url_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    meta_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    redirect_to: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    page_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # product / collection / page / blog / other

    # relationships
    project: Mapped[Project] = relationship(back_populates="url_records")


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # relationships
    project: Mapped[Project] = relationship(back_populates="crawl_logs")
