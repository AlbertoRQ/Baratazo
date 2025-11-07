from pathlib import Path
from sqlmodel import SQLModel, create_engine
import os

# Permite override por variable de entorno si quieres (opcional)
ENV_DB = os.getenv("BARATAZO_DB")

if ENV_DB:
    db_path = Path(ENV_DB)
else:
    # RUTA ABSOLUTA A TU BD FUERA DE pagina_web
    db_path = Path(r"C:/Users/alber/OneDrive/Desktop/Proyectos/Baratazo/db/baratazo.db")

# Asegura el esquema sqlite:/// + path POSIX
DB_URL = f"sqlite:///{db_path.as_posix()}"

engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

def init_db():
    # No borra nada; solo crea la tabla si no existe
    from .models import Producto
    SQLModel.metadata.create_all(engine)
