# ================== MERCADONA (web nueva) – TODAS LAS SUBCATEGORÍAS ==================
# pip install -U selenium pandas
# (opcional fallback) pip install -U webdriver-manager

import re, time, hashlib
import pandas as pd
from typing import Optional, Set, List, Dict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, SessionNotCreatedException, WebDriverException

# --------- CONFIG ---------
SCROLL_PAUSE = 0.10
NO_NEW_LOOPS_TO_STOP = 5       # cortar scroll cuando no salen nuevos X veces

# ---------- util ----------
def _num_es(s: Optional[str]):
    if not s: return None
    s = str(s).replace("\xa0", " ").strip()
    m = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)|\d+,\d+|\d+(?:\.\d+)?)(?=\s*(?:€|euros?))", s, flags=re.I)
    t = m.group(1) if m else (re.findall(r"\d{1,3}(?:\.\d{3})*(?:,\d+)|\d+,\d+|\d+(?:\.\d+)?", s) or [None])[-1]
    if t is None: return None
    if "," in t and "." in t: t = t.replace(".", "").replace(",", ".")
    elif "," in t:            t = t.replace(",", ".")
    try: return float(t)
    except: return None

def _build_driver(headless: bool = True, load_images: bool = True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new"); opts.add_argument("--window-size=1366,900")
    else:
        opts.add_argument("--start-maximized"); opts.add_argument("--window-size=1366,900")
    opts.page_load_strategy = "eager"
    prefs = {"intl.accept_languages": "es-ES,es"}
    if not load_images:
        prefs["profile.managed_default_content_settings.images"] = 2
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--lang=es-ES")
    try:
        driver = webdriver.Chrome(options=opts)  # Selenium Manager
    except (SessionNotCreatedException, WebDriverException):
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(0)
    return driver

# ---------- normalización y precios ----------
_NUM_RE = r"(?:\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+,\d+|\d+(?:\.\d+)?)"

def _to_float_es(s: str):
    if s is None: return None
    s = s.strip()
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s:            s = s.replace(",", ".")
    try: return float(s)
    except: return None

_W = {"mg": 0.001, "g": 1.0, "gr": 1.0, "kg": 1000.0}
_V = {"ml": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0, "lt": 1000.0}

def parse_totals_simple(format_text: str):
    """
    Regla simple:
      - Si hay 'x' => multiplica factores y usa la unidad del último tramo (como ya hacíamos).
      - Si NO hay 'x' => prioriza pares (número + unidad) de PESO/VOLUMEN; si no hay, usa unidades.
    Devuelve totales en g / ml / units.
    """
    if not format_text:
        return {"g": 0.0, "ml": 0.0, "units": 0}

    t = re.sub(r"\s+", " ", str(format_text).lower()).strip()

    def _to_float_es(s: str):
        if s is None: return None
        s = s.strip()
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try: return float(s)
        except: return None

    # mapas base
    W = {"mg": 0.001, "g": 1.0, "gr": 1.0, "kg": 1000.0}
    V = {"ml": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0, "lt": 1000.0}
    U_pat = r"(uds?|unidades?|servicios?|rollos?|latas?|botellas?|bricks?)"

    # 1) Caso con multiplicador (x/×/*) → mantenemos la lógica anterior
    if re.search(r"[x×*]", t):
        parts = re.split(r"\s*[x×*]\s*", t)
        if not parts:
            return {"g":0.0,"ml":0.0,"units":0}

        last = parts[-1]
        # elegir unidad de last priorizando peso/volumen
        m_w = re.search(rf"({_NUM_RE})\s*(mg|kg|gr?|g)\b", last)
        m_v = re.search(rf"({_NUM_RE})\s*(ml|cl|dl|lt|l)\b", last)
        base_num = unit = None
        kind = None
        if m_w and (not m_v or m_w.start() > m_v.start()):
            base_num = _to_float_es(m_w.group(1)); unit = m_w.group(2); kind = "W"
        elif m_v:
            base_num = _to_float_es(m_v.group(1)); unit = m_v.group(2); kind = "V"
        else:
            # caer a unidades si no hay peso/volumen
            m_u = re.search(rf"({_NUM_RE})\s*{U_pat}\b", last)
            if m_u:
                mult = 1.0
                for p in parts:
                    n = re.search(_NUM_RE, p)
                    if n: 
                        f = _to_float_es(n.group(0))
                        if f: mult *= f
                return {"g":0.0, "ml":0.0, "units": int(round(mult))}
            return {"g":0.0,"ml":0.0,"units":0}

        # multiplicador = producto de números en los tramos anteriores
        mult = 1.0
        for p in parts[:-1]:
            n = re.search(_NUM_RE, p)
            if n:
                f = _to_float_es(n.group(0))
                if f: mult *= f

        if kind == "W":
            return {"g": base_num * W[unit] * mult, "ml": 0.0, "units": 0}
        else:
            return {"g": 0.0, "ml": base_num * V[unit] * mult, "units": 0}

    # 2) Caso simple (sin 'x'): buscar *pares* número+unidad priorizando peso/volumen
    #   - Coger el *último* par de peso o volumen (suele ser el más específico: "botella 750 ml")
    pairs_w = list(re.finditer(rf"({_NUM_RE})\s*(mg|kg|gr?|g)\b", t))
    pairs_v = list(re.finditer(rf"({_NUM_RE})\s*(ml|cl|dl|lt|l)\b", t))

    if pairs_w or pairs_v:
        if pairs_v and (not pairs_w or pairs_v[-1].start() > pairs_w[-1].start()):
            m = pairs_v[-1]; num = _to_float_es(m.group(1)); unit = m.group(2)
            total_ml = (num or 0.0) * V[unit]
            return {"g": 0.0, "ml": total_ml, "units": 0}
        else:
            m = pairs_w[-1]; num = _to_float_es(m.group(1)); unit = m.group(2)
            total_g = (num or 0.0) * W[unit]
            return {"g": total_g, "ml": 0.0, "units": 0}

    # 3) Si no hay peso/volume, intentar unidades (uds, botellas, etc.)
    m_u = re.search(rf"({_NUM_RE})\s*{U_pat}\b", t)
    if m_u:
        num = _to_float_es(m_u.group(1)) or 0.0
        return {"g":0.0, "ml":0.0, "units": int(round(num))}

    # 4) Último recurso: si sólo hay un número suelto, asumir unidades
    m_only = re.search(_NUM_RE, t)
    if m_only:
        num = _to_float_es(m_only.group(0)) or 0.0
        return {"g":0.0, "ml":0.0, "units": int(round(num))}

    return {"g":0.0,"ml":0.0,"units":0}

def parse_price_per_from_label(price_per_unit_text: str):
    if not price_per_unit_text: return {"ppkg":None,"ppl":None,"ppunit":None}
    txt = price_per_unit_text.lower(); val = _num_es(price_per_unit_text)
    return {
        "ppkg": val if ("€/kg" in txt or "€ / kg" in txt) else None,
        "ppl":  val if ("€/l"  in txt or "€ / l"  in txt) else None,
        "ppunit": val if ("€/ud" in txt or "€/unidad" in txt) else None
    }

def compute_normalized_prices(row):
    price = row.get("price")
    fmt = (row.get("format_text") or "").strip()
    pput = (row.get("price_per_unit_text") or "").strip()
    totals = parse_totals_simple(fmt); g, ml, units = totals["g"], totals["ml"], totals["units"]
    site = parse_price_per_from_label(pput)
    price_kg = price_l = price_unit_count = None
    if price is not None:
        if g > 0:   price_kg = price * (1000.0 / g)
        if ml > 0:  price_l  = price * (1000.0 / ml)
        if units>0: price_unit_count = price / units
    if price_kg is None:         price_kg = site["ppkg"]
    if price_l is None:          price_l  = site["ppl"]
    if price_unit_count is None: price_unit_count = site["ppunit"]
    return pd.Series({
        "price_kg": price_kg, "price_l": price_l, "price_unit_count": price_unit_count,
        "total_g": g or None, "total_ml": ml or None, "total_units": units or None,
    })

def enrich_prices(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.assign(price_kg=None, price_l=None, price_unit_count=None,
                         total_g=None, total_ml=None, total_units=None)
    extra = df.apply(compute_normalized_prices, axis=1)
    out = pd.concat([df, extra], axis=1)
    for c in ["price_kg", "price_l", "price_unit_count"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").round(4)
    return out

# ---------- extractor (sin URLs) ----------
def _key_for_seen(name_full: str, price_label: str) -> str:
    return hashlib.sha1(f"{name_full}|{price_label}".encode("utf-8")).hexdigest()

def _extract_all_products_on_current_page(driver, pause: float, section: str, subcategory: str) -> pd.DataFrame:
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='product-cell']"))
    )

    seen: Set[str] = set()
    out: List[Dict] = []
    no_new_loops = 0
    cat_path = f"{section} > {subcategory}".strip(" >")

    last_scroll_y = -1
    while True:
        cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid='product-cell']")

        new_count = 0
        for el in cards:
            try:
                name_core = el.find_element(By.CSS_SELECTOR, "h4.product-cell__description-name").text.strip()
                fmt_el = el.find_elements(By.CSS_SELECTOR, ".product-format")
                format_text = fmt_el[0].text.strip() if fmt_el else ""
                name_full = (name_core + " " + format_text).strip()

                price_el = (el.find_elements(By.CSS_SELECTOR, ".product-price [aria-label]") or
                            el.find_elements(By.CSS_SELECTOR, ".product-price"))[0]
                price_label = price_el.get_attribute("aria-label") or price_el.text.strip()
                price = _num_es(price_label)

                key = _key_for_seen(name_full, price_label)
                if key in seen:
                    continue

                # imagen (opcional)
                img_url = ""
                img_el = el.find_elements(By.CSS_SELECTOR, ".product-cell__image-wrapper img")
                if img_el:
                    img_url = (img_el[0].get_attribute("src") or img_el[0].get_attribute("data-src") or "")
                    if not img_url:
                        srcset = img_el[0].get_attribute("srcset") or ""
                        if srcset:
                            try: img_url = srcset.split(",")[-1].strip().split(" ")[0]
                            except Exception: pass

                out.append({
                    "section": section,
                    "subcategory": subcategory,
                    "category_path": cat_path,
                    "name": name_full,
                    "price": price,
                    "price_per_unit_text": price_label,
                    "format_text": format_text,
                    "img_url": img_url,
                })
                seen.add(key); new_count += 1

            except Exception:
                continue

        if new_count == 0: no_new_loops += 1
        else: no_new_loops = 0
        if no_new_loops >= NO_NEW_LOOPS_TO_STOP:
            break

        try:
            driver.execute_script("window.scrollBy(0, Math.floor(window.innerHeight*0.9));")
        except Exception:
            pass
        time.sleep(pause)

        try: cur_y = driver.execute_script("return window.pageYOffset;")
        except Exception: cur_y = -1
        if cur_y == last_scroll_y:
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(pause * 1.5)
                cur_y = driver.execute_script("return window.pageYOffset;")
            except Exception:
                pass
            if cur_y == last_scroll_y:
                break
        last_scroll_y = cur_y

    return pd.DataFrame(out)

