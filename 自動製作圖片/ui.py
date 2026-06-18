import re
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from image_engine import render

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None

OUTPUT_DIR = Path(__file__).parent / 'output'

_COLORS = [
    '深空黑', '黑色鈦金屬', '白色鈦金屬', '原色鈦金屬', '自然鈦金屬',
    '星光色', '午夜色', '黑色', '白色', '藍色', '紅色', '綠色',
    '紫色', '金色', '銀色', '灰色', '粉色', '黃色',
]


def _auto_warranty(model: str) -> str:
    """根據機型自動推算店保天數：iPhone 12+ / Air = 90天，其餘 = 30天"""
    m = model.upper()
    if 'IPHONE' not in m:
        return '30天'                               # Android
    if re.search(r'\bX[SR]?\b', m):                # X / XS / XR
        return '30天'
    if re.search(r'\bSE\b', m):                    # SE 系列
        return '30天'
    if re.search(r'\bAIR\b', m):                   # iPhone Air
        return '90天'
    num = re.search(r'IPHONE\s*(\d+)', m)
    if num and int(num.group(1)) >= 12:
        return '90天'
    return '30天'

# ── 跨平台剪貼板（macOS: pbpaste/pbcopy；其他: tkinter）──────────────

def _pb_get() -> str:
    if sys.platform == 'darwin':
        return subprocess.run(['pbpaste'], capture_output=True, text=True).stdout
    try:
        import tkinter as _tk
        _r = _tk.Tk(); _r.withdraw()
        text = _r.clipboard_get(); _r.destroy()
        return text
    except Exception:
        return ''

def _pb_set(text: str):
    if sys.platform == 'darwin':
        subprocess.run(['pbcopy'], input=text, text=True)
    else:
        import tkinter as _tk
        _r = _tk.Tk(); _r.withdraw()
        _r.clipboard_clear(); _r.clipboard_append(text)
        _r.update(); _r.destroy()


# ── 解析 ──────────────────────────────────────────────────────────────

def parse_one(text: str) -> dict:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    out = dict(model='', capacity='', serial='', color='',
               battery='', condition='', warranty='')
    if not lines:
        return out
    first = lines[0]
    full  = '\n'.join(lines)   # 所有行合併，供保固搜尋用

    m = re.search(r'電池[健康度]*\s*[:：]?\s*(\d+)\s*%?', first, re.IGNORECASE)
    if m:
        out['battery'] = m.group(1)
    m = re.search(r'#\s*(\w+)', first)
    if m:
        out['serial'] = m.group(1)
    m = re.search(r'(\d+\s*[GT]B)', first, re.IGNORECASE)
    if m:
        out['capacity'] = m.group(1).upper().replace(' ', '')
    for c in _COLORS:
        if c in first:
            out['color'] = c
            break
    # 明確保固：支援「保固20261230」及「保固2026/12/30」兩種格式，搜尋所有行
    m = re.search(r'保固\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', full)
    if m:
        out['warranty'] = f"保固{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    else:
        m = re.search(r'保固\s*(\d{6,})', full)
        if m:
            out['warranty'] = '保固' + m.group(1)
        else:
            # 明確天數：「N天」「N個月」「N年」（只找第一行，避免條件備註誤判）
            m = re.search(r'(\d+\s*(?:天|個月|月|年))', first)
            if m:
                out['warranty'] = m.group(1)

    clean = first
    for pat in [r'電池[健康度]*\s*[:：]?\s*\d+\s*%?(?:\s*[（(]\d+[）)])?', r'#\s*\w+', r'\d+\s*[GT]B',
                r'\$[\d,]+', r'有盒|無盒|原廠盒|全配',
                r'(?:原廠)?保固[\d/\-]*', r'\d+\s*(?:天|個月|月|年)',
                r'原廠', r'\b0\b']:
        clean = re.sub(pat, '', clean, flags=re.IGNORECASE)
    if out['color']:
        clean = clean.replace(out['color'], '')
    # 移除殘留中文字及特殊符號，確保 model 只含英數字
    clean = re.sub(r'[一-鿿㐀-䶿＀-￯]+', '', clean)
    clean = re.sub(r'[^\w\s]', ' ', clean)
    clean = re.sub(r'\b\d{3,}\b', '', clean)   # 移除獨立的 3 位以上數字（非機型編號）
    out['model'] = ' '.join(clean.split())

    # 若無明確保固，根據機型自動推算
    if not out['warranty']:
        out['warranty'] = _auto_warranty(out['model'])

    parts = []
    box = re.search(r'(有盒|無盒|原廠盒|全配)', first)
    if box:
        parts.append(box.group(1))
    for line in lines[1:]:
        if not re.match(r'^\$[\d,]+$', line):
            parts.append(line)
    out['condition'] = '  '.join(parts)
    return out


def parse_all(raw: str) -> list[dict]:
    blocks = re.split(r'\n{2,}', raw.strip())
    return [parse_one(b) for b in blocks if b.strip()]


# ── 快捷鍵與右鍵選單（用 pbpaste/pbcopy，繞過 tkinter 限制）──────────

