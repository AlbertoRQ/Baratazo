# ================== MERCADONA (web clásica) – login 1x + varias búsquedas ==================
# Requisitos: pip install undetected-chromedriver selenium pandas

import os, time, re, pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    UnexpectedAlertPresentException,
    SessionNotCreatedException,
    WebDriverException,
)

URL_SEARCH_NEW     = "https://tienda.mercadona.es/search-results?query=atun"   # dispara modal CP
URL_CLASSIC_LOGIN  = "https://www.mercadona.es/ns/entrada.php"
URL_FRAMESET       = "https://www.telecompra.mercadona.es/ns/buscador.php"

# ----- helpers numéricos -----
def _num_es(s: str):
    if not s:
        return None
    s = str(s).replace("\xa0", " ").strip()

    # 1) número seguido de € / euros
    m = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)|\d+,\d+|\d+(?:\.\d+)?)(?=\s*(?:€|euros?))",
                  s, flags=re.I)
    if m:
        t = m.group(1)
    else:
        # 2) si no, toma el ÚLTIMO número del texto (evita el '1' de '1 kg')
        nums = re.findall(r"\d{1,3}(?:\.\d{3})*(?:,\d+)|\d+,\d+|\d+(?:\.\d+)?", s)
        if not nums:
            return None
        t = nums[-1]

    # Normaliza español -> float
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except:
        return None

# ----- helpers anti-alert/popups -----
def _dismiss_any_alerts(driver, timeout: float = 2.0) -> bool:
    """Cierra cualquier alert()/confirm() abierta; True si cerró algo."""
    try:
        WebDriverWait(driver, timeout).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        txt = alert.text
        try:
            alert.accept()
        except Exception:
            alert.dismiss()
        print(f"⚠️ Alert cerrado: {txt!r}")
        return True
    except Exception:
        return False

def _safe_get(driver, url: str, retries: int = 2, pause: float = 0.6):
    """driver.get con manejo de alerts y reintentos cortos."""
    last = None
    for _ in range(retries + 1):
        try:
            driver.get(url)
            return
        except UnexpectedAlertPresentException as e:
            last = e
            _dismiss_any_alerts(driver, timeout=1.5)
            time.sleep(pause)
        except WebDriverException as e:
            last = e
            time.sleep(pause)
    if last:
        raise last

# ----- construcción del driver (UC) -----
def _setup_driver(version_main=None, headless=False):
    # version_main se ignora a propósito: uc detecta solo la versión correcta
    opts = uc.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1366,900")
    else:
        opts.add_argument("--start-maximized")
        opts.add_argument("--window-size=1366,900")

    # Estabilidad y menos popups
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    opts.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    })

    try:
        driver = uc.Chrome(options=opts)
    except (SessionNotCreatedException, WebDriverException):
        # reintento “limpio”
        driver = uc.Chrome(options=opts)

    driver.set_page_load_timeout(60)
    driver.implicitly_wait(5)
    return driver

# ----- login una vez -----
def _login_once(driver, cp, user, password, wait=15):
    w = lambda s=wait: WebDriverWait(driver, s)

    # Abre la nueva web para disparar el CP
    _safe_get(driver, URL_SEARCH_NEW)
    _dismiss_any_alerts(driver, timeout=1.5)

    # Cookies
    try:
        w(8).until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        _dismiss_any_alerts(driver, timeout=0.8)
    except: pass

    # Código postal
    try:
        ip = w(12).until(EC.presence_of_element_located((By.XPATH, "//input[@name='postalCode']")))
        ip.clear()
        for ch in cp: ip.send_keys(ch); time.sleep(0.04)
        w(12).until(EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='postal-code-checker-button']"))).click()
        _dismiss_any_alerts(driver, timeout=1.0)
    except: pass

    # Ir a la web clásica si sale el botón
    try:
        w(8).until(EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='go-to-classic-button']"))).click()
        _dismiss_any_alerts(driver, timeout=1.0)
    except: pass

    # Asegurar página de login clásica
    if "mercadona.es/ns/" not in driver.current_url:
        _safe_get(driver, "https://www.mercadona.es/")
        _safe_get(driver, URL_CLASSIC_LOGIN)

    # Usuario/Password
    u = w().until(EC.presence_of_element_located((By.ID, "username")))
    u.clear(); u.send_keys(user)
    p = w().until(EC.presence_of_element_located((By.ID, "password")))
    p.clear(); p.send_keys(password)
    time.sleep(0.6)
    btn = w().until(EC.element_to_be_clickable((By.ID, "ImgEntradaAut")))
    try:
        btn.send_keys(Keys.SPACE)
    except Exception:
        btn.click()
    time.sleep(2)
    _dismiss_any_alerts(driver, timeout=1.5)

    # Si aparece página de error, reintento rápido
    html = driver.page_source.lower()
    if ("codigo de error" in html) or ("código de error" in html):
        _safe_get(driver, URL_CLASSIC_LOGIN)
        u = w().until(EC.presence_of_element_located((By.ID, "username")))
        u.clear(); u.send_keys(user)
        p = w().until(EC.presence_of_element_located((By.ID, "password")))
        p.clear(); p.send_keys(password)
        btn = w().until(EC.element_to_be_clickable((By.ID, "ImgEntradaAut")))
        try:
            btn.send_keys(Keys.SPACE)
        except Exception:
            btn.click()
        time.sleep(1.8)
        _dismiss_any_alerts(driver, timeout=1.5)

