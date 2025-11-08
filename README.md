# Baratazo 🛒
Proyecto personal para comparar precios de supermercados (Mercadona, Bonpreu, Consum, etc.) usando scrapers en Python, una base de datos SQLite y una web sencilla.

---

## 1. Lanzar la web
Lanzar la web con Uvicorn desde el path del proyecto:
```bash
uvicorn pagina_web.app:app --reload
```

Abrir en el navegador:
```bash
http://127.0.0.1:8000
```

---

## 2. Requisitos rápidos
```bash
pip install fastapi "uvicorn[standard]" jinja2 sqlmodel sqlalchemy pandas selenium webdriver-manager
```
> Usa Chrome/Chromium. Selenium Manager lo detecta automáticamente.

---

## 3. Estructura mínima
```
Baratazo/
├─ pagina_web/          # FastAPI + plantillas + DB init
│  ├─ app.py
│  ├─ db.py             # init_db() crea tablas si no existen
│  ├─ models.py         # product, category, product_category
│  ├─ utils.py
│  └─ templates/        # base.html, index.html, detail.html
├─ scrapers/
│  ├─ mercadona.py
│  ├─ bonpreu.py
│  └─ consum.py
├─ scripts/
│  └─ guardar_mercadona.py  # reload_mercadona(df)
└─ db/                  # baratazo.db (se crea aquí)
```

---

## 4. Base de datos (ruta y creación)
Configura la ruta y crea las tablas:
```python
import os, pathlib
ROOT = r"C:\Users\alber\OneDrive\Desktop\Proyectos\Baratazo"
os.environ["BARATAZO_DB"] = fr"{ROOT}\db\baratazo.db"
pathlib.Path(fr"{ROOT}\db").mkdir(parents=True, exist_ok=True)

from pagina_web.db import init_db
init_db()  # crea product, category, product_category
```

**Esquema (resumen):**
- `product(id TEXT PK, title, store, price_unit, price_kg, image, product_url)`
- `category(id TEXT PK, category, subcategory)`
- `product_category(product_id, category_id)` (N:N)

> `id` de `product` = hash estable de `store + title`. Un producto puede estar en varias categorías (relación N:N).

---

## 5. Scraper + carga (Mercadona)
```python
from scrapers.mercadona import scrape_mercadona
from scripts.guardar_mercadona import reload_mercadona

df = scrape_mercadona(cp="08203", headless=True, load_images=False, pause=0.10)
reload_mercadona(df)  # borra productos de 'Mercadona' y recarga todos
```

---

## 6. API útil
- `GET /` → buscador + tabla + lista tipo ticket  
- `GET /health` → estado  
- `GET /api/stores` → tiendas disponibles  
- `GET /api/products?q=leche&store=Mercadona&sort=kg_asc`  
  - `sort`: `recientes | unit_asc | unit_desc | kg_asc | kg_desc`  
  - “Recientes” ordena por `ROWID DESC` (SQLite)

---

## 7. Trucos rápidos
- Si editas scrapers sin reiniciar:
  ```python
  import importlib, scripts.guardar_mercadona as gm
  gm = importlib.reload(gm)
  ```
- Si faltan productos al scrapear, sube `pause` y/o pon `load_images=False`.
- Evita abrir el `.db` en un viewer mientras insertas (bloqueos).
