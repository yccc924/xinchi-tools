import sys
import tkinter as tk

try:
    import pyperclip as _pyperclip
    def _pbcopy(text: str):
        try: _pyperclip.copy(text)
        except Exception: pass
    def _pbpaste() -> str:
        try: return _pyperclip.paste()
        except Exception: return ''
except ImportError:
    # pyperclip 未安裝時的備用方案（不建立新 Tk root，改用 after 傳入 widget）
    def _pbcopy(text: str):
        try:
            r = tk.Tk(); r.withdraw()
            r.clipboard_clear(); r.clipboard_append(text)
            r.update(); r.destroy()
        except Exception: pass
    def _pbpaste() -> str:
        try:
            r = tk.Tk(); r.withdraw()
            t = r.clipboard_get(); r.destroy(); return t
        except Exception: return ''


# ── 右鍵選單（CTkTextbox 專用）───────────────────────────────────────────────

def attach(widget, readonly: bool = False):
    """為 tk.Text 或 tk.Entry 加右鍵選單與快捷鍵。"""
    if isinstance(widget, tk.Entry):
        _attach_entry(widget, readonly)
        return
    w = widget

    def _copy():
        try: _pbcopy(w.get(tk.SEL_FIRST, tk.SEL_LAST))
        except tk.TclError: pass

    def _cut():
        if readonly: return
        try:
            _pbcopy(w.get(tk.SEL_FIRST, tk.SEL_LAST))
            w.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError: pass

    def _paste():
        if readonly: return
        text = _pbpaste()
        if not text: return
        try: w.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError: pass
        w.insert(tk.INSERT, text)

    def _select_all():
        w.tag_add(tk.SEL, '1.0', tk.END)

    menu = tk.Menu(w, tearoff=0)
    if not readonly:
        menu.add_command(label='剪下', command=_cut)
    menu.add_command(label='複製', command=_copy)
    if not readonly:
        menu.add_command(label='貼上', command=_paste)
    menu.add_separator()
    menu.add_command(label='全選', command=_select_all)

    def show_menu(e):
        w.focus_set()
        try: menu.tk_popup(e.x_root, e.y_root)
        finally: menu.grab_release()

    w.bind('<Button-2>', show_menu)
    w.bind('<Button-3>', show_menu)
    if sys.platform == 'darwin':
        w.bind('<Control-Button-1>', show_menu)

    # Direct keyboard shortcuts on the widget (macOS only).
    # macOS intercepts Cmd+C/X/V at the OS level — they never arrive as
    # <Command-c> key events in Tk. Only the virtual events <<Copy>>,
    # <<Cut>>, <<Paste>> fire. Cmd+A and Cmd+Z do fire as <Meta-/Command->.
    if sys.platform == 'darwin':
        def _kb_copy(e=None):
            try: _pbcopy(w.get(tk.SEL_FIRST, tk.SEL_LAST))
            except tk.TclError: pass
            # No 'break' — let the native class binding also run so the
            # selection highlight stays correct.

        def _kb_cut(e=None):
            if readonly: return 'break'
            try:
                _pbcopy(w.get(tk.SEL_FIRST, tk.SEL_LAST))
                w.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError: pass
            return 'break'

        def _kb_paste(e=None):
            if readonly: return 'break'
            text = _pbpaste()
            if text:
                try: w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except tk.TclError: pass
                w.insert(tk.INSERT, text)
            return 'break'      # prevent double-paste from class binding

        def _kb_select_all(e=None):
            w.tag_add(tk.SEL, '1.0', tk.END)
            w.mark_set(tk.INSERT, tk.END)
            return 'break'

        def _kb_undo(e=None):
            if readonly: return 'break'
            try: w.edit_undo()
            except Exception: pass
            return 'break'

        def _kb_redo(e=None):
            if readonly: return 'break'
            try: w.edit_redo()
            except Exception: pass
            return 'break'

        # Virtual events: the only reliable way to catch Cmd+C/X/V on macOS
        w.bind('<<Copy>>', _kb_copy)
        if not readonly:
            w.bind('<<Cut>>', _kb_cut)
            w.bind('<<Paste>>', _kb_paste)

        # Cmd+A and Cmd+Z do arrive as key events (not intercepted by macOS)
        for _pfx in ('<Meta-', '<Command-'):
            w.bind(f'{_pfx}a>', _kb_select_all)
            if not readonly:
                w.bind(f'{_pfx}z>', _kb_undo)
                w.bind(f'{_pfx}Z>', _kb_redo)


