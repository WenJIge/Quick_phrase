# quick_phrase.py
import ctypes, json, os, sys, time, threading, winreg
import keyboard, pyperclip, tkinter as tk, tkinter.font as tkfont
from tkinter import messagebox, filedialog
from PIL import Image, ImageDraw, ImageTk
import pystray

DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "QuickPhrase")
os.makedirs(DIR, exist_ok=True)
CFG, ICO = os.path.join(DIR, "phrases.json"), os.path.join(DIR, "QuickPhrase.ico")
REG, RNAME = r"Software\Microsoft\Windows\CurrentVersion\Run", "QuickPhrase"
DEF = ["欢迎使用QuickPhrase", "BUG请反馈至 stonebey332211@outlook.com", "关注UP吧，求求您了(B站:雲-绮石Stone)"]

BG, CARD, BOR = "#F5F7FA", "#FFFFFF", "#DDE3EA"
PRI, PRIH, PRIA = "#2D7DD2", "#4A90DB", "#1F6DBF"
TXT, MUT, HOV, ACT, OK, WARN = "#2C3E50", "#7F8C9A", "#EEF3FA", "#E1EAF5", "#27AE60", "#E67E22"


def dpi_aware():
    for fn in (
        lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
        lambda: ctypes.windll.user32.SetProcessDPIAware(),
    ):
        try: fn(); return
        except Exception: pass


def scale_of(root):
    try:
        root.update_idletasks()
        return ctypes.windll.user32.GetDpiForWindow(root.winfo_id()) / 96.0
    except Exception: return 1.0


def app_icon(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    k = size / 64.0; sx = lambda v: int(v * k)
    d.rounded_rectangle([sx(2), sx(2), sx(62), sx(62)], radius=sx(14), fill=(45, 125, 210, 255))
    d.rounded_rectangle([sx(18), sx(12), sx(46), sx(52)], radius=sx(5), outline="white", width=max(1, sx(4)))
    for y, x2 in ((26, 40), (34, 40), (42, 34)):
        d.line([sx(26), sx(y), sx(x2), sx(y)], fill="white", width=max(1, sx(4)))
    return img


def save_ico():
    try: app_icon(256).save(ICO, format="ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    except Exception as e: print("ico:", e)


def autostart_cmd():
    if getattr(sys, "frozen", False): return f'"{sys.executable}" --startup'
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.path.exists(pyw): py = pyw
    return f'"{py}" "{os.path.abspath(sys.argv[0])}" --startup'


def autostart_state():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG) as k:
            return bool(winreg.QueryValueEx(k, RNAME)[0])
    except Exception: return False


def set_autostart(on):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG, 0, winreg.KEY_SET_VALUE) as k:
            if on: winreg.SetValueEx(k, RNAME, 0, winreg.REG_SZ, autostart_cmd())
            else:
                try: winreg.DeleteValue(k, RNAME)
                except FileNotFoundError: pass
        return True
    except Exception as e:
        print("autostart:", e); return False


