# consum_scraper.py
# Python 3.10+  |  pip install selenium pandas

from __future__ import annotations
import re, time, urllib.parse as ul
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Callable, Iterable, Optional
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ActionChains


BASE = "https://tienda.consum.es/es"

# ---------- Selectores ----------
XPATH_MENU_BTN = "//cmp-menu-button//button | //cmp-menu-button//*[local-name()='svg' or self::button][1]"
XPATH_CATEGORY_LINKS = "//a[contains(@class,'element-list__link') and contains(@href, '/es/c/')]"

# Cards y campos dentro de cada card
XPATH_PRODUCT_CARD = "//cmp-widget-product-v2 | //cmp-widget-product"
XPATH_A_HREF = ".//a[contains(@href,'/es/p/')]"

# Paginación
XPATH_PAGINATION_CONTAINER = "//*[contains(@class,'pagination') or contains(@class,'pager')]"
XPATH_PAGINATION_NUMBERS = (
    "//nav[contains(@aria-label,'pag') or contains(translate(@aria-label,'PAG','pag'),'pag')]//a|"
    "//nav[contains(@aria-label,'pag') or contains(translate(@aria-label,'PAG','pag'),'pag')]//button|"
    "//*[contains(@class,'pagination')]//a|//*[contains(@class,'pagination')]//button|"
    "//*[contains(@class,'pagination')]//span"
)

# Botón "Siguiente" (varias variantes reales)
XPATH_NEXT_BUTTON = (
    "//a[contains(@class,'next-page') and not(contains(@class,'disabled'))] | "
    "//a[contains(@aria-label,'Siguiente') and not(contains(@class,'disabled'))] | "
    "//button[contains(@aria-label,'Siguiente') and not(@disabled)] | "
    "//a[@rel='next' and not(contains(@class,'disabled'))] | "
    "//*[name()='title' and normalize-space()='Siguiente']/ancestor::*[self::a or self::button][1]"
)

# ---------- Parámetros ----------
WAIT_PAGE = 100
WAIT_PRODUCTS = 100
SLEEP_BETWEEN_PAGES = 0.02
MAX_PAGES_CAP = 200
TIME_SLEEP = 2.5

# ---------- Utils ----------
def _chrome_driver(headless: bool = True) -> webdriver.Chrome:
    o = Options()
    if headless: o.add_argument("--headless=new")
    o.add_argument("--window-size=1400,1000")
    o.add_argument("--disable-gpu"); o.add_argument("--no-sandbox"); o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--lang=es-ES")
    o.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    o.page_load_strategy = "eager"
    return webdriver.Chrome(options=o)


_num = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)|\d+,\d+|\d+(?:\.\d+)?)")
def _first_num(t: str) -> Optional[float]:
    if not t: return None
    m = _num.search(t.replace("\xa0"," "))
    if not m: return None
    val = m.group(1).replace(".","").replace(",",".")
    try: return float(val)
    except: return None

def _js_scroll_bottom(drv): drv.execute_script("window.scrollTo(0, 10000);")

def _get_page_param(url: str) -> int:
    try:
        v = ul.parse_qs(ul.urlparse(url).query).get("page", ["1"])[0]
        return int(v) if str(v).isdigit() else 1
    except: return 1

def _ensure_orderby(url: str) -> str:
    if "orderById=" in url: return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}orderById=5"

def _with_page(url: str, page: int) -> str:
    parsed = ul.urlparse(url)
    qs = dict(ul.parse_qsl(parsed.query, keep_blank_values=True))
    qs["page"] = str(page)
    new_query = ul.urlencode(qs)
    return ul.urlunparse(parsed._replace(query=new_query))

def _page1(url: str) -> str:
    return _with_page(_ensure_orderby(url.split("?")[0]), 1)

def _first_product_href_on_page(drv) -> str:
    try:
        a = drv.find_elements(By.XPATH, XPATH_A_HREF)
        if a:
            return (a[0].get_attribute("href") or "").split("?")[0]
    except Exception:
        pass
    return ""

