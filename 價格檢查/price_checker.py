#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多通路電商底價全自動稽核系統 v1.0
支援平台：炘馳官網(Cyberbiz) / 蝦皮購物 / 旋轉拍賣(Carousell) / 手機王(SOGI) / FB市集
"""

import os
import re
import sys
import json
import time
import random
import shutil
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional

import requests
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Page


# ═══════════════════════════════════════════════════════════════════════════════
# 一、設定區（每次使用前，請確認以下所有參數正確）
# ═══════════════════════════════════════════════════════════════════════════════

# Excel 底價表檔名（請放在本程式同一目錄下，副檔名可省略）
EXCEL_PATH = "115-6-1二手機開價"

# Telegram Bot 設定（由整合 app 的設定頁填入，此處留空）
TG_TOKEN   = ""
TG_CHAT_ID = ""

# ── 蝦皮設定 ─────────────────────────────────────────────────────────────────
SHOPEE_SHOP_ID  = 541225412   # sin_chih 的 shop_id（固定值）

# 使用本機真實 Chrome 設定檔，繼承登入狀態 + 維持高 reCAPTCHA 分數
# 執行前必須關閉所有 Chrome 視窗，否則 Playwright 會報錯
if platform.system() == "Darwin":
    _default_chrome = Path.home() / "Library/Application Support/Google/Chrome"
elif platform.system() == "Windows":
    _default_chrome = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"
else:
    _default_chrome = Path.home() / ".config/google-chrome"

CHROME_USER_DATA_DIR = os.environ.get("CHROME_USER_DATA_DIR", str(_default_chrome))
CHROME_PROFILE       = os.environ.get("CHROME_PROFILE", "Default")

# ── 五大通路賣場網址 ──────────────────────────────────────────────────────────
# 【機制：URL 分頁 ?page=N】Cyberbiz 類 Shopify 架構，server-side rendering
CYBERBIZ_BASE_URL   = "https://www.sinchih.com.tw"
CYBERBIZ_COLLECTION = "iphone"   # 使用 iPhone 系列頁（含所有 iPhone 型號）

# 【機制：自動登入 + API response 攔截 + URL 分頁】
SHOPEE_URL          = "https://shopee.tw/sin_chih"

# 【機制：無限滾動 Infinite Scroll + JS SPA】
CAROUSELL_URL       = "https://tw.carousell.com/u/sin_chih/"

# 【機制：點擊「更多」展開 + 品牌子頁導航，多行排版】
SOGI_SHOP_URL       = "https://www.sogi.com.tw/shops/1337"

# 【機制：無限滾動，需登入，設為輔助平台，失敗自動跳過】
FB_MARKETPLACE_URL  = "https://www.facebook.com/marketplace/profile/100036514041501/"

# ── 防封鎖設定 ────────────────────────────────────────────────────────────────
MAX_PAGES  = 50   # 單一平台最大翻頁 / 滾動次數（防無限迴圈）
DELAY_MIN  = 3.0  # 每次動作最小延遲（秒）
DELAY_MAX  = 7.0  # 每次動作最大延遲（秒）

# ── 暫停／停止鉤子（由 UI 設定）──────────────────────────────────────────────
_pause_fn = None   # 由 UI 注入 threading.Event.wait
_stop_fn  = None   # 由 UI 注入，回傳 True 表示應立即停止


class _UserStopped(Exception):
    """使用者按下停止時從 _check_pause 拋出，讓 scraper 快速退出。"""


def _check_pause():
    if _stop_fn is not None and _stop_fn():
        raise _UserStopped()
    if _pause_fn is not None:
        _pause_fn()              # 暫停時阻塞於此，繼續後才往下執行
    if _stop_fn is not None and _stop_fn():
        raise _UserStopped()    # 從暫停繼續後若已是停止狀態也要退出

# 輪替 User-Agent 池（模擬不同裝置的真實瀏覽器）
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 日誌設定
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 二、工具函數
# ═══════════════════════════════════════════════════════════════════════════════

def random_delay(min_s: float = DELAY_MIN, max_s: float = DELAY_MAX) -> None:
    """隨機延遲，模擬真人操作節奏，防止被平台偵測為機器人。每 0.3 s 檢查暫停/停止。"""
    delay = random.uniform(min_s, max_s)
    log.debug(f"  延遲 {delay:.1f} 秒...")
    deadline = time.time() + delay
    while time.time() < deadline:
        _check_pause()
        time.sleep(min(0.3, max(0.0, deadline - time.time())))


def sanitize(text: str) -> str:
    """
    字串去骨清洗函數（同時適用於 Excel 商品名稱 與 網頁商品標題）。

    處理流程：
      1. 全形字元轉半形（英數符號範圍 U+FF01~FF5E）
      2. 英文字母全部轉大寫
      3. 容量單位標準化：數字後的 GB / g → G（避免影響 Galaxy/Google 等品牌詞）
      4. 移除所有非英數字符（空格、括號、破折號等全部去骨）

    範例：
      "iPhone 17  Pro  Max (256g)"         → "IPHONE17PROMAX256G"
      "Samsung Galaxy S24 Ultra 512GB"     → "SAMSUNGGALAXYS24ULTRA512G"
      "iPhone 16 Plus 128GB【售完】"        → "IPHONE16PLUS128G"
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    # 步驟 1：全形轉半形
    chars = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:   # 全形英數與符號區段
            chars.append(chr(code - 0xFEE0))
        elif code == 0x3000:            # 全形空格
            chars.append(" ")
        else:
            chars.append(ch)
    text = "".join(chars)

    # 步驟 2：英文大寫
    text = text.upper()

    # 步驟 3：容量單位標準化（先處理較長形式，再處理孤立字母）
    # 只匹配「數字 + 可選空格 + GB/TB」，不影響 GALAXY、GOOGLE 等品牌詞
    text = re.sub(r'(\d+)\s*GB', r'\1G', text)   # 256GB → 256G
    text = re.sub(r'(\d+)\s*TB', r'\1T', text)   # 1TB   → 1T
    # 孤立的 G/T：只處理數字後方的（避免影響品牌名詞）
    text = re.sub(r'(\d+)\s*G(?=[^A-Z]|$)', r'\1G', text)
    text = re.sub(r'(\d+)\s*T(?=[^A-Z]|$)', r'\1T', text)

    # 步驟 4：移除所有非英數字符
    text = re.sub(r'[^A-Z0-9]', '', text)

    return text