# ── Entry 右鍵選單 ────────────────────────────────────────────────────────────

def _attach_entry(widget: tk.Entry, readonly: bool = False):
    w = widget

    def _copy():
        try: _pbcopy(w.selection_get())
        except tk.TclError: pass

    def _cut():
        if readonly: return
        try:
            _pbcopy(w.selection_get())
            w.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError: pass

    def _paste():
        if readonly: return
        text = _pbpaste()
        if not text: return
        try: w.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError: pass
        w.insert(tk.INSERT, text)

    def _select_all():
        w.select_range(0, tk.END)
        w.icursor(tk.END)

    menu = tk.Menu(w, tearoff=0)
    if not readonly:
        menu.add_command(label='剪下', command=_cut)
    menu.add_command(label='複製', command=_copy)
    if not readonly:
        menu.add_command(label='貼上', command=_paste)
    menu.add_separator()
    menu.add_command(label='全選', command=_select_all)

    def show_menu(e):
        w.focus_set()
        try: menu.tk_popup(e.x_root, e.y_root)
        finally: menu.grab_release()

    w.bind('<Button-2>', show_menu)
    w.bind('<Button-3>', show_menu)
    if sys.platform == 'darwin':
        w.bind('<Control-Button-1>', show_menu)

    if sys.platform == 'darwin':
        def _kb_copy(e=None):
            try: _pbcopy(w.selection_get())
            except tk.TclError: pass

        def _kb_cut(e=None):
            if readonly: return 'break'
            try:
                _pbcopy(w.selection_get())
                w.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError: pass
            return 'break'

        def _kb_paste(e=None):
            if readonly: return 'break'
            text = _pbpaste()
            if not text: return 'break'
            try: w.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError: pass
            w.insert(tk.INSERT, text)
            return 'break'

        def _kb_select_all(e=None):
            w.select_range(0, tk.END)
            w.icursor(tk.END)
            return 'break'

        w.bind('<<Copy>>', _kb_copy)
        if not readonly:
            w.bind('<<Cut>>', _kb_cut)
            w.bind('<<Paste>>', _kb_paste)
        for _pfx in ('<Meta-', '<Command-'):
            w.bind(f'{_pfx}a>', _kb_select_all)


# ── 全域快捷鍵────────────────────────────────────────────────────────────────
#
# macOS 攔截 Cmd+C / Cmd+X，Tk 收到的 keysym 是 '??'，所以
# <Meta-Key-c> / <Meta-Key-x> 永遠不觸發。
# 正確做法：綁定 <<Copy>> / <<Cut>> / <<Paste>> 虛擬事件，
# 以及 <Meta-Key-z/Z/v/a>（這幾個 keysym 正常）。
#
# ─────────────────────────────────────────────────────────────────────────────