def _first_card_el(drv):
    try:
        cards = drv.find_elements(By.XPATH, XPATH_PRODUCT_CARD)
        return cards[0] if cards else None
    except Exception:
        return None

def _scroll_to_paginator(drv):
    try:
        conts = drv.find_elements(By.XPATH, XPATH_PAGINATION_CONTAINER)
        if conts:
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", conts[-1])
    except Exception:
        pass

def _deep_click_next_js(drv) -> bool:
    """
    Busca y clica el botón 'Siguiente' dentro de posibles shadow roots (ej. <cmp-pagination>).
    Devuelve True si se pudo clickar; False si no se encontró o estaba deshabilitado.
    """
    script = r"""
    (function(){
      function findDeep(root, matcher) {
        const hit = matcher(root);
        if (hit) return hit;
        const all = root.querySelectorAll('*');
        for (let i=0; i<all.length; i++) {
          const n = all[i];
          const h1 = matcher(n);
          if (h1) return h1;
          if (n.shadowRoot) {
            const h2 = findDeep(n.shadowRoot, matcher);
            if (h2) return h2;
          }
        }
        return null;
      }
      function isNext(el) {
        if (!el) return false;
        if (el.disabled) return false;
        const lab = ((el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent) || '').toLowerCase();
        if (lab.includes('siguiente') || lab.includes('next')) return true;
        if ((el.getAttribute('rel') || '').toLowerCase() === 'next') return true;
        const t = el.querySelector && el.querySelector('title');
        if (t && (t.textContent || '').trim().toLowerCase() === 'siguiente') return true;
        return false;
      }
      function matcher(scope){
        const zones = [
          scope, 
          scope.querySelector && scope.querySelector('cmp-pagination'),
          scope.querySelector && scope.querySelector('[class*="pagination"], [class*="pager"]'),
        ].filter(Boolean);
        for (const z of zones){
          const cand = z.querySelectorAll && z.querySelectorAll(
            'a[aria-label],button[aria-label],a[rel="next"],button[rel="next"],a[title],button[title],a.next,button.next'
          );
          if (!cand) continue;
          for (const el of cand) if (isNext(el)) return el;
        }
        return null;
      }
      const target = findDeep(document, matcher);
      if (!target) return false;
      try { target.scrollIntoView({block:'center'}); } catch(e) {}
      try {
        const opts = {bubbles:true, composed:true};
        target.dispatchEvent(new PointerEvent('pointerdown', opts));
        target.dispatchEvent(new MouseEvent('mousedown', opts));
        target.dispatchEvent(new MouseEvent('click', opts));
        return true;
      } catch(e) {
        try { target.click(); return true; } catch(e2) { return false; }
      }
    })();
    """
    try:
        return bool(drv.execute_script(script))
    except Exception:
        return False