def parse_price(price_str) -> Optional[int]:
    """
    從任意格式的價格值中提取整數（支援 NT$25,000 / $25000 / 25,000 / 浮點數 等格式）。
    特別處理 Excel 讀出的浮點數（如 22000.0），先轉 float 再轉 int，避免去除小數點
    後位數錯誤（例：'22000.0' 若直接 re.sub 會變成 '220000'）。
    """
    if price_str is None or str(price_str).strip() in ("", "nan"):
        return None
    # 優先嘗試直接數值轉換（處理 int / float / '22000.0' 等情況）
    try:
        return int(float(str(price_str).replace(",", "")))
    except (ValueError, TypeError):
        pass
    # fallback：移除所有非數字字符
    digits = re.sub(r'[^0-9]', '', str(price_str))
    return int(digits) if digits else None


def revert_shopee_price(shopee_price: int) -> int:
    """
    蝦皮售價反推還原公式（含邊界值的累進制）。
    目的：蝦皮因手續費高，賣家會在底價上加碼，本函數將加碼還原回基礎價，
    才能與 Excel 底價進行公平比對。

    費率區間（採大於等於含邊界值的累進制）：
      NT$11,000 ~ 21,999  → 扣回 1,000
      NT$22,000 ~ 32,999  → 扣回 2,000
      NT$33,000 以上      → 扣回 3,000
      低於 NT$11,000      → 不調整
    """
    if 11000 <= shopee_price <= 21999:
        return shopee_price - 1000
    elif 22000 <= shopee_price <= 32999:
        return shopee_price - 2000
    elif shopee_price >= 33000:
        return shopee_price - 3000
    else:
        return shopee_price


# ═══════════════════════════════════════════════════════════════════════════════
# 三、Excel 底價表讀取
# ═══════════════════════════════════════════════════════════════════════════════

def load_price_table(path: str = EXCEL_PATH) -> dict:
    """
    讀取炘馳通訊「矩陣格式」Excel 底價表，回傳 { 去骨商品Key: 底價 } 字典。

    Excel 格式說明（每 2 列為一組）：
      Row N   → Col 0: iPhone 型號（如 16 Pro、16 ProMax）
                Col 1-6: 容量+條件（如 256G電80~89、256G電90~100 保內100%）
      Row N+1 → Col 0: NaN
                Col 1-6: 對應底價（若同格含多價格以空格分隔，如 29000 30000）

    底價取用規則：
    - 同一型號相同容量若有多個條件（電量/保固），取「最低價」作為底線
    - 目的：只要任一條件的最低允許價格被突破，就視為異常

    特殊處理：
    - "X / XS"：拆分為 X 和 XS 兩個型號，各自建立 key
    - "AIR"：視為 "iPhone AIR"（請注意比對說明）
    - 多價格格內含「29000 30000」：取最小值 29000 作為底線
    """
    candidates = [Path(path), Path(path + ".xlsx")]
    excel_file = next((p for p in candidates if p.exists()), None)

    if excel_file is None:
        msg = f"找不到 Excel 底價表！已嘗試路徑：{[str(p) for p in candidates]}"
        log.error(f"❌ {msg}")
        raise FileNotFoundError(msg)

    try:
        # 以 header=None 讀取，所有值當作字串，保留原始結構
        df = pd.read_excel(str(excel_file), header=None, dtype=str)
    except FileNotFoundError:
        raise
    except Exception as e:
        log.error(f"❌ Excel 讀取失敗：{e}")
        raise RuntimeError(f"Excel 讀取失敗：{e}") from e

    price_table: dict[str, int] = {}

    def _add_entry(full_model: str, floor_price: int):
        """寫入底價表，同一 key 保留較低底價。"""
        key = sanitize(full_model)
        if key:
            if key not in price_table or price_table[key] > floor_price:
                price_table[key] = floor_price

    # 從 index=1 開始（index=0 是標題列），每 2 列一組
    i = 1
    while i < len(df) - 1:
        model_row = df.iloc[i]
        price_row = df.iloc[i + 1]
        i += 2

        model_raw = str(model_row.iloc[0]).strip()
        if model_raw.lower() in ("nan", ""):
            continue

        # 處理「X / XS」類型 → 拆成多個型號
        if "/" in model_raw:
            sub_models = [m.strip() for m in model_raw.split("/")]
        else:
            sub_models = [model_raw]

        for sub_model in sub_models:
            for col in range(1, len(df.columns)):
                cap_val   = str(model_row.iloc[col]).strip()
                price_val = str(price_row.iloc[col]).strip()

                if cap_val.lower() == "nan" or price_val.lower() == "nan":
                    continue

                # 從容量欄位提取儲存容量代碼（128G / 256G / 512G / 1T 等）
                # 格式範例：256G電80~89、1T 電90~100、128G電90~100 保內100%
                m = re.search(r'(\d+)\s*([GT])(?:B)?', cap_val.upper())
                if not m:
                    continue
                storage_num  = m.group(1)
                storage_unit = m.group(2)  # G 或 T（B 在 (?:B)? 中是非捕獲）
                storage = f"{storage_num}{storage_unit}"

                # 從價格欄提取所有有效底價（同格可能有多個，如「29000 30000」）
                prices = [int(p) for p in re.findall(r'\b\d{4,6}\b', price_val.replace(',', ''))]
                if not prices:
                    continue
                floor_price = min(prices)  # 取最低價作為底線

                # 建立完整型號名（加 iPhone 前綴），寫入底價表
                full_model = f"iPhone {sub_model} {storage}"
                _add_entry(full_model, floor_price)

    log.info(f"✅ 底價表讀取完成，共 {len(price_table)} 個型號變體（來源：{excel_file.name}）。")
    return price_table


# ═══════════════════════════════════════════════════════════════════════════════
# 四、Telegram 通知
# ═══════════════════════════════════════════════════════════════════════════════

TG_MAX_LEN = 4000  # Telegram 單則訊息上限為 4096 字元，保留緩衝


