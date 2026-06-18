import os
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import openpyxl

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _dnd_root_ok = True
except ImportError:
    _dnd_root_ok = False

HAS_DND = False

if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(_BASE, "config.txt")

# ── Windows 95 色彩系統 ───────────────────────────────────────────────────────
WIN_BG     = "#c0c0c0"   # 視窗主體灰
ACTIVE_TB  = "#000080"   # 啟動標題列深藍
INACT_TB   = "#808080"   # 非啟動標題列灰
TITLE_FG   = "#ffffff"   # 標題列文字
TXT_BG     = "#ffffff"   # 文字框白底
TXT_FG     = "#000000"   # 文字黑
SEL_BG     = "#000080"   # 選取背景藍
SEL_FG     = "#ffffff"   # 選取文字白
BTN_FACE   = "#c0c0c0"   # 按鈕面灰

# macOS 用 Geneva（近似 MS Sans Serif），Windows 用原生字型
_F = "Geneva" if sys.platform == "darwin" else "MS Sans Serif"
_FS = 9 if sys.platform == "darwin" else 8


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("二手機自動報價工具")
        self.root.geometry("720x520")
        self.root.configure(bg=WIN_BG)
        self.root.resizable(True, True)
        self.root.minsize(580, 400)

        self.price_db = {}
        self.warranty_keys = set()
        self.file_path_var = tk.StringVar(value="（尚未載入報價單）")
        self.status_var = tk.StringVar(value="請選擇報價單...")

        self._build_menubar(self.root)
        self._build_app_ui(self.root)

    # ════════════════════════════════════════════════════════════════════════
    # 選單列
    # ════════════════════════════════════════════════════════════════════════

    def _build_menubar(self, parent):
        mb = tk.Frame(parent, bg=WIN_BG)
        mb.pack(fill=tk.X)
        tk.Frame(parent, bg="#808080", height=1).pack(fill=tk.X)

        defs = [
            ("檔案(F)", [
                ("載入報價單...",    self._browse_file),
                None,
                ("結束(X)",         self.root.destroy),
            ]),
            ("編輯(E)", [
                ("剪下(T)  Ctrl+X", self._menu_cut),
                ("複製(C)  Ctrl+C", self._menu_copy),
                ("貼上(P)  Ctrl+V", self._menu_paste),
            ]),
            ("說明(H)", [
                ("關於...",          self._show_about),
            ]),
        ]

        for title, items in defs:
            lbl = tk.Label(mb, text=title, font=(_F, _FS),
                           bg=WIN_BG, fg=TXT_FG,
                           padx=6, pady=2, cursor="arrow")
            lbl.pack(side=tk.LEFT)

            popup = tk.Menu(self.root, tearoff=0,
                            bg=WIN_BG, fg=TXT_FG,
                            activebackground=SEL_BG, activeforeground=SEL_FG,
                            font=(_F, _FS), relief="raised", bd=2)
            for item in items:
                if item is None:
                    popup.add_separator()
                else:
                    popup.add_command(label=item[0], command=item[1])

            def _make_show(m, l):
                def show(e):
                    l.config(bg=SEL_BG, fg=SEL_FG)
                    try:
                        m.post(l.winfo_rootx(), l.winfo_rooty() + l.winfo_height())
                    finally:
                        l.config(bg=WIN_BG, fg=TXT_FG)
                return show

            lbl.bind("<Button-1>", _make_show(popup, lbl))

    # ════════════════════════════════════════════════════════════════════════
    # 主要 UI 內容
    # ════════════════════════════════════════════════════════════════════════

    def _build_app_ui(self, parent):
        # 狀態列最先 pack（side=BOTTOM 確保永遠在最底）
        stat_f = tk.Frame(parent, bg=WIN_BG, relief="sunken", bd=1)
        stat_f.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(stat_f, textvariable=self.status_var,
                 font=(_F, _FS), bg=WIN_BG, fg=TXT_FG,
                 anchor="w", padx=6, pady=2).pack(fill=tk.X)

        inner = tk.Frame(parent, bg=WIN_BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 4))

        # ── ① 報價單檔案列 ──────────────────────────────────────────────
        file_row = tk.Frame(inner, bg=WIN_BG)
        file_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(file_row, text="報價單:", font=(_F, _FS),
                 bg=WIN_BG, fg=TXT_FG).pack(side=tk.LEFT, padx=(0, 4))

        tk.Entry(file_row, textvariable=self.file_path_var,
                 font=(_F, _FS),
                 bg=TXT_BG, fg=TXT_FG,
                 relief="sunken", bd=2,
                 state="readonly",
                 readonlybackground=TXT_BG).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self._win95_btn(file_row, "瀏覽...(Browse)", self._browse_file, w=16).pack(side=tk.RIGHT)

        # ── ② 左右文字欄 ────────────────────────────────────────────────
        cols = tk.Frame(inner, bg=WIN_BG)
        cols.pack(fill=tk.BOTH, expand=True)

        # 左：輸入
        lf = tk.Frame(cols, bg=WIN_BG)
        lf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        tk.Label(lf, text="機況文字輸入區:", font=(_F, _FS),
                 bg=WIN_BG, fg=TXT_FG, anchor="w").pack(fill=tk.X, pady=(0, 2))

        lc = tk.Frame(lf, relief="sunken", bd=2, bg=TXT_BG)
        lc.pack(fill=tk.BOTH, expand=True)
        sb_l = tk.Scrollbar(lc, orient=tk.VERTICAL)
        sb_l.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_in = tk.Text(lc, font=(_F, _FS),
                              bg=TXT_BG, fg=TXT_FG,
                              relief="flat", bd=0,
                              insertbackground=TXT_FG,
                              selectbackground=SEL_BG, selectforeground=SEL_FG,
                              undo=True, wrap=tk.WORD,
                              yscrollcommand=sb_l.set)
        sb_l.config(command=self.txt_in.yview)
        self.txt_in.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 右：輸出
        rf = tk.Frame(cols, bg=WIN_BG)
        rf.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))
        tk.Label(rf, text="報價結果輸出區:", font=(_F, _FS),
                 bg=WIN_BG, fg=TXT_FG, anchor="w").pack(fill=tk.X, pady=(0, 2))

        rc = tk.Frame(rf, relief="sunken", bd=2, bg=TXT_BG)
        rc.pack(fill=tk.BOTH, expand=True)
        sb_r = tk.Scrollbar(rc, orient=tk.VERTICAL)
        sb_r.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_out = tk.Text(rc, font=(_F, _FS),
                               bg=TXT_BG, fg=TXT_FG,
                               relief="flat", bd=0,
                               selectbackground=SEL_BG, selectforeground=SEL_FG,
                               state=tk.DISABLED, wrap=tk.WORD,
                               yscrollcommand=sb_r.set)
        sb_r.config(command=self.txt_out.yview)
        self.txt_out.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── ③ 操作按鈕列 ────────────────────────────────────────────────
        btn_row = tk.Frame(inner, bg=WIN_BG)
        btn_row.pack(fill=tk.X, pady=(6, 0))

        self._win95_btn(btn_row, "貼上文字(F4)", self._paste, w=14).pack(side=tk.LEFT, padx=(0, 4))
        self._win95_btn(btn_row, "轉換價格(F5)", self._process, w=14).pack(side=tk.LEFT, padx=(0, 4))
        self._win95_btn(btn_row, "複製結果(F6)", self._copy,   w=14).pack(side=tk.LEFT, padx=(0, 4))
        self._win95_btn(btn_row, "清除(Del)",    self._clear,  w=10).pack(side=tk.LEFT)

        # 快捷鍵
        self._bind_shortcuts()
        self.root.after(50, self._load_config)

    # ── Win95 按鈕 ────────────────────────────────────────────────────────

    def _win95_btn(self, parent, text, cmd, w=None):
        b = tk.Button(parent, text=text, command=cmd,
                      font=(_F, _FS),
                      bg=WIN_BG, fg=TXT_FG,
                      activebackground=WIN_BG, activeforeground=TXT_FG,
                      relief="raised", bd=2,
                      padx=6, pady=3, cursor="arrow")
        if w:
            b.config(width=w)
        self._bind_press(b)
        return b

    def _bind_press(self, btn):
        btn.bind("<ButtonPress-1>",   lambda e: btn.config(relief="sunken"))
        btn.bind("<ButtonRelease-1>", lambda e: btn.config(relief="raised"))

    def _set_status(self, msg):
        self.status_var.set(msg)

    # ── 編輯選單 ──────────────────────────────────────────────────────────

    def _menu_cut(self):
        w = self.root.focus_get()
        if not isinstance(w, tk.Text) or w is not self.txt_in:
            return
        try:
            text = w.get("sel.first", "sel.last")
            self._pbcopy(text)
            w.delete("sel.first", "sel.last")
            self._set_status("已剪下選取文字")
        except tk.TclError:
            pass

    def _menu_copy(self):
        w = self.root.focus_get()
        if not isinstance(w, tk.Text):
            return
        try:
            text = w.get("sel.first", "sel.last")
            self._pbcopy(text)
            self._set_status("已複製選取文字")
        except tk.TclError:
            pass

    def _menu_paste(self):
        w = self.root.focus_get()
        if not isinstance(w, tk.Text) or w is not self.txt_in:
            return
        text = self._pbpaste()
        try:
            w.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        w.insert("insert", text)
        self._set_status("已貼上文字")

    def _clear(self):
        self.txt_in.delete("1.0", tk.END)
        self.txt_out.configure(state=tk.NORMAL)
        self.txt_out.delete("1.0", tk.END)
        self.txt_out.configure(state=tk.DISABLED)
        self._set_status("已清除")

    def _show_about(self):
        messagebox.showinfo(
            "關於 二手機自動報價工具",
            "二手機自動報價工具  v1.0\n\n"
            "操作步驟：\n"
            "  1. 檔案 → 載入報價單（.xlsx）\n"
            "  2. 貼上機況文字\n"
            "  3. 按「轉換價格」自動填入 $\n"
            "  4. 按「複製結果」貼給客戶"
        )

    # ── 系統剪貼簿（跨平台）──────────────────────────────────────────────

    def _pbcopy(self, text):
        if sys.platform == "darwin":
            import subprocess
            subprocess.run(["pbcopy"], input=text.encode("utf-8"))
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _pbpaste(self):
        if sys.platform == "darwin":
            import subprocess
            return subprocess.run(["pbpaste"], capture_output=True).stdout.decode("utf-8")
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return ""

    # ════════════════════════════════════════════════════════════════════════
    # 鍵盤快捷鍵
    # ════════════════════════════════════════════════════════════════════════

    def _bind_shortcuts(self):
        if sys.platform == "darwin":
            self._bind_mac()
        else:
            self._bind_win()

    def _bind_mac(self):
        def on_cmd_key(e):
            if not (e.state & 8):
                return
            ch = (e.char or "").lower()
            w = e.widget
            if ch == "c":
                try:
                    self._pbcopy(w.get("sel.first", "sel.last"))
                except Exception:
                    pass
                return "break"
            if ch == "x":
                try:
                    t = w.get("sel.first", "sel.last")
                    self._pbcopy(t)
                    w.delete("sel.first", "sel.last")
                except Exception:
                    pass
                return "break"
            if ch == "v":
                try:
                    t = self._pbpaste()
                    try:
                        w.delete("sel.first", "sel.last")
                    except tk.TclError:
                        pass
                    w.insert("insert", t)
                except Exception:
                    pass
                return "break"
            if ch == "a":
                w.tag_add("sel", "1.0", "end")
                return "break"
            if ch == "z":
                try:
                    w.edit_undo()
                except Exception:
                    pass
                return "break"

        for w in (self.txt_in, self.txt_out):
            w.bind("<KeyPress>", on_cmd_key, add=True)

    def _bind_win(self):
        def copy(e):
            try:
                t = e.widget.get("sel.first", "sel.last")
                e.widget.clipboard_clear(); e.widget.clipboard_append(t)
            except Exception:
                pass
            return "break"

        def cut(e):
            try:
                t = e.widget.get("sel.first", "sel.last")
                e.widget.clipboard_clear(); e.widget.clipboard_append(t)
                e.widget.delete("sel.first", "sel.last")
            except Exception:
                pass
            return "break"

        def paste(e):
            try:
                t = e.widget.clipboard_get()
                try:
                    e.widget.delete("sel.first", "sel.last")
                except tk.TclError:
                    pass
                e.widget.insert("insert", t)
            except Exception:
                pass
            return "break"

        def sel_all(e):
            e.widget.tag_add("sel", "1.0", "end")
            return "break"

        def undo(e):
            try:
                e.widget.edit_undo()
            except Exception:
                pass
            return "break"

        for w in (self.txt_in, self.txt_out):
            w.bind("<Control-c>", copy)
            w.bind("<Control-x>", cut)
            w.bind("<Control-v>", paste)
            w.bind("<Control-a>", sel_all)
            w.bind("<Control-z>", undo)

    # ════════════════════════════════════════════════════════════════════════
    # 檔案處理
    # ════════════════════════════════════════════════════════════════════════

    def _browse_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel 檔案", "*.xlsx *.xls")],
            title="載入報價單 Excel 檔案",
        )
        if path:
            self._load_excel(path)

    # ════════════════════════════════════════════════════════════════════════
    # 設定持久化
    # ════════════════════════════════════════════════════════════════════════

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    path = f.read().strip()
                if path and os.path.exists(path):
                    self._load_excel(path)
            except Exception:
                pass

    def _save_config(self, path):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(path)
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════════
    # Excel 解析
    # ════════════════════════════════════════════════════════════════════════

    def _normalize_model(self, raw):
        s = str(raw).strip().upper().replace(" ", "")
        s = s.replace("／", "/")
        return s

    def _load_excel(self, path):
        try:
            self.root.config(cursor="watch" if sys.platform == "darwin" else "wait")
            self.root.update()

            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            db = {}
            warranty_keys = set()

            i = 0
            while i < len(rows):
                model_raw = rows[i][0]
                if model_raw is None or str(model_raw).strip() in ("", "nan"):
                    i += 1; continue
                if any(kw in str(model_raw) for kw in ("二手機", "賣價", "開價")):
                    i += 1; continue
                if i + 1 >= len(rows):
                    break

                header_row = rows[i]
                price_row  = rows[i + 1]
                model_key  = self._normalize_model(model_raw)

                for col in range(1, len(header_row)):
                    spec  = header_row[col]
                    price = price_row[col] if col < len(price_row) else None
                    if spec is None or price is None:
                        continue
                    spec_s = str(spec).strip()
                    if not spec_s or spec_s == "nan":
                        continue

                    cap_m = re.search(r"(\d+)(G|T)", spec_s, re.IGNORECASE)
                    if not cap_m:
                        continue
                    capacity = cap_m.group(1) + cap_m.group(2).upper()

                    if ("80~89" in spec_s or "80-89" in spec_s or "沒有100%" in spec_s):
                        btype = "80~89"
                    elif ("90~100" in spec_s or "90-100" in spec_s or
                          "保內100%" in spec_s or re.search(r"保內\s*90", spec_s)):
                        btype = "90~100"
                    else:
                        btype = "90~100"

                    key = (model_key, capacity, btype)
                    parts = str(price).strip().split()
                    try:
                        db[key] = int(float(parts[0]))
                    except Exception:
                        db[key] = str(price)

                    if "保內100%" in spec_s and len(parts) >= 2:
                        try:
                            db[(model_key, capacity, "保內100%")] = int(float(parts[1]))
                        except Exception:
                            pass

                    if "保內" in spec_s and len(parts) < 2:
                        warranty_keys.add(key)

                i += 2

            self.price_db    = db
            self.warranty_keys = warranty_keys
            self._save_config(path)

            fname = os.path.basename(path)
            self.file_path_var.set(path)
            count = len(set(k[0] for k in db))
            self._set_status(f"成功載入：{fname}  （共 {count} 種機型、{len(db)} 筆價格）")

        except Exception as e:
            messagebox.showerror("載入失敗", f"無法解析 Excel：\n{e}")
            self._set_status("載入失敗")
        finally:
            self.root.config(cursor="")

    # ════════════════════════════════════════════════════════════════════════
    # 型號辨識
    # ════════════════════════════════════════════════════════════════════════

    def _detect_model(self, header):
        m = re.search(r"IPHONE\s+(.*?)\s*\d+\s*[GT]", header, re.IGNORECASE)
        if m:
            model_text = m.group(1).upper().replace(" ", "")
        else:
            model_text = header.upper().replace(" ", "")

        known = sorted(set(k[0] for k in self.price_db), key=len, reverse=True)
        for model_key in known:
            if "/" in model_key:
                for part in sorted(model_key.split("/"), key=len, reverse=True):
                    if part in model_text:
                        return model_key
            else:
                if model_key == model_text or (model_key in model_text and len(model_key) > 2):
                    return model_key
        return "未知"

    # ════════════════════════════════════════════════════════════════════════
    # 核心轉換
    # ════════════════════════════════════════════════════════════════════════

    def _process(self):
        if not self.price_db:
            messagebox.showwarning("提示", "請先載入報價單 Excel 檔案！")
            return
        raw = self.txt_in.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("提示", "請貼入機況文字！")
            return

        out_blocks = []
        filled = 0
        for block in raw.split("\n\n"):
            lines = block.split("\n")
            header_idx = next(
                (i for i, l in enumerate(lines) if "IPHONE" in l.upper()), None
            )
            if header_idx is None:
                out_blocks.append(block)
                continue

            header   = lines[header_idx].upper()
            cap_m = re.search(r"(\d+)\s*(T(?:B)?|G(?:B)?)", header, re.IGNORECASE)
            if cap_m:
                unit = "T" if cap_m.group(2).upper().startswith("T") else "G"
                capacity = cap_m.group(1) + unit
            else:
                capacity = "128G"
            model    = self._detect_model(header)

            batt_m = re.search(r"電池[健康度]*\s*[:：]?\s*(\d+)\s*%", block)
            if batt_m:
                batt_val = int(batt_m.group(1))
            else:
                batt_m2  = re.search(r"(\d+)\s*%", header)
                batt_val = int(batt_m2.group(1)) if batt_m2 else 100
            btype = "80~89" if batt_val < 90 else "90~100"

            price = self.price_db.get((model, capacity, btype))
            if price is None and btype == "80~89":
                price = self.price_db.get((model, capacity, "90~100"))

            has_bonus = (
                ("原廠保固" in block and "無原廠保固" not in block) or
                "換過原廠電池" in block
            )
            if batt_val == 100 and has_bonus:
                wp = self.price_db.get((model, capacity, "保內100%"))
                if isinstance(wp, int):
                    price = wp
                elif (model, capacity, btype) not in self.warranty_keys and isinstance(price, int):
                    price += 1000

            new_lines = []
            for line in lines:
                if line.strip() == "$":
                    if isinstance(price, int):
                        new_lines.append(f"${price}")
                        filled += 1
                    else:
                        new_lines.append(f"$ (查無 {model} {capacity} 電{btype})")
                else:
                    new_lines.append(line)
            out_blocks.append("\n".join(new_lines))

        result = "\n\n".join(out_blocks)
        self.txt_out.configure(state=tk.NORMAL)
        self.txt_out.delete("1.0", tk.END)
        self.txt_out.insert("1.0", result)
        self.txt_out.configure(state=tk.DISABLED)
        self._set_status(f"轉換完成，共填入 {filled} 筆價格")

    # ════════════════════════════════════════════════════════════════════════
    # 剪貼簿操作
    # ════════════════════════════════════════════════════════════════════════

    def _paste(self):
        text = self._pbpaste()
        if text:
            self.txt_in.delete("1.0", tk.END)
            self.txt_in.insert("1.0", text)
            self._set_status("已貼上文字")
        else:
            self._set_status("剪貼簿沒有文字")

    def _copy(self):
        text = self.txt_out.get("1.0", tk.END).strip()
        if not text:
            self._set_status("沒有內容可複製")
            return
        self._pbcopy(text)
        self._set_status("已複製到剪貼簿，可直接貼上傳 LINE 或發文")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