def _do_paste(widget):
    clip = _pb_get()
    if not clip:
        return
    if isinstance(widget, tk.Text):
        try:
            widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        widget.insert(tk.INSERT, clip)
    elif isinstance(widget, tk.Entry):
        try:
            widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        widget.insert(tk.INSERT, clip)


def _do_copy(widget):
    try:
        sel = (widget.get(tk.SEL_FIRST, tk.SEL_LAST)
               if isinstance(widget, tk.Text) else widget.selection_get())
        _pb_set(sel)
    except tk.TclError:
        pass


def _do_cut(widget):
    try:
        if isinstance(widget, tk.Text):
            sel = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        else:
            sel = widget.selection_get()
            widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        _pb_set(sel)
    except tk.TclError:
        pass


def _do_select_all(widget):
    if isinstance(widget, tk.Text):
        widget.tag_add(tk.SEL, '1.0', tk.END)
    elif isinstance(widget, tk.Entry):
        widget.select_range(0, tk.END)


def _attach(app: 'App', widget: tk.Widget):
    """綁定快捷鍵 + 右鍵選單到指定元件"""

    # 快捷鍵：同時綁 Command 和 Meta（不同 macOS Tk 版本用不同 modifier）
    def _paste(e):  _do_paste(e.widget);  return 'break'
    def _copy(e):   _do_copy(e.widget);   return 'break'
    def _cut(e):    _do_cut(e.widget);    return 'break'
    def _selall(e): _do_select_all(e.widget); return 'break'

    for mod in ('<Command-', '<Meta-'):
        widget.bind(f'{mod}v>', _paste)
        widget.bind(f'{mod}c>', _copy)
        widget.bind(f'{mod}x>', _cut)
        widget.bind(f'{mod}a>', _selall)

    # 右鍵選單
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label='剪下',  command=lambda: _do_cut(widget))
    menu.add_command(label='複製',  command=lambda: _do_copy(widget))
    menu.add_command(label='貼上',  command=lambda: _do_paste(widget))
    menu.add_separator()
    menu.add_command(label='全選',  command=lambda: _do_select_all(widget))

    def show_menu(e):
        widget.focus_set()
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    widget.bind('<Button-2>', show_menu)
    widget.bind('<Button-3>', show_menu)
    widget.bind('<Control-Button-1>', show_menu)


# ── 主視窗 ────────────────────────────────────────────────────────────

def _parse_dnd(data: str) -> list[Path]:
    """解析 tkinterdnd2 拖曳路徑（處理含空格的路徑）"""
    result = []
    for m in re.finditer(r'\{([^}]+)\}|([^\s{}]+)', data):
        p = Path(m.group(1) or m.group(2))
        if p.exists():
            result.append(p)
    return result


