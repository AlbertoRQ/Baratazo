from typing import Optional
from sqlmodel import SQLModel, Field

class Producto(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    price_unit: float
    price_kg: float
    image: Optional[str] = None
    store: str