# ----- búsqueda en frames (sin relogin) -----
def _type_in_search_any_frame(driver, term):
    """Encuentra #busc_ref en cualquier frame y busca el término."""
    def try_here():
        try:
            inp = driver.find_element(By.ID, "busc_ref")
        except NoSuchElementException:
            try:
                inp = driver.find_element(By.NAME, "busc_ref")
            except NoSuchElementException:
                return False
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
        try: inp.clear()
        except: pass
        try:
            for ch in term: inp.send_keys(ch); time.sleep(0.04)
        except:
            inp.send_keys(term)
        inp.send_keys(Keys.ENTER)
        return True

    # DFS por frames/iframes
    def dfs(depth=0, max_depth=5):
        if depth > max_depth: return False
        if try_here(): return True
        frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
        for f in frames:
            try:
                driver.switch_to.frame(f)
                if dfs(depth+1, max_depth): return True
            except: pass
            finally:
                driver.switch_to.parent_frame()
        return False

    if "telecompra.mercadona.es/ns/" not in driver.current_url:
        _safe_get(driver, URL_FRAMESET); time.sleep(0.5)
    driver.switch_to.default_content()
    return dfs()

def _enter_results_frame(driver, wait=12):
    w = lambda s=wait: WebDriverWait(driver, s)
    driver.switch_to.default_content()
    try:
        w().until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "mainFrame")))
    except TimeoutException:
        w().until(EC.frame_to_be_available_and_switch_to_it((
            By.XPATH, "//frame[contains(@name,'main') or contains(@src,'resultado') or contains(@src,'mostrar') or contains(@src,'productos')]"
        )))
    w().until(EC.presence_of_element_located((By.XPATH, "//table[@id='TaulaLlista']//tr[td]")))

# ----- extracción de una página -----
def _extract_current_page(driver):
    driver.switch_to.default_content()
    try:
        WebDriverWait(driver, 2).until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "mainFrame")))
    except TimeoutException:
        pass

    rows = driver.find_elements(By.XPATH, "//table[@id='TaulaLlista']//tr[td]")
    out = []
    for r in rows:
        # Nombre
        name = None
        for xp in [
            ".//td[contains(@headers,'header1')]//span[normalize-space()]",
            ".//td[1]//span[normalize-space()]",
        ]:
            try:
                name = r.find_element(By.XPATH, xp).text.strip()
                if name: break
            except: pass

        # Precio €
        price_text = None
        for xp in [
            ".//span[starts-with(@id,'txtPrecio')]",
            ".//td[contains(@headers,'header2')]//span[contains(@class,'tdcenter')][normalize-space()]",
            ".//span[contains(text(),'€')]",
        ]:
            try:
                price_text = r.find_element(By.XPATH, xp).text.strip()
                if price_text: break
            except: pass
        price = _num_es(price_text)

        # €/kg (varios formatos)
        ppk_text = None
        for xp in [
            ".//span[starts-with(@id,'txtprecio_uni')]",
            ".//span[contains(@class,'precio_ud')]",
            ".//*[contains(.,'€/kg') or contains(.,'€/kilo')]",
            ".//*[contains(.,'P.N.E.')]",
            ".//*[contains(translate(.,'KG','kg'),'kg') and contains(.,'Euro')]",
        ]:
            try:
                ppk_text = r.find_element(By.XPATH, xp).text.strip()
                if ppk_text: break
            except: pass
        price_per_kg = _num_es(ppk_text)

        if name:
            out.append({
                "name": name,
                "price": price,
                "price_per_kg": price_per_kg,
                "price_per_kg_text": ppk_text
            })
    return pd.DataFrame(out).drop_duplicates().reset_index(drop=True)