def _click_next_page(drv, timeout: int = 12) -> bool:
    """
    Avanza usando el BOTÓN 'Siguiente' (sin forzar URL).
    Estrategia: ActionChains -> click en hijo interno -> ráfaga de eventos JS.
    Considera avance cuando:
      - Cambia el nº de cards,
      - o el primer card se vuelve 'stale',
      - o cambia el primer href de producto.
    """
    _scroll_to_paginator(drv)

    before_first_href = _first_product_href_on_page(drv)
    before_first_card = _first_card_el(drv)
    before_count = len(drv.find_elements(By.XPATH, XPATH_PRODUCT_CARD))

    # localizar el <a class="next-page">
    xp_next = "//a[contains(@class,'next-page') and not(contains(@class,'disabled'))]"
    try:
        btn = WebDriverWait(drv, 5).until(EC.element_to_be_clickable((By.XPATH, xp_next)))
    except TimeoutException:
        btns = drv.find_elements(By.XPATH, XPATH_NEXT_BUTTON)
        btn = btns[0] if btns else None

    if not btn:
        return False

    try:
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    except Exception:
        pass

    # Intento 1: click real con ActionChains
    try:
        ActionChains(drv).move_to_element(btn).pause(0.05).click().perform()
    except Exception:
        pass

    t0 = time.time()
    while time.time() - t0 < timeout/3:
        cur_count = len(drv.find_elements(By.XPATH, XPATH_PRODUCT_CARD))
        cur_first = _first_product_href_on_page(drv)
        try:
            if before_first_card is not None:
                _ = before_first_card.is_enabled()
        except Exception:
            _wait_products_present(drv); return True
        if (cur_count != before_count and cur_count > 0) or (cur_first and cur_first != before_first_href):
            _wait_products_present(drv); return True
        time.sleep(0.1)

    # Intento 2: click en hijo interno (icono)
    try:
        child = btn.find_element(By.XPATH, ".//span[contains(@class,'tol-icon-component')] | .//cmp-svg-viewer | .//*[name()='svg']")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", child)
        ActionChains(drv).move_to_element(child).pause(0.05).click().perform()
    except Exception:
        pass

    t1 = time.time()
    while time.time() - t1 < timeout/3:
        cur_count = len(drv.find_elements(By.XPATH, XPATH_PRODUCT_CARD))
        cur_first = _first_product_href_on_page(drv)
        try:
            if before_first_card is not None:
                _ = before_first_card.is_enabled()
        except Exception:
            _wait_products_present(drv); return True
        if (cur_count != before_count and cur_count > 0) or (cur_first and cur_first != before_first_href):
            _wait_products_present(drv); return True
        time.sleep(0.1)

    # Intento 3: ráfaga de eventos JS sobre el <a>
    try:
        js = """
        const el = arguments[0];
        try { el.scrollIntoView({block:'center'}); } catch(e){}
        const opts = {bubbles:true, cancelable:true, composed:true, button:0};
        el.dispatchEvent(new PointerEvent('pointerdown', opts));
        el.dispatchEvent(new MouseEvent('mousedown', opts));
        el.dispatchEvent(new MouseEvent('mouseup', opts));
        el.dispatchEvent(new MouseEvent('click', opts));
        """
        drv.execute_script(js, btn)
    except Exception:
        pass

    t2 = time.time()
    while time.time() - t2 < timeout/3:
        cur_count = len(drv.find_elements(By.XPATH, XPATH_PRODUCT_CARD))
        cur_first = _first_product_href_on_page(drv)
        try:
            if before_first_card is not None:
                _ = before_first_card.is_enabled()
        except Exception:
            _wait_products_present(drv); return True
        if (cur_count != before_count and cur_count > 0) or (cur_first and cur_first != before_first_href):
            _wait_products_present(drv); return True
        time.sleep(0.1)

    return False

# ---------- Data ----------
@dataclass
class ConsumItem:
    name: str
    brand: str
    price: Optional[float]
    price_text: str
    ppu_text: str
    image: str

# ---------- Steps ----------
def _accept_cookies(drv):
    for xp in ["//button[contains(.,'Aceptar') or contains(.,'Aceptar todas')]", "//button[@id='onetrust-accept-btn-handler']"]:
        try:
            btn = WebDriverWait(drv, 4).until(EC.element_to_be_clickable((By.XPATH, xp)))
            btn.click(); return
        except TimeoutException:
            continue

def _open_menu_and_get_categories(drv) -> List[str]:
    try:
        WebDriverWait(drv, 8).until(EC.element_to_be_clickable((By.XPATH, XPATH_MENU_BTN))).click()
    except TimeoutException:
        pass
    links = set(); t0 = time.time()
    while time.time() - t0 < 8:
        for a in drv.find_elements(By.XPATH, XPATH_CATEGORY_LINKS):
            href = (a.get_attribute("href") or "").split("?")[0]
            if "/es/c/" in href: links.add(href)
        drv.execute_script("const el=document.querySelector('.element-list__ul'); if(el) el.scrollTop=el.scrollHeight;")
    return sorted({_page1(u) for u in links})

