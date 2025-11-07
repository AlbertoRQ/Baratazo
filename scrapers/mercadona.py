# ================== MERCADONA (web nueva) – TODAS LAS SUBCATEGORÍAS ==================
# pip install -U selenium pandas
# (opcional fallback) pip install -U webdriver-manager

import re, time, pandas as pd
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, SessionNotCreatedException, WebDriverException

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

    # velocidad + estabilidad
    opts.page_load_strategy = "eager"
    prefs = {
        "profile.managed_default_content_settings.stylesheets": 1,
        "profile.managed_default_content_settings.cookies": 1,
        "profile.managed_default_content_settings.javascript": 1,
        "intl.accept_languages": "es-ES,es",
    }
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

# ---------- núcleo de extracción de productos de la página actual ----------
def _extract_all_products_on_current_page(driver, pause: float = 0.12):
    # asegurar al menos 1 tarjeta
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='product-cell']"))
    )

    # scroll agresivo hasta estabilizar nº de tarjetas
    stable, last_cnt = 0, -1
    while stable < 2:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        cnt = len(driver.find_elements(By.CSS_SELECTOR, "[data-testid='product-cell']"))
        if cnt == last_cnt:
            stable += 1
        else:
            stable = 0
            last_cnt = cnt
    driver.execute_script("window.scrollBy(0, -400)"); time.sleep(0.1)

    cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid='product-cell']")
    items = []
    for el in cards:
        try:
            name = el.find_element(By.CSS_SELECTOR, "h4.product-cell__description-name").text.strip()
            fmt = el.find_elements(By.CSS_SELECTOR, ".product-format")
            format_text = fmt[0].text.strip() if fmt else ""

            price_el = (el.find_elements(By.CSS_SELECTOR, ".product-price [aria-label]") or
                        el.find_elements(By.CSS_SELECTOR, ".product-price"))[0]
            price_label = price_el.get_attribute("aria-label") or price_el.text.strip()
            price = _num_es(price_label)

            # URL producto
            a_tag = el.find_elements(By.CSS_SELECTOR, "a.product-cell__content-link")
            product_url = a_tag[0].get_attribute("href") if a_tag else ""

            # Imagen
            img_url = ""
            img_el = el.find_elements(By.CSS_SELECTOR, ".product-cell__image-wrapper img")
            if img_el:
                img_url = (img_el[0].get_attribute("src") or img_el[0].get_attribute("data-src") or "")
                if not img_url:
                    srcset = img_el[0].get_attribute("srcset") or ""
                    if srcset:
                        try:
                            img_url = srcset.split(",")[-1].strip().split(" ")[0]
                        except Exception:
                            pass

            items.append({
                "name": name,
                "price": price,
                "price_per_unit_text": price_label,
                "format_text": format_text,
                "product_url": product_url,
                "img_url": img_url,
            })
        except Exception:
            continue

    return pd.DataFrame(items)

# ---------- scraping de TODAS las subcategorías ----------
def scrape_mercadona(
    start_category_url: str = "https://tienda.mercadona.es/categories/112",
    cp: str = "08203",
    headless: bool = True,
    load_images: bool = True,
    pause: float = 0.12,
):
    """
    Recorre todas las secciones del menú y todas sus subcategorías.
    Devuelve DataFrame con: section, subcategory, name, price, price_per_unit_text, format_text, product_url, img_url
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

        # localizar las SECCIONES (grandes)
        # intentamos en el menú lateral: items con clase similar a 'category-menu__item'
        def _get_section_elements():
            return driver.find_elements(By.CSS_SELECTOR, "[class*='category-menu'] li[class*='category-menu__item']")

        sections = _get_section_elements()
        if not sections:
            # fallback: a veces el nav es otro contenedor
            sections = driver.find_elements(By.XPATH, "//li[contains(@class,'category-menu__item')]")
        print(f"→ Secciones detectadas: {len(sections)}")

        all_rows = []

        # Recorremos por índice, re-localizando cada vez (el DOM cambia)
        sec_count = len(sections)
        for si in range(sec_count):
            sections = _get_section_elements()
            if si >= len(sections):
                break
            sec = sections[si]

            # nombre de sección
            sec_name = ""
            try:
                sec_name = (sec.find_element(By.CSS_SELECTOR, ".category-menu__header label").text.strip())
            except Exception:
                try:
                    sec_name = sec.find_element(By.CSS_SELECTOR, "label").text.strip()
                except Exception:
                    sec_name = f"Sección_{si+1}"

            # abre/colapsa con el botón cabecera si no están visibles las subcategorías
            try:
                subs_ul = sec.find_elements(By.CSS_SELECTOR, "ul")
                subs_visible = bool(subs_ul and subs_ul[0].is_displayed())
            except Exception:
                subs_visible = False
            if not subs_visible:
                try:
                    header_btn = sec.find_elements(By.CSS_SELECTOR, "button")[0]
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", header_btn)
                    header_btn.click()
                    time.sleep(0.2)
                except Exception:
                    pass

            print(f"\n=== SECCIÓN {si+1}/{sec_count}: {sec_name} ===")

            # subcategorías: botones dentro de la sección
            # clases vistas: category-item__link / category-item_link
            sub_btns = sec.find_elements(By.CSS_SELECTOR, "li[class*='category-item'] button[id]")
            if not sub_btns:
                sub_btns = sec.find_elements(By.XPATH, ".//li[contains(@class,'category-item')]//button[@id]")

            print(f"  • Subcategorías: {len(sub_btns)}")

            for bi in range(len(sub_btns)):
                # re-obtener el botón porque el DOM cambia al navegar
                sections = _get_section_elements()
                if si >= len(sections): break
                sec = sections[si]
                sub_btns = sec.find_elements(By.CSS_SELECTOR, "li[class*='category-item'] button[id]") \
                           or sec.find_elements(By.XPATH, ".//li[contains(@class,'category-item')]//button[@id]")
                if bi >= len(sub_btns): break
                btn = sub_btns[bi]

                sub_name = btn.text.strip() or f"Sub_{bi+1}"
                sub_id = btn.get_attribute("id") or ""
                print(f"    → {bi+1}/{len(sub_btns)}  {sub_name} (id={sub_id})  …click")

                # click y esperar a que salgan productos (o que cambie la URL)
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)

                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='product-cell']"))
                    )
                except TimeoutException:
                    print("      ⚠️ No aparecieron tarjetas, salto.")
                    continue

                # extraer productos de esta subcategoría
                t0 = time.time()
                df = _extract_all_products_on_current_page(driver, pause=pause)
                dt = time.time() - t0
                n = len(df)
                print(f"      ✔ {n} productos en {dt:.1f}s")

                if n:
                    df.insert(0, "subcategory", sub_name)
                    df.insert(0, "section", sec_name)
                    all_rows.append(df)

        if not all_rows:
            print("\n⚠️ No se recogieron productos.")
            return pd.DataFrame(columns=[
                "section","subcategory","name","price","price_per_unit_text","format_text","product_url","img_url"
            ])

        out = pd.concat(all_rows, ignore_index=True).drop_duplicates().reset_index(drop=True)
        print(f"\n✅ TOTAL productos: {len(out)}")
        return out

    finally:
        None
        # try:
        #     driver.quit()
        # except Exception:
        #     pass

# ======= Ejemplo de uso =======
# df = scrape_mercadona_all_categories(
#     start_category_url="https://tienda.mercadona.es/categories/112",
#     cp="08203",
#     headless=True,
#     load_images=True,   # si te importa la columna img_url; pon False para ir aún más rápido
#     pause=0.10
# )
# print(df.head(), len(df))