def send_telegram(message: str) -> bool:
    """發送 Telegram 訊息（HTML 模式，支援超連結）。若訊息過長自動分割發送。"""
    if not TG_TOKEN or not TG_CHAT_ID:
        log.info("📱 Telegram 未設定，跳過通知。")
        return False
    api_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

    # 若訊息超過限制，分割後逐段發送
    chunks = [message[i:i+TG_MAX_LEN] for i in range(0, len(message), TG_MAX_LEN)]
    success = True
    for chunk in chunks:
        payload = {
            "chat_id": TG_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            resp = requests.post(api_url, json=payload, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.error(f"❌ Telegram 發送失敗：{e}")
            success = False
    if success:
        log.info("📱 Telegram 訊息發送成功。")
    return success


def build_alert_message(violations: list[dict]) -> str:
    """將底價破防清單組成 Telegram HTML 格式訊息（含可點擊超連結）。"""
    header = (
        f"🚨 <b>【底價破防告警】</b> 🚨\n"
        f"共發現 <b>{len(violations)}</b> 件商品低於底價，請立即修正！\n"
        f"{'─' * 30}\n"
    )
    lines = [header]
    for v in violations:
        lines.append(
            f"📌 <b>通路：</b>{v['platform']}\n"
            f"🏷 <b>商品：</b>{v['title']}\n"
            f"💰 <b>網頁售價：</b>NT${v['web_price']:,}\n"
            f"💰 <b>還原基礎價：</b>NT${v['base_price']:,}\n"
            f"⛔ <b>設定底價：</b>NT${v['floor']:,}\n"
            f"🔗 <a href=\"{v['url']}\">→ 點此前往修改上架價格</a>\n"
            f"{'─' * 30}\n"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 五、Playwright 瀏覽器工廠
# ═══════════════════════════════════════════════════════════════════════════════

def make_browser_context(pw, headless: bool = True):
    """
    建立隨機 User-Agent 的 Chromium 瀏覽器 Context。
    注入 JS 隱藏 webdriver 屬性，防止被平台偵測為自動化工具。
    """
    ua = random.choice(USER_AGENTS)
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--flag-switches-begin",
            "--disable-site-isolation-trials",
            "--flag-switches-end",
        ],
    )
    context = browser.new_context(
        user_agent=ua,
        viewport={"width": 1366, "height": 768},
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        extra_http_headers={
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    # 加強反偵測：隱藏 webdriver 標記、mock chrome 物件
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        delete navigator.__proto__.webdriver;
        if (!window.chrome) window.chrome = {runtime: {}};
        const origQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (p) =>
            p.name === 'notifications'
                ? Promise.resolve({state: Notification.permission})
                : origQuery(p);
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-TW','zh','en-US']});
    """)
    return browser, context


# ═══════════════════════════════════════════════════════════════════════════════
# 六、各平台爬蟲
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 6A. Cyberbiz（炘馳通訊官網） ─────────────────────────────────────────────
#
# 機制：URL 分頁（?page=N），Cyberbiz 類 Shopify 架構。
# 觀察：
#   - 網站採 Cyberbiz 平台建置（類 Shopify），商品列表為 SSR 靜態 HTML。
#   - 翻頁方式：/collections/all?page=1、?page=2 ...
#   - 無限滾動或 Load More 按鈕不存在於此平台。
#   - 商品卡片 class 名稱依版型而定，程式內建多組備選 selector。
#
# ─────────────────────────────────────────────────────────────────────────────

def scrape_cyberbiz(page: Page) -> list[dict]:
    """
    抓取 Cyberbiz（sinchih.com.tw）全部在售商品。

    實地確認的頁面結構（2026-06）：
      - 商品卡片 selector：.product
      - 商品連結元素：a.productClick
          data-name="IPHONE 17 PRO MAX 256GB #41695"  ← 直接讀 attribute，最可靠
          data-price="37500"                           ← 直接讀 attribute，無需解析文字
          href="/products/..."
      - 備用 title selector：p.title（class="title qk-text--center"）
      - 備用 price selector：[class*=money_tag]

    翻頁機制：?page=N，共約 520 件商品，每頁 24 件，約 22 頁。
    """
    results = []
    seen_urls: set[str] = set()   # 用來偵測 Cyberbiz 超過最後一頁後重複返回舊頁的情況
    base_url = f"{CYBERBIZ_BASE_URL}/collections/{CYBERBIZ_COLLECTION}"

    for page_num in range(1, MAX_PAGES + 1):
        _check_pause()
        url = f"{base_url}?page={page_num}"
        log.info(f"  [Cyberbiz] 第 {page_num} 頁：{url}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector(".product", timeout=10000)
        except PlaywrightTimeout:
            log.info(f"  [Cyberbiz] 第 {page_num} 頁無商品，判定為最後一頁。")
            break

        if page.locator(".product").count() == 0:
            log.info(f"  [Cyberbiz] 第 {page_num} 頁無商品，判定為最後一頁。")
            break

        new_this_page = 0
        for card in page.locator(".product").all():
            try:
                link = card.locator("a.productClick").first
                if link.count() > 0:
                    title     = link.get_attribute("data-name") or ""
                    price_str = link.get_attribute("data-price") or ""
                    href      = link.get_attribute("href") or ""
                else:
                    title     = card.locator("p.title").first.inner_text().strip() if card.locator("p.title").count() > 0 else ""
                    price_str = card.locator("[class*=money_tag]").first.inner_text().strip() if card.locator("[class*=money_tag]").count() > 0 else ""
                    href      = card.locator("a").first.get_attribute("href") or "" if card.locator("a").count() > 0 else ""

                if not href.startswith("http"):
                    href = CYBERBIZ_BASE_URL + href

                # 已見過的 URL 跳過（避免 Cyberbiz 超頁後重複返回最後一頁的舊資料）
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                if title:
                    results.append({
                        "platform": "Cyberbiz(炘馳官網)",
                        "title":    title,
                        "price_str": price_str,
                        "url":      href,
                    })
                    new_this_page += 1

            except Exception as e:
                log.debug(f"  [Cyberbiz] 解析商品失敗：{e}")
                continue

        log.info(f"  [Cyberbiz] 第 {page_num} 頁：新增 {new_this_page} 件商品。")

        # 本頁全部都是舊資料 → 已到最後一頁，Cyberbiz 在重複返回舊頁，停止
        if new_this_page == 0:
            log.info(f"  [Cyberbiz] 本頁無新商品，判定為超出末頁，停止翻頁。")
            break

        random_delay()

    log.info(f"✅ [Cyberbiz] 共抓到 {len(results)} 件商品（翻了 {page_num} 頁）。")
    return results


# ─── 6B. 蝦皮購物（Shopee） ───────────────────────────────────────────────────
#
# 機制：
#   1. 把使用者 Chrome 的 profile 資料（Cookies, Local Storage 等）同步到
#      .shopee_chrome，讓 CDP Chrome 繼承真實身份，避免被 Shopee 識別為新瀏覽器。
#   2. 用 CDP 啟動無 automation-flag 的 Chrome。
#   3. 在瀏覽器內直接導覽到 Shopee 搜尋 API URL（Chrome 自動帶 anti-bot 簽名 header），
#      讀取 JSON 回應。
#
# 前提：Chrome 已開啟並登入 shopee.tw（供 browser_cookie3 確認 session 存在）。
#

SHOPEE_CHROME_DIR = Path(os.environ.get("SHOPEE_CHROME_DIR", str(Path.home() / ".shopee_chrome")))
SHOPEE_DEBUG_PORT = int(os.environ.get("SHOPEE_DEBUG_PORT", "9222"))
CHROME_BIN        = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 從賣場頁面 DOM 提取商品連結與價格（過濾非本賣場商品用 shopid 比對）
_SHOPEE_EXTRACT_JS = """(function() {
    var results = [], seen = new Set();

    document.querySelectorAll('a[href]').forEach(function(a) {
        var m = a.href.match(/-i\\.([0-9]+)\\.([0-9]+)/);
        if (!m || seen.has(a.href)) return;
        seen.add(a.href);

        var slug = decodeURIComponent(a.href.replace(/.*shopee\\.tw\\//, '').replace(/-i\\.[0-9]+\\.[0-9]+.*/, ''));
        var name = slug.replace(/-/g, ' ').trim();

        // 往上走父層找 NT$ 價格
        // 只看「葉節點」（沒有子元素的最小單位），避免相鄰元素文字被 textContent 串接
        // 例：$6,500 緊鄰 5售出 → textContent = "$6,5005" 導致誤抓
        var price = 0;
        var cur = a.parentElement;
        for (var d = 0; d < 8 && cur && !price; d++) {
            var leaves = cur.querySelectorAll('*');
            for (var k = 0; k < leaves.length; k++) {
                var el = leaves[k];
                if (el.childElementCount > 0) continue;   // 跳過有子元素的容器
                var t = el.textContent.trim();
                var pm = t.match(/^[$＄]?([\d,]+)$/);     // 文字內容就是純數字（含逗號）
                if (!pm) continue;
                var p = parseInt(pm[1].replace(/,/g, ''));
                if (p >= 1000 && p <= 100000) { price = p; break; }
            }
            cur = cur.parentElement;
        }

        results.push({shopid: m[1], itemid: m[2], url: a.href, name: name, price: price});
    });
    return JSON.stringify(results);
})()"""


def _sync_shopee_chrome_profile():
    """
    把使用者 Chrome 的 profile 關鍵資料複製到 .shopee_chrome，
    讓 CDP Chrome 繼承真實身份（Shopee anti-bot 需要 LocalStorage 的歷史資料）。
    """
    src = Path(CHROME_USER_DATA_DIR) / CHROME_PROFILE
    dst = SHOPEE_CHROME_DIR / "Default"
    dst.mkdir(parents=True, exist_ok=True)

    for name in ("Cookies", "Local Storage", "Session Storage", "Preferences"):
        s, d = src / name, dst / name
        try:
            if s.is_file():
                shutil.copy2(str(s), str(d))
            elif s.is_dir():
                if d.exists():
                    shutil.rmtree(str(d))
                shutil.copytree(str(s), str(d))
        except Exception as exc:
            log.debug(f"  [蝦皮] 同步 {name} 失敗（{exc}），跳過。")


def _shopee_raw_cdp(debug_port: int, inject_cookies: list[dict] | None = None) -> list[dict]:
    """
    用原生 CDP WebSocket 從蝦皮賣場頁面 DOM 抓取商品。
    逐頁導覽 shopee.tw/sin_chih?page=N，用 _SHOPEE_EXTRACT_JS 提取連結，
    再用 shopid 過濾確保只收自己店的商品。
    """
    import websocket as wsclient

    try:
        tabs   = requests.get(f"http://127.0.0.1:{debug_port}/json", timeout=5).json()
        target = next(t for t in tabs if t.get("type") == "page")
        ws_url = target["webSocketDebuggerUrl"]
    except Exception as e:
        raise RuntimeError(f"CDP 連線失敗：{e}")

    ws     = wsclient.create_connection(ws_url, timeout=30)
    cmd_id = [0]

    def send(method, params=None) -> int:
        cmd_id[0] += 1
        cid = cmd_id[0]
        ws.send(json.dumps({"id": cid, "method": method,
                             **({"params": params} if params else {})}))
        return cid

    def drain(seconds: float):
        ws.settimeout(0.3)
        end = time.time() + seconds
        while time.time() < end:
            try: ws.recv()
            except wsclient.WebSocketTimeoutException: pass

    def wait_load(timeout: float = 15.0):
        ws.settimeout(1.0)
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = json.loads(ws.recv())
                if msg.get("method") == "Page.loadEventFired":
                    return
            except wsclient.WebSocketTimeoutException:
                pass

    def run_js(code: str, timeout: float = 10.0) -> str:
        eid = send("Runtime.evaluate", {"expression": code, "returnByValue": True})
        ws.settimeout(1.0)
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = json.loads(ws.recv())
            except wsclient.WebSocketTimeoutException:
                continue
            if msg.get("id") == eid:
                return msg.get("result", {}).get("result", {}).get("value", "") or ""
        return ""

    results:  list[dict] = []
    seen_ids: set[str]   = set()

    try:
        send("Network.enable")
        send("Page.enable")
        send("Network.setCacheDisabled", {"cacheDisabled": True})
        drain(0.3)

        if inject_cookies:
            send("Network.setCookies", {"cookies": inject_cookies})
            drain(0.2)
            log.info(f"  [蝦皮] 注入 {len(inject_cookies)} 個 cookie。")

        # 先暖機首頁讓 anti-bot JS 初始化，再導覽賣場頁
        log.info("  [蝦皮] 前往首頁暖機...")
        send("Page.navigate", {"url": "https://shopee.tw"})
        wait_load(10)
        time.sleep(2)

        def wait_for_items(min_count: int = 3, timeout: float = 30.0) -> bool:
            """等待 DOM 中出現足夠數量的商品連結（React 渲染完才會有）。"""
            end = time.time() + timeout
            while time.time() < end:
                val = run_js("document.querySelectorAll('a[href*=\"-i.\"]').length", timeout=3)
                try:
                    if int(val or 0) >= min_count:
                        return True
                except (ValueError, TypeError):
                    pass
                time.sleep(1)
                _check_pause()  # 每輪等待後立即檢查暫停/停止
            return False

        log.info("  [蝦皮] 前往賣場頁，分頁抓取...")
        send("Page.navigate", {"url": SHOPEE_URL})
        wait_load(15)
        time.sleep(6)   # 等 React 初次渲染

        for page_num in range(MAX_PAGES):
            _check_pause()
            # 等商品出現；若超時則重新導覽該頁再試一次
            if not wait_for_items():
                current_url = (f"{SHOPEE_URL}?page={page_num}" if page_num > 0
                               else SHOPEE_URL)
                log.info(f"  [蝦皮] 第 {page_num} 頁等待超時，重新導覽後再試一次...")
                send("Page.navigate", {"url": current_url})
                wait_load(15)
                time.sleep(6)
                if not wait_for_items():
                    log.info(f"  [蝦皮] 第 {page_num} 頁無商品（已到末頁），停止。")
                    break

            raw = run_js(_SHOPEE_EXTRACT_JS)
            try:
                dom_items = json.loads(raw) if raw else []
            except Exception:
                dom_items = []

            # 只保留本賣場的商品（shopid 比對，排除廣告/推薦）
            shop_items = [it for it in dom_items
                          if str(it.get("shopid")) == str(SHOPEE_SHOP_ID)]

            new_count = 0
            for it in shop_items:
                item_id = str(it.get("itemid", ""))
                if not item_id or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                results.append({
                    "platform":  "蝦皮購物",
                    "title":     it.get("name", "").strip(),
                    "price_str": str(it.get("price", 0)),
                    "url":       it.get("url", ""),
                })
                new_count += 1

            log.info(f"  [蝦皮] 第 {page_num} 頁：DOM {len(dom_items)} 件，"
                     f"本賣場新增 {new_count} 件，累計 {len(results)} 件。")

            if new_count == 0:
                log.info("  [蝦皮] 本頁無新商品，判定已全部載入。")
                break

            # 導覽至下一頁
            next_url = f"{SHOPEE_URL}?page={page_num + 1}"
            log.info(f"  [蝦皮] 前往第 {page_num + 1} 頁...")
            send("Page.navigate", {"url": next_url})
            wait_load(15)
            time.sleep(4)   # 等 React 重新渲染新頁面（首頁已用 6s，後續頁面 4s 即可）

    finally:
        ws.close()

    return results


def scrape_shopee(pw) -> list[dict]:  # noqa: ARG001  pw 保留供介面一致
    """
    1. browser_cookie3 確認 Chrome 蝦皮 session 存在
    2. 同步 Chrome profile 資料到 .shopee_chrome（繼承身份）
    3. CDP 啟動 Chrome → 在瀏覽器內呼叫 Shopee API → 讀取 JSON
    """
    import browser_cookie3

    try:
        raw_cookies = (list(browser_cookie3.chrome(domain_name=".shopee.tw")) +
                       list(browser_cookie3.chrome(domain_name="shopee.tw")))
    except Exception as e:
        log.warning(f"  [蝦皮] 讀取 Chrome cookie 失敗：{e}")
        return []

    if not any(c.name == "SPC_SI" for c in raw_cookies):
        log.warning("  [蝦皮] Chrome 找不到蝦皮 session，請先在 Chrome 登入 shopee.tw。")
        return []

    # 同步 Chrome profile 讓 .shopee_chrome 繼承身份
    log.info("  [蝦皮] 同步 Chrome profile 資料至 .shopee_chrome...")
    _sync_shopee_chrome_profile()

    # 準備 CDP cookie 格式
    cdp_cookies = []
    seen_names:  set[str] = set()
    for c in raw_cookies:
        if c.name in seen_names:
            continue
        seen_names.add(c.name)
        domain = c.domain if c.domain.startswith(".") else f".{c.domain}"
        entry: dict = {
            "name": c.name, "value": c.value,
            "domain": domain, "path": c.path or "/",
            "secure": bool(getattr(c, "secure", False)),
            "httpOnly": False,
        }
        if c.expires and int(c.expires) > 0:
            entry["expires"] = int(c.expires)
        cdp_cookies.append(entry)

    log.info(f"  [蝦皮] 從 Chrome 讀取 {len(cdp_cookies)} 個 cookie，啟動 CDP Chrome...")

    chrome_proc = None
    try:
        subprocess.run(["pkill", "-f", str(SHOPEE_CHROME_DIR)], capture_output=True)
        time.sleep(1)

        chrome_proc = subprocess.Popen(
            [
                CHROME_BIN,
                f"--user-data-dir={SHOPEE_CHROME_DIR}",
                "--profile-directory=Default",
                f"--remote-debugging-port={SHOPEE_DEBUG_PORT}",
                f"--remote-allow-origins=http://127.0.0.1:{SHOPEE_DEBUG_PORT}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-first-run-tabs",
                "--lang=zh-TW",
                "--disable-features=Translate",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info(f"  [蝦皮] Chrome 啟動中（port {SHOPEE_DEBUG_PORT}）...")
        time.sleep(4)

        results = _shopee_raw_cdp(SHOPEE_DEBUG_PORT, cdp_cookies)
        log.info(f"✅ [蝦皮] 共抓到 {len(results)} 件商品。")
        return results

    except _UserStopped:
        raise   # 讓停止訊號繼續往上傳，不能被吞掉
    except Exception as e:
        log.warning(f"  [蝦皮] 抓取失敗：{e}")
        return []
    finally:
        if chrome_proc:
            chrome_proc.terminate()


# ─── 6C. 旋轉拍賣（Carousell） ────────────────────────────────────────────────
#
# 機制：點擊「瀏覽更多」按鈕展開更多商品（非無限滾動）。
# 觀察：
#   - 賣家商品頁預設只顯示部分商品，需點擊「瀏覽更多」按鈕才會展開剩餘商品。
#   - 直接 HTTP 請求回傳 403，必須用 Playwright 模擬瀏覽器。
#   - 商品連結格式：/p/product-name-XXXXX
#
# ─────────────────────────────────────────────────────────────────────────────

# 「瀏覽更多」按鈕的備選 selector（依優先序嘗試）
CAROUSELL_MORE_SELECTORS = [
    "button:has-text('瀏覽更多')",
    "div[role='button']:has-text('瀏覽更多')",
    "a:has-text('瀏覽更多')",
    "button:has-text('Load more')",
    "button:has-text('See more')",
    "[data-testid='listing-card-load-more']",
]


def scrape_carousell(page: Page) -> list[dict]:
    """
    抓取旋轉拍賣（tw.carousell.com/u/sin_chih/）全部在售商品。
    策略：
      1. 等待頁面完全載入（networkidle）
      2. 滾動到底 + 偵測商品數增加（無限滾動）
      3. 若有「瀏覽更多」類按鈕則順帶點擊
    """
    results = []
    log.info(f"  [旋轉拍賣] 前往：{CAROUSELL_URL}")

    try:
        page.goto(CAROUSELL_URL, wait_until="domcontentloaded", timeout=30000)
        # networkidle 等待 SPA 完成初次渲染
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeout:
            pass
        # 等待商品連結出現
        try:
            page.wait_for_selector("a[href*='/p/']", timeout=20000)
        except PlaywrightTimeout:
            title = page.title()
            body_preview = (page.locator("body").inner_text() or "")[:200].strip()
            log.warning(f"  [旋轉拍賣] 未偵測到商品連結（頁面：{title!r}）。")
            log.warning(f"  [旋轉拍賣] 頁面內容預覽：{body_preview!r}")
        random_delay(2, 4)
    except PlaywrightTimeout:
        log.warning("  [旋轉拍賣] 頁面載入超時，嘗試繼續。")

    initial_count = page.locator("a[href*='/p/']").count()
    log.info(f"  [旋轉拍賣] 初始商品數：{initial_count}")

    # 滾動展開 + 嘗試點擊「瀏覽更多」按鈕
    no_increase_streak = 0
    prev_count = initial_count
    for scroll_i in range(MAX_PAGES):
        _check_pause()
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        random_delay(2.0, 3.5)

        # 嘗試多種「瀏覽更多」按鈕 selector（不同版本/語言）
        clicked = False
        for sel in CAROUSELL_MORE_SELECTORS:
            try:
                btn = page.locator(sel).last
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    random_delay(DELAY_MIN, DELAY_MAX)
                    clicked = True
                    break
            except Exception:
                continue

        curr_count = page.locator("a[href*='/p/']").count()
        log.info(
            f"  [旋轉拍賣] 第 {scroll_i + 1} 次{'（含點擊按鈕）' if clicked else '（滾動）'}：{prev_count} → {curr_count} 件。"
        )

        if curr_count <= prev_count:
            no_increase_streak += 1
            if no_increase_streak >= 2:
                log.info("  [旋轉拍賣] 商品數連續 2 次不再增加，判定已全部載入。")
                break
        else:
            no_increase_streak = 0
        prev_count = curr_count

    # 提取商品資料
    seen_urls: set[str] = set()
    for link in page.locator("a[href*='/p/']").all():
        try:
            href = link.get_attribute("href") or ""
            if not href:
                continue
            full_url = f"https://tw.carousell.com{href}" if href.startswith("/") else href
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            full_text = link.inner_text() or ""

            # 過濾已售出商品
            if "已售出" in full_text or "Sold" in full_text:
                continue

            # Carousell 標題通常在第一行
            lines = [ln.strip() for ln in full_text.split("\n") if ln.strip()]
            title = lines[0] if lines else (link.get_attribute("aria-label") or "")

            # 找台幣價格（格式：$25,000 或 TWD 25,000 或 NT$25,000）
            price_str = ""
            price_match = re.search(r'(?:NT\$|TWD|＄|\$)\s*([\d,]+)', full_text)
            if price_match:
                price_str = price_match.group(1)
            else:
                nums = re.findall(r'\b\d{4,6}\b', re.sub(r',', '', full_text))
                price_str = nums[0] if nums else ""

            if title:
                results.append({
                    "platform": "旋轉拍賣(Carousell)",
                    "title": title,
                    "price_str": price_str,
                    "url": full_url,
                })
        except Exception as e:
            log.debug(f"  [旋轉拍賣] 解析商品元素失敗：{e}")
            continue

    log.info(f"✅ [旋轉拍賣] 共抓到 {len(results)} 件商品。")
    return results


# ─── 6D. 手機王（SOGI） ────────────────────────────────────────────────────────
#
# 機制：品牌分頁子頁導航，每個品牌頁單頁顯示全部商品。
# 觀察（實地訪問確認）：
#   - 品牌子頁格式：/shops/1337/brands/[ID]?hall_id=1，頁面可正常訪問。
#   - 商品 HTML 結構（已確認）：
#       <a href="/shops/1337/used/178499">
#         <img ...>
#         <h3>Apple iPhone 16 Pro Max 256GB</h3>
#         <ul>
#           <li>二手價 $29,000</li>      ← 價格在第一個 <li>
#           <li>狀　態 <strong>A級</strong></li>
#           <li>更新日期 <strong>2026/06/07</strong></li>
#         </ul>
#       </a>
#   - 品牌清單上限 200 件，目前各品牌件數：
#     Apple 129 / Samsung 18 / vivo 5 / Google 3 / OPPO 3 / 小米 2 / ASUS 1 / realme 1
#   - 未偵測到分頁按鈕，推測為單頁顯示全部。
#
# ─────────────────────────────────────────────────────────────────────────────

# 硬編碼已確認的品牌子頁（從靜態 HTML 取得，確保不會因 JS 渲染遺漏）
# 若日後新增品牌，可直接在此 list 補充，格式：/shops/1337/brands/[ID]?hall_id=1
SOGI_KNOWN_BRANDS = [
    "https://www.sogi.com.tw/shops/1337/brands/116?hall_id=1",   # Apple   (129 件)
    "https://www.sogi.com.tw/shops/1337/brands/22?hall_id=1",    # SAMSUNG  (18 件)
    "https://www.sogi.com.tw/shops/1337/brands/5603?hall_id=1",  # vivo      (5 件)
    "https://www.sogi.com.tw/shops/1337/brands/4041?hall_id=1",  # Google    (3 件)
    "https://www.sogi.com.tw/shops/1337/brands/5372?hall_id=1",  # OPPO      (3 件)
    "https://www.sogi.com.tw/shops/1337/brands/5368?hall_id=1",  # 小米      (2 件)
    "https://www.sogi.com.tw/shops/1337/brands/49?hall_id=1",    # ASUS      (1 件)
    "https://www.sogi.com.tw/shops/1337/brands/6012?hall_id=1",  # realme    (1 件)
]


def _extract_sogi_items(page: Page, source_url: str) -> list[dict]:
    """
    從 SOGI 品牌頁面提取商品列表。

    確認的 HTML 結構（2026-06）：
      <div class="mix-item" data-sort-price="29000">
        <div class="box my-2">
          <figure><a href="/shops/1337/used/XXXXX"><img alt="型號名稱"></a></figure>
          <div class="clearfix">
            <a href="/shops/1337/used/XXXXX">
              <div class="text-row-2 text-black">Apple iPhone 16 Pro Max 256GB</div>
            </a>
            <ul class="list-group">
              <li><span class="text-price h6">$29,000</span></li>
            </ul>
          </div>
        </div>
      </div>

    策略：以 .box.my-2 為卡片單位，從外層 .mix-item 讀 data-sort-price。
    已售出商品（含「已售出」文字）直接跳過。
    """
    items = []
    for card in page.locator(".box.my-2").all():
        try:
            # 已售出跳過
            card_text = card.inner_text()
            if "已售出" in card_text:
                continue

            # URL：從卡片內任一 a[href*='/shops/1337/used/'] 取得
            a_el = card.locator("a[href*='/shops/1337/used/']").first
            if a_el.count() == 0:
                continue
            href = a_el.get_attribute("href") or ""
            full_url = f"https://www.sogi.com.tw{href}" if href.startswith("/") else href

            # 標題：div.text-row-2（標題 div），fallback: img alt
            title = ""
            title_el = card.locator(".text-row-2").first
            if title_el.count() > 0:
                title = title_el.inner_text().strip()
            if not title:
                img = card.locator("img").first
                title = img.get_attribute("alt") or "" if img.count() > 0 else ""

            # 價格：span.text-price.h6（最精確），fallback: 外層 .mix-item 的 data-sort-price
            price_str = ""
            price_el = card.locator(".text-price.h6").first
            if price_el.count() > 0:
                m = re.search(r'\$([\d,]+)', price_el.inner_text())
                if m:
                    price_str = m.group(1)
            if not price_str:
                # 往上找 .mix-item 的 data-sort-price
                sort_price = card.evaluate(
                    "el => el.closest('.mix-item')?.dataset?.sortPrice || ''"
                )
                price_str = sort_price if sort_price else ""

            if title:
                items.append({
                    "platform": "手機王(SOGI)",
                    "title":    title,
                    "price_str": price_str,
                    "url":      full_url,
                })
        except Exception as e:
            log.debug(f"  [手機王] 解析商品元素失敗（來源：{source_url}）：{e}")
    return items


def scrape_sogi(page: Page) -> list[dict]:
    """
    抓取手機王（sogi.com.tw/shops/1337）全部在售商品。
    策略：
      1. 以硬編碼品牌清單（SOGI_KNOWN_BRANDS）為主，確保 8 個品牌全部涵蓋。
      2. 同時從主頁動態發現額外品牌連結，避免遺漏新增品牌。
      3. 每個品牌頁支援翻頁（若未來超過單頁上限時自動處理）。
    """
    results: list[dict] = []
    seen_urls: set[str] = set()

    def add_items(new_items: list[dict]):
        for item in new_items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                results.append(item)

    # ── 步驟 1：從主頁動態補充品牌連結（捕捉新增品牌） ──────────────────────
    log.info(f"  [手機王] 掃描主頁動態品牌連結：{SOGI_SHOP_URL}")
    dynamic_brands: set[str] = set(SOGI_KNOWN_BRANDS)  # 先放入已知清單
    try:
        page.goto(SOGI_SHOP_URL, wait_until="domcontentloaded", timeout=30000)
        random_delay(2, 4)
        for a in page.locator("a[href*='/shops/1337/brands/']").all():
            href = a.get_attribute("href") or ""
            if href:
                full = f"https://www.sogi.com.tw{href}" if href.startswith("/") else href
                dynamic_brands.add(full)
        log.info(f"  [手機王] 品牌子頁總計：{len(dynamic_brands)} 個（含已知 {len(SOGI_KNOWN_BRANDS)} 個）。")
    except _UserStopped:
        raise   # 停止訊號必須穿透
    except Exception as e:
        log.warning(f"  [手機王] 主頁掃描失敗（{e}），改用硬編碼品牌清單繼續。")

    # ── 步驟 2：逐一訪問每個品牌子頁 ─────────────────────────────────────────
    for brand_url in dynamic_brands:
        _check_pause()
        brand_name = brand_url.split("/brands/")[1].split("?")[0]  # 取 ID 作日誌用
        for page_num in range(1, MAX_PAGES + 1):
            _check_pause()
            paged_url = brand_url if page_num == 1 else f"{brand_url}&page={page_num}"
            log.info(f"  [手機王] 品牌 {brand_name} 第 {page_num} 頁：{paged_url}")

            try:
                page.goto(paged_url, wait_until="domcontentloaded", timeout=30000)
                random_delay(DELAY_MIN, DELAY_MAX)
            except PlaywrightTimeout:
                log.warning(f"  [手機王] {paged_url} 載入超時，跳過此頁。")
                break

            # 偵測 404 頁（停止翻頁）
            title_tag = page.title() or ""
            if "404" in title_tag or "找不到" in title_tag:
                log.info(f"  [手機王] 品牌 {brand_name} 第 {page_num} 頁 404，停止翻頁。")
                break

            page_items = _extract_sogi_items(page, paged_url)
            add_items(page_items)
            log.info(f"  [手機王] 品牌 {brand_name} 第 {page_num} 頁：抓到 {len(page_items)} 件。")

            # 無商品 → 已超出頁數範圍
            if not page_items:
                break

            # 檢查下一頁連結（SOGI 若有分頁通常用 &page=N 或 rel="next"）
            has_next = page.locator(
                "a[rel='next'], .pagination .next a, a:text('下一頁'), a:text('›')"
            ).count() > 0
            if not has_next:
                break

    log.info(f"✅ [手機王] 共抓到 {len(results)} 件商品（涵蓋 {len(dynamic_brands)} 個品牌）。")
    return results


# ─── 6E. Facebook Marketplace（輔助平台） ─────────────────────────────────────
#
# 機制：無限滾動，但需登入，Meta 反爬蟲極嚴。
# 策略：嘗試抓取，任何異常皆被 try/except 捕捉並跳過，不影響其他平台執行。
#
# ─────────────────────────────────────────────────────────────────────────────

def scrape_fb(page: Page) -> list[dict]:
    """
    嘗試抓取 FB Marketplace 賣家頁。
    預期大概率因未登入或反爬蟲機制而失敗（回傳空清單屬正常，不影響其他平台）。
    """
    results = []
    log.info(f"  [FB市集] 前往：{FB_MARKETPLACE_URL}")

    try:
        page.goto(FB_MARKETPLACE_URL, wait_until="domcontentloaded", timeout=20000)
        random_delay(3, 5)

        # 偵測登入牆
        page_text = page.inner_text("body") or ""
        login_keywords = ["登入", "Log In", "login", "請先登入", "sign in", "登録"]
        if any(kw.lower() in page_text.lower() for kw in login_keywords):
            log.warning("  [FB市集] 偵測到登入要求，無法取得商品資料，跳過此平台。")
            return []

        # 嘗試滾動若干次
        for _ in range(min(8, MAX_PAGES)):
            _check_pause()
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            random_delay(2, 4)

        # 只抓賣家個人檔案的商品（href 含 ref=marketplace_profile），
        # 過濾掉 FB 主動推薦的 top_picks 隨機商品（會造成假告警）
        seen_urls: set[str] = set()
        for item in page.locator("a[href*='/marketplace/item/']").all():
            try:
                href = item.get_attribute("href") or ""
                if "marketplace_profile" not in href:
                    continue
                full_url = f"https://www.facebook.com{href}" if href.startswith("/") else href
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                text = item.inner_text() or ""
                lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                title = lines[0] if lines else ""
                price_match = re.search(r'(?:NT\$|TWD|＄|\$)\s*([\d,]+)', text)
                price_str = price_match.group(1) if price_match else ""
                if title:
                    results.append({
                        "platform": "FB市集",
                        "title": title,
                        "price_str": price_str,
                        "url": full_url,
                    })
            except Exception:
                continue

    except _UserStopped:
        raise   # 停止訊號必須穿透
    except Exception as e:
        log.warning(
            f"  [FB市集] 抓取失敗（{type(e).__name__}: {e}），"
            "跳過此平台，不影響其他通路執行。"
        )

    log.info(f"✅ [FB市集] 抓到 {len(results)} 件商品（若為 0 屬正常，此為輔助平台）。")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 七、核心稽核比對邏輯
# ═══════════════════════════════════════════════════════════════════════════════

def audit(scraped_items: list[dict], price_table: dict) -> list[dict]:
    """
    將抓到的所有商品與 Excel 底價表比對，找出基礎價低於底價的違規商品。

    比對邏輯：
    1. 對商品標題進行去骨清洗（sanitize），得到唯一索引 Key。
    2. 在 price_table 中搜尋「最長子字串匹配」（優先選最精確的型號）。
    3. 蝦皮商品先套用 revert_shopee_price() 還原基礎價。
    4. 基礎價 < 底價  → 底價破防，加入告警清單。
    5. 基礎價 >= 底價 → 正常（有溢價/換電池/保固），安全放行。
    6. 找不到對應型號 → 忽略（可能已售完或為特殊品）。
    """
    violations = []

    for item in scraped_items:
        web_price = parse_price(item.get("price_str", ""))
        if not web_price or web_price <= 0:
            log.debug(f"  略過（無法解析價格）：{item['title']}")
            continue

        # 蝦皮平台：先套公式還原基礎價
        base_price = (
            revert_shopee_price(web_price)
            if item["platform"] == "蝦皮購物"
            else web_price
        )

        title_key = sanitize(item["title"])
        if not title_key:
            continue

        # 在底價表中尋找最長匹配（子字串，雙向）
        floor_price: Optional[int] = None
        best_match_len = 0
        for excel_key, floor in price_table.items():
            if excel_key in title_key or title_key in excel_key:
                match_len = len(excel_key)
                if match_len > best_match_len:
                    floor_price = floor
                    best_match_len = match_len

        if floor_price is None:
            log.debug(f"  找不到對應型號（忽略）：{item['title']}")
            continue

        if base_price < floor_price:
            violations.append({
                "platform":  item["platform"],
                "title":     item["title"],
                "web_price": web_price,
                "base_price": base_price,
                "floor":     floor_price,
                "url":       item.get("url", ""),
            })
            log.warning(
                f"  🚨 底價破防！[{item['platform']}] {item['title']} "
                f"基礎價 NT${base_price:,} < 底價 NT${floor_price:,}"
            )
        else:
            log.debug(
                f"  ✅ 正常 [{item['platform']}] {item['title']} "
                f"基礎價 NT${base_price:,} >= 底價 NT${floor_price:,}"
            )

    return violations


# ═══════════════════════════════════════════════════════════════════════════════
# 八、主程式
# ═══════════════════════════════════════════════════════════════════════════════

def run_scraper(pw, scraper_fn, platform_name: str) -> list[dict]:
    """統一的爬蟲執行包裝：建立獨立瀏覽器 context，執行完畢後自動關閉。"""
    browser, context = make_browser_context(pw)
    page = context.new_page()
    try:
        return scraper_fn(page)
    except _UserStopped:
        raise   # 停止訊號必須穿透，不能被吞掉
    except Exception as e:
        log.error(f"  [{platform_name}] 抓取時發生未預期錯誤：{e}")
        return []
    finally:
        context.close()
        browser.close()


def main():
    log.info("=" * 62)
    log.info("  多通路電商底價全自動稽核系統  v1.0")
    log.info("=" * 62)

    # 1. 讀取 Excel 底價表
    price_table = load_price_table(EXCEL_PATH)

    all_scraped: list[dict] = []

    # 2. 啟動 Playwright，依序抓取各平台（每個平台使用獨立 Browser Context）
    with sync_playwright() as pw:

        log.info("\n📦 [1/5] 抓取 Cyberbiz（炘馳通訊官網）...")
        all_scraped.extend(run_scraper(pw, scrape_cyberbiz, "Cyberbiz"))

        log.info("\n📦 [2/5] 抓取 蝦皮購物（使用本機 Chrome）...")
        all_scraped.extend(scrape_shopee(pw))

        log.info("\n📦 [3/5] 抓取 旋轉拍賣（Carousell）...")
        all_scraped.extend(run_scraper(pw, scrape_carousell, "旋轉拍賣"))

        log.info("\n📦 [4/5] 抓取 手機王（SOGI）...")
        all_scraped.extend(run_scraper(pw, scrape_sogi, "手機王"))

        log.info("\n📦 [5/5] 嘗試抓取 FB Marketplace（輔助平台）...")
        all_scraped.extend(run_scraper(pw, scrape_fb, "FB市集"))

    log.info(f"\n📊 全通路共抓到 {len(all_scraped)} 件商品，開始稽核比對...")

    # 3. 稽核比對
    violations = audit(all_scraped, price_table)

    # 4. Telegram 通知
    log.info("\n📱 發送 Telegram 通知...")
    if violations:
        log.warning(f"  ⚠️  發現 {len(violations)} 件底價破防商品！")
        send_telegram(build_alert_message(violations))
    else:
        log.info("  ✅ 全網巡檢完畢，無任何異常！")
        send_telegram(
            "🤖 <b>今日全網巡檢完畢！</b>\n\n"
            "✅ 在線商品價格皆在底價防禦線之內，無人標錯價。\n"
            f"📊 共巡查 <b>{len(all_scraped)}</b> 件商品 / "
            f"<b>{len(price_table)}</b> 個型號底價。"
        )

    log.info("\n🏁 稽核系統執行完畢。")


if __name__ == "__main__":
    main()