def _wait_products_present(drv) -> bool:
    try:
        WebDriverWait(drv, WAIT_PRODUCTS).until(
            EC.presence_of_element_located((By.XPATH, XPATH_PRODUCT_CARD))
        )
        return True
    except TimeoutException:
        return False

def _scroll_until_stable(drv, log: Callable[[str],None]|None=None,
                         max_rounds=30, idle_rounds=1) -> None:
    last = 0; stagnant = 0
    cards = drv.find_elements(By.XPATH, XPATH_PRODUCT_CARD)
    cur = len(cards)
    if log: log(f"↕️ Ronda {1}: DOM={cur}")
    _js_scroll_bottom(drv)

def _parse_cards_batch_js(drv):
    script = r"""
    return Array.from(document.querySelectorAll('cmp-widget-product-v2, cmp-widget-product')).map(c=>{
      const q = s => c.querySelector(s);
      const text = n => n ? (n.textContent || "").replace(/\u00a0/g," ").replace(/\s+/g," ").trim() : "";

      // URL
      const a = q('a[href*="/es/p/"]');
      const href = a ? a.href.split("?")[0] : "";

      // Marca (varias clases posibles)
      const brand =
        text(q('.product-info-name--name p.u-size--20')) ||
        text(q('.product-info-name p.u-size'))    ||
        text(q('.product-info-name [class*="u-size"]')) ||
        "";

      // Título
      const title =
        text(q('.product-info-name--name h1.u-title-3')) ||
        text(q('div.product-info-name h1')) ||
        "";

      // Nombre final = "MARCA TÍTULO" (o texto del <a> si faltan)
      // const name = (brand ? brand + " " : "") + (title || text(a));
      const name = title;
      
      // Precio principal (texto)
      const pw = q('.product-info-price__price');
      let priceText = "";
      if (pw){
        const off = pw.querySelector('.price');
        priceText = text(off) || text(pw);
      }

      // Precio por unidad (€/kg, €/l…) – dos ubicaciones reales
      const ppu =
        text(q('lib-product-info-price .price__ppu')) ||
        text(q('.product-info-name--price'));

        // Imagen (solo la del producto, NO promos)
        let img = "";
        {
        // candidatos razonables dentro de la card
        const candidates = Array.from(
            c.querySelectorAll(
            'cmp-image picture img, picture.image-component img, img.image-component__image, img.image-component, img'
            )
        );

        for (const el of candidates) {
            // 1) descarta si está dentro de bloques de promociones
            const inPromo = el.closest('lib-product-info-promotions, .product-info-promotions, [class*="promotions"]');
            if (inPromo) continue;

            // 2) saca URL (src / data-src / srcset)
            let u = el.getAttribute('src') || el.getAttribute('data-src') || "";
            if (!u) {
            const ss = el.getAttribute('srcset') || el.getAttribute('data-srcset') || "";
            if (ss) u = ss.split(',')[0].trim().split(' ')[0]; // primer candidato de srcset
            }
            if (!u) continue;

            // 3) descarta imágenes de assets de promoción
            if (/\/assets\/promotion\//i.test(u)) continue;

            // 4) ok, nos quedamos con esta
            img = u;
            break;
        }

        // (opcional) subir resolución en CDN típico
        if (img && /\/\d{2,4}x\d{2,4}\//.test(img)) {
            img = img.replace(/\/\d{2,4}x\d{2,4}\//, '/300x300/');
        }
        }


      return { href, name, brand, title, priceText, ppu, img };
    });
    """
    return drv.execute_script(script) or []


def _read_total_pages_from_pagination(drv) -> Optional[int]:
    try:
        conts = drv.find_elements(By.XPATH, XPATH_PAGINATION_CONTAINER)
        if conts:
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", conts[-1])
        nums = []
        for el in drv.find_elements(By.XPATH, XPATH_PAGINATION_NUMBERS):
            t = (el.get_attribute("aria-label") or el.text or "").strip()
            for n in re.findall(r"\d+", t):
                try: nums.append(int(n))
                except: pass
        if nums:
            mx = max(nums)
            if mx >= 1:
                return mx
    except Exception:
        pass
    return None