def install_edit_menu(root: tk.Tk, menubar: 'tk.Menu | None' = None):
    """
    全域快捷鍵，覆蓋整個 app。
    macOS: 虛擬事件 + Meta-Key 雙管齊下。
    Windows/Linux: Control-Key。
    """

    def _w(e):
        """取得觸發事件的 widget。若事件落在 root 上改用 focus_get()。"""
        if e is not None and hasattr(e, 'widget'):
            w = e.widget
            # When macOS routes Cmd+key to the main NSWindow, e.widget is root.
            # Fall back to Tk focus to find the actual editing widget.
            if w is root or not isinstance(w, (tk.Text, tk.Entry)):
                w = root.focus_get() or w
            return w
        return root.focus_get()

    def _text_editable(w):
        return isinstance(w, tk.Text) and str(w.cget('state')) != 'disabled'

    def _entry_editable(w):
        return isinstance(w, tk.Entry) and str(w.cget('state')) not in ('disabled', 'readonly')

    # ── copy ─────────────────────────────────────────────────────────────────
    # macOS 已把選取文字放進 clipboard，pbcopy 只是確保 pbpaste 也能讀到同樣內容

    def do_copy(e=None):
        w = _w(e)
        if isinstance(w, tk.Text):
            try: _pbcopy(w.get(tk.SEL_FIRST, tk.SEL_LAST))
            except tk.TclError: pass
        elif isinstance(w, tk.Entry):
            try: _pbcopy(w.selection_get())
            except tk.TclError: pass
        # 不 return 'break'：讓 macOS 原生複製也能繼續執行

    # ── cut ──────────────────────────────────────────────────────────────────
    # Entry 的 cut 由 macOS NSTextField 原生處理，不需攔截（否則會 double-cut）

    def do_cut(e=None):
        w = _w(e)
        if _text_editable(w):
            try:
                _pbcopy(w.get(tk.SEL_FIRST, tk.SEL_LAST))
                w.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError: pass
            return 'break'
        # Entry：不攔截，讓 macOS 原生處理

    # ── paste ─────────────────────────────────────────────────────────────────
    # Entry 的 paste 由 macOS NSTextField 原生處理，不需攔截（否則會 double-paste）

    def do_paste(e=None):
        w = _w(e)
        if _text_editable(w):
            text = _pbpaste()
            if text:
                try: w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except tk.TclError: pass
                w.insert(tk.INSERT, text)
            return 'break'
        # Entry：不攔截，讓 macOS 原生處理

    # ── select all ────────────────────────────────────────────────────────────

    def do_select_all(e=None):
        w = _w(e)
        if isinstance(w, tk.Text):
            w.tag_add(tk.SEL, '1.0', tk.END)
            w.mark_set(tk.INSERT, tk.END)
        elif isinstance(w, tk.Entry):
            w.select_range(0, tk.END)
            w.icursor(tk.END)
        return 'break'

    # ── undo / redo ───────────────────────────────────────────────────────────
    # Entry 的 undo 由 macOS NSTextField 原生處理，不回傳 'break' 才不會封鎖它

    def do_undo(e=None):
        w = _w(e)
        if _text_editable(w):
            try: w.edit_undo()
            except Exception: pass
            return 'break'
        # Entry：不攔截，讓 macOS 原生處理

    def do_redo(e=None):
        w = _w(e)
        if _text_editable(w):
            try: w.edit_redo()
            except Exception: pass
            return 'break'

    # ── macOS 綁定 ────────────────────────────────────────────────────────────

    if sys.platform == 'darwin':
        # 系統 Edit 選單（顯示用）
        # menubar 可由呼叫端預先建立並加入其他選單（例如「工具」），
        # 若未傳入則自行建立
        if menubar is None:
            menubar = tk.Menu(root)
        root.configure(menu=menubar)
        edit = tk.Menu(menubar, tearoff=0)

        menubar.add_cascade(label='Edit', menu=edit)
        edit.add_command(label='Undo',       accelerator='⌘Z',  command=do_undo)
        edit.add_command(label='Redo',       accelerator='⌘⇧Z', command=do_redo)
        edit.add_separator()
        edit.add_command(label='Cut',        accelerator='⌘X',  command=do_cut)
        edit.add_command(label='Copy',       accelerator='⌘C',  command=do_copy)
        edit.add_command(label='Paste',      accelerator='⌘V',  command=do_paste)
        edit.add_separator()
        edit.add_command(label='Select All', accelerator='⌘A',  command=do_select_all)

        # Cmd+C → keysym='??'（macOS 攔截），改綁虛擬事件
        root.bind_all('<<Copy>>', do_copy)

        # Cmd+X / A / Z / Shift+Z
        # 注意：Cmd+V 不綁，讓 tk.Text / Entry 原生 <<Paste>> class binding 處理，
        # 避免 <Meta-Key-v> 和 <<Paste>> 同時觸發導致 double paste
        for prefix in ('<Meta-', '<Command-'):
            root.bind_all(f'{prefix}x>', do_cut)
            root.bind_all(f'{prefix}a>', do_select_all)
            root.bind_all(f'{prefix}z>', do_undo)
            root.bind_all(f'{prefix}Z>', do_redo)

        return menubar

    # ── Windows / Linux ──────────────────────────────────────────────────────

    else:
        root.bind_all('<Control-z>', do_undo)
        root.bind_all('<Control-y>', do_redo)
        root.bind_all('<Control-x>', do_cut)
        root.bind_all('<Control-c>', do_copy)
        root.bind_all('<Control-v>', do_paste)
        root.bind_all('<Control-a>', do_select_all)