# ----- siguiente página -----
def _click_next(driver):
    driver.switch_to.default_content()
    try:
        WebDriverWait(driver, 6).until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "mainFrame")))
    except TimeoutException:
        return False
    try:
        nxt = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((
            By.XPATH, "//a[@id='NEXT' or contains(@href,'Posterior') or contains(@onclick,'Posterior') or contains(.,'Página siguiente')]"
        )))
    except TimeoutException:
        return False
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", nxt)
    time.sleep(0.15)
    try: nxt.click()
    except: driver.execute_script("arguments[0].click();", nxt)
    # esperar recarga
    driver.switch_to.default_content()
    try:
        WebDriverWait(driver, 8).until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "mainFrame")))
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.XPATH, "//table[@id='TaulaLlista']//tr[td]")))
    except TimeoutException:
        pass
    return True

# ----- recolectar todas las páginas para un término -----
def _collect_all_pages(driver, max_pages=50):
    all_pages, visited = [], 0
    while True:
        visited += 1
        dfp = _extract_current_page(driver)
        all_pages.append(dfp)
        if visited >= max_pages: break
        if not _click_next(driver): break
    if not all_pages:
        return pd.DataFrame(columns=["name","price","price_per_kg", "price_per_kg_text"])
    return pd.concat(all_pages, ignore_index=True).drop_duplicates().reset_index(drop=True)

# ===================== FUNCIÓN PÚBLICA =====================
def scrape_mercadona_old(terms, user=None, password=None, cp="29009",
                     version_main=139, headless=False, max_pages=50):
    """
    terms: lista de strings a buscar (p.ej. ['leche','atun'])
    user/password: credenciales de la web clásica (si None, toma MERCADONA_USER/MERCADONA_PASS)
    Devuelve: DataFrame con todas las filas y columna 'query'.
    """
    user = user or os.getenv("MERCADONA_USER")
    password = password or os.getenv("MERCADONA_PASS")
    if not user or not password:
        raise ValueError("Faltan credenciales (user/password o variables de entorno MERCADONA_USER/MERCADONA_PASS).")

    driver = _setup_driver(version_main=version_main, headless=headless)
    try:
        # 1) Login una sola vez
        _login_once(driver, cp=cp, user=user, password=password)

        # 2) Para cada término, buscar en frames y recolectar
        dfs = []
        for term in terms:
            print(f"\n====== Buscando: {term} ======")
            ok = _type_in_search_any_frame(driver, term)
            if not ok:
                # por si han cambiado de página: ir al frameset y reintentar
                _safe_get(driver, URL_FRAMESET); time.sleep(0.5)
                _dismiss_any_alerts(driver, timeout=1.0)
                ok = _type_in_search_any_frame(driver, term)
            if not ok:
                print(f"⛔ No se pudo lanzar la búsqueda de '{term}'."); continue

            try:
                _enter_results_frame(driver)
                df_term = _collect_all_pages(driver, max_pages=max_pages)
            except Exception as e:
                print(f"⚠️ No se encontraron productos en esta búsqueda. ({e})")
                df_term = pd.DataFrame(columns=["name","price","price_per_kg", "price_per_kg_text"])
            if len(df_term):
                df_term["query"] = term
                dfs.append(df_term)
                print(f"✔ {len(df_term)} filas para '{term}'")
            else:
                print(f"ℹ️ 0 filas para '{term}'")

        if not dfs:
            return pd.DataFrame(columns=["name","price","price_per_kg", "price_per_kg_text"])

        out = pd.concat(dfs, ignore_index=True).drop_duplicates().reset_index(drop=True)

        print(f"\nTOTAL filas (todos los términos): {len(out)}")
        return out
    finally:
        # driver.quit()  # descomenta si quieres cerrar al terminar
        pass
