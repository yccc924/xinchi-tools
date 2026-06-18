import re
import sys
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

from core.win95 import (
    WIN_BG, TXT_BG, TXT_FG, SEL_BG, SEL_FG, BTN_FACE,
    _F, _FS, w95_btn, w95_entry, w95_text
)

from core.parser import parse_all
from core.price_lookup import load_excel, detect_model, lookup_price
from core.image_engine import render
from core.shortcuts import attach
import core.config as cfg

SUPPORTED  = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}
if getattr(sys, 'frozen', False):
    OUTPUT_DIR = Path(sys.executable).parent / 'output'
else:
    OUTPUT_DIR = Path(__file__).parent.parent / 'output'


def _pbcopy(text: str):
    if sys.platform == 'darwin':
        subprocess.run(['pbcopy'], input=text, text=True)
    else:
        import tkinter as _tk
        r = _tk.Tk(); r.withdraw()
        r.clipboard_clear(); r.clipboard_append(text)
        r.update(); r.destroy()


class CombinedPage(tk.Frame):
    def __init__(self, master, config: dict, **kwargs):
        super().__init__(master, bg=WIN_BG, **kwargs)
        self._images: list[Path] = []
        self._price_db: dict     = {}
        self._warranty_keys: set = set()
        self._build()
        if config.get('excel_path') and Path(config['excel_path']).exists():
            self._do_load_excel(config['excel_path'])

    def on_config_update(self, config: dict):
        path = config.get('excel_path', '')
        if path and Path(path).exists():
            self._do_load_excel(path)

    # ── 頁籤切換 ─────────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        self._active_tab = idx
        for i, btn in enumerate(self._tab_btns):
            btn.configure(relief='sunken' if i == idx else 'raised')
        if idx == 0:
            self._tab_make.grid()
            self._tab_price.grid_remove()
        else:
            self._tab_make.grid_remove()
            self._tab_price.grid()

    # ── 建立 UI ──────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # 主體列可伸縮

        # Row 0: 標題
        tk.Label(self, text='製作 & 報價',
                 font=(_F, _FS, 'bold'), bg=WIN_BG, fg=TXT_FG).grid(
            row=0, column=0, sticky='w', padx=20, pady=(16, 8))

        # Row 1: 主體（左＋右）
        mid = tk.Frame(self, bg=WIN_BG)
        mid.grid(row=1, column=0, sticky='nsew', padx=20, pady=4)
        mid.grid_columnconfigure(0, weight=3)
        mid.grid_columnconfigure(1, weight=2)
        mid.grid_rowconfigure(1, weight=1)

        # 左欄：機況文字（跨 2 row 以對齊頁籤列＋內容）
        left = tk.Frame(mid, bg=WIN_BG, relief='raised', bd=2)
        left.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        tk.Label(left, text='機況文字（每筆用空行隔開）',
                 font=(_F, _FS), bg=WIN_BG, fg=TXT_FG, anchor='w').grid(
            row=0, column=0, sticky='w', padx=10, pady=(8, 2))
        txt_outer, self._txt = w95_text(left)
        txt_outer.grid(row=1, column=0, sticky='nsew', padx=8, pady=(0, 8))
        self._txt.bind('<KeyRelease>', lambda e: self._refresh_status())
        attach(self._txt)

        # 右欄頂部：頁籤列
        tab_bar = tk.Frame(mid, bg=WIN_BG)
        tab_bar.grid(row=0, column=1, sticky='ew', pady=(0, 0))

        self._active_tab = 0
        self._tab_btns = []
        for i, label in enumerate(['製作圖片', '填寫報價']):
            b = tk.Button(tab_bar, text=label,
                          font=(_F, _FS), bg=BTN_FACE, fg=TXT_FG,
                          relief='raised', bd=2, padx=10, pady=3,
                          cursor='arrow',
                          command=lambda i=i: self._switch_tab(i))
            b.pack(side='left')
            self._tab_btns.append(b)
        self._tab_btns[0].configure(relief='sunken')  # 預設選中第一個

        # 右欄內容：容器 frame
        right_content = tk.Frame(mid, bg=WIN_BG, relief='raised', bd=2)
        right_content.grid(row=1, column=1, sticky='nsew')
        right_content.grid_columnconfigure(0, weight=1)
        right_content.grid_rowconfigure(0, weight=1)

        # ── Tab 0：製作圖片 ──
        self._tab_make = tk.Frame(right_content, bg=WIN_BG)
        self._tab_make.grid(row=0, column=0, sticky='nsew')
        self._tab_make.grid_columnconfigure(0, weight=1)
        self._tab_make.grid_rowconfigure(1, weight=1)

        tk.Label(self._tab_make, text='圖片清單（依檔名排序）',
                 font=(_F, _FS), bg=WIN_BG, fg=TXT_FG, anchor='w').grid(
            row=0, column=0, sticky='w', padx=10, pady=(8, 2))
        img_outer, self._img_box = w95_text(self._tab_make, readonly=True)
        img_outer.grid(row=1, column=0, sticky='nsew', padx=8)
        attach(self._img_box, readonly=True)

        img_btns = tk.Frame(self._tab_make, bg=WIN_BG)
        img_btns.grid(row=2, column=0, padx=8, pady=8, sticky='ew')
        img_btns.grid_columnconfigure((0, 1), weight=1)
        w95_btn(img_btns, '選擇圖片', command=self._pick).grid(
            row=0, column=0, padx=(0, 4), sticky='ew')
        w95_btn(img_btns, '清除', command=self._clear).grid(
            row=0, column=1, padx=(4, 0), sticky='ew')

        # ── Tab 1：填寫報價 ──
        self._tab_price = tk.Frame(right_content, bg=WIN_BG)
        self._tab_price.grid(row=0, column=0, sticky='nsew')
        self._tab_price.grid_columnconfigure(0, weight=1)
        self._tab_price.grid_rowconfigure(2, weight=1)
        self._tab_price.grid_remove()  # 預設隱藏

        # 報價單 Excel 列
        excel_row = tk.Frame(self._tab_price, bg=WIN_BG)
        excel_row.grid(row=0, column=0, sticky='ew', padx=8, pady=(8, 4))
        excel_row.grid_columnconfigure(1, weight=1)
        tk.Label(excel_row, text='報價單 Excel：',
                 font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(
            row=0, column=0, padx=(0, 8))
        self._excel_var = tk.StringVar(value='（尚未載入，僅產生圖片）')
        w95_entry(excel_row, textvariable=self._excel_var,
                  state='readonly').grid(row=0, column=1, sticky='ew', padx=(0, 8))
        w95_btn(excel_row, '瀏覽', command=self._browse_excel,
                width=8).grid(row=0, column=2)

        # 報價結果標籤列
        result_label_row = tk.Frame(self._tab_price, bg=WIN_BG)
        result_label_row.grid(row=1, column=0, sticky='ew', padx=8, pady=(4, 0))
        tk.Label(result_label_row, text='填好價格的文字：',
                 font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).pack(side='left')
        w95_btn(result_label_row, '開啟 output 資料夾',
                command=self._open_output).pack(side='right')
        w95_btn(result_label_row, '複製',
                command=self._copy_result).pack(side='right', padx=(0, 8))

        # 報價結果文字
        result_outer, self._result_txt = w95_text(self._tab_price, readonly=True)
        result_outer.grid(row=2, column=0, sticky='nsew', padx=8, pady=(4, 8))
        attach(self._result_txt, readonly=True)

        # Row 2: 狀態列
        self._lbl_status = tk.Label(self, text='', font=(_F, _FS),
                                    bg=WIN_BG, fg='#808080', anchor='w')
        self._lbl_status.grid(row=2, column=0, sticky='w', padx=20, pady=(2, 0))

        # Row 3: 底部按鈕（全部產生）
        bot = tk.Frame(self, bg=WIN_BG)
        bot.grid(row=3, column=0, sticky='ew', padx=20, pady=8)
        self._btn_run = w95_btn(bot, '全部產生', command=self._run)
        self._btn_run.pack(side='left')
        self._lbl_run = tk.Label(bot, text='就緒', font=(_F, _FS),
                                 bg=WIN_BG, fg='#808080')
        self._lbl_run.pack(side='left', padx=12)

    # ── Excel ────────────────────────────────────────────────────────────

    def _browse_excel(self):
        path = filedialog.askopenfilename(
            filetypes=[('Excel', '*.xlsx *.xls')], title='選擇報價單 Excel')
        if path:
            self._do_load_excel(path)
            cfg.update({'excel_path': path})

    def _do_load_excel(self, path: str):
        try:
            self._price_db, self._warranty_keys = load_excel(path)
            count = len(set(k[0] for k in self._price_db))
            self._excel_var.set(f'{Path(path).name}  （{count} 種機型、{len(self._price_db)} 筆）')
        except Exception as e:
            messagebox.showerror('載入失敗', f'無法解析 Excel：\n{e}')

    # ── 圖片 ─────────────────────────────────────────────────────────────

    def _pick(self):
        paths = filedialog.askopenfilenames(
            filetypes=[('圖片', '*.jpg *.jpeg *.png *.webp *.avif'), ('全部', '*.*')])
        if not paths:
            return
        self._images = sorted([Path(p) for p in paths], key=lambda p: p.name)
        self._refresh_images()
        self._refresh_status()

    def _clear(self):
        self._images = []
        self._refresh_images()
        self._refresh_status()

    def _refresh_images(self):
        self._img_box.configure(state='normal')
        self._img_box.delete('1.0', 'end')
        for i, p in enumerate(self._images, 1):
            self._img_box.insert('end', f'{i}. {p.name}\n')
        self._img_box.configure(state='disabled')

    # ── 狀態 ─────────────────────────────────────────────────────────────

    def _refresh_status(self):
        nc = len(parse_all(self._txt.get('1.0', 'end')))
        ni = len(self._images)
        if nc == 0 and ni == 0:
            self._lbl_status.configure(text='', fg='#808080')
        elif nc == ni and nc > 0:
            self._lbl_status.configure(
                text=f'✓  {nc} 筆機況 ←→ {ni} 張圖片，數量對齊，可以產生',
                fg='#2a8a2a')
        else:
            self._lbl_status.configure(
                text=f'⚠  機況 {nc} 筆 vs 圖片 {ni} 張，數量不符',
                fg='#cc3333')

    # ── 產生 ─────────────────────────────────────────────────────────────

    def _run(self):
        # 防止重複觸發（按鈕 disabled 時仍可能被快捷鍵呼叫）
        if self._btn_run.cget('state') == 'disabled':
            return

        raw_text = self._txt.get('1.0', 'end').strip()
        if not raw_text:
            messagebox.showwarning('提醒', '請貼上機況文字')
            return
        if not self._images:
            messagebox.showwarning('提醒', '請選擇圖片')
            return

        raw_blocks = [b for b in re.split(r'\n{2,}', raw_text) if b.strip()]
        parsed     = parse_all(raw_text)

        if len(parsed) != len(self._images):
            messagebox.showwarning(
                '數量不符',
                f'機況 {len(parsed)} 筆，圖片 {len(self._images)} 張\n請確認數量一致')
            return

        OUTPUT_DIR.mkdir(exist_ok=True)
        self._btn_run.configure(state='disabled')
        self._lbl_run.configure(text='產生中… 0/' + str(len(self._images)), fg='#808080')

        # 把耗時的 render() 移到背景執行緒，完成後用 after() 推回主執行緒更新 UI
        total      = len(self._images)
        price_db   = dict(self._price_db)          # 背景執行緒用的快照
        war_keys   = set(self._warranty_keys)
        has_price  = bool(price_db)

        def _worker():
            done = 0
            err  = 0
            filled_blocks = []

            for idx, (data, raw_block, img_path) in enumerate(
                    zip(parsed, raw_blocks, self._images), start=1):

                # ① 查報價（純計算，無 UI 操作）
                if price_db:
                    header    = raw_block.split('\n')[0]
                    model_key = detect_model(header, price_db)
                    cap_key   = re.sub(r'B$', '', data['capacity'], flags=re.IGNORECASE)
                    price     = lookup_price(price_db, war_keys,
                                             model_key, cap_key,
                                             data['battery'], raw_block)
                    if isinstance(price, int):
                        filled = re.sub(r'^\$$', f'${price}', raw_block, flags=re.MULTILINE)
                    else:
                        label  = f'查無 {model_key} {data["capacity"]}' if model_key != '未知' else '查無機型'
                        filled = re.sub(r'^\$$', f'$ ({label})', raw_block, flags=re.MULTILINE)
                else:
                    filled = raw_block
                filled_blocks.append(filled)

                # ② 產生圖片
                try:
                    out = OUTPUT_DIR / (img_path.stem + '.jpg')
                    render(image_path=img_path, output_path=out, **data)
                    done += 1
                except Exception as ex:
                    err += 1
                    print(f'[圖片錯誤] {img_path.name}: {ex}')

                # 每張完成後即時更新進度標籤（推回主執行緒）
                progress_text = f'產生中… {idx}/{total}'
                try:
                    if self.winfo_exists():
                        self.after(0, lambda t=progress_text: self._safe_set_lbl_run(t, '#808080'))
                except tk.TclError:
                    pass

            # 全部完成 → 推回主執行緒做最終 UI 更新
            result_text = '\n\n'.join(filled_blocks)
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self._on_done(result_text, done, err, has_price))
            except tk.TclError:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _safe_set_lbl_run(self, text: str, color: str):
        """主執行緒回呼：安全地更新進度標籤。"""
        try:
            if self.winfo_exists():
                self._lbl_run.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _on_done(self, result_text: str, done: int, err: int, has_price: bool):
        """主執行緒回呼：背景執行緒全部完成後更新 UI。"""
        try:
            if not self.winfo_exists():
                return
            self._result_txt.configure(state='normal')
            self._result_txt.delete('1.0', 'end')
            self._result_txt.insert('1.0', result_text)
            self._result_txt.configure(state='disabled')

            msg = f'完成 {done} 張圖片' + ('，已填入價格' if has_price else '') + (f'（失敗 {err} 張）' if err else '')
            self._lbl_run.configure(text=msg, fg='#2a8a2a' if not err else '#cc3333')
            self._btn_run.configure(state='normal')

            self._switch_tab(1)  # 自動跳到填寫報價頁籤顯示結果
        except tk.TclError:
            pass

    # ── 複製 / 開啟 ──────────────────────────────────────────────────────

    def _copy_result(self):
        text = self._result_txt.get('1.0', 'end').strip()
        if text:
            _pbcopy(text)

    def _open_output(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        if sys.platform == 'darwin':
            subprocess.run(['open', str(OUTPUT_DIR)])
        elif sys.platform == 'win32':
            subprocess.run(['explorer', str(OUTPUT_DIR)])
        else:
            subprocess.run(['xdg-open', str(OUTPUT_DIR)])