class RBtn(tk.Canvas):
    """圆角按钮。self.c = (常态, hover, active, 前景, 描边)"""
    def __init__(self, parent, text, cmd, primary=False, s=1.0, minw=0):
        font = ("Microsoft YaHei UI", 10, "bold" if primary else "normal")
        self.c = (PRI if primary else CARD, PRIH if primary else HOV,
                  PRIA if primary else ACT, "white" if primary else TXT,
                  PRI if primary else BOR)
        self.r = max(4, int(8 * s))
        self.text, self.font, self.cmd = text, font, cmd
        f = tkfont.Font(font=font)
        px, py = int((22 if primary else 14) * s), int((9 if primary else 8) * s)
        self.w = max(int(minw * s), f.measure(text) + px * 2)
        self.h = f.metrics("linespace") + py * 2
        try: bg = parent.cget("bg")
        except Exception: bg = BG
        super().__init__(parent, width=self.w, height=self.h, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._paint(self.c[0])
        self.bind("<Enter>", lambda e: self._paint(self.c[1]))
        self.bind("<Leave>", lambda e: self._paint(self.c[0]))
        self.bind("<ButtonPress-1>", lambda e: self._paint(self.c[2]))
        self.bind("<ButtonRelease-1>", self._up)

    def _paint(self, fill):
        self.delete("all")
        w, h, r = self.w, self.h, self.r
        pts = [1+r,1, 1+r,1, w-1-r,1, w-1-r,1, w-1,1, w-1,1+r, w-1,1+r, w-1,h-1-r,
               w-1,h-1-r, w-1,h-1, w-1-r,h-1, w-1-r,h-1, 1+r,h-1, 1+r,h-1, 1,h-1, 1,h-1-r,
               1,h-1-r, 1,1+r, 1,1+r, 1,1]
        self.create_polygon(pts, smooth=True, fill=fill, outline=self.c[4], width=1)
        self.create_text(w/2, h/2, text=self.text, fill=self.c[3], font=self.font)

    def _up(self, e):
        inside = 0 <= e.x <= self.w and 0 <= e.y <= self.h
        self._paint(self.c[1] if inside else self.c[0])
        if inside and self.cmd:
            try: self.cmd()
            except Exception as ex: print("btn:", ex)

    def set_text(self, t): self.text = t; self._paint(self.c[0])


class App:
    def __init__(self):
        dpi_aware(); save_ico()
        self.hide = "--startup" in sys.argv
        self.phrases = self._load()
        self.hotkeys, self.paused = [], False
        self.q, self.lk = [], threading.Lock()
        self.tray, self.quit = None, False
        self.ico_ref, self.sc = None, 1.0
        self._build()
        if self.hide: self.root.withdraw()
        self._bind_hotkeys()
        self._build_tray()
        self.root.after(100, self._poll)

    # ---- 配置 ----
    def _load(self):
        try:
            with open(CFG, encoding="utf-8") as f: d = json.load(f)
            if isinstance(d, list): return [str(x) for x in d]
        except Exception: pass
        return list(DEF)

    def _save(self):
        try:
            with open(CFG, "w", encoding="utf-8") as f:
                json.dump(self.phrases, f, ensure_ascii=False, indent=2)
        except Exception as e: messagebox.showerror("保存失败", str(e))

    # ---- 跨线程队列 ----
    def _post(self, fn):
        with self.lk: self.q.append(fn)

    def _poll(self):
        with self.lk: acts, self.q = self.q[:], []
        for fn in acts:
            try: fn()
            except Exception as e: print("ui:", e)
        if not self.quit: self.root.after(100, self._poll)

    def _px(self, v): return int(v * self.sc)

    def _btn(self, p, text, cmd, primary=False, minw=0):
        return RBtn(p, text, cmd, primary, self.sc, minw)

    # ---- 界面 ----
    def _build(self):
        self.root = tk.Tk()
        self.root.title("快捷短语 QuickPhrase")
        try:
            self.ico_ref = ImageTk.PhotoImage(app_icon(256))
            self.root.iconphoto(True, self.ico_ref)
        except Exception: pass
        self.sc = scale_of(self.root)
        try: self.root.tk.call("tk", "scaling", self.sc * 4 / 3)
        except Exception: pass
        self.root.configure(bg=BG)
        self.root.geometry(f"{self._px(600)}x{self._px(560)}")
        self.root.minsize(self._px(540), self._px(480))
        for n in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try: tkfont.nametofont(n).configure(family="Microsoft YaHei UI")
            except Exception: pass

        hd = tk.Frame(self.root, bg=BG)
        hd.pack(fill="x", padx=self._px(24), pady=(self._px(20), self._px(8)))
        tk.Label(hd, text="快捷短语", bg=BG, fg=TXT,
                 font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        tk.Label(hd, text="每行一条短语  ·  第 N 行对应 Ctrl + Shift + N",
                 bg=BG, fg=MUT, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(self._px(2), 0))

        card = tk.Frame(self.root, bg=CARD, highlightthickness=1, highlightbackground=BOR)
        card.pack(fill="both", expand=True, padx=self._px(24), pady=self._px(10))
        self.text = tk.Text(card, wrap="word", undo=True,
                            font=("Microsoft YaHei UI", 10),
                            bg=CARD, fg=TXT, bd=0, highlightthickness=0,
                            insertbackground=PRI, selectbackground="#CCE0F5",
                            padx=self._px(14), pady=self._px(12),
                            spacing3=self._px(4), relief="flat")
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", "\n".join(self.phrases))

        r1 = tk.Frame(self.root, bg=BG)
        r1.pack(fill="x", padx=self._px(24), pady=(self._px(6), self._px(8)))
        l1 = tk.Frame(r1, bg=BG); l1.pack(side="left")
        self._btn(l1, "保存并应用", self.apply, True, 110).pack(side="left")
        self.pause_btn = self._btn(l1, "暂停", self.toggle_pause, False, 68)
        self.pause_btn.pack(side="left", padx=self._px(10))
        self.status = tk.Label(r1, bg=BG, fg=OK, font=("Microsoft YaHei UI", 9))
        self.status.pack(side="right", pady=self._px(10))

        r2 = tk.Frame(self.root, bg=BG)
        r2.pack(fill="x", padx=self._px(24), pady=(0, self._px(22)))
        l2 = tk.Frame(r2, bg=BG); l2.pack(side="left")
        self._btn(l2, "导入", self.do_import, False, 64).pack(side="left")
        self._btn(l2, "导出", self.do_export, False, 64).pack(side="left", padx=self._px(8))
        self._btn(l2, "打开配置目录", self.open_dir).pack(side="left")
        r2r = tk.Frame(r2, bg=BG); r2r.pack(side="right")
        self.auto_btn = self._btn(r2r,
            "开机自启：开" if autostart_state() else "开机自启：关",
            self.toggle_auto, False, 120)
        self.auto_btn.pack(side="left")
        self._btn(r2r, "关于", self.show_about, False, 64).pack(side="left", padx=self._px(8))

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self._refresh_status()

    def _refresh_status(self):
        n = sum(1 for p in self.phrases if p.strip())
        self.status.config(
            text=f"●  {'已暂停' if self.paused else '运行中'} · 已注册 {n} 条",
            fg=WARN if self.paused else OK,
        )

    # ---- 热键 ----
    def _bind_hotkeys(self):
        for h in self.hotkeys:
            try: keyboard.remove_hotkey(h)
            except Exception: pass
        self.hotkeys.clear()
        for i, p in enumerate(self.phrases[:9]):
            if not p.strip(): continue
            try:
                h = keyboard.add_hotkey(
                    f"ctrl+shift+{i+1}",
                    lambda t=p: None if self.paused else self._paste(t),
                )
                self.hotkeys.append(h)
            except Exception as e: print(f"hotkey {i+1}:", e)

    def _paste(self, text):
        for _ in range(30):
            if not (keyboard.is_pressed("ctrl") or keyboard.is_pressed("shift")): break
            time.sleep(0.01)
        time.sleep(0.03)
        try: old = pyperclip.paste()
        except Exception: old = None
        try:
            pyperclip.copy(text); time.sleep(0.04)
            keyboard.send("ctrl+v"); time.sleep(0.20)
        except Exception as e: print("paste:", e)
        if old is not None:
            try: pyperclip.copy(old)
            except Exception: pass

    # ---- 操作 ----
    def apply(self):
        lines = self.text.get("1.0", "end").split("\n")
        while lines and not lines[-1].strip(): lines.pop()
        self.phrases = lines
        self._save(); self._bind_hotkeys(); self._refresh_status()

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.set_text("恢复" if self.paused else "暂停")
        self._refresh_status()
        try: self.tray.update_menu()
        except Exception: pass

    def toggle_auto(self):
        cur = autostart_state()
        if not set_autostart(not cur):
            messagebox.showerror("设置失败", "无法修改注册表，请尝试管理员身份运行。", parent=self.root)
            return
        self.auto_btn.set_text("开机自启：关" if cur else "开机自启：开")
        try: self.tray.update_menu()
        except Exception: pass

    def do_export(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出短语", defaultextension=".json",
            initialfile="phrases.json",
            filetypes=[("JSON", "*.json"), ("文本", "*.txt"), ("所有", "*.*")])
        if not path: return
        try:
            if path.lower().endswith(".txt"):
                with open(path, "w", encoding="utf-8") as f: f.write("\n".join(self.phrases))
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.phrases, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("导出成功", f"已导出 {len(self.phrases)} 条短语到:\n{path}", parent=self.root)
        except Exception as e: messagebox.showerror("导出失败", str(e), parent=self.root)

    def do_import(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="导入短语",
            filetypes=[("JSON / 文本", "*.json *.txt"), ("JSON", "*.json"),
                       ("文本", "*.txt"), ("所有", "*.*")])
        if not path: return
        try:
            if path.lower().endswith(".txt"):
                with open(path, encoding="utf-8") as f: lines = f.read().splitlines()
            else:
                with open(path, encoding="utf-8") as f: data = json.load(f)
                if not isinstance(data, list): raise ValueError("JSON 顶层必须是数组")
                lines = [str(x) for x in data]
        except Exception as e:
            messagebox.showerror("导入失败", str(e), parent=self.root); return
        if not lines:
            messagebox.showwarning("导入", "文件是空的。", parent=self.root); return
        c = messagebox.askyesnocancel(
            "导入方式",
            f"共 {len(lines)} 条。\n\n「是」= 替换\n「否」= 追加\n「取消」= 放弃",
            parent=self.root)
        if c is None: return
        self.phrases = lines if c else (self.phrases + lines)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(self.phrases))
        self._save(); self._bind_hotkeys(); self._refresh_status()

    def open_dir(self):
        try: os.startfile(DIR)
        except Exception: pass

    def show_about(self):
        messagebox.showinfo(
            "关于 QuickPhrase",
            "本软件由DeepSeek开发,作者——雲-绮石Stone,\n"
            "禁止商业用途,个人二次使用源码等无需署名",
            parent=self.root)

    # ---- 托盘 ----
    def _build_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", lambda i, it: self._post(self.show_win), default=True),
            pystray.MenuItem(lambda it: "恢复热键" if self.paused else "暂停热键",
                             lambda i, it: self._post(self.toggle_pause)),
            pystray.MenuItem("保存并应用", lambda i, it: self._post(self.apply)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("导入短语…",
                             lambda i, it: self._post(lambda: self._visible(self.do_import))),
            pystray.MenuItem("导出短语…",
                             lambda i, it: self._post(lambda: self._visible(self.do_export))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda it: "关闭开机自启" if autostart_state() else "开启开机自启",
                             lambda i, it: self._post(self.toggle_auto)),
            pystray.MenuItem("关于", lambda i, it: self._post(self.show_about)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda i, it: (i.stop(), self._post(self.shutdown))),
        )
        self.tray = pystray.Icon("QuickPhrase", app_icon(64), "快捷短语 QuickPhrase", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _visible(self, fn):
        was_hidden = not self.root.winfo_viewable()
        if was_hidden:
            self.root.deiconify(); self.root.lift()
            try:
                self.root.attributes("-topmost", True)
                self.root.after(300, lambda: self.root.attributes("-topmost", False))
            except Exception: pass
            self.root.update_idletasks()
        try: fn()
        finally:
            if was_hidden: self.root.withdraw()

    def show_win(self):
        self.root.deiconify(); self.root.lift(); self.root.focus_force()

    def hide_to_tray(self):
        self.root.withdraw()
        try: self.tray.notify("热键依然有效，右键托盘图标可退出。", "已最小化到托盘")
        except Exception: pass

    def shutdown(self):
        self.quit = True
        for h in self.hotkeys:
            try: keyboard.remove_hotkey(h)
            except Exception: pass
        try: keyboard.unhook_all()
        except Exception: pass
        try: self.root.destroy()
        except Exception: pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()