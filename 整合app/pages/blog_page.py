import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from bs4 import BeautifulSoup

import core.config as cfg
from core.shortcuts import attach
from core.win95 import (
    WIN_BG, TXT_BG, TXT_FG, SEL_BG, SEL_FG, BTN_FACE,
    _F, _FS, w95_btn, w95_entry, w95_text, w95_option_menu, w95_scrollable_frame
)

CATEGORIES = ['最新消息', '教學資訊', '購買建議']


class BlogPage(tk.Frame):
    def __init__(self, master, config: dict, **kwargs):
        super().__init__(master, bg=WIN_BG, **kwargs)
        self._running = False
        self._articles: list[dict] = []
        self._history_articles: list[dict] = []
        self._mode = 'session'          # 'session' | 'history'
        self._current_idx: int = -1
        self._blog_dir: Path | None = None
        self._build()

    def _get_blog_dir(self) -> Path:
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent / 'blog-generator'
        return Path(__file__).resolve().parent.parent.parent / 'blog-generator'

    def on_config_update(self, config: dict):
        pass

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)

        tk.Label(self, text='部落格自動生成',
                 font=(_F, _FS, 'bold'), bg=WIN_BG, fg=TXT_FG).grid(
            row=0, column=0, sticky='w', padx=20, pady=(16, 8))

        # 操作列
        top = tk.Frame(self, bg=WIN_BG)
        top.grid(row=1, column=0, sticky='ew', padx=20, pady=(0, 8))

        # ── 步驟一：生成文章 ──────────────────────────────
        step1 = tk.LabelFrame(top, text='生成文章',
                               font=(_F, _FS), bg=WIN_BG, fg=TXT_FG, bd=2, relief='groove')
        step1.pack(side='left', padx=(0, 12), pady=2, ipadx=6, ipady=4)

        self._btn_run = w95_btn(step1, '開始生成', command=self._toggle_run, width=12)
        self._btn_run.pack(side='left', padx=(4, 4))

        tk.Label(step1, text='篇數：', font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).pack(side='left')
        self._max_var = tk.StringVar(value='5')
        w95_entry(step1, textvariable=self._max_var, width=4).pack(side='left', padx=(2, 4))

        self._lbl_status = tk.Label(top, text='', font=(_F, _FS), bg=WIN_BG, fg='#808080')
        self._lbl_status.pack(side='left', padx=8)

        # 主體：左欄 + 右欄
        body = tk.Frame(self, bg=WIN_BG)
        body.grid(row=2, column=0, sticky='nsew', padx=20, pady=(0, 8))
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # 左欄：頁籤 + 文章列表
        left = tk.Frame(body, width=200, bg=WIN_BG, relief='raised', bd=2)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        left.grid_propagate(False)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # 頁籤列（本次生成 / 歷史記錄）
        left_tabs = tk.Frame(left, bg=WIN_BG)
        left_tabs.grid(row=0, column=0, sticky='ew')
        left_tabs.grid_columnconfigure(0, weight=1)
        left_tabs.grid_columnconfigure(1, weight=1)

        self._left_tab_btns: list[tk.Button] = []
        for col, (label, mode) in enumerate([('本次生成', 'session'), ('歷史記錄', 'history')]):
            b = tk.Button(left_tabs, text=label,
                          font=(_F, _FS), bg=BTN_FACE, fg=TXT_FG,
                          relief='raised', bd=2, pady=2,
                          activebackground=SEL_BG, activeforeground=SEL_FG,
                          command=lambda m=mode: self._switch_mode(m))
            b.grid(row=0, column=col, sticky='ew')
            self._left_tab_btns.append(b)
        self._left_tab_btns[0].configure(relief='sunken')

        list_outer, self._list_frame = w95_scrollable_frame(left)
        list_outer.grid(row=1, column=0, sticky='nsew')
        self._list_frame.grid_columnconfigure(0, weight=1)

        # 右欄：文章編輯 + 複製
        right = tk.Frame(body, bg=WIN_BG, relief='sunken', bd=2)
        right.grid(row=0, column=1, sticky='nsew')
        right.grid_columnconfigure(1, weight=1)
        right.grid_rowconfigure(5, weight=1)

        self._right_frame = right
        self._right_placeholder = tk.Label(
            right, text='<- 點左側選擇一篇文章', font=(_F, _FS),
            bg=WIN_BG, fg='#808080')
        self._right_placeholder.place(relx=0.5, rely=0.5, anchor='center')

        pad = {'padx': (12, 8), 'pady': 4}

        tk.Label(right, text='分類：',       font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(row=0, column=0, sticky='e', **pad)
        self._cat_var = tk.StringVar(value=CATEGORIES[0])
        self._cat_menu = w95_option_menu(right, self._cat_var, CATEGORIES)
        self._cat_menu.grid(row=0, column=1, sticky='w', **pad)

        tk.Label(right, text='參考網址：', font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(row=1, column=0, sticky='e', **pad)
        self._url_var = tk.StringVar()
        url_entry = w95_entry(right, textvariable=self._url_var, state='readonly')
        url_entry.grid(row=1, column=1, sticky='ew', **pad)
        attach(url_entry, readonly=True)

        tk.Label(right, text='標題：',       font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(row=2, column=0, sticky='e', **pad)
        self._title_var = tk.StringVar()
        _title_e = w95_entry(right, textvariable=self._title_var)
        _title_e.grid(row=2, column=1, sticky='ew', **pad)
        attach(_title_e)

        tk.Label(right, text='描述：',       font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(row=3, column=0, sticky='e', **pad)
        self._desc_var = tk.StringVar()
        _desc_e = w95_entry(right, textvariable=self._desc_var)
        _desc_e.grid(row=3, column=1, sticky='ew', **pad)
        attach(_desc_e)

        tk.Label(right, text='關鍵字：',     font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(row=4, column=0, sticky='e', **pad)
        self._kw_var = tk.StringVar()
        _kw_e = w95_entry(right, textvariable=self._kw_var)
        _kw_e.grid(row=4, column=1, sticky='ew', **pad)
        attach(_kw_e)

        tk.Label(right, text='完整 HTML：',  font=(_F, _FS), bg=WIN_BG, fg=TXT_FG).grid(
            row=5, column=0, sticky='ne', pady=(8, 4), padx=(12, 8))
        content_outer = tk.Frame(right, relief='sunken', bd=2, bg=TXT_BG)
        content_outer.grid(row=5, column=1, sticky='nsew', padx=(0, 8), pady=(4, 4))
        content_sb = tk.Scrollbar(content_outer, orient=tk.VERTICAL)
        content_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._content_box = tk.Text(
            content_outer, font=('Courier New', _FS),
            bg=TXT_BG, fg=TXT_FG, relief='flat', bd=0,
            wrap=tk.WORD, undo=True,
            insertbackground=TXT_FG,
            selectbackground=SEL_BG, selectforeground=SEL_FG,
            yscrollcommand=content_sb.set)
        content_sb.config(command=self._content_box.yview)
        self._content_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        attach(self._content_box, readonly=False)

        # 按鈕列：複製 HTML + 確認
        btn_row = tk.Frame(right, bg=WIN_BG)
        btn_row.grid(row=6, column=0, columnspan=2, sticky='e', padx=8, pady=(4, 8))

        self._btn_copy = w95_btn(btn_row, '複製 HTML', command=self._copy_html, width=12)
        self._btn_copy.pack(side='left', padx=(0, 8))

        self._btn_preview = w95_btn(btn_row, '預覽', command=self._preview_html, width=8)
        self._btn_preview.pack(side='left', padx=(0, 8))

        self._btn_confirm = w95_btn(btn_row, '確認這篇 ->', command=self._confirm_current, width=14)
        self._btn_confirm.pack(side='left', padx=(0, 8))

        self._btn_delete = w95_btn(btn_row, '刪除這篇', command=self._delete_current, width=10)
        self._btn_delete.pack(side='left', padx=(0, 8))
        self._btn_delete.pack_forget()      # 歷史模式才顯示

        self._btn_delete_all = w95_btn(btn_row, '全部刪除', command=self._delete_all, width=10)
        self._btn_delete_all.pack(side='left')
        self._btn_delete_all.pack_forget()  # 歷史模式才顯示

        self._set_right_visible(False)

        # log
        log_outer, self._log = w95_text(self, readonly=True, height=6, mono=True)
        log_outer.grid(row=3, column=0, sticky='ew', padx=20, pady=(0, 20))
        attach(self._log, readonly=True)

        self._log.tag_configure('ok',   foreground='#0a7d2c')
        self._log.tag_configure('warn', foreground='#b07000')
        self._log.tag_configure('err',  foreground='#c0202a')
        self._log.tag_configure('dim',  foreground='#7a7770')

    # ── 右欄顯示切換 ─────────────────────────────────────────────────────────

    def _set_right_visible(self, visible: bool):
        if visible:
            self._right_placeholder.place_forget()
        else:
            self._right_placeholder.place(relx=0.5, rely=0.5, anchor='center')

    # ── 左欄列表刷新 ─────────────────────────────────────────────────────────

    @property
    def _active_list(self) -> list[dict]:
        return self._history_articles if self._mode == 'history' else self._articles

    def _refresh_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        for i, art in enumerate(self._active_list):
            short = art['title'][:18] + ('...' if len(art['title']) > 18 else '')
            icon  = '✓' if art.get('confirmed') else '○'
            color = '#2a8a2a' if art.get('confirmed') else TXT_FG
            btn = tk.Button(
                self._list_frame, text=f'{i+1}. {short}  {icon}', anchor='w',
                font=(_F, _FS), bg=BTN_FACE, fg=color,
                relief='flat', bd=1, padx=4,
                activebackground=SEL_BG, activeforeground=SEL_FG,
                command=lambda idx=i: self._select_article(idx))
            btn.grid(row=i, column=0, sticky='ew', padx=2, pady=1)

    # ── 文章選取 ─────────────────────────────────────────────────────────────

    def _select_article(self, idx: int):
        self._save_current_edits()
        self._current_idx = idx
        art = self._active_list[idx]

        self._set_right_visible(True)
        self._cat_var.set(art.get('category', CATEGORIES[0]))
        self._url_var.set(art.get('url', ''))
        self._title_var.set(art.get('title', ''))
        self._desc_var.set(art.get('description', ''))
        self._kw_var.set(art.get('keywords', ''))

        self._content_box.configure(state='normal')
        self._content_box.delete('1.0', 'end')
        self._content_box.insert('1.0', art.get('content', ''))

    def _save_current_edits(self):
        if self._mode == 'history':
            return
        if self._current_idx < 0 or self._current_idx >= len(self._articles):
            return
        art = self._articles[self._current_idx]
        art['category']           = self._cat_var.get()
        art['title']              = self._title_var.get()
        art['description']        = self._desc_var.get()
        art['keywords']           = self._kw_var.get()
        art['content']            = self._content_box.get('1.0', 'end').rstrip('\n')

    # ── 確認這篇 ─────────────────────────────────────────────────────────────

    def _confirm_current(self):
        if self._current_idx < 0 or self._mode == 'history':
            return
        self._save_current_edits()
        self._articles[self._current_idx]['confirmed'] = True
        self._refresh_list()
        next_idx = self._current_idx + 1
        if next_idx < len(self._articles):
            self._select_article(next_idx)

    # ── 複製 HTML ────────────────────────────────────────────────────────────

    def _copy_html(self):
        if self._current_idx < 0:
            return
        self._save_current_edits()
        art = self._active_list[self._current_idx]
        html = art.get('content', '')
        self.clipboard_clear()
        self.clipboard_append(html)
        self._log_write(f'已複製 HTML+CSS：{art.get("title", "")}')

    # ── HTML 預覽 ─────────────────────────────────────────────────────────────

    def _preview_html(self):
        if self._current_idx < 0:
            return
        art = self._active_list[self._current_idx]
        cms_html = art.get('content', '')

        try:
            import glob as _glob
            if not getattr(sys, 'frozen', False):
                _venv = Path(__file__).resolve().parent.parent / 'venv'
                for _pat in ['lib/python*/site-packages', 'Lib/site-packages']:
                    for _sp in _glob.glob(str(_venv / _pat)):
                        if _sp not in sys.path:
                            sys.path.insert(0, _sp)
            from tkinterweb import HtmlFrame
        except ImportError:
            _pip = r'venv\Scripts\pip' if sys.platform == 'win32' else 'venv/bin/pip'
            messagebox.showwarning('缺少套件', f'需要安裝 tkinterweb：\n{_pip} install tkinterweb')
            return

        # 包進完整 HTML 文件並載入 style.css
        blog_dir = self._get_blog_dir()
        css_file = blog_dir / 'style.css'
        css_raw  = css_file.read_text(encoding='utf-8') if css_file.exists() else ''
        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{margin:0;padding:16px;font-family:sans-serif;}}</style>
{css_raw}
</head><body>
{cms_html}
</body></html>"""

        title = art.get('title', 'HTML 預覽')
        win = tk.Toplevel(self)
        win.title(f'預覽 — {title}')
        win.geometry('900x720')
        win.configure(bg=WIN_BG)

        frame = HtmlFrame(win, horizontal_scrollbar='auto', vertical_scrollbar='auto',
                          messages_enabled=False)
        frame.load_html(full_html)
        frame.pack(fill='both', expand=True)

    # ── 左欄頁籤切換（本次生成 / 歷史記錄）─────────────────────────────────────

    def _switch_mode(self, mode: str):
        if mode == self._mode:
            return
        self._save_current_edits()
        self._mode = mode
        self._current_idx = -1
        self._set_right_visible(False)

        for i, btn in enumerate(self._left_tab_btns):
            btn.configure(relief='sunken' if i == (['session', 'history'].index(mode)) else 'raised')

        if mode == 'history':
            self._load_history()
            self._btn_confirm.pack_forget()
            self._btn_delete.pack(side='left', padx=(0, 8))
            self._btn_delete_all.pack(side='left')
        else:
            self._btn_delete.pack_forget()
            self._btn_delete_all.pack_forget()
            self._btn_confirm.pack(side='left', padx=(0, 8))

        self._refresh_list()

    def _load_history(self):
        """掃描 blog-generator/output 載入所有已生成的 HTML 檔案。"""
        blog_dir  = self._get_blog_dir()
        output_dir = blog_dir / 'output'
        if not output_dir.exists():
            self._history_articles = []
            return
        filenames = sorted(
            [f.name for f in output_dir.iterdir() if f.suffix == '.html'],
            reverse=True,
        )
        self._history_articles = self._load_articles_from_output(output_dir, filenames)

    def _remove_urls_from_done(self, urls_to_remove: list[str]):
        """從 done.txt 移除指定的 URL，讓這些文章可以重新生成。"""
        done_path = self._done_txt_path()
        if not done_path.exists() or not urls_to_remove:
            return
        remove_set = set(urls_to_remove)
        existing = [u for u in done_path.read_text(encoding='utf-8').splitlines() if u.strip()]
        kept = [u for u in existing if u not in remove_set]
        done_path.write_text('\n'.join(kept) + ('\n' if kept else ''), encoding='utf-8')

    def _delete_current(self):
        """刪除歷史記錄中當前選取的那一篇（HTML 檔 + done.txt 紀錄）。"""
        if self._current_idx < 0 or self._mode != 'history':
            return
        art = self._history_articles[self._current_idx]
        fpath = art.get('_file', '')
        if fpath and Path(fpath).exists():
            try:
                Path(fpath).unlink()
            except Exception as e:
                messagebox.showerror('刪除失敗', str(e))
                return
        url = art.get('url', '')
        if url:
            self._remove_urls_from_done([url])
        self._history_articles.pop(self._current_idx)
        # 若 output/ 已全部清空，直接清空 done.txt
        output_dir = self._done_txt_path().parent / 'output'
        if not any(output_dir.glob('*.html')):
            self._done_txt_path().write_text('', encoding='utf-8')
        self._current_idx = -1
        self._set_right_visible(False)
        self._refresh_list()

    def _delete_all(self):
        """刪除所有歷史記錄文章（HTML 檔 + done.txt 紀錄）。"""
        if self._mode != 'history' or not self._history_articles:
            return
        if not messagebox.askyesno('確認', f'確定要刪除全部 {len(self._history_articles)} 篇歷史文章嗎？'):
            return
        failed = []
        urls_to_remove = []
        for art in self._history_articles:
            fpath = art.get('_file', '')
            if fpath and Path(fpath).exists():
                try:
                    Path(fpath).unlink()
                except Exception as e:
                    failed.append(f'{Path(fpath).name}: {e}')
            if art.get('url'):
                urls_to_remove.append(art['url'])
        self._remove_urls_from_done(urls_to_remove)
        # 確保 output/ 清空後 done.txt 也一起清空（防止 URL 匹配失敗殘留舊紀錄）
        output_dir = self._done_txt_path().parent / 'output'
        if not any(output_dir.glob('*.html')):
            self._done_txt_path().write_text('', encoding='utf-8')
        if failed:
            messagebox.showerror('部分刪除失敗', '\n'.join(failed))
        self._history_articles = []
        self._current_idx = -1
        self._set_right_visible(False)
        self._refresh_list()

    # ── done.txt 路徑 ────────────────────────────────────────────────────────

    def _done_txt_path(self) -> Path:
        return self._get_blog_dir() / 'done.txt'

    # ── 開始/停止生成 ────────────────────────────────────────────────────────

    def _toggle_run(self):
        if self._running:
            self._running = False
            self._btn_run.configure(text='開始生成')
            return

        config = cfg.load()
        if not config.get('nvidia_api_key') and not config.get('gemini_api_key'):
            messagebox.showwarning('提醒', '請先到「設定」填入 Gemini 或 NVIDIA API Key')
            return

        self._running = True
        self._btn_run.configure(text='停止')
        self._log.configure(state='normal')
        self._log.delete('1.0', 'end')
        self._log.configure(state='disabled')
        self._lbl_status.configure(text='生成中…', fg='#808080')

        self._articles    = []
        self._current_idx = -1
        self._refresh_list()
        self._set_right_visible(False)

        threading.Thread(target=self._run_blog, daemon=True).start()

    # ── log 輸出 ─────────────────────────────────────────────────────────────

    def _log_write(self, text: str):
        try:
            if self.winfo_exists():
                self.after(0, self._log_write_main, text)
        except tk.TclError:
            pass

    def _log_write_main(self, text: str):
        self._log.configure(state='normal')
        idx = self._log.index('end')
        self._log.insert('end', text + '\n')

        t = text
        if any(c in t for c in ('已儲存', '已生成', '完成', '已更新', '✅', '已複製')):
            tag = 'ok'
        elif any(c in t for c in ('[警告]', '警告', '⚠')):
            tag = 'warn'
        elif any(c in t for c in ('[錯誤]', '錯誤', '失敗', '❌', '[停止]')):
            tag = 'err'
        elif any(c in t for c in ('就緒', '請')):
            tag = 'dim'
        else:
            tag = ''
        if tag:
            self._log.tag_add(tag, idx, 'end-1c')

        self._log.see('end')
        self._log.configure(state='disabled')

    # ── 生成後載入 HTML ──────────────────────────────────────────────────────

    def _load_articles_from_output(self, output_dir: Path, filenames: list[str],
                                    meta: dict = None):
        blog_dir = self._get_blog_dir()
        css_file = blog_dir / 'style.css'
        css = css_file.read_text(encoding='utf-8') if css_file.exists() else ''

        articles = []
        for fname in filenames:
            fpath = output_dir / fname
            try:
                html = fpath.read_text(encoding='utf-8')
                soup = BeautifulSoup(html, 'lxml')

                # 優先用 meta（本次生成），fallback 解析 HTML
                m      = (meta or {}).get(fname, {})
                title  = m.get('title') or (soup.title.get_text(strip=True) if soup.title else fname)
                source = m.get('source', '')
                url    = m.get('url', '')

                if not source:
                    source_a = soup.select_one('.post-meta a')
                    source   = source_a.get_text(strip=True) if source_a else ''
                    url      = source_a.get('href', '') if source_a else ''

                desc_tag = soup.find('meta', attrs={'name': 'description'})
                desc     = m.get('desc') or (desc_tag.get('content', '') if desc_tag else '')
                kw_tag   = soup.find('meta', attrs={'name': 'keywords'})
                kw       = m.get('kw') or (kw_tag.get('content', '') if kw_tag else '')

                # Extract CMS-ready snippet from saved file
                art_div = soup.find('div', class_='article-content')
                if art_div:
                    inner = art_div.decode_contents().strip()
                else:
                    body_tag = soup.find('body')
                    inner = body_tag.decode_contents().strip() if body_tag else html
                cms_content = f'{css}\n<!-- 文章內容開始 -->\n<div class="article-content">\n{inner}\n</div>'

                articles.append({
                    'title':              title,
                    'description':        desc,
                    'keywords':           kw,
                    'content':            cms_content,   # CMS 用（無 DOCTYPE/html 外層）
                    'category':           CATEGORIES[0],
                    'highlight_keywords': '',
                    'confirmed':          False,
                    'source':             source,
                    'url':                url,
                    '_file':              str(fpath),
                })
            except Exception as e:
                self._log_write(f'[載入失敗] {fname}：{e}')
        return articles

    # ── 主生成邏輯 ───────────────────────────────────────────────────────────

    def _run_blog(self):
        import logging
        import os
        import time

        blog_dir = self._get_blog_dir()
        self._blog_dir = blog_dir

        if str(blog_dir) not in sys.path:
            sys.path.insert(0, str(blog_dir))
        if not getattr(sys, 'frozen', False):
            import glob as _glob
            for _pat in ['venv/lib/python*/site-packages', 'venv/Lib/site-packages']:
                for _sp in _glob.glob(str(blog_dir / _pat)):
                    if _sp not in sys.path:
                        sys.path.insert(1, _sp)

        self._log_write('▶ 初始化…')

        class _UiHandler(logging.Handler):
            def __init__(self, cb):
                super().__init__()
                self._cb = cb
            def emit(self, record):
                self._cb(self.format(record))

        handler    = _UiHandler(self._log_write)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%H:%M:%S'))
        blog_logger = logging.getLogger('main')
        blog_logger.addHandler(handler)
        blog_logger.setLevel(logging.INFO)

        generated_files: list[str] = []
        output_dir = blog_dir / 'output'

        try:
            # 先載入 blog-generator 的 .env（含 GEMINI_API_KEY、PROVIDER、MODEL 等）
            from dotenv import load_dotenv as _load_dotenv
            _load_dotenv(str(blog_dir / '.env'), override=True)

            config = cfg.load()
            if config.get('nvidia_api_key'):
                os.environ['NVIDIA_API_KEY'] = config['nvidia_api_key']
            if config.get('gemini_api_key'):
                os.environ['GEMINI_API_KEY'] = config['gemini_api_key']

            try:
                max_n = int(self._max_var.get())
            except ValueError:
                max_n = 5

            self._log_write('載入模組…')
            import importlib
            import main as blog_main
            importlib.reload(blog_main)

            import config as blog_config
            importlib.reload(blog_config)
            blog_config.MAX_PER_RUN = max_n

            # 修正：blog_main 的 DONE_FILE 是相對路徑，CWD 不一定是 blog_dir
            # 強制改成絕對路徑，確保 load/save done.txt 讀寫同一個檔案
            blog_main.DONE_FILE = str(blog_dir / blog_config.DONE_FILE)

            from openai import OpenAI
            output_dir = blog_dir / blog_config.OUTPUT_DIR
            output_dir.mkdir(exist_ok=True)

            client = OpenAI(
                api_key  = blog_config.NVIDIA_API_KEY,
                base_url = blog_config.NVIDIA_BASE_URL,
            )
            self._log_write('API 連線就緒')

            # 確保 prompt.md 有內容
            guidelines = blog_main.load_text(str(blog_dir / 'prompt.md'))
            if not guidelines:
                tone_samples = blog_main.load_text(str(blog_dir / 'tone_samples.txt'))
                if tone_samples:
                    guidelines = blog_main.generate_prompt_from_tone(client, tone_samples)
                    blog_main.save_text(str(blog_dir / 'prompt.md'), guidelines)
                    self._log_write('prompt.md 已生成')
                    time.sleep(blog_config.API_DELAY)
                else:
                    self._log_write('[警告] tone_samples.txt 為空，使用預設指南')
                    guidelines = '使用正體中文、台灣用語，語氣親切活潑，自稱小編。'

            # 抓文章
            self._log_write('抓取網站文章中，請稍候…')

            # 校正 done.txt：若 output 目錄沒有任何 HTML，代表歷史記錄已清空，同步清空 done.txt
            output_dir = blog_dir / blog_config.OUTPUT_DIR
            output_dir.mkdir(exist_ok=True)
            if not any(output_dir.glob('*.html')):
                Path(blog_main.DONE_FILE).write_text('', encoding='utf-8')

            done_urls    = blog_main.load_done_urls()
            all_articles = blog_main.fetch_articles_from_websites()

            deal_articles = [a for a in all_articles if blog_main.is_deal_article(a['title'], a['url'])]
            done_articles = [a for a in all_articles if a['url'] in done_urls
                             and not blog_main.is_deal_article(a['title'], a['url'])]
            new_articles  = [a for a in all_articles
                             if a['url'] not in done_urls
                             and not blog_main.is_deal_article(a['title'], a['url'])]

            self._log_write(f'共 {len(all_articles)} 篇 — 過濾 {len(deal_articles)} 篇優惠文 / 已處理 {len(done_articles)} 篇 / 未處理 {len(new_articles)} 篇')

            if deal_articles:
                self._log_write(f'\n【過濾優惠文 {len(deal_articles)} 篇】')
                for a in deal_articles:
                    self._log_write(f'  ✂ [{a["source"]}] {a["title"]}')

            if done_articles:
                self._log_write(f'\n【已處理 {len(done_articles)} 篇】')
                for a in done_articles:
                    self._log_write(f'  ✓ [{a["source"]}] {a["title"]}')

            if new_articles:
                self._log_write(f'\n【未處理 {len(new_articles)} 篇】')
                for a in new_articles:
                    self._log_write(f'  · [{a["source"]}] {a["title"]}')
                self._log_write('')

            if not new_articles:
                self._log_write('沒有新文章，結束')
                return

            # AI 選文
            top_articles = blog_main.rank_articles_by_traffic(client, new_articles, max_n)
            time.sleep(blog_config.API_DELAY)

            from datetime import datetime, timezone, timedelta
            TW_TZ     = timezone(timedelta(hours=8))
            today_str = datetime.now(TW_TZ).strftime('%Y-%m-%d')
            css          = blog_main.load_text(str(blog_dir / 'style.css'))
            tone_samples = blog_main.load_text(str(blog_dir / 'tone_samples.txt'))

            processed_urls = []

            for idx, article in enumerate(top_articles, 1):
                if not self._running:
                    self._log_write('[停止] 使用者中斷生成')
                    break

                self._log_write(f'[{idx}/{len(top_articles)}] 處理：{article["title"]}')

                content = blog_main.fetch_full_content(article['url'])

                if not self._running:          # 抓完全文後再檢查一次，比等 AI 寫完快得多
                    self._log_write('[停止] 使用者中斷生成')
                    break

                if not content:
                    self._log_write('[警告] 全文擷取失敗，改用摘要')
                    content = article.get('summary', '')
                if not content:
                    self._log_write('[警告] 無可用內容，略過此篇')
                    continue

                try:
                    import re as _re
                    raw = blog_main.rewrite_article(client, article['title'], content, guidelines, css=css, tone_samples=tone_samples)
                    time.sleep(blog_config.API_DELAY)

                    # 解析 AI 輸出的四個 tag
                    title_m = _re.search(r'<title>(.*?)</title>', raw, _re.DOTALL)
                    desc_m  = _re.search(r'<desc>(.*?)</desc>',   raw, _re.DOTALL)
                    kw_m    = _re.search(r'<kw>(.*?)</kw>',       raw, _re.DOTALL)
                    cont_m  = _re.search(r'<content>(.*?)</content>', raw, _re.DOTALL)

                    zh_title   = title_m.group(1).strip() if title_m else article['title']
                    zh_desc    = desc_m.group(1).strip()  if desc_m  else ''
                    zh_kw      = kw_m.group(1).strip()    if kw_m    else ''
                    zh_content = cont_m.group(1).strip()  if cont_m  else raw
                    # AI 有時會把外層 <div class="article-content"> 一起輸出，剝掉它
                    _div_m = _re.match(
                        r'^\s*<div[^>]*class=["\']article-content["\'][^>]*>(.*)</div>\s*$',
                        zh_content, _re.DOTALL | _re.IGNORECASE
                    )
                    if _div_m:
                        zh_content = _div_m.group(1).strip()

                    filename = blog_main.safe_filename(zh_title, today_str)
                    filepath = output_dir / filename
                    full_html = blog_main.build_html(
                        title    = zh_title,
                        content  = zh_content,
                        source   = article['source'],
                        url      = article['url'],
                        date_str = today_str,
                        css      = css,
                        desc     = zh_desc,
                        kw       = zh_kw,
                    )
                    blog_main.save_text(str(filepath), full_html)
                    cms_html = _build_html(
                        title    = zh_title,
                        content  = zh_content,
                        source   = article['source'],
                        url      = article['url'],
                        date_str = today_str,
                        css      = css,
                    )
                    new_art = {
                        'title':              zh_title,
                        'description':        zh_desc,
                        'keywords':           zh_kw,
                        'content':            cms_html,   # CMS 用（無 DOCTYPE/html 外層）
                        'category':           CATEGORIES[0],
                        'highlight_keywords': '',
                        'confirmed':          False,
                        'source':             article['source'],
                        'url':                article['url'],
                        '_file':              str(filepath),
                    }
                    self._log_write(f'已儲存：{zh_title}')
                    generated_files.append(filename)
                    processed_urls.append(article['url'])
                    # 每篇完成立刻推到 UI，不等全部跑完
                    try:
                        if self.winfo_exists():
                            self.after(0, self._append_article, new_art)
                    except tk.TclError:
                        pass

                except Exception as e:
                    self._log_write(f'[錯誤] 處理失敗 {article["url"]}：{e}')
                    continue

            if processed_urls:
                blog_main.save_done_urls(processed_urls)
                self._log_write(f'done.txt 已更新，新增 {len(processed_urls)} 筆')

        except Exception as e:
            import traceback
            self._log_write(f'[錯誤] {e}')
            self._log_write(traceback.format_exc())
        finally:
            blog_logger.removeHandler(handler)
            self._running = False
            try:
                if self.winfo_exists():
                    self.after(0, self._on_generation_done, bool(generated_files))
            except tk.TclError:
                pass

    def _append_article(self, art: dict):
        """每篇文章生成後立刻加進列表（在主執行緒呼叫）。"""
        self._articles.append(art)
        self._refresh_list()
        self._lbl_status.configure(
            text=f'已生成 {len(self._articles)} 篇…', fg='#808080')
        # 第一篇出現時自動開啟
        if len(self._articles) == 1:
            self._select_article(0)

    def _on_generation_done(self, has_articles: bool):
        self._btn_run.configure(text='開始生成')
        if has_articles:
            self._lbl_status.configure(
                text=f'完成，共 {len(self._articles)} 篇', fg='#2a8a2a')
        else:
            self._lbl_status.configure(text='完成（無新文章）', fg='#808080')


# ── HTML 建構（獨立函式，供複製時重新組裝）────────────────────────────────────

_CTA_BLOCK = """\
<hr />
<p>👉 加入官方 LINE，讓我幫你精準找出最值得的一台。<a href="https://lin.ee/9LzFhZu" target="_blank" rel="noopener">點我加入</a></p>
<p>👉 加入我們的 LINE 社群！每天上架馬上報給你知道。<a href="https://line.me/ti/g2/2ofv-ff5V1O6ol0HEWM7USM7BILMry17XjTplg?utm_source=invitation&utm_medium=link_copy&utm_campaign=default" target="_blank" rel="noopener">點我加入社群</a></p>"""


def _build_html(content: str, css: str = '', **_) -> str:
    """CMS-ready snippet: style.css 內容（已含 <style> 標籤）+ 文章內容。"""
    return f"""{css}
<!-- 文章內容開始 -->
<div class="article-content">
{content}
{_CTA_BLOCK}
</div>"""
