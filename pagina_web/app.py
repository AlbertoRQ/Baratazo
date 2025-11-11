# pagina_web/app.py
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
    qsql = "SELECT DISTINCT store FROM product ORDER BY store"
    rows = _fetch_all(qsql, {})
    return [r["store"] for r in rows]


# ========= HTML =========

@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: Optional[str] = None) -> HTMLResponse:
    # Arrancamos sin resultados; el front llama a /api/products
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "items": [], "q": (q or "")},
    )


@app.get("/product/{product_id}", response_class=HTMLResponse)
def detail(request: Request, product_id: str) -> HTMLResponse:
    qsql = """
        SELECT id, title, price_unit, price_kg, image, store, product_url
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
    store: Optional[str] = None,  # ahora puede venir "Mercadona,Bonpreu,Consum"
    sort: Optional[str] = Query(default="recientes"),  # recientes | unit_asc | unit_desc | kg_asc | kg_desc
    limit: int = Query(default=400, ge=1, le=2000),
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    clauses: List[str] = []

    # --- Filtro por tiendas (multi) ---
    # admite: "", None, "todas", "all" -> no filtra
    stores_list: List[str] = []
    if store:
        # separa por coma y limpia vacíos
        stores_list = [s.strip() for s in store.split(",") if s.strip()]
        if len(stores_list) == 1 and stores_list[0].lower() in ("todas", "todos", "all", "0"):
            stores_list = []

    if stores_list:
        ph = ", ".join(f":s{i}" for i in range(len(stores_list)))
        clauses.append(f"store IN ({ph})")
        for i, s in enumerate(stores_list):
            params[f"s{i}"] = s

    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    # Base query (usamos ROWID para “recientes” en SQLite)
    qsql = f"""
        SELECT 
          id, title, price_unit, price_kg, image, store, ROWID AS _rowid
        FROM product
        {where_sql}
        ORDER BY ROWID DESC
        LIMIT :limit
    """
    params["limit"] = limit
    items = _fetch_all(qsql, params)

    # --- Filtro por texto (mín. 2 letras) ---
    if q and len(q.strip()) >= 2:
        items = [it for it in items if matches_query(it["title"], q)]

    # Helpers de precio
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

    # --- Ordenación en memoria (ya traemos pocos gracias a LIMIT) ---
    s = (sort or "recientes").lower()
    if s == "unit_asc":
        items.sort(key=lambda it: _price_for(it, "price_unit", "price_kg", 1e12))
    elif s == "unit_desc":
        items.sort(key=lambda it: _price_for(it, "price_unit", "price_kg", -1.0), reverse=True)
    elif s == "kg_asc":
        items.sort(key=lambda it: _price_for(it, "price_kg", "price_unit", 1e12))
    elif s == "kg_desc":
        items.sort(key=lambda it: _price_for(it, "price_kg", "price_unit", -1.0), reverse=True)
    else:  # recientes
        items.sort(key=lambda it: it.get("_rowid", 0), reverse=True)

    # Limpia la clave interna
    for it in items:
        it.pop("_rowid", None)

    return items
