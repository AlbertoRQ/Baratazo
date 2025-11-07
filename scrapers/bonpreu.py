# ================== BONPREU – "FORMATGES I VINS" (scroll inteligente) ==================
# pip install -U selenium pandas webdriver-manager

import re, time
import pandas as pd
from typing import Optional
from collections import deque

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import SessionNotCreatedException, WebDriverException

ROOT = "https://www.compraonline.bonpreuesclat.cat/categories?source=navigation"
TARGET_SUBSTR = "formatges-i-vins"

HEADLESS = False
LOAD_IMAGES = False

PAUSE = 0.28
STABLE_ROUNDS = 6
MAX_SCROLL_STEPS = 400
SCROLL_STEP_PX = 600

def _num_es(s: Optional[str]):
    if not s:
        return None
    s = str(s).replace("\xa0", " ").replace("€", "").strip()
    m = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)|\d+,\d+|\d+(?:\.\d+)?)", s)
    if not m:
        return None
    t = m.group(1)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except:
        return None

def _build_driver(headless=True, load_images=False):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1400,1000")
    else:
        opts.add_argument("--start-maximized")
        opts.add_argument("--window-size=1400,1000")
    opts.page_load_strategy = "eager"
    prefs = {"intl.accept_languages": "es-ES,ca-ES,es"}
    if not load_images:
        prefs["profile.managed_default_content_settings.images"] = 2
        opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-notifications")
    try:
        driver = webdriver.Chrome(options=opts)
    except (SessionNotCreatedException, WebDriverException):
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(40)
    driver.implicitly_wait(0)
    return driver

def _accept_cookies(driver):
    try:
        WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()
        print("✅ Cookies aceptadas")
        time.sleep(0.4)
    except Exception:
        pass

JS_SCRAPE_VISIBLE = r"""
const cards = Array.from(
  document.querySelectorAll('div.product-card-container, [data-test="fop-card"], article[data-test="product-card"]')
);
const take = (el, sels) => { for (const s of sels){ const n = el.querySelector(s); if(n) return n; } return null; };
return cards.map(el => {
  const nameEl  = take(el, ["h3[data-test='fop-title']", "h3"]);
  const priceEl = take(el, ["[data-test='fop-price']", ".price"]);
  const ppuEl   = take(el, ["[data-test='fop-price-per-unit']", ".price-per-unit"]);
  const offerEl = take(el, ["[data-test='fop-offer-text']", ".offer"]);
  const imgEl   = take(el, ["img[data-test='lazy-load-image']", "img"]);
  const linkEl  = take(el, ["a[data-test='fop-product-link']", "a"]);
  const txt = n => (n ? (n.textContent || "").trim() : "");
  const attr = (n,a) => (n ? (n.getAttribute(a) || "").trim() : "");
  let img = attr(imgEl, "src") || attr(imgEl, "data-src") || "";
  if (!img) {
    const ss = attr(imgEl, "srcset");
    if (ss) { try { img = ss.split(",").pop().trim().split(" ")[0]; } catch(e){} }
  }
  let href = attr(linkEl, "href");
  if (href && href.startsWith("/")) href = location.origin + href;
  return {
    name: txt(nameEl),
    price_text: txt(priceEl),
    ppu_text: txt(ppuEl),
    offer: txt(offerEl),
    img_url: img,
    product_url: href,
  };
});
"""

def _get_left_sidebar_category_links(driver):
    # asegura que el sidebar se haya renderizado
    for _ in range(2):
        driver.execute_script("window.scrollBy(0, 300);"); time.sleep(0.1)
        driver.execute_script("window.scrollBy(0, -300);"); time.sleep(0.1)
    hrefs = driver.execute_script("""
        const as = Array.from(document.querySelectorAll("a[data-test='root-category-link']"));
        const out = [];
        for (const a of as) {
          const href = a.getAttribute('href') || '';
          if (!href) continue;
          try {
            const u = new URL(href, location.origin).toString();
            if (!u.endsWith('/categories')) out.push(u);
          } catch(e){}
        }
        return out;
    """)
    out, seen = [], set()
    for u in hrefs:
        if isinstance(u, str) and u not in seen:
            seen.add(u); out.append(u)
    return out

