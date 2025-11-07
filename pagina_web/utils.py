from typing import Optional, List
import re
import unicodedata

STOPWORDS = {
    "de", "la", "el", "los", "las", "y", "en", "con", "para",
    "un", "una", "unos", "unas", "del", "al"
}


def normalize(text: Optional[str]) -> str:
    """
    Minúsculas, sin tildes, solo letras/números y espacios.
    """
    if not text:
        return ""
    text = text.lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def tokens(text: Optional[str]) -> List[str]:
    """
    Texto → lista de palabras útiles (sin stopwords, sin cosas de 1 letra).
    """
    norm = normalize(text)
    parts = norm.split()
    return [p for p in parts if p not in STOPWORDS and len(p) > 1]


def _token_match(q: str, t: str) -> bool:
    """
    Regla de emparejamiento a nivel de palabra:
    - palabras cortas (<=3): SOLO exactas  → pan ≠ panales
    - palabras largas: permite substring    → semi ⊂ semidesnatada
    """
    if len(q) <= 3:
        return q == t
    return q in t


def matches_query(title: str, query: str) -> bool:
    """
    Devuelve True si TODAS las palabras de la búsqueda aparecen en el título
    (según _token_match).

    Ejemplos:
    - "pan" NO matchea "pañales"
    - "pan" SÍ matchea "pan de molde"
    - "pan de barra" SÍ matchea "barra de pan" y NO "pan de molde"
    - "leche semidesnatada" NO matchea "leche entera"
    """
    q_tokens = tokens(query)
    if not q_tokens:
        return True

    t_tokens = tokens(title)
    if not t_tokens:
        return False

    return all(
        any(_token_match(q, t) for t in t_tokens)
        for q in q_tokens
    )
