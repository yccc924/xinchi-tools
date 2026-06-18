import tkinter as tk
from datetime import datetime

import core.config as cfg
from core.shortcuts import install_edit_menu
from core.win95 import WIN_BG, TXT_FG, SEL_BG, SEL_FG, _F, _FS

# ── Palette ───────────────────────────────────────────────────────────────────
DESKTOP_BG = "#7a7a7a"
PLATINUM   = "#d4d0c8"
INK        = "#161616"
ICON_SEL   = "#2358e6"
BAR_BORDER = "#76736c"

TOOLS = [
    ('combined',    '製作 & 報價', '#4a7fc1'),
    ('price_check', '價格稽核',    '#c14a4a'),
    ('blog',        '部落格',      '#4ac14a'),
    ('settings',    '設定',        '#8888aa'),
]


def _shade(color: str, amt: int) -> str:
    h = color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'#{max(0,min(255,r+amt)):02x}{max(0,min(255,g+amt)):02x}{max(0,min(255,b+amt)):02x}'


class DesktopIcon(tk.Frame):
    """Mac OS 9 desktop icon with per-tool glyph."""

    def __init__(self, master, key: str, label: str, color: str, on_open, **kwargs):
        super().__init__(master, bg=DESKTOP_BG, cursor='hand2', **kwargs)
        self._key     = key
        self._color   = color
        self._on_open = on_open

        self._cv = tk.Canvas(self, width=54, height=54,
                              bg=DESKTOP_BG, highlightthickness=0)
        self._cv.pack()
        self._draw_icon()

        self._lbl = tk.Label(self, text=label, font=(_F, _FS),
                             bg=DESKTOP_BG, fg='white',
                             padx=3, pady=1, wraplength=82, justify='center')
        self._lbl.pack()

        for w in (self, self._cv, self._lbl):
            w.bind('<Button-1>',        self._on_click)
            w.bind('<Double-Button-1>', self._on_dbl)

    # ── Icon drawing ──────────────────────────────────────────────────────────

    def _draw_icon(self):
        c = self._cv
        c.delete('all')
        col = self._color
        x1, y1, x2, y2 = 3, 3, 51, 51
        mid_y = (y1 + y2) // 2

        # Drop shadow
        c.create_rectangle(x1+4, y1+4, x2+4, y2+4, fill='#303030', outline='')

        # Tile – gradient via two halves
        c.create_rectangle(x1, y1, x2, mid_y, fill=_shade(col, 20), outline='')
        c.create_rectangle(x1, mid_y, x2, y2,  fill=_shade(col, -15), outline='')

        # Outer border
        c.create_rectangle(x1, y1, x2, y2, fill='', outline='#111111', width=1)

        # Inset highlight (top + left edges)
        c.create_line(x1+1, y1+1, x2-1, y1+1, fill='#d8d8d8')
        c.create_line(x1+1, y1+1, x1+1, y2-1, fill='#d8d8d8')

        # Per-tool glyph
        gx1, gy1, gx2, gy2 = x1+5, y1+5, x2-5, y2-5
        fn = {
            'combined':    self._glyph_quote,
            'price_check': self._glyph_audit,
            'blog':        self._glyph_blog,
            'settings':    self._glyph_settings,
        }.get(self._key)
        if fn:
            fn(c, gx1, gy1, gx2, gy2)

    def _glyph_quote(self, c, x1, y1, x2, y2):
        # Picture frame with mountain + sun
        c.create_rectangle(x1+1, y1+2, x2-1, y2, outline='white', fill='', width=2)
        mid = (x1 + x2) // 2
        c.create_polygon(x1+2, y2-2, mid-3, y1+10, mid+3, y1+16, x2-4, y1+10, x2-2, y2-2,
                         fill='white', outline='')
        c.create_oval(x1+2, y1+2, x1+10, y1+10, fill='#ffd060', outline='white', width=1)

    def _glyph_audit(self, c, x1, y1, x2, y2):
        # Magnifying glass with check mark
        cx, cy, r = x1+12, y1+12, 9
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline='white', fill='', width=2)
        c.create_line(cx+r-3, cy+r-3, x2, y2, fill='white', width=3)
        c.create_line(cx-4, cy+1, cx-1, cy+5, fill='white', width=2)
        c.create_line(cx-1, cy+5, cx+5, cy-3, fill='white', width=2)

    def _glyph_blog(self, c, x1, y1, x2, y2):
        # Document + pencil
        dx2 = x2 - 9
        c.create_rectangle(x1, y1+1, dx2, y2, outline='white', fill='', width=2)
        for ly in [y1+8, y1+14, y1+20]:
            c.create_line(x1+4, ly, dx2-4, ly, fill='white', width=1)
        # Pencil
        c.create_polygon(x2-8, y1, x2, y1+2, x2-1, y1+18, x2-9, y1+16,
                         fill='#ffd060', outline='white', width=1)
        c.create_polygon(x2-9, y1+16, x2-1, y1+18, x2-2, y1+22, x2-10, y1+20,
                         fill='#444444', outline='')

    def _glyph_settings(self, c, x1, y1, x2, y2):
        # Three slider lines with knobs
        knob_x = [x2-5, x1+8, x2-8]
        for i, ly in enumerate([y1+6, y1+14, y1+22]):
            c.create_line(x1, ly, x2, ly, fill='white', width=2)
            kx = knob_x[i]
            c.create_oval(kx-5, ly-5, kx+5, ly+5,
                          fill=_shade(self._color, -30), outline='white', width=1)

    # ── Selection ─────────────────────────────────────────────────────────────

    def select(self):
        self._lbl.configure(bg=ICON_SEL)

    def deselect(self):
        self._lbl.configure(bg=DESKTOP_BG)

    def _on_click(self, e):
        self.event_generate('<<IconClick>>', when='tail')
        self.select()

    def _on_dbl(self, e):
        self._on_open()


class MacDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('炘馳工具箱')
        self.geometry('960x680')
        self.minsize(640, 480)
        self.configure(bg=DESKTOP_BG)

        # Remove native macOS title bar (traffic lights + space) before showing
        self.withdraw()
        try:
            self.tk.call('tk::unsupported::MacWindowStyle', 'style',
                         self._w, 'document', 'noTitleBar')
        except Exception:
            pass
        self.deiconify()

        self._config  = cfg.load()
        self._windows: dict[str, tk.Toplevel] = {}
        self._pages:   dict[str, tk.Frame]    = {}
        self._icons:   list[DesktopIcon]      = []
        self._clock_id = None
        self._dsk_drag: dict = {}

        self._build_menubar()
        self._build_desktop()

        # Desktop background: click to deselect; drag to move window
        self.bind('<ButtonPress-1>',   self._desktop_press)
        self.bind('<B1-Motion>',       self._desktop_drag)
        self.bind('<<IconClick>>',     self._deselect_all)

        # 原生 macOS 選單列：先建 menubar 加「工具」，再交由 install_edit_menu 加 Edit
        import sys as _sys
        if _sys.platform == 'darwin':
            import tkinter as _tk
            _native_bar = _tk.Menu(self)
            _tools_menu = _tk.Menu(_native_bar, tearoff=0)
            for _k, _lbl, _ in TOOLS:
                _tools_menu.add_command(label=_lbl,
                                        command=lambda k=_k: self._open_tool(k))
            _native_bar.add_cascade(label='工具', menu=_tools_menu)
        else:
            _native_bar = None
        self._edit_menubar = install_edit_menu(self, menubar=_native_bar)

        # Cmd+W closes the focused tool window
        for seq in ('<Command-w>', '<Meta-w>'):
            self.bind_all(seq, self._close_focused_tool)

    # ── Menu bar (Canvas gradient) ────────────────────────────────────────────

    def _build_menubar(self):
        self._bar = tk.Canvas(self, height=22, highlightthickness=0, bd=0)
        self._bar.pack(side='top', fill='x')
        tk.Frame(self, bg=BAR_BORDER, height=1).pack(side='top', fill='x')
        self._bar.bind('<Configure>', self._draw_menubar)
        self.after(80, self._draw_menubar)
        self.after(120, self._tick)   # start clock after first draw

    def _draw_menubar(self, event=None):
        c = self._bar
        w = c.winfo_width()
        if w <= 1:
            return
        c.delete('all')

        # Gradient: #fbfaf7 → #ddd9d0 (55%) → #cfcabf
        top = (0xfb, 0xfa, 0xf7)
        mi  = (0xdd, 0xd9, 0xd0)
        bot = (0xcf, 0xca, 0xbf)
        for y in range(22):
            t = y / 21.0
            if t < 0.55:
                s = t / 0.55
                rgb = tuple(int(top[i] + (mi[i]  - top[i]) * s) for i in range(3))
            else:
                s = (t - 0.55) / 0.45
                rgb = tuple(int(mi[i]  + (bot[i] - mi[i])  * s) for i in range(3))
            c.create_line(0, y, w, y, fill='#{:02x}{:02x}{:02x}'.format(*rgb))
        c.create_line(0, 0, w, 0, fill='#ffffff')   # inset white highlight

        fn  = (_F, _FS)
        fna = (_F, _FS + 2, 'bold')

        # Window control dots: red (quit), yellow (minimize), green (zoom)
        DOT_Y, DOT_R = 11, 5
        for x, col, cmd in [
            (8,  '#ff5f57', lambda e: self._quit()),
            (20, '#febc2e', lambda e: self.iconify()),
            (32, '#28c840', lambda e: self._toggle_zoom()),
        ]:
            dot = c.create_oval(x-DOT_R, DOT_Y-DOT_R, x+DOT_R, DOT_Y+DOT_R,
                                fill=col, outline=_shade(col, -30), width=1)
            c.tag_bind(dot, '<Button-1>', cmd)

        apple = c.create_text(52, 11, text='⌘', font=fna, fill=INK, anchor='center')
        c.tag_bind(apple, '<Button-1>', lambda e: self._show_apple_menu(40))

        self._clock_id = c.create_text(w - 8, 11, text='', font=fn, fill=INK, anchor='e')

    def _tick(self):
        now  = datetime.now()
        h    = now.hour
        ampm = '上午' if h < 12 else '下午'
        h12  = h % 12 or 12
        ts   = f'{ampm} {h12}:{now.minute:02d}'
        if self._clock_id is not None:
            try:
                w = self._bar.winfo_width()
                self._bar.coords(self._clock_id, w - 8, 11)
                self._bar.itemconfig(self._clock_id, text=ts)
            except Exception:
                return  # widget 已 destroy，停止排程
        try:
            self.after(20000, self._tick)
        except Exception:
            pass

    def _show_apple_menu(self, x_off: int):
        menu = tk.Menu(self, tearoff=0,
                       bg=PLATINUM, fg=TXT_FG,
                       activebackground=SEL_BG, activeforeground=SEL_FG,
                       font=(_F, _FS))
        menu.add_command(label='關於炘馳工具箱…', command=self._show_about)
        menu.add_separator()
        menu.add_command(label='結束', command=self._quit)
        rx = self._bar.winfo_rootx() + x_off
        ry = self._bar.winfo_rooty() + 23
        try:
            menu.tk_popup(rx, ry)
        finally:
            menu.grab_release()

    def _show_about(self):
        from tkinter import messagebox
        messagebox.showinfo('關於炘馳工具箱',
                            '炘馳工具箱\n\n製作 & 報價 / 價格稽核 / 部落格\n\nMac OS 9 Edition')

    def _toggle_zoom(self):
        if self.wm_state() == 'zoomed':
            self.wm_state('normal')
        else:
            try:
                self.wm_state('zoomed')
            except Exception:
                pass

    # ── Desktop icons ─────────────────────────────────────────────────────────

    def _build_desktop(self):
        for i, (key, label, color) in enumerate(TOOLS):
            ico = DesktopIcon(self, key, label, color,
                              on_open=lambda k=key: self._open_tool(k))
            ico.place(x=14, y=34 + i * 82)
            self._icons.append(ico)

    def _deselect_all(self, event=None):
        for ico in self._icons:
            ico.deselect()

    def _desktop_press(self, e):
        self._deselect_all()
        self._dsk_drag = {
            'x0': e.x_root, 'y0': e.y_root,
            'wx': self.winfo_x(), 'wy': self.winfo_y(),
        }

    def _desktop_drag(self, e):
        if not self._dsk_drag:
            return
        nx = self._dsk_drag['wx'] + (e.x_root - self._dsk_drag['x0'])
        ny = self._dsk_drag['wy'] + (e.y_root - self._dsk_drag['y0'])
        self.geometry(f'+{nx}+{ny}')

    # ── Tool windows ──────────────────────────────────────────────────────────

    def _open_tool(self, key: str):
        if key in self._windows and self._windows[key].winfo_exists():
            self._windows[key].lift()
            self._windows[key].focus_force()
            return

        n   = len([w for w in self._windows.values() if w.winfo_exists()])
        win = tk.Toplevel(self)
        # Hide immediately so we can set style before it appears
        win.withdraw()
        try:
            win.tk.call('tk::unsupported::MacWindowStyle', 'style',
                        win._w, 'document', 'noTitleBar')
        except Exception:
            win.overrideredirect(True)   # fallback if Tcl call unsupported
        name = next(l for k, l, _ in TOOLS if k == key)
        win.title(name)
        win.geometry(f'1050x720+{140 + n*22}+{34 + n*22}')
        win.configure(bg=WIN_BG)

        self._add_win_titlebar(win, name, key)

        config = cfg.load()
        if key == 'combined':
            from pages.combined_page import CombinedPage
            page = CombinedPage(win, config)
        elif key == 'price_check':
            from pages.price_check_page import PriceCheckPage
            page = PriceCheckPage(win, config)
        elif key == 'blog':
            from pages.blog_page import BlogPage
            page = BlogPage(win, config)
        elif key == 'settings':
            from pages.settings_page import SettingsPage
            page = SettingsPage(win, config, on_save=lambda: cfg.load())
        else:
            win.destroy()
            return

        page.pack(fill='both', expand=True)
        self._pages[key]   = page
        self._windows[key] = win
        win.protocol('WM_DELETE_WINDOW', lambda k=key: self._close_tool(k))
        # Show only after all content is built (prevents flash)
        win.deiconify()
        win.lift()
        win.focus_force()

    def _add_win_titlebar(self, win: tk.Toplevel, title: str, key: str):
        """Mac OS 9 pinstripe title bar drawn on a Canvas."""
        tb = tk.Canvas(win, height=20, highlightthickness=0, bd=0, bg=PLATINUM)
        tb.pack(fill='x', side='top')
        tk.Frame(win, bg='#84817a', height=1).pack(fill='x', side='top')

        _drag: dict = {}
        _prev_geom: list = [None]   # survives redraws; tracks pre-zoom geometry

        def _zoom_toggle(e, w=win):
            if _prev_geom[0]:
                w.geometry(_prev_geom[0])
                _prev_geom[0] = None
            else:
                _prev_geom[0] = w.geometry()
                w.geometry(f'{w.winfo_screenwidth()}x{w.winfo_screenheight()}+0+0')
            return 'break'

        def _redraw(e=None):
            tb_w = tb.winfo_width()
            if tb_w <= 1:
                return
            tb.delete('all')

            # Pinstripes: dark / light alternating
            for y in range(0, 20, 2):
                tb.create_line(0, y, tb_w, y, fill='#cdc8bc')
            for y in range(1, 20, 2):
                tb.create_line(0, y, tb_w, y, fill='#efece4')

            # Colored control dots (macOS style: red=close, yellow=minimize, green=zoom)
            DOT_Y, DOT_R = 10, 5
            # Close (red) — left side
            close_dot = tb.create_oval(8-DOT_R, DOT_Y-DOT_R, 8+DOT_R, DOT_Y+DOT_R,
                                        fill='#ff5f57', outline='#e0443e', width=1)
            tb.tag_bind(close_dot, '<Button-1>',
                        lambda e, k=key: (self._close_tool(k), 'break')[1])
            # Minimize (yellow) — iconify to Dock
            min_dot = tb.create_oval(24-DOT_R, DOT_Y-DOT_R, 24+DOT_R, DOT_Y+DOT_R,
                                      fill='#febc2e', outline='#d9a025', width=1)
            tb.tag_bind(min_dot, '<Button-1>',
                        lambda e, w=win: (w.iconify(), 'break')[1])
            # Zoom (green)
            zoom_dot = tb.create_oval(40-DOT_R, DOT_Y-DOT_R, 40+DOT_R, DOT_Y+DOT_R,
                                       fill='#28c840', outline='#14a02e', width=1)
            tb.tag_bind(zoom_dot, '<Button-1>', _zoom_toggle)

            # Title: draw then cover pinstripes behind it with platinum rect
            tid = tb.create_text(tb_w // 2, 10, text=title,
                                  font=(_F, _FS, 'bold'), fill='#1b1b1b')
            bbox = tb.bbox(tid)
            if bbox:
                bg = tb.create_rectangle(bbox[0]-10, 1, bbox[2]+10, 19,
                                          fill=PLATINUM, outline='')
                tb.tag_raise(tid, bg)

        tb.bind('<Configure>', _redraw)

        def _press(e):
            _drag['x0'] = e.x_root
            _drag['y0'] = e.y_root
            _drag['wx'] = win.winfo_x()
            _drag['wy'] = win.winfo_y()

        def _motion(e):
            if not _drag:
                return
            nx = _drag['wx'] + (e.x_root - _drag['x0'])
            ny = max(23, _drag['wy'] + (e.y_root - _drag['y0']))
            win.geometry(f'+{nx}+{ny}')

        tb.bind('<ButtonPress-1>', _press)
        tb.bind('<B1-Motion>',    _motion)

    def _quit(self):
        """先停所有背景執行緒，150 ms 後再 destroy，避免 after() 回呼讀到已釋放的 C widget。"""
        for page in self._pages.values():
            if hasattr(page, '_running'):
                page._running = False
        self.after(150, self.destroy)

    def _close_tool(self, key: str):
        if key in self._pages:
            page = self._pages.pop(key)
            if hasattr(page, '_running'):
                page._running = False
        if key in self._windows:
            self._windows[key].destroy()
            del self._windows[key]

    def _close_focused_tool(self, e=None):
        # Try Tk focus first
        focused = self.focus_get()
        if focused and focused is not self:
            top = focused.winfo_toplevel()
            for key, win in list(self._windows.items()):
                if win.winfo_exists() and win is top:
                    self._close_tool(key)
                    return 'break'
        # Fallback: find which tool window is under the mouse pointer
        mx, my = self.winfo_pointerxy()
        for key, win in list(self._windows.items()):
            if not win.winfo_exists():
                continue
            wx, wy = win.winfo_rootx(), win.winfo_rooty()
            ww, wh = win.winfo_width(), win.winfo_height()
            if wx <= mx <= wx + ww and wy <= my <= wy + wh:
                self._close_tool(key)
                return 'break'
        return 'break'


if __name__ == '__main__':
    MacDesktop().mainloop()