# ---------- scraping de TODAS las subcategorías ----------
def scrape_mercadona(
    start_category_url: str = "https://tienda.mercadona.es/categories/112",
    cp: str = "08203",
    headless: bool = True,
    load_images: bool = True,
    pause: float = SCROLL_PAUSE,
):
    """
    Devuelve DataFrame con columnas:
      section, subcategory, category_path, name, price, price_per_unit_text, format_text,
      img_url, price_kg, price_l, price_unit_count, total_g, total_ml, total_units
    """
    driver = _build_driver(headless=headless, load_images=load_images)
    wait = WebDriverWait(driver, 12)

    try:
        print(f"→ Abriendo {start_category_url}")
        driver.get(start_category_url)

        # cookies
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
            print("✓ Cookies aceptadas")
        except Exception:
            pass

        # modal CP
        try:
            form = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "form.postal-code-checker"))
            )
            ip = (form.find_elements(By.CSS_SELECTOR, "[data-testid='postal-code-checker-input']") or
                  form.find_elements(By.CSS_SELECTOR, "input[name='postalCode']"))[0]
            ip.clear(); ip.send_keys(cp)
            btn = (form.find_elements(By.CSS_SELECTOR, "[data-testid='postal-code-checker-button']") or
                   form.find_elements(By.CSS_SELECTOR, "button[type='button'], input[type='submit']"))[0]
            btn.click()
            WebDriverWait(driver, 15).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, "form.postal-code-checker"))
            )
            print(f"✓ CP fijado: {cp}")
        except TimeoutException:
            print("• CP ya estaba fijado")

        def _get_sections():
            secs = driver.find_elements(By.CSS_SELECTOR, "[class*='category-menu'] li[class*='category-menu__item']")
            if not secs:
                secs = driver.find_elements(By.XPATH, "//li[contains(@class,'category-menu__item')]")
            return secs

        sections = _get_sections()
        print(f"→ Secciones detectadas: {len(sections)}")

        all_rows = []
        for si in range(len(sections)):
            sections = _get_sections()
            if si >= len(sections): break
            sec = sections[si]

            try:
                sec_name = sec.find_element(By.CSS_SELECTOR, ".category-menu__header label").text.strip()
            except Exception:
                try: sec_name = sec.find_element(By.CSS_SELECTOR, "label").text.strip()
                except Exception: sec_name = f"Sección_{si+1}"

            # desplegar subcategorías si hace falta
            try:
                header_btn = (sec.find_elements(By.CSS_SELECTOR, ".category-menu__header button") or
                              sec.find_elements(By.CSS_SELECTOR, "button"))[0]
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", header_btn)
                if not sec.find_elements(By.CSS_SELECTOR, "li[class*='category-item'] button[id]"):
                    header_btn.click(); time.sleep(0.2)
            except Exception:
                pass

            print(f"\n=== SECCIÓN {si+1}/{len(sections)}: {sec_name} ===")

            sub_btns = sec.find_elements(By.CSS_SELECTOR, "li[class*='category-item'] button[id]")
            if not sub_btns:
                try:
                    header_btn = (sec.find_elements(By.CSS_SELECTOR, ".category-menu__header button") or
                                  sec.find_elements(By.CSS_SELECTOR, "button"))[0]
                    header_btn.click(); time.sleep(0.2); header_btn.click(); time.sleep(0.2)
                except Exception:
                    pass
                sub_btns = sec.find_elements(By.CSS_SELECTOR, "li[class*='category-item'] button[id]")

            print(f"  • Subcategorías: {len(sub_btns)}")

            for bi in range(len(sub_btns)):
                sections = _get_sections()
                if si >= len(sections): break
                sec = sections[si]
                sub_btns = sec.find_elements(By.CSS_SELECTOR, "li[class*='category-item'] button[id]") \
                           or sec.find_elements(By.XPATH, ".//li[contains(@class,'category-item')]//button[@id]")
                if bi >= len(sub_btns): break
                btn = sub_btns[bi]

                sub_name = btn.text.strip() or f"Sub_{bi+1}"
                sub_id = btn.get_attribute("id") or ""
                print(f"    → {bi+1}/{len(sub_btns)}  {sub_name} (id={sub_id})  …click")

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                try: btn.click()
                except Exception: driver.execute_script("arguments[0].click();", btn)

                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='product-cell']"))
                    )
                except TimeoutException:
                    print("      ⚠️ No aparecieron tarjetas, salto.")
                    continue

                t0 = time.time()
                df = _extract_all_products_on_current_page(driver, pause=pause, section=sec_name, subcategory=sub_name)
                dt = time.time() - t0
                print(f"      ✔ {len(df)} productos en {dt:.1f}s")

                if not df.empty:
                    df = enrich_prices(df)
                    all_rows.append(df)

                # -------- TEST rápido: parar tras la primera subcategoría --------
                # return pd.concat(all_rows, ignore_index=True)  # ← COMENTA para rascar todo

        if not all_rows:
            print("\n⚠️ No se recogieron productos.")
            return pd.DataFrame(columns=[
                "section","subcategory","category_path","name","price","price_per_unit_text","format_text",
                "img_url","price_kg","price_l","price_unit_count","total_g","total_ml","total_units"
            ])

        out = pd.concat(all_rows, ignore_index=True).drop_duplicates().reset_index(drop=True)
        print(f"\n✅ TOTAL productos: {len(out)}")
        return out

    finally:
        try: driver.quit()
        except Exception: pass

# ======= Ejemplo de uso =======
# df = scrape_mercadona(
#     start_category_url="https://tienda.mercadona.es/categories/112",
#     cp="08203",
#     headless=True,
#     load_images=True,
#     pause=0.10
# )
# print(df.head(), len(df))
