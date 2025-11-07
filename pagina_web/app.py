from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from .db import engine, init_db


app = FastAPI(title="Baratazo")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}

def _fetch_all(q: str, params: Dict[str, Any]):
    with engine.connect() as conn:
        rows = conn.execute(text(q), params).mappings().all()
        return [dict(r) for r in rows]

def _fetch_one(q: str, params: Dict[str, Any]):
    with engine.connect() as conn:
        row = conn.execute(text(q), params).mappings().first()
        return dict(row) if row else None
    
def _norm(s: str) -> str:
    if not s:
        return ""
    # quita tildes/ü/ñ y pasa a minúsculas
    trans = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return s.translate(trans).lower().strip()

@app.get("/api/stores")
def api_stores():
    qsql = "SELECT DISTINCT store FROM producto ORDER BY store"
    rows = _fetch_all(qsql, {})
    return [r["store"] for r in rows]



# -------- HTML --------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: Optional[str] = None):
    items = []
    if q and len(q.strip()) >= 2:
        qn = _norm(q)
        qsql = """
            SELECT rowid AS id, title, price_unit, price_kg, image, store
            FROM producto
            WHERE LOWER(
              REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(title,
              'á','a'),'é','e'),'í','i'),'ó','o'),'ú','u'),'ü','u'),'ñ','n')
            ) LIKE :q
            ORDER BY rowid DESC
            LIMIT 200
        """
        items = _fetch_all(qsql, {"q": f"%{qn}%"})
    return templates.TemplateResponse("index.html", {"request": request, "items": items, "q": q or ""})


@app.get("/product/{product_id}", response_class=HTMLResponse)
def detail(request: Request, product_id: int):
    qsql = """
        SELECT rowid AS id, title, price_unit, price_kg, image, store
        FROM producto
        WHERE rowid = :id
    """
    p = _fetch_one(qsql, {"id": product_id})
    return templates.TemplateResponse("detail.html", {"request": request, "product": p})

# -------- API --------
@app.get("/api/products")
def api_products(
    q: Optional[str] = None,
    store: Optional[str] = None,
    sort: Optional[str] = Query(default="recientes")  # recientes | unit_asc | unit_desc | kg_asc | kg_desc
):
    qn = _norm(q) if (q and len(q.strip()) >= 2) else None

    clauses = []
    params: Dict[str, Any] = {}

    if qn:
        clauses.append("""
            LOWER(
              REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(title,
              'á','a'),'é','e'),'í','i'),'ó','o'),'ú','u'),'ü','u'),'ñ','n')
            ) LIKE :q
        """)
        params["q"] = f"%{qn}%"

    if store:
        clauses.append("store = :store")
        params["store"] = store

    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    order_map = {
        "unit_asc":  "COALESCE(price_unit, 1e12) ASC",
        "unit_desc": "COALESCE(price_unit, -1) DESC",
        "kg_asc":    "COALESCE(price_kg, 1e12) ASC",
        "kg_desc":   "COALESCE(price_kg, -1) DESC",
        "recientes": "rowid DESC",
    }
    order_sql = order_map.get(sort, "rowid DESC")

    qsql = f"""
        SELECT rowid AS id, title, price_unit, price_kg, image, store
        FROM producto
        {where_sql}
        ORDER BY {order_sql}
        LIMIT 200
    """
    return _fetch_all(qsql, params)
