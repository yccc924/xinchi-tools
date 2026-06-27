"""Cyberbiz 後台自動上架模組"""

import sys
import time
from pathlib import Path

# 確保 content.py 可以被 import（無論從哪個目錄執行）
_DIR = Path(__file__).parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

import browser_cookie3
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from content import product_name, product_slug, brief_description, full_description_html

ADMIN_URL       = 'https://sinchih.cyberbiz.co/admin'
NEW_PRODUCT_URL = f'{ADMIN_URL}/products/new'
DOMAIN          = 'sinchih.cyberbiz.co'


def _get_chrome_cookies() -> list[dict]:
    """從 Chrome 讀取 Cyberbiz 後台的 Cookie（不需要關閉 Chrome）。"""
    try:
        jar = browser_cookie3.chrome(domain_name=DOMAIN)
        cookies = []
        for c in jar:
            ck: dict = {
                'name':   c.name,
                'value':  c.value,
                'domain': c.domain or DOMAIN,
                'path':   c.path or '/',
            }
            if c.expires and c.expires > 0:
                ck['expires'] = float(c.expires)
            if c.secure:
                ck['secure'] = True
            cookies.append(ck)
        return cookies
    except Exception as e:
        raise RuntimeError(f'讀取 Chrome Cookie 失敗：{e}')


def list_product(
    data:        dict,
    image_path:  Path,
    price:       int,
    sequence:    int,
    on_status=None,
) -> None:
    """
    在 Cyberbiz 後台自動上架一件商品。

    data       — parse_one() 回傳的字典
                 (model, capacity, color, serial, battery, condition, warranty)
    image_path — 已渲染的商品圖片路徑（image_engine.render 輸出）
    price      — 售價（整數）
    sequence   — 今日流水號，用於產生 URL slug
    on_status  — 可選的進度回呼 (str) -> None，用於更新 UI 狀態列
    """

    def status(msg: str):
        if on_status:
            on_status(msg)

    status('讀取 Chrome Cookie…')
    cookies = _get_chrome_cookies()

    status('啟動瀏覽器…')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        context = browser.new_context(
            viewport={'width': 1440, 'height': 900},
            locale='zh-TW',
            timezone_id='Asia/Taipei',
        )
        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()

        # ── 開啟後台新增商品頁 ──────────────────────────────────────────
        status('開啟後台新增商品頁…')
        page.goto(NEW_PRODUCT_URL, timeout=30000)

        # 若被導向登入頁，等使用者手動登入（SMS 驗證碼情境）
        if 'login' in page.url.lower():
            status('⚠ 請在瀏覽器中完成登入，系統會自動繼續')
            page.wait_for_url(f'**products/new**', timeout=120000)

        page.wait_for_load_state('networkidle', timeout=20000)

        # ── 1. 商品名稱 ─────────────────────────────────────────────────
        status('填寫商品名稱…')
        name = product_name(data)
        _fill_first(page, [
            'input[name="product[title]"]',
            '#product_title',
            'input[placeholder*="商品名稱"]',
        ], name)

        # ── 2. 商品網址 slug ────────────────────────────────────────────
        status('填寫商品網址…')
        slug = product_slug(sequence)
        _fill_first(page, [
            'input[name="product[handle]"]',
            '#product_handle',
            'input[placeholder*="網址"]',
        ], slug)

        # ── 3. 商品簡述 ─────────────────────────────────────────────────
        status('填寫商品簡述…')
        brief = brief_description(data)
        _fill_first(page, [
            'textarea[name="product[brief_description]"]',
            'textarea[name="product[description_short]"]',
            '#product_brief_description',
            'textarea[placeholder*="簡述"]',
        ], brief, optional=True)

        # ── 4. 上傳商品圖片 ─────────────────────────────────────────────
        status('上傳商品圖片…')
        _upload_image(page, image_path)

        # ── 5. 商品售價 ─────────────────────────────────────────────────
        status('填寫商品售價…')
        _fill_first(page, [
            'input[name="variant[price]"]',
            'input[name="product[variants][0][price]"]',
            '#price',
            'input[placeholder*="售價"]',
        ], str(price))

        # ── 6. 先儲存（取得商品 ID 後才能操作描述頁） ─────────────────
        status('儲存商品（第一次）…')
        _click_save(page)

        # ── 7. 商品介紹 HTML（CKEditor 源碼模式） ─────────────────────
        status('填入商品介紹 HTML…')
        html_content = full_description_html(data)
        _fill_ckeditor(page, html_content)

        # ── 8. 最終儲存 ─────────────────────────────────────────────────
        status('最終儲存…')
        _click_save(page)

        time.sleep(1)
        browser.close()

    status('完成')


