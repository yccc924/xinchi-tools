import tkinter as tk

root = tk.Tk()
root.title("按鍵測試 - 按 Command+C/V/A 看看")
root.geometry("400x300")

log = tk.Text(root, font=("Arial", 12))
log.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
log.insert("1.0", "請在這裡按 Command+C / Command+V / Command+A\n每次按鍵的名稱會顯示在這裡\n\n")

def on_key(e):
    msg = f"keysym={e.keysym!r}  state={e.state}  char={e.char!r}\n"
    log.insert("end", msg)
    log.see("end")

root.bind_all("<Key>", on_key)
root.mainloop()
