import os, sys
from pathlib import Path
from sqlalchemy import inspect

# 1) Fuerza la ruta exacta del .db
DB_FILE = r"C:\Users\alber\OneDrive\Desktop\Proyectos\Baratazo\db\baratazo.db"
os.environ["BARATAZO_DB"] = DB_FILE
Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)

# 2) Asegura que Python ve tu proyecto
sys.path.insert(0, r"C:\Users\alber\OneDrive\Desktop\Proyectos\Baratazo")

# 3) Crea tablas
from pagina_web.db import init_db, engine, DB_URL
from pagina_web.models import Product, Category, ProductCategory  # <- IMPORTANTE para create_all
init_db()

# 4) Comprueba
print(" ")
print("DB_URL ->", DB_URL)
print("DB existe ->", Path(DB_FILE).exists(), DB_FILE)
insp = inspect(engine)
print("Tablas ->", insp.get_table_names())
print(" ")