def _discover_total_pages(drv, cat_url_page1: str, log: Callable[[str],None]|None=None) -> int:
    drv.get(cat_url_page1); time.sleep(TIME_SLEEP); _accept_cookies(drv)
    total = _read_total_pages_from_pagination(drv)
    if total:
        return min(total, MAX_PAGES_CAP)
    pages = 1
    while pages < MAX_PAGES_CAP:
        nxt = _with_page(cat_url_page1, pages + 1)
        drv.get(nxt); time.sleep(TIME_SLEEP)
        if not _wait_products_present(drv):
            break
        pages += 1
        if log: log(f"➡️ Detectada página {pages}")
    return pages

def _scrape_category(drv, cat_url: str, log: Callable[[str],None]|None=None) -> List[ConsumItem]:
    cat_url_p1 = _page1(cat_url)
    total_pages = _discover_total_pages(drv, cat_url_p1, log)
    if total_pages == 0:
        if log: log("⛔ Sin productos en page=1. Siguiente categoría.")
        return []

    if log: log(f"📄 Páginas detectadas: {total_pages}")
    items: List[ConsumItem] = []
    seen_urls: Set[str] = set()

    drv.get(_with_page(cat_url_p1, 1))
    time.sleep(TIME_SLEEP); time.sleep(TIME_SLEEP)

    for p in range(1, total_pages + 1):
        _scroll_until_stable(drv, log)
        cards = drv.find_elements(By.XPATH, XPATH_PRODUCT_CARD)
        if log: log(f"✅ Página {p}/{total_pages}: DOM={len(cards)}")

        rows = _parse_cards_batch_js(drv)
        for r in rows:
            u = (r.get("href") or "")
            if not u or u in seen_urls: 
                continue
            seen_urls.add(u)
            items.append(ConsumItem(
                name=r.get("name") or "",
                brand=r.get("brand") or "",
                price=_first_num((r.get("priceText") or "").replace("\xa0"," ")),
                price_text=r.get("priceText") or "",
                ppu_text=r.get("ppu") or "",
                image=r.get("img") or ""
            ))

        if p < total_pages:
            ok = _click_next_page(drv, timeout=WAIT_PAGE)
            if not ok:
                if log: log("⛔ No avanzó con 'Siguiente'. Corto categoría.")
                break
            time.sleep(SLEEP_BETWEEN_PAGES)

    return items

# ---------- API pública ----------
def scrape_consum(headless: bool = True,
                  out_csv: Optional[str] = None,
                  limit_categories: Optional[int] = None,
                  categories: Optional[Iterable[str]] = None,
                  progress: Optional[Callable[[str], None]] = print) -> pd.DataFrame:
    drv = _chrome_driver(headless=headless)
    rows: List[Dict] = []
    try:
        drv.get(BASE); _accept_cookies(drv)
        cats = list(categories) if categories else _open_menu_and_get_categories(drv)
        if progress: progress(f"📂 Categorías detectadas: {len(cats)}")
        if limit_categories: cats = cats[:limit_categories]

        for i, cat in enumerate(cats, 1):
            if progress: progress(f"\n---- [{i}/{len(cats)}] {cat} ----")
            try:
                items = _scrape_category(drv, cat, log=progress)
                rows.extend([asdict(x) for x in items])
                if progress: progress(f"🧺 {len(items)} productos")
            except Exception as e:
                if progress: progress(f"⚠️ Error en {cat}: {e}")
    finally:
        drv.quit()

    df = pd.DataFrame(rows)
    if not df.empty:
        cols = ["name","brand","price","price_text","ppu_text","image"]
        df = df.reindex(columns=cols)
        if out_csv:
            df.to_csv(out_csv, index=False, encoding="utf-8-sig")
            if progress: progress(f"\n✅ Guardado: {out_csv} ({len(df)} filas)")
    else:
        if progress: progress("\n⚠️ No se capturaron productos.")
    return df
