import sys
import tkinter as tk

WIN_BG   = "#d4d0c8"   # Platinum
TXT_BG   = "#ffffff"
TXT_FG   = "#000000"
SEL_BG   = "#2358e6"   # Mac OS 9 highlight blue
SEL_FG   = "#ffffff"
BTN_FACE = "#d4d0c8"   # Platinum

_F  = "Geneva" if sys.platform == "darwin" else "MS Sans Serif"
_FS = 9 if sys.platform == "darwin" else 8


def w95_btn(parent, text, command=None, width=None):
    b = tk.Button(parent, text=text, command=command,
                  font=(_F, _FS), bg=BTN_FACE, fg=TXT_FG,
                  activebackground=BTN_FACE, activeforeground=TXT_FG,
                  relief="raised", bd=2, padx=6, pady=3, cursor="arrow")
    if width:
        b.config(width=width)
    b.bind("<ButtonPress-1>",   lambda e: b.config(relief="sunken"))
    b.bind("<ButtonRelease-1>", lambda e: b.config(relief="raised"))
    return b


def w95_entry(parent, textvariable=None, show="", state="normal", width=None):
    kw = dict(font=(_F, _FS), bg=TXT_BG, fg=TXT_FG,
              relief="sunken", bd=2, insertbackground=TXT_FG,
              selectbackground=SEL_BG, selectforeground=TXT_FG,
              disabledbackground=WIN_BG, readonlybackground=TXT_BG,
              show=show, state=state)
    if textvariable is not None:
        kw["textvariable"] = textvariable
    if width is not None:
        kw["width"] = width
    return tk.Entry(parent, **kw)


def w95_text(parent, readonly=False, height=None, mono=False):
    """Returns (outer_frame, tk.Text). Grid/pack outer_frame; pass tk.Text to attach()."""
    outer = tk.Frame(parent, relief="sunken", bd=2, bg=TXT_BG)
    sb = tk.Scrollbar(outer, orient=tk.VERTICAL)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    font = ("Courier New", _FS) if mono else (_F, _FS)
    kw = dict(font=font, bg=TXT_BG, fg=TXT_FG, relief="flat", bd=0, wrap=tk.WORD,
              insertbackground=TXT_FG,
              selectbackground=SEL_BG, selectforeground=SEL_FG,
              inactiveselectbackground=SEL_BG,
              yscrollcommand=sb.set, undo=not readonly)
    if height is not None:
        kw["height"] = height
    if readonly:
        kw["state"] = "disabled"
    txt = tk.Text(outer, **kw)
    sb.config(command=txt.yview)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return outer, txt


def w95_option_menu(parent, variable, values):
    opt = tk.OptionMenu(parent, variable, *values)
    opt.config(font=(_F, _FS), bg=BTN_FACE, fg=TXT_FG,
               activebackground=SEL_BG, activeforeground=SEL_FG,
               relief="raised", bd=2)
    opt["menu"].config(font=(_F, _FS), bg=BTN_FACE, fg=TXT_FG,
                       activebackground=SEL_BG, activeforeground=SEL_FG)
    return opt


def w95_scrollable_frame(parent):
    """Returns (outer_frame, inner_frame). Grid/pack outer_frame, add widgets to inner_frame."""
    outer = tk.Frame(parent, bg=WIN_BG, relief="sunken", bd=2)
    canvas = tk.Canvas(outer, bg=WIN_BG, highlightthickness=0)
    sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=WIN_BG)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    return outer, inner
