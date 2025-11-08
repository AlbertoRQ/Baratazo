from typing import Optional, Dict, Any, List
from pathlib import Path

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .db import engine, init_db
from .utils import matches_query


app = FastAPI(title="Baratazo")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ========= Helpers DB =========

def _fetch_all(q: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text(q), params).mappings().all()
        return [dict(r) for r in rows]

def _fetch_one(q: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(text(q), params).mappings().first()
        return dict(row) if row else None


# ========= API auxiliar =========

@app.get("/api/stores")
def api_stores() -> List[str]:
    # >>> CAMBIO: ahora la tabla es product <<<
    qsql = "SELECT DISTINCT store FROM product ORDER BY store"
    rows = _fetch_all(qsql, {})
    return [r["store"] for r in rows]


# ========= HTML =========

@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: Optional[str] = None) -> HTMLResponse:
    items: List[Dict[str, Any]] = []

    if q and len(q.strip()) >= 2:
        # >>> CAMBIO: ahora leemos de product. Usamos ROWID para “recientes”.
        qsql = """
            SELECT 
              id,                -- TEXT PK
              title, 
              price_unit, 
              price_kg, 
              image, 
              store,
              ROWID AS _rowid    -- para ordenar “recientes” en plantilla si hiciera falta
            FROM product
            ORDER BY ROWID DESC
        """
        rows = _fetch_all(qsql, {})
        items = [r for r in rows if matches_query(r["title"], q)]

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "items": items, "q": q or ""},
    )


@app.get("/product/{product_id}", response_class=HTMLResponse)
def detail(request: Request, product_id: str) -> HTMLResponse:
    # >>> CAMBIO: id es TEXT, no rowid. Traemos también product_url por si quieres enlazar.
    qsql = """
        SELECT 
          id, title, price_unit, price_kg, image, store, product_url
        FROM product
        WHERE id = :id
    """
    product = _fetch_one(qsql, {"id": product_id})

    return templates.TemplateResponse(
        "detail.html",
        {"request": request, "product": product},
    )


# ========= API JSON =========

@app.get("/api/products")
def api_products(
    q: Optional[str] = None,
    store: Optional[str] = None,
    sort: Optional[str] = Query(default="recientes"),  # recientes | unit_asc | unit_desc | kg_asc | kg_desc
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    clauses: List[str] = []

    # filtro tienda
    if store:
        store_norm = store.strip().lower()
        if store_norm not in ("todos", "todas", "all", "0"):
            clauses.append("store = :store")
            params["store"] = store

    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    # >>> CAMBIO: tabla product y usamos ROWID para “recientes”
    qsql = f"""
        SELECT 
          id, title, price_unit, price_kg, image, store, ROWID AS _rowid
        FROM product
        {where_sql}
        ORDER BY ROWID DESC
    """
    items = _fetch_all(qsql, params)

    # filtro texto
    if q and len(q.strip()) >= 2:
        items = [it for it in items if matches_query(it["title"], q)]

    # helpers precio
    def _as_float(value: Any, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except Exception:
            return default

    def _price_for(it: Dict[str, Any], primary: str, secondary: str, default: float) -> float:
        v = it.get(primary)
        if v is None or v == 0:
            v = it.get(secondary)
        return _as_float(v, default)

    # ordenación
    if sort == "unit_asc":
        items.sort(key=lambda it: _price_for(it, "price_unit", "price_kg", 1e12))
    elif sort == "unit_desc":
        items.sort(key=lambda it: _price_for(it, "price_unit", "price_kg", -1.0), reverse=True)
    elif sort == "kg_asc":
        items.sort(key=lambda it: _price_for(it, "price_kg", "price_unit", 1e12))
    elif sort == "kg_desc":
        items.sort(key=lambda it: _price_for(it, "price_kg", "price_unit", -1.0), reverse=True)
    else:  # recientes
        items.sort(key=lambda it: it.get("_rowid", 0), reverse=True)

    # Limpia la clave interna si no quieres exponerla
    for it in items:
        it.pop("_rowid", None)

    return items
