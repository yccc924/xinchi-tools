import sys
import threading
import tempfile
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

from core.win95 import (
    WIN_BG, TXT_BG, TXT_FG, SEL_BG, SEL_FG, BTN_FACE,
    _F, _FS, w95_btn, w95_text, w95_scrollable_frame,
)
from core.shortcuts import attach

# 讓 lister.py / content.py 從 上架/ 資料夾可被 import
_LISTING_DIR = Path(__file__).parent.parent.parent / '上架'
if str(_LISTING_DIR) not in sys.path:
    sys.path.insert(0, str(_LISTING_DIR))

MAX_ROWS  = 20
IMG_TYPES = [('圖片', '*.jpg *.jpeg *.png *.webp *.avif *.gif *.bmp'), ('全部', '*.*')]


class ListingPage(tk.Frame):
    def __init__(self, master, config: dict, **kwargs):
        super().__init__(master, bg=WIN_BG, **kwargs)
        self._config           = config
        self._rows: list[dict] = []
        self._worker_running   = False
        self._build()

    def on_config_update(self, config: dict):
        self._config = config

    # ── 建立 UI ──────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Row 0: 標題列 + 流水號起始
        top = tk.Frame(self, bg=WIN_BG)
        top.grid(row=0, column=0, sticky='ew', padx=20, pady=(16, 8))

        tk.Label(top, text='自動上架',
                 font=(_F, _FS, 'bold'), bg=WIN_BG, fg=TXT_FG).pack(side='left')

        tk.Label(top, text='流水號起始：',
                 font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).pack(side='left', padx=(24, 4))
        self._seq_var = tk.IntVar(value=1)
        tk.Spinbox(top, from_=1, to=999, textvariable=self._seq_var,
                   width=4, font=(_F, _FS),
                   bg=TXT_BG, fg=TXT_FG, relief='sunken', bd=2).pack(side='left')

        # Row 1: 可捲動列表區
        scroll_outer, self._inner = w95_scrollable_frame(self)
        scroll_outer.grid(row=1, column=0, sticky='nsew', padx=20, pady=(0, 4))
        self._inner.grid_columnconfigure(1, weight=1)

        hdr_kw = dict(font=(_F, _FS, 'bold'), bg=WIN_BG, fg=TXT_FG)
        tk.Label(self._inner, text='#',       **hdr_kw).grid(row=0, column=0, padx=(6, 4),  pady=(4, 2))
        tk.Label(self._inner, text='機況文字', **hdr_kw).grid(row=0, column=1, padx=4,        pady=(4, 2), sticky='w')
        tk.Label(self._inner, text='圖片',     **hdr_kw).grid(row=0, column=2, padx=4,        pady=(4, 2))
        tk.Label(self._inner, text='狀態',     **hdr_kw).grid(row=0, column=3, padx=(4, 8),  pady=(4, 2))

        self._add_row()

        # Row 2: 底部按鈕列
        bot = tk.Frame(self, bg=WIN_BG)
        bot.grid(row=2, column=0, sticky='ew', padx=20, pady=8)

        w95_btn(bot, '+ 新增一列', command=self._add_row).pack(side='left')
        w95_btn(bot, '開始上架',   command=self._run).pack(side='left', padx=(8, 0))

        self._lbl_run = tk.Label(bot, text='就緒', font=(_F, _FS),
                                 bg=WIN_BG, fg='#808080')
        self._lbl_run.pack(side='left', padx=12)

    # ── 列管理 ───────────────────────────────────────────────────────────

    def _add_row(self):
        if len(self._rows) >= MAX_ROWS:
            messagebox.showwarning('提醒', f'最多只能新增 {MAX_ROWS} 列')
            return

        idx      = len(self._rows)
        grid_row = idx + 1  # row 0 是標頭

        tk.Label(self._inner, text=f'{idx + 1}.',
                 font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(
            row=grid_row, column=0, padx=(6, 4), pady=4, sticky='n')

        txt_outer, txt = w95_text(self._inner, height=4)
        txt_outer.grid(row=grid_row, column=1, padx=4, pady=4, sticky='ew')
        attach(txt)

        right = tk.Frame(self._inner, bg=WIN_BG)
        right.grid(row=grid_row, column=2, padx=4, pady=4, sticky='n')

        w95_btn(right, '選圖片',
                command=lambda i=idx: self._pick_image(i)).pack(side='top', fill='x')
        img_label = tk.Label(right, text='（未選擇）',
                             font=(_F, _FS), bg=WIN_BG, fg='#808080',
                             width=20, anchor='w', wraplength=140)
        img_label.pack(side='top', fill='x', pady=(2, 0))

        status_label = tk.Label(self._inner, text='待上架',
                                font=(_F, _FS), bg=WIN_BG, fg='#808080')
        status_label.grid(row=grid_row, column=3, padx=(4, 8), pady=4, sticky='n')

        self._rows.append({
            'text':         txt,
            'image_path':   None,
            'img_label':    img_label,
            'status_label': status_label,
        })

    # ── 選圖片 ───────────────────────────────────────────────────────────

    def _pick_image(self, row_idx: int):
        path = filedialog.askopenfilename(
            filetypes=IMG_TYPES, title=f'選擇第 {row_idx + 1} 列的圖片')
        if not path:
            return
        p   = Path(path)
        row = self._rows[row_idx]
        row['image_path'] = p
        name = p.name if len(p.name) <= 20 else p.name[:17] + '...'
        row['img_label'].configure(text=name, fg=TXT_FG)

    # ── 執行 ─────────────────────────────────────────────────────────────

    def _run(self):
        if self._worker_running:
            return

        excel_path = self._config.get('excel_path', '')
        if not excel_path or not Path(excel_path).exists():
            messagebox.showwarning('提醒', '請先在設定頁設定底價表 Excel 檔案')
            return

        rows_data = []
        for i, row in enumerate(self._rows):
            raw_text = row['text'].get('1.0', 'end').strip()
            if not raw_text:
                messagebox.showwarning('提醒', f'第 {i + 1} 列的機況文字不可為空')
                return
            if row['image_path'] is None:
                messagebox.showwarning('提醒', f'第 {i + 1} 列尚未選擇圖片')
                return
            rows_data.append({
                'raw_text':   raw_text,
                'image_path': row['image_path'],
            })

        if not rows_data:
            messagebox.showwarning('提醒', '請先新增至少一列資料')
            return

        self._worker_running = True
        self._lbl_run.configure(text='上架中…', fg='#808080')
        for row in self._rows:
            row['status_label'].configure(text='待上架', fg='#808080')

        seq_start = self._seq_var.get()
        threading.Thread(
            target=self._start_listing,
            args=(rows_data, excel_path, seq_start),
            daemon=True,
        ).start()

    # ── 背景上架（完整流程） ─────────────────────────────────────────────

    def _start_listing(self, rows_data: list[dict], excel_path: str, seq_start: int):
        from core.parser       import parse_one
        from core.price_lookup import load_excel, lookup_price
        from core.image_engine import render as render_image
        import lister

        try:
            price_db, warranty_keys = load_excel(excel_path)
        except Exception as e:
            self._ui(lambda: self._lbl_run.configure(
                text=f'載入底價表失敗：{e}', fg='#cc3333'))
            self._worker_running = False
            return

        tmp_dir = Path(tempfile.mkdtemp(prefix='listing_'))

        for idx, row_data in enumerate(rows_data):
            seq = seq_start + idx

            # 解析機況
            self._set_row_status(idx, '解析機況…', '#e07000')
            try:
                parsed = parse_one(row_data['raw_text'])
            except Exception as e:
                self._set_row_status(idx, f'解析失敗：{e}', '#cc3333')
                continue

            if not parsed.get('model'):
                self._set_row_status(idx, '無法辨識機型', '#cc3333')
                continue

            # 查詢底價
            self._set_row_status(idx, '查詢底價…', '#e07000')
            price = lookup_price(
                price_db, warranty_keys,
                parsed['model'], parsed['capacity'],
                parsed['battery'], row_data['raw_text'],
            )
            if price is None:
                self._set_row_status(idx, '查無底價，跳過', '#cc3333')
                continue

            # 渲染商品圖
            self._set_row_status(idx, '製作商品圖…', '#e07000')
            try:
                rendered = render_image(
                    image_path   = row_data['image_path'],
                    warranty     = parsed.get('warranty',  ''),
                    battery      = parsed.get('battery',   ''),
                    color        = parsed.get('color',     ''),
                    serial       = parsed.get('serial',    ''),
                    model        = parsed.get('model',     ''),
                    capacity     = parsed.get('capacity',  ''),
                    condition    = parsed.get('condition', ''),
                    output_path  = tmp_dir / f'product_{seq}.jpg',
                )
            except Exception as e:
                self._set_row_status(idx, f'做圖失敗：{e}', '#cc3333')
                continue

            # 自動上架
            self._set_row_status(idx, '上架中…', '#e07000')
            try:
                lister.list_product(
                    data       = parsed,
                    image_path = rendered,
                    price      = price,
                    sequence   = seq,
                    on_status  = lambda msg, i=idx: self._set_row_status(i, msg, '#e07000'),
                )
                self._set_row_status(idx, '已上架', '#2a8a2a')
            except Exception as e:
                self._set_row_status(idx, f'上架失敗：{e}', '#cc3333')

        success = sum(
            1 for row in self._rows
            if row['status_label'].cget('text') == '已上架'
        )
        self._ui(lambda s=success, t=len(rows_data): self._on_listing_done(s, t))

    # ── 完成 ─────────────────────────────────────────────────────────────

    def _on_listing_done(self, success: int, total: int):
        self._worker_running = False
        try:
            if self.winfo_exists():
                color = '#2a8a2a' if success == total else '#e07000'
                self._lbl_run.configure(
                    text=f'完成 {success}/{total} 件', fg=color)
        except Exception:
            pass

    # ── 安全更新 UI ──────────────────────────────────────────────────────

    def _set_row_status(self, idx: int, text: str, color: str):
        def _update():
            try:
                if self.winfo_exists():
                    self._rows[idx]['status_label'].configure(text=text, fg=color)
            except Exception:
                pass
        self._ui(_update)

    def _ui(self, fn):
        try:
            if self.winfo_exists():
                self.after(0, fn)
        except Exception:
            pass