_SUPPORTED = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('炘馳通訊 — 批次圖片製作')
        self.geometry('820x680')
        self.minsize(700, 500)
        self._images: list[Path] = []
        self._has_dnd = False
        self._editing_widget = None   # 追蹤最後獲得焦點的文字元件
        self.bind_all('<FocusIn>', self._on_focus_in)
        self._build()

    def _build(self):
        # macOS Edit 選單（系統層級 Cmd+C/V/X/A 路由）
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        edit = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='Edit', menu=edit)
        edit.add_command(label='Cut',        accelerator='Command+X',
                        command=lambda: _do_cut(self._editing_widget))
        edit.add_command(label='Copy',       accelerator='Command+C',
                        command=lambda: _do_copy(self._editing_widget))
        edit.add_command(label='Paste',      accelerator='Command+V',
                        command=lambda: _do_paste(self._editing_widget))
        edit.add_separator()
        edit.add_command(label='Select All', accelerator='Command+A',
                        command=lambda: _do_select_all(self._editing_widget))

        # 頂部標題列
        bar = tk.Frame(self, bg='#2b2b2b')
        bar.pack(fill='x')
        tk.Label(bar, text='炘馳通訊  批次圖片製作',
                font=('System', 15, 'bold'), fg='#e85d18',
                bg='#2b2b2b').pack(side='left', padx=14, pady=10)

        # 主區域
        mid = tk.Frame(self)
        mid.pack(fill='both', expand=True, padx=10, pady=(8, 4))

        # 左：機況文字
        lf = tk.LabelFrame(mid, text='  機況文字（每筆用空行隔開）  ',
                           font=('System', 13, 'bold'))
        lf.pack(side='left', fill='both', expand=True, padx=(0, 6))

        self.txt = tk.Text(lf, font=('System', 13), wrap='word',
                          relief='flat', borderwidth=0)
        sb_txt = ttk.Scrollbar(lf, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb_txt.set)
        sb_txt.pack(side='right', fill='y')
        self.txt.pack(fill='both', expand=True, padx=6, pady=6)
        _attach(self, self.txt)
        self.txt.bind('<KeyRelease>', lambda e: self._refresh_status())

        # 右：圖片清單
        rf = tk.LabelFrame(mid, text='  圖片清單（依檔名排序）  ',
                           font=('System', 13, 'bold'), width=230)
        rf.pack(side='right', fill='both', padx=(6, 0))
        rf.pack_propagate(False)

        self.lb = tk.Listbox(rf, font=('System', 12), activestyle='none',
                            selectbackground='#e85d18', width=26)
        sb_lb = ttk.Scrollbar(rf, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb_lb.set)
        sb_lb.pack(side='right', fill='y')
        self.lb.pack(fill='both', expand=True, padx=6, pady=(6, 0))

        self.lbl_drop = tk.Label(rf, text='拖曳照片至此處',
                                 font=('System', 11), fg='#aaaaaa')
        self.lbl_drop.pack(pady=(2, 4))

        if self._has_dnd:
            for target in (self.lb, rf, self.lbl_drop):
                target.drop_target_register(DND_FILES)
                target.dnd_bind('<<Drop>>', self._on_drop)

        bf = tk.Frame(rf)
        bf.pack(fill='x', padx=6, pady=(0, 6))
        tk.Button(bf, text='選擇圖片', command=self._pick,
                 font=('System', 12), padx=6).pack(side='left')
        tk.Button(bf, text='清除', command=self._clear,
                 font=('System', 12), fg='#cc3333').pack(side='right')

        # 匹配狀態
        self.lbl_match = tk.Label(self, text='', font=('System', 12),
                                 anchor='w')
        self.lbl_match.pack(fill='x', padx=14, pady=2)

        ttk.Separator(self, orient='horizontal').pack(fill='x', padx=10, pady=4)

        # 底部
        bot = tk.Frame(self)
        bot.pack(fill='x', padx=10, pady=(2, 12))
        tk.Button(bot, text='全部產生', command=self._run,
                 bg='#e85d18', fg='white', font=('System', 15, 'bold'),
                 relief='flat', padx=24, pady=8).pack(side='left')
        self.lbl_status = tk.Label(bot, text='就緒', fg='gray',
                                  font=('System', 12))
        self.lbl_status.pack(side='left', padx=14)

    def _on_focus_in(self, e):
        if isinstance(e.widget, (tk.Text, tk.Entry)):
            self._editing_widget = e.widget

    def _refresh_listbox(self):
        self.lb.delete(0, tk.END)
        for i, p in enumerate(self._images, 1):
            self.lb.insert(tk.END, f'{i}. {p.name}')
        hint = '' if self._images else '拖曳照片至此處'
        self.lbl_drop.config(text=hint)

    def _on_drop(self, e):
        new = [p for p in _parse_dnd(e.data)
               if p.suffix.lower() in _SUPPORTED]
        combined = sorted(set(self._images) | set(new), key=lambda p: p.name)
        self._images = combined
        self._refresh_listbox()
        self._refresh_status()

    def _pick(self):
        paths = filedialog.askopenfilenames(
            initialdir=str(Path(__file__).parent / 'input'),
            filetypes=[('圖片', '*.jpg *.jpeg *.png *.webp *.avif'), ('全部', '*.*')],
        )
        if not paths:
            return
        self._images = sorted([Path(p) for p in paths], key=lambda p: p.name)
        self._refresh_listbox()
        self._refresh_status()

    def _clear(self):
        self._images = []
        self._refresh_listbox()
        self._refresh_status()

    def _refresh_status(self):
        nc = len(parse_all(self.txt.get('1.0', tk.END)))
        ni = len(self._images)
        if nc == 0 and ni == 0:
            self.lbl_match.config(text='', fg='gray')
        elif nc == ni and nc > 0:
            self.lbl_match.config(
                text=f'✓  {nc} 筆機況  ←→  {ni} 張圖片，順序對齊，可以產生',
                fg='#2a8a2a')
        else:
            self.lbl_match.config(
                text=f'⚠  機況 {nc} 筆  vs  圖片 {ni} 張，數量不符！',
                fg='#cc3333')

    def _run(self):
        conditions = parse_all(self.txt.get('1.0', tk.END))
        if not conditions:
            messagebox.showwarning('提醒', '請貼上機況文字')
            return
        if not self._images:
            messagebox.showwarning('提醒', '請選擇圖片')
            return
        if len(conditions) != len(self._images):
            messagebox.showwarning(
                '數量不符',
                f'機況 {len(conditions)} 筆，圖片 {len(self._images)} 張\n'
                '請確認兩邊數量一致。')
            return

        OUTPUT_DIR.mkdir(exist_ok=True)
        done = err = 0
        self.lbl_status.config(text='產生中…', fg='gray')
        self.update()

        for d, img_path in zip(conditions, self._images):
            out = OUTPUT_DIR / (img_path.stem + '.jpg')
            try:
                render(image_path=img_path, output_path=out, **d)
                done += 1
            except Exception as ex:
                err += 1
                print(f'[錯誤] {img_path.name}: {ex}')

        msg = f'完成 {done} 張，已存至 output/'
        if err:
            msg += f'（失敗 {err} 張）'
        self.lbl_status.config(text=msg,
                               fg='#2a8a2a' if not err else '#cc3333')


if __name__ == '__main__':
    App().mainloop()
