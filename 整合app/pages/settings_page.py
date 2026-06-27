from tkinter import filedialog
import tkinter as tk

import core.config as cfg
from core.win95 import WIN_BG, TXT_BG, TXT_FG, SEL_BG, SEL_FG, BTN_FACE, _F, _FS, w95_btn, w95_entry

_FIELDS = [
    ('excel_path',         '底價表 Excel 路徑',    False, True),
    ('gemini_api_key',     'Gemini API Key',        True,  False),
    ('nvidia_api_key',     'NVIDIA API Key',        True,  False),
    ('nvidia_base_url',    'NVIDIA Base URL',       False, False),
    ('telegram_bot_token', 'Telegram Bot Token',    True,  False),
    ('telegram_chat_id',   'Telegram Chat ID',      False, False),
]

_DEFAULTS = {
    'nvidia_base_url': 'https://integrate.api.nvidia.com/v1',
}

DEFAULT_BRANDS = [
    'IPHONE', 'IPAD', 'APPLE WATCH', 'SAMSUNG', 'XIAOMI',
    'OPPO', 'VIVO', 'ASUS', 'SONY', 'HUAWEI', 'REALME',
]

# Row index constants (relative to grid)
_SAVE_ROW    = len(_FIELDS) + 1
_SAVED_ROW   = len(_FIELDS) + 2
_BRANDS_ROW  = len(_FIELDS) + 3


class SettingsPage(tk.Frame):
    def __init__(self, master, config: dict, on_save=None, **kwargs):
        super().__init__(master, bg=WIN_BG, **kwargs)
        self._on_save = on_save
        self._vars: dict[str, tk.StringVar] = {}
        self._saved_lbl = None
        self._brand_listbox: tk.Listbox | None = None
        self._brand_entry_var = tk.StringVar()
        self._build(config)

    def _build(self, config: dict):
        self.grid_columnconfigure(0, weight=1)

        tk.Label(self, text='設定',
                 font=(_F, _FS, 'bold'), bg=WIN_BG, fg=TXT_FG).grid(
            row=0, column=0, sticky='w', padx=20, pady=(16, 20))

        for i, (key, label, secret, has_browse) in enumerate(_FIELDS, 1):
            row_frame = tk.Frame(self, bg=WIN_BG)
            row_frame.grid(row=i, column=0, sticky='ew', padx=20, pady=5)
            row_frame.grid_columnconfigure(1, weight=1)

            tk.Label(row_frame, text=label, font=(_F, _FS), bg=WIN_BG, fg=TXT_FG,
                     width=22, anchor='w').grid(row=0, column=0, padx=(0, 12))

            default = _DEFAULTS.get(key, '')
            val     = config.get(key) or default
            var     = tk.StringVar(value=val)
            self._vars[key] = var

            show = '*' if secret else ''
            w95_entry(row_frame, textvariable=var, show=show).grid(
                row=0, column=1, sticky='ew')

            if has_browse:
                w95_btn(row_frame, '瀏覽', command=lambda k=key: self._browse(k), width=8).grid(
                    row=0, column=2, padx=(8, 0))

        w95_btn(self, '儲存設定', command=self._save, width=14).grid(
            row=_SAVE_ROW, column=0, pady=24)

        # ── 品牌清單管理區塊 ──────────────────────────────────────────────
        self._build_brands_section(config)

    def _build_brands_section(self, config: dict):
        section_frame = tk.Frame(self, bg=WIN_BG)
        section_frame.grid(row=_BRANDS_ROW, column=0, sticky='ew', padx=20, pady=(0, 20))
        section_frame.grid_columnconfigure(0, weight=1)

        # Section title
        tk.Label(section_frame, text='品牌清單',
                 font=(_F, _FS, 'bold'), bg=WIN_BG, fg=TXT_FG).grid(
            row=0, column=0, sticky='w', pady=(0, 8))

        # Listbox + Scrollbar container
        lb_frame = tk.Frame(section_frame, bg=WIN_BG)
        lb_frame.grid(row=1, column=0, sticky='ew')
        lb_frame.grid_columnconfigure(0, weight=1)

        scrollbar = tk.Scrollbar(lb_frame, orient='vertical')
        scrollbar.grid(row=0, column=1, sticky='ns')

        self._brand_listbox = tk.Listbox(
            lb_frame,
            font=(_F, _FS),
            bg=TXT_BG,
            fg=TXT_FG,
            selectbackground=SEL_BG,
            selectforeground=SEL_FG,
            relief='sunken',
            bd=2,
            height=8,
            yscrollcommand=scrollbar.set,
            activestyle='dotbox',
            exportselection=False,
        )
        self._brand_listbox.grid(row=0, column=0, sticky='ew')
        scrollbar.config(command=self._brand_listbox.yview)

        # Populate listbox
        brands = cfg.load().get('brands', DEFAULT_BRANDS)
        for brand in brands:
            self._brand_listbox.insert(tk.END, brand)

        # Add row: entry + 新增 button
        add_frame = tk.Frame(section_frame, bg=WIN_BG)
        add_frame.grid(row=2, column=0, sticky='ew', pady=(8, 0))
        add_frame.grid_columnconfigure(0, weight=1)

        w95_entry(add_frame, textvariable=self._brand_entry_var).grid(
            row=0, column=0, sticky='ew', padx=(0, 8))

        w95_btn(add_frame, '新增', command=self._add_brand, width=8).grid(
            row=0, column=1)

        w95_btn(section_frame, '刪除選取品牌', command=self._delete_brand, width=16).grid(
            row=3, column=0, sticky='w', pady=(8, 0))

        # Allow pressing Enter in the entry to add brand
        self._brand_entry_var.trace_add('write', lambda *_: None)
        add_frame.winfo_children()[0].bind('<Return>', lambda e: self._add_brand())

    def _add_brand(self):
        raw = self._brand_entry_var.get().strip().upper()
        if not raw:
            return
        existing = list(self._brand_listbox.get(0, tk.END))
        if raw in existing:
            self._brand_entry_var.set('')
            return
        self._brand_listbox.insert(tk.END, raw)
        self._brand_entry_var.set('')

    def _delete_brand(self):
        selected = self._brand_listbox.curselection()
        # Delete in reverse order to keep indices stable
        for idx in reversed(selected):
            self._brand_listbox.delete(idx)

    def _browse(self, key: str):
        path = filedialog.askopenfilename(
            filetypes=[('Excel', '*.xlsx *.xls')], title='選擇 Excel 檔案')
        if path:
            self._vars[key].set(path)

    def _save(self):
        data = {k: v.get().strip() for k, v in self._vars.items()}

        # Collect current brand list from Listbox
        brands = list(self._brand_listbox.get(0, tk.END))
        data['brands'] = brands

        cfg.update(data)

        if self._saved_lbl:
            self._saved_lbl.destroy()
        lbl = tk.Label(self, text='✓ 已儲存',
                       font=(_F, _FS), bg=WIN_BG, fg='#2a8a2a')
        lbl.grid(row=_SAVED_ROW, column=0, pady=4)
        self._saved_lbl = lbl

        def _clear(w=lbl):
            try:
                if w.winfo_exists():
                    w.configure(text='')
            except tk.TclError:
                pass
        self.after(3000, _clear)

        if self._on_save:
            self._on_save()
