# models.py
from __future__ import annotations
from typing import Optional
from uuid import uuid5, NAMESPACE_URL
import re
from sqlmodel import SQLModel, Field, UniqueConstraint


# --- helpers de IDs deterministas ---
def _norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def make_product_id(store: str, title: str) -> str:
    base = f"{_norm_text(store)}|{_norm_text(title)}"
    return str(uuid5(NAMESPACE_URL, base))  # TEXT UUID v5 estable

def make_category_id(category: str, subcategory: str) -> str:
    base = f"{_norm_text(category)}>{_norm_text(subcategory)}"
    return str(uuid5(NAMESPACE_URL, base))


# --- Tablas ---
class Product(SQLModel, table=True):
    __tablename__ = "product"
    # ID determinista (uuid v5 de store+title)
    id: str = Field(primary_key=True, default=None)
    title: str = Field(index=True)
    store: str = Field(index=True)
    price_unit: Optional[float] = None
    price_kg: Optional[float] = None
    image: Optional[str] = None
    product_url: Optional[str] = None

    # Único lógico por store+title (además del id)
    __table_args__ = (
        UniqueConstraint("store", "title", name="ux_product_store_title"),
    )


class Category(SQLModel, table=True):
    __tablename__ = "category"
    # ID determinista (uuid v5 de category>subcategory)
    id: str = Field(primary_key=True, default=None)
    category: str
    subcategory: str
    __table_args__ = (
        UniqueConstraint("category", "subcategory", name="ux_category_sub"),
    )


class ProductCategory(SQLModel, table=True):
    __tablename__ = "product_category"
    product_id: str = Field(foreign_key="product.id", primary_key=True)
    category_id: str = Field(foreign_key="category.id", primary_key=True)