def _scroll_anywhere(driver, step=SCROLL_STEP_PX):
    """
    Estrategia múltiple: contenedor -> window -> rueda -> eventos -> tecla.
    Aumenta muchísimo la probabilidad de que el scroll ocurra.
    """
    # 1) intenta hacer focus/click en la zona principal
    try:
        el = driver.execute_script("""
            return document.querySelector('div[data-test="infinite-scroll-component"]')
                || document.querySelector('[data-test="product-list"]')
                || document.querySelector('main')
                || document.body;
        """)
        if el:
            try:
                we = driver.find_element(By.TAG_NAME, "main")
                ActionChains(driver).move_to_element_with_offset(we, 10, 10).click().perform()
            except Exception:
                ActionChains(driver).move_by_offset(10, 10).click().perform()
    except Exception:
        pass

    # 2) JS: scroll en contenedor y en window + wheel + eventos
    try:
        driver.execute_script(f"""
            const el = document.querySelector('div[data-test="infinite-scroll-component"]')
                   || document.querySelector('[data-test="product-list"]')
                   || document.querySelector('main')
                   || document.scrollingElement
                   || document.documentElement
                   || document.body;
            try {{ el.scrollBy(0, {int(step)}); }} catch(e) {{}}
            try {{ window.scrollBy(0, {int(step)}); }} catch(e) {{}}

            try {{
              const evt = new WheelEvent('wheel', {{deltaY:{int(step)}, bubbles:true, cancelable:true}});
              (el || document).dispatchEvent(evt);
              window.dispatchEvent(new Event('scroll', {{bubbles:true}}));
              window.dispatchEvent(new Event('resize', {{bubbles:true}}));
            }} catch(e) {{}}
        """)
    except Exception:
        pass

    # 3) tecla PAGE_DOWN (por si todo lo anterior es interceptado)
    try:
        ActionChains(driver).send_keys(Keys.PAGE_DOWN).perform()
    except Exception:
        pass

def _scrape_category_virtualized(url: str) -> pd.DataFrame:
    driver = _build_driver(headless=HEADLESS, load_images=LOAD_IMAGES)
    rows, seen = [], set()
    try:
        driver.get(url)
        _accept_cookies(driver)
        time.sleep(1.0)

        # Click focus al body/main antes del primer scroll
        try:
            driver.find_element(By.TAG_NAME, "body").click()
        except Exception:
            pass

        stable = 0
        steps = 0
        last_total = 0

        while stable < STABLE_ROUNDS and steps < MAX_SCROLL_STEPS:
            # raspa lo visible AHORA
            batch = driver.execute_script(JS_SCRAPE_VISIBLE)
            new_added = 0
            for b in batch:
                name = (b.get("name") or "").strip()
                if not name:
                    continue
                key = b.get("product_url") or (name, b.get("price_text", ""))
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "name": name,
                    "price": _num_es(b.get("price_text", "")),
                    "price_text": b.get("price_text", ""),
                    "price_per_unit_text": b.get("ppu_text", ""),
                    "offer": b.get("offer", ""),
                    "img_url": b.get("img_url", ""),
                    "product_url": b.get("product_url", ""),
                    "category_url": url,
                })
                new_added += 1

            total = len(rows)
            if new_added == 0 or total == last_total:
                stable += 1
            else:
                stable = 0
                last_total = total

            _scroll_anywhere(driver, SCROLL_STEP_PX)
            time.sleep(PAUSE)
            steps += 1

        df = pd.DataFrame(rows)
        if not df.empty:
            df.drop_duplicates(subset=["product_url","name","price_text"], inplace=True)
            df.reset_index(drop=True, inplace=True)
        print(f"🧮 {len(df)} productos extraídos de {url}")
        return df
    finally:
        try: driver.quit()
        except: pass

def scrape_bonpreu(headless: bool = True) -> pd.DataFrame:
    global HEADLESS
    HEADLESS = headless

    base = _build_driver(headless=HEADLESS, load_images=False)
    try:
        base.get(ROOT)
        _accept_cookies(base)
        WebDriverWait(base, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-test='root-category-link']"))
        )
        cat_urls = _get_left_sidebar_category_links(base)
    finally:
        try: base.quit()
        except: pass

    
    if not cat_urls:
        return pd.DataFrame(columns=["name","price","price_text","price_per_unit_text","offer","img_url","product_url","category_url"])

    dfs = []
    for url in cat_urls:
        df = _scrape_category_virtualized(url)
        if not df.empty: dfs.append(df)

    if dfs:
        final = pd.concat(dfs, ignore_index=True)
        final.drop_duplicates(subset=["product_url","name","price_text"], inplace=True)
    else:
        final = pd.DataFrame(columns=["name","price","price_text","price_per_unit_text","offer","img_url","product_url","category_url"])
    return final

if __name__ == "__main__":
    df = scrape_bonpreu(headless=False)  # visible para que confirmes que hace scroll
    print(df.head(10))
    print("Total productos:", len(df))
