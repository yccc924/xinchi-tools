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


class SettingsPage(tk.Frame):
    def __init__(self, master, config: dict, on_save=None, **kwargs):
        super().__init__(master, bg=WIN_BG, **kwargs)
        self._on_save = on_save
        self._vars: dict[str, tk.StringVar] = {}
        self._saved_lbl = None
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
            row=len(_FIELDS) + 1, column=0, pady=24)

    def _browse(self, key: str):
        path = filedialog.askopenfilename(
            filetypes=[('Excel', '*.xlsx *.xls')], title='選擇 Excel 檔案')
        if path:
            self._vars[key].set(path)

    def _save(self):
        data = {k: v.get().strip() for k, v in self._vars.items()}
        cfg.update(data)

        if self._saved_lbl:
            self._saved_lbl.destroy()
        lbl = tk.Label(self, text='✓ 已儲存',
                       font=(_F, _FS), bg=WIN_BG, fg='#2a8a2a')
        lbl.grid(row=len(_FIELDS) + 2, column=0, pady=4)
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
