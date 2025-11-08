# guardar_mercadona.py
import pandas as pd
import numpy as np
from sqlmodel import Session
from sqlalchemy import text

from pagina_web.db import engine
from pagina_web.models import (
    Product, Category, ProductCategory,
    make_product_id, make_category_id
)

STORE = "Mercadona"

def _col_or(df: pd.DataFrame, name: str, default_value):
    """Devuelve df[name] si existe; si no, una Series llena con default_value."""
    if name in df.columns:
        return df[name]
    return pd.Series([default_value] * len(df), index=df.index)

def reload_mercadona(df_mercadona: pd.DataFrame):
    # --- 1) Normaliza DF de entrada (columnas opcionales seguras) ---
    # price_per_kg_or_l_or_unit fallback a price_per_kg_or_l; si ninguna existe -> NaN
    if "price_per_kg_or_l_or_unit" in df_mercadona.columns:
        pcol = df_mercadona["price_per_kg_or_l_or_unit"]
    elif "price_per_kg_or_l" in df_mercadona.columns:
        pcol = df_mercadona["price_per_kg_or_l"]
    else:
        pcol = pd.Series(np.nan, index=df_mercadona.index)

    df = pd.DataFrame({
        "title": df_mercadona["name"].astype(str).str.strip(),
        "store": STORE,
        "price_unit": pd.to_numeric(_col_or(df_mercadona, "price", np.nan), errors="coerce"),
        "price_kg": pd.to_numeric(pcol, errors="coerce"),
        "image": _col_or(df_mercadona, "img_url", "").fillna("").astype(str),
        "product_url": _col_or(df_mercadona, "product_url", "").fillna("").astype(str),
        "category": _col_or(df_mercadona, "section", _col_or(df_mercadona, "category", "")).fillna("").astype(str),
        "subcategory": _col_or(df_mercadona, "subcategory", "").fillna("").astype(str),
    })

    # Fallback: si no hay price_kg, usa price_unit
    df["price_kg"] = df["price_kg"].fillna(df["price_unit"])

    # --- 2) Wipe del supermercado (borra enlaces + productos de esa store) ---
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM product_category
             WHERE product_id IN (SELECT id FROM product WHERE store = :store)
        """), {"store": STORE})
        conn.execute(text("DELETE FROM product WHERE store = :store"), {"store": STORE})

    # --- 3) Inserta productos únicos (1 por title+store) ---
    df_prod = df.drop_duplicates(subset=["store", "title"], keep="first")

    inserted_p = inserted_c = linked = 0
    with Session(engine) as s:
        # Productos
        for r in df_prod.itertuples(index=False):
            pid = make_product_id(r.store, r.title)
            p = Product(
                id=pid,
                title=r.title,
                store=r.store,
                price_unit=(None if pd.isna(r.price_unit) else float(r.price_unit)),
                price_kg=(None if pd.isna(r.price_kg) else float(r.price_kg)),
                image=(r.image or None) if r.image else None,
                product_url=(r.product_url or None) if r.product_url else None,
            )
            s.add(p)
            inserted_p += 1

        s.flush()

        # Categorías + enlaces (todas las filas para multi-categoría)
        for r in df.itertuples(index=False):
            cat = (r.category or "").strip()
            sub = (r.subcategory or "").strip()
            if not (cat or sub):
                continue

            cid = make_category_id(cat, sub)
            c = s.get(Category, cid)
            if c is None:
                c = Category(id=cid, category=cat, subcategory=sub)
                s.add(c)
                inserted_c += 1

            pid = make_product_id(r.store, r.title)
            pc = ProductCategory(product_id=pid, category_id=cid)
            try:
                s.add(pc)
                s.flush()
                linked += 1
            except Exception:
                s.rollback()  # ya existía el enlace; continuar

        s.commit()

    print(f"✅ {STORE}: productos_insertados={inserted_p}, categorias_nuevas={inserted_c}, enlaces_creados={linked}")
