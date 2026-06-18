#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蝦皮購物 單平台測試腳本

執行前必須關閉所有 Chrome 視窗，再執行：
    source venv/bin/activate && python test_shopee.py
"""

from price_checker import (
    load_price_table, scrape_shopee, audit,
    build_alert_message, send_telegram,
    EXCEL_PATH, log
)
from playwright.sync_api import sync_playwright

def main():
    log.info("=" * 50)
    log.info("  蝦皮購物 單平台測試（使用本機 Chrome）")
    log.info("=" * 50)

    price_table = load_price_table(EXCEL_PATH)

    with sync_playwright() as pw:
        log.info("\n📦 抓取 蝦皮購物...")
        items = scrape_shopee(pw)

    if not items:
        log.warning("  抓到 0 件商品。請確認：")
        log.warning("  1. 已執行 shopee_setup_session() 完成登入")
        log.warning("  2. 所有 Chrome 視窗已關閉再執行此腳本")
        return

    log.info(f"\n📋 共抓到 {len(items)} 件商品：")
    for i, item in enumerate(items, 1):
        log.info(f"  [{i:03d}] {item['title']!r}  價格={item['price_str']!r}  URL={item['url']}")

    log.info(f"\n🔍 開始比對底價...")
    violations = audit(items, price_table)

    log.info(f"\n{'='*50}")
    if violations:
        log.warning(f"⚠️  發現 {len(violations)} 件底價破防！")
        for v in violations:
            log.warning(
                f"  [{v['platform']}] {v['title']}\n"
                f"    網頁價 NT${v['web_price']:,}  →  底價 NT${v['floor']:,}"
            )
        send_telegram(build_alert_message(violations))
    else:
        log.info("✅ 蝦皮所有商品均在底價防禦線之內！")
    log.info("=" * 50)

if __name__ == "__main__":
    main()