# ─── 工具函式 ────────────────────────────────────────────────────────────────

def _fill_first(page, selectors: list[str], value: str, optional: bool = False) -> bool:
    """依序嘗試選擇器，找到第一個存在的欄位並填入值。"""
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() > 0 and loc.is_visible(timeout=1000):
                loc.fill(value)
                return True
        except Exception:
            continue
    if not optional:
        raise RuntimeError(f'找不到欄位，已嘗試：{selectors}')
    return False


def _upload_image(page, image_path: Path) -> None:
    """嘗試多種方式觸發圖片上傳。"""
    # 方法 A：直接找 file input
    file_input = page.locator('input[type="file"][accept*="image"], input[type="file"]').first
    if file_input.count() > 0:
        try:
            file_input.set_input_files(str(image_path))
            time.sleep(2)
            return
        except Exception:
            pass

    # 方法 B：點擊上傳按鈕觸發 file chooser
    upload_triggers = [
        'button:has-text("上傳")',
        'button:has-text("新增圖片")',
        'button:has-text("Add image")',
        '.product-image-upload button',
        '[data-image-upload]',
    ]
    for sel in upload_triggers:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible(timeout=500):
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    loc.click()
                fc_info.value.set_files(str(image_path))
                time.sleep(2)
                return
            except Exception:
                continue

    raise RuntimeError('找不到圖片上傳按鈕，請手動上傳圖片')


def _click_save(page) -> None:
    """點擊儲存按鈕並等待網路靜止。"""
    save_selectors = [
        'button[name="commit"]:has-text("儲存")',
        'button[type="submit"]:has-text("儲存")',
        'input[type="submit"][value="儲存"]',
        'button:has-text("儲存草稿")',
        'button:has-text("Save")',
    ]
    for sel in save_selectors:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible(timeout=1000):
            loc.click()
            try:
                page.wait_for_load_state('networkidle', timeout=20000)
            except PWTimeout:
                pass
            return
    raise RuntimeError('找不到儲存按鈕')


def _fill_ckeditor(page, html: str) -> None:
    """透過 CKEditor 4 源碼模式填入 HTML。"""
    # 方法 A：使用 CKEditor JS API（最可靠）
    try:
        result = page.evaluate("""
            (html) => {
                if (typeof CKEDITOR === 'undefined') return false;
                var keys = Object.keys(CKEDITOR.instances);
                if (keys.length === 0) return false;
                CKEDITOR.instances[keys[0]].setData(html);
                return true;
            }
        """, html)
        if result:
            time.sleep(0.5)
            return
    except Exception:
        pass

    # 方法 B：點擊 Source 按鈕切換源碼模式，再填入 textarea
    try:
        source_btn = None
        for sel in ['a.cke_button__source', '.cke_button__source',
                    'a[title="Source"]', 'a[title="源碼"]']:
            loc = page.locator(sel).first
            if loc.count() > 0:
                source_btn = loc
                break

        if source_btn is None:
            raise RuntimeError('找不到 CKEditor Source 按鈕')

        source_btn.click()
        time.sleep(0.5)

        src_area = page.locator('textarea.cke_source').first
        if src_area.count() > 0:
            src_area.fill(html)
        else:
            raise RuntimeError('找不到 CKEditor 源碼 textarea')

        # 切回 WYSIWYG
        source_btn.click()
        time.sleep(0.3)
        return

    except Exception as e:
        raise RuntimeError(f'CKEditor 填入失敗：{e}')
