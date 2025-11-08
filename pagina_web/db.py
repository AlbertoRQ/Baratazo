# db.py
from pathlib import Path
from sqlmodel import SQLModel, create_engine
from sqlalchemy import event, text
import os

ENV_DB = os.getenv("BARATAZO_DB")
db_path = Path(ENV_DB) if ENV_DB else Path(r"C:\Users\alber\OneDrive\Desktop\Proyectos\Baratazo\db\baratazo.db")
DB_URL = f"sqlite:///{db_path.as_posix()}"

engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

# ✅ En engines síncronos se engancha el evento directamente al engine
def _set_sqlite_pragma(dbapi_conn, conn_record):
    # Activa claves foráneas en SQLite
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()

event.listen(engine, "connect", _set_sqlite_pragma)  # <-- en vez de engine.sync_engine

def init_db():
    from .models import Product, Category, ProductCategory
    SQLModel.metadata.create_all(engine)
    # (opcional) Refuerza índices/uniques
    with engine.begin() as conn:
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_product_store_title ON product(store, title);"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_category_sub ON category(category, subcategory);"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_product_category_pk ON product_category(product_id, category_id);"))
