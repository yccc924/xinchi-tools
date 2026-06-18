import sys
import logging
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

import core.config as cfg
from core.shortcuts import attach
from core.win95 import WIN_BG, TXT_BG, TXT_FG, SEL_BG, SEL_FG, BTN_FACE, _F, _FS, w95_btn, w95_entry, w95_text


class _UiHandler(logging.Handler):
    """把 price_checker 的 log 轉送到 UI textbox。"""
    def __init__(self, callback):
        super().__init__()
        self._cb = callback
        self.setFormatter(logging.Formatter('%(asctime)s  %(message)s', '%H:%M:%S'))

    def emit(self, record):
        self._cb(self.format(record))


class PriceCheckPage(tk.Frame):
    def __init__(self, master, config: dict, **kwargs):
        super().__init__(master, bg=WIN_BG, **kwargs)
        self._running = False
        self._pause_event = threading.Event()
        self._pause_event.set()   # 預設不暫停
        self._build()
        if config.get('excel_path') and Path(config['excel_path']).exists():
            self._excel_var.set(config['excel_path'])

    def on_config_update(self, config: dict):
        if config.get('excel_path'):
            self._excel_var.set(config['excel_path'])

    # ── 建立 UI ──────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        tk.Label(self, text='多通路價格稽核',
                 font=(_F, _FS, 'bold'), bg=WIN_BG, fg=TXT_FG).grid(
            row=0, column=0, sticky='w', padx=20, pady=(16, 8))

        # 底價表（與製作&報價頁共用同一個 Excel）
        excel_row = tk.Frame(self, bg=WIN_BG)
        excel_row.grid(row=1, column=0, sticky='ew', padx=20, pady=(0, 12))
        excel_row.grid_columnconfigure(1, weight=1)

        tk.Label(excel_row, text='底價表 Excel：', font=(_F, _FS), bg=WIN_BG, fg=TXT_FG, width=14).grid(
            row=0, column=0, padx=(0, 8))
        self._excel_var = tk.StringVar(value='（尚未設定）')
        w95_entry(excel_row, textvariable=self._excel_var, state='readonly').grid(
            row=0, column=1, sticky='ew', padx=(0, 8))
        w95_btn(excel_row, '瀏覽', command=self._browse_excel, width=8).grid(row=0, column=2)

        tk.Label(self,
                 text='蝦皮需要 Chrome 保持開啟並已登入 shopee.tw（自動讀取 cookie，無需重新登入）',
                 font=(_F, _FS), bg=WIN_BG, fg='#808080', anchor='w').grid(
            row=2, column=0, sticky='w', padx=20, pady=(0, 4))

        # 操作列
        op_row = tk.Frame(self, bg=WIN_BG)
        op_row.grid(row=3, column=0, sticky='ew', padx=20, pady=(0, 8))

        self._btn_run = w95_btn(op_row, '開始稽核', command=self._toggle, width=12)
        self._btn_run.pack(side='left')

        self._btn_pause = w95_btn(op_row, '暫停', command=self._toggle_pause, width=8)
        self._btn_pause.pack(side='left', padx=(8, 0))
        self._btn_pause.pack_forget()   # 初始隱藏

        self._lbl_status = tk.Label(op_row, text='', font=(_F, _FS), bg=WIN_BG, fg='#808080')
        self._lbl_status.pack(side='left', padx=12)

        # 執行記錄
        log_outer, self._log = w95_text(self, readonly=True, mono=True)
        log_outer.grid(row=4, column=0, sticky='nsew', padx=20, pady=(0, 20))
        attach(self._log, readonly=True)

        self._log.tag_configure('ok',   foreground='#0a7d2c')
        self._log.tag_configure('warn', foreground='#b07000')
        self._log.tag_configure('err',  foreground='#c0202a')
        self._log.tag_configure('dim',  foreground='#7a7770')

    # ── Excel ────────────────────────────────────────────────────────────

    def _browse_excel(self):
        path = filedialog.askopenfilename(
            filetypes=[('Excel', '*.xlsx *.xls')], title='選擇底價表 Excel')
        if path:
            self._excel_var.set(path)
            cfg.update({'excel_path': path})

    # ── 稽核 ─────────────────────────────────────────────────────────────

    def _toggle(self):
        if self._running:
            self._running = False
            self._pause_event.set()   # 解除暫停，讓執行緒能偵測到停止
            self._btn_run.configure(text='開始稽核')
            self._btn_pause.pack_forget()
            return

        excel = self._excel_var.get()
        if not excel or excel == '（尚未設定）':
            messagebox.showwarning('提醒', '請先選擇底價表 Excel')
            return
        if not Path(excel).exists():
            messagebox.showwarning('提醒', f'找不到檔案：\n{excel}')
            return

        self._running = True
        self._pause_event.set()
        self._btn_run.configure(text='停止')
        self._btn_pause.configure(text='暫停')
        self._btn_pause.pack(side='left', padx=(8, 0))
        self._log.configure(state='normal')
        self._log.delete('1.0', 'end')
        self._log.configure(state='disabled')
        self._lbl_status.configure(text='稽核中…', fg='#808080')

        threading.Thread(target=self._run, args=(excel,), daemon=True).start()

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()   # 暫停
            self._btn_pause.configure(text='繼續')
            self._lbl_status.configure(text='已暫停', fg='#808000')
        else:
            self._pause_event.set()     # 繼續
            self._btn_pause.configure(text='暫停')
            self._lbl_status.configure(text='稽核中…', fg='#808080')

    def _log_write(self, text: str):
        try:
            if self.winfo_exists():
                self.after(0, self._append_log, text)
        except tk.TclError:
            pass

    def _append_log(self, text: str):
        self._log.configure(state='normal')
        idx = self._log.index('end')
        self._log.insert('end', text + '\n')

        t = text
        if any(c in t for c in ('✅', '🏁', '全網巡檢完畢', '無任何異常', '執行完畢')):
            tag = 'ok'
        elif any(c in t for c in ('⚠️', '⚠', '破防', '異常', '警告')):
            tag = 'warn'
        elif any(c in t for c in ('❌', '[錯誤]', '錯誤', '失敗')):
            tag = 'err'
        elif any(c in t for c in ('就緒', '請確認', '› ')):
            tag = 'dim'
        else:
            tag = ''
        if tag:
            self._log.tag_add(tag, idx, 'end-1c')

        self._log.see('end')
        self._log.configure(state='disabled')

    def _run(self, excel_path: str):
        checker_dir = Path(__file__).parent.parent.parent / '價格檢查'
        if str(checker_dir) not in sys.path:
            sys.path.insert(0, str(checker_dir))

        handler = _UiHandler(self._log_write)
        logger  = None

        def pause_check():
            """在平台間呼叫：暫停時阻塞直到繼續或停止。"""
            self._pause_event.wait()

        try:
            import price_checker as pc
            from playwright.sync_api import sync_playwright

            pc.EXCEL_PATH = excel_path
            pc._pause_fn  = self._pause_event.wait       # 暫停：阻塞直到繼續
            pc._stop_fn   = lambda: not self._running    # 停止：讓 scraper 拋出 _UserStopped
            config = cfg.load()
            pc.TG_TOKEN   = config.get('telegram_bot_token', '')
            pc.TG_CHAT_ID = config.get('telegram_chat_id', '')

            logger = logging.getLogger('price_checker')
            logger.addHandler(handler)

            # ── 逐平台執行（每個平台前先檢查暫停/停止）──────────────────────────
            price_table = pc.load_price_table(excel_path)
            all_scraped = []

            platforms = [
                ('Cyberbiz（炘馳通訊官網）', '1', lambda pw: pc.run_scraper(pw, pc.scrape_cyberbiz, 'Cyberbiz')),
                ('蝦皮購物（使用本機 Chrome）', '2', lambda pw: pc.scrape_shopee(pw)),
                ('旋轉拍賣（Carousell）',       '3', lambda pw: pc.run_scraper(pw, pc.scrape_carousell, '旋轉拍賣')),
                ('手機王（SOGI）',              '4', lambda pw: pc.run_scraper(pw, pc.scrape_sogi, '手機王')),
                ('FB Marketplace（輔助平台）',  '5', lambda pw: pc.run_scraper(pw, pc.scrape_fb, 'FB市集')),
            ]

            try:
                with sync_playwright() as pw:
                    for name, num, fn in platforms:
                        pause_check()
                        if not self._running:
                            break
                        self._log_write(f'\n📦 [{num}/5] 抓取 {name}...')
                        try:
                            all_scraped.extend(fn(pw))
                        except pc._UserStopped:
                            break       # scraper 內部偵測到停止，退出平台迴圈
            except pc._UserStopped:
                pass                    # 在平台間的 pause_check 觸發的停止

            if not self._running:
                self._log_write('\n⏹ 稽核已手動停止。')
            else:
                pause_check()
                self._log_write(f'\n📊 全通路共抓到 {len(all_scraped)} 件商品，開始稽核比對...')
                violations = pc.audit(all_scraped, price_table)

                self._log_write('\n📱 發送 Telegram 通知...')
                if violations:
                    self._log_write(f'  ⚠️  發現 {len(violations)} 件底價破防商品！')
                    pc.send_telegram(pc.build_alert_message(violations))
                else:
                    self._log_write('  ✅ 全網巡檢完畢，無任何異常！')
                    pc.send_telegram(
                        f'🤖 <b>今日全網巡檢完畢！</b>\n\n'
                        f'✅ 在線商品價格皆在底價防禦線之內，無人標錯價。\n'
                        f'📊 共巡查 <b>{len(all_scraped)}</b> 件商品 / '
                        f'<b>{len(price_table)}</b> 個型號底價。'
                    )
                self._log_write('\n🏁 稽核系統執行完畢。')

        except Exception as e:
            self._log_write(f'[錯誤] {e}')
        finally:
            if logger:
                logger.removeHandler(handler)
            try:
                pc._pause_fn = None
                pc._stop_fn  = None
            except Exception:
                pass
            self._running = False
            self._pause_event.set()
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self._btn_run.configure(text='開始稽核'))
                    self.after(0, self._btn_pause.pack_forget)
                    self.after(0, lambda: self._lbl_status.configure(text='完成', fg='#2a8a2a'))
            except tk.TclError:
                pass
