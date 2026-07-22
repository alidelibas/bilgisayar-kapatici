# -*- coding: utf-8 -*-
"""
Bilgisayar Kapatici
--------------------
Windows icin zamanlayicili kapatma / yeniden baslatma / oturum kapatma /
kilitleme / uyku modu / alarm uygulamasi.

Gereksinimler (kendi bilgisayarinizda .exe olusturmadan once):
    pip install pystray pillow

.exe olusturmak icin (Windows uzerinde, bu klasorde):
    pip install pyinstaller pystray pillow
    pyinstaller --onefile --noconsole --icon=icon.ico --name "BilgisayarKapatici" main.py

Olusan .exe dosyasi: dist/BilgisayarKapatici.exe
"""

import sys
import os
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

IS_WINDOWS = sys.platform.startswith("win")

# pystray / PIL sadece sistem tepsisi (tray) icin gerekli. Yoksa uygulama
# yine calisir, sadece "tepsiye kucult" ozelligi pasif olur.
try:
    import pystray
    from PIL import Image
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

if IS_WINDOWS:
    try:
        import winsound
    except ImportError:
        winsound = None
else:
    winsound = None

BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")

# ---------------------------------------------------------------------------
# Renkler - Koyu tema 
# ---------------------------------------------------------------------------
COLOR_BG = "#262624"            # ana arka plan (koyu, sicak gri)
COLOR_TITLEBAR = "#1F1E1D"      # baslik cubugu (biraz daha koyu)
COLOR_ACCENT = "#CC785C"        # sicak terrakota vurgu rengi
COLOR_ACCENT_HOVER = "#B8684F"
COLOR_TEXT = "#E8E6E3"          # ana metin (kirik beyaz)
COLOR_SUBTEXT = "#9C9A97"       # ikincil / soluk metin
COLOR_CARD = "#30302E"          # kart / panel arka plani
COLOR_BORDER = "#3E3D3A"        # ince kenarliklar
COLOR_DANGER = "#C4554D"
COLOR_DANGER_HOVER = "#AC463F"
COLOR_HOVER_NEUTRAL = "#3A3937"   # notr hover (baslik cubugu butonlari)
COLOR_INPUT_BG = "#3A3937"        # spinbox arka plani
COLOR_DISABLED_BG = "#3A3937"
COLOR_DISABLED_FG = "#6E6C69"
COLOR_RESUME_BG = "#33402F"       # 'Devam Et' - koyu, yumusak yesil ton
COLOR_RESUME_HOVER = "#3D4C38"
COLOR_RESUME_FG = "#A9CBA0"
COLOR_CANCEL_BG = "#3D2A27"        # 'Iptal Et' - koyu, yumusak kirmizi ton
COLOR_CANCEL_HOVER = "#48322E"
COLOR_CANCEL_FG = "#E0958C"


class BilgisayarKapatici(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Bilgisayar Kapatici")
        self.geometry("380x560")
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)

        # Ozel (cerceve olmayan) pencere - kendi baslik cubugumuzu cizecegiz
        self.overrideredirect(True)

        try:
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass

        # Durum degiskenleri
        self.state_mode = "idle"          # idle | running | paused
        self.remaining_seconds = 0
        self.total_seconds = 0
        self.countdown_job = None
        self.alarm_playing = False
        self.tray_icon = None

        self.action_var = tk.StringVar(value="kapat")

        self._build_titlebar()
        self._build_body()

        # Pencereyi ekranda ortala
        self.update_idletasks()
        w, h = 350, 650
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # Baslik cubugu (custom titlebar)
    # ------------------------------------------------------------------
    def _build_titlebar(self):
        bar = tk.Frame(self, bg=COLOR_TITLEBAR, height=40)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        icon_lbl = tk.Label(bar, text="\u23FB", bg=COLOR_TITLEBAR,
                             fg=COLOR_ACCENT, font=("Segoe UI", 13, "bold"))
        icon_lbl.pack(side="left", padx=(12, 6))

        title_lbl = tk.Label(bar, text="Bilgisayar Kapatici", bg=COLOR_TITLEBAR,
                              fg=COLOR_TEXT, font=("Segoe UI", 10, "bold"))
        title_lbl.pack(side="left")

        # Surukleyerek pencereyi tasima
        for widget in (bar, icon_lbl, title_lbl):
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)

        # Sag ust butonlar: kucult, tepsiye kucult, kapat
        btn_close = self._titlebar_button(bar, "\u2715", self.on_close,
                                           hover_bg=COLOR_DANGER, hover_fg=COLOR_TEXT)
        btn_close.pack(side="right", fill="y")

        btn_tray = self._titlebar_button(bar, "\u2013", self.minimize_to_tray)
        # tepsiye kucult icin tepsi simgesi kullan
        btn_tray.config(text="\u25A0")
        btn_tray.pack(side="right", fill="y")

        btn_min = self._titlebar_button(bar, "\u2013", self.minimize_window)
        btn_min.pack(side="right", fill="y")

    def _titlebar_button(self, parent, text, command, hover_bg=COLOR_HOVER_NEUTRAL,
                          hover_fg=COLOR_TEXT):
        btn = tk.Label(parent, text=text, bg=COLOR_TITLEBAR, fg=COLOR_TEXT,
                        font=("Segoe UI", 11), width=4, cursor="hand2")

        def on_enter(_e):
            btn.config(bg=hover_bg, fg=hover_fg)

        def on_leave(_e):
            btn.config(bg=COLOR_TITLEBAR, fg=COLOR_TEXT)

        def on_click(_e):
            command()

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<Button-1>", on_click)
        return btn

    def _start_move(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_move(self, event):
        x = self.winfo_pointerx() - self._drag_x
        y = self.winfo_pointery() - self._drag_y
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # Govde (body)
    # ------------------------------------------------------------------
    def _build_body(self):
        body = tk.Frame(self, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=18, pady=(14, 16))

        # --- Zaman ayari karti ---
        time_card = tk.Frame(body, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                              highlightthickness=1)
        time_card.pack(fill="x", pady=(0, 12))

        tk.Label(time_card, text="Sure Ayari", bg=COLOR_CARD, fg=COLOR_SUBTEXT,
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(10, 2))

        time_row = tk.Frame(time_card, bg=COLOR_CARD)
        time_row.pack(padx=14, pady=(0, 14))

        self.hour_var = tk.StringVar(value="01")
        self.min_var = tk.StringVar(value="00")
        self.sec_var = tk.StringVar(value="00")

        self.hour_spin = self._make_spinbox(time_row, self.hour_var, 0, 23)
        tk.Label(time_row, text="Saat", bg=COLOR_CARD, fg=COLOR_SUBTEXT,
                  font=("Segoe UI", 8)).grid(row=1, column=0)

        tk.Label(time_row, text=":", bg=COLOR_CARD, fg=COLOR_TEXT,
                  font=("Segoe UI", 16, "bold")).grid(row=0, column=1, padx=4)

        self.min_spin = self._make_spinbox(time_row, self.min_var, 0, 59)
        tk.Label(time_row, text="Dakika", bg=COLOR_CARD, fg=COLOR_SUBTEXT,
                  font=("Segoe UI", 8)).grid(row=1, column=2)

        tk.Label(time_row, text=":", bg=COLOR_CARD, fg=COLOR_TEXT,
                  font=("Segoe UI", 16, "bold")).grid(row=0, column=3, padx=4)

        self.sec_spin = self._make_spinbox(time_row, self.sec_var, 0, 59)
        tk.Label(time_row, text="Saniye", bg=COLOR_CARD, fg=COLOR_SUBTEXT,
                  font=("Segoe UI", 8)).grid(row=1, column=4)

        # --- Geri sayim gostergesi ---
        self.countdown_lbl = tk.Label(body, text="01:00:00", bg=COLOR_BG,
                                       fg=COLOR_ACCENT, font=("Segoe UI", 30, "bold"))
        self.countdown_lbl.pack(pady=(2, 10))

        self.status_lbl = tk.Label(body, text="Hazir", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                                    font=("Segoe UI", 9))
        self.status_lbl.pack(pady=(0, 10))

        # --- Eylem secimi karti ---
        action_card = tk.Frame(body, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                                highlightthickness=1)
        action_card.pack(fill="x", pady=(0, 14))

        tk.Label(action_card, text="Ne Yapilsin?", bg=COLOR_CARD, fg=COLOR_SUBTEXT,
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(10, 4))

        actions = [
            ("kapat", "\u23FB  Kapat"),
            ("yeniden_baslat", "\u21BB  Yeniden Baslat"),
            ("oturum_kapat", "\u26AA  Oturumu Kapat"),
            ("oturum_kilitle", "\u1F512 Oturumu Kilitle".replace("\u1F512", "\U0001F512")),
            ("uyku", "\u263D  Uyku Modu"),
            ("alarm", "\u23F0  Alarm Cal"),
        ]
        for value, label in actions:
            rb = tk.Radiobutton(action_card, text=label, value=value,
                                 variable=self.action_var, bg=COLOR_CARD,
                                 fg=COLOR_TEXT, activebackground=COLOR_CARD,
                                 selectcolor=COLOR_CARD, font=("Segoe UI", 10),
                                 anchor="w", padx=4, cursor="hand2")
            rb.pack(fill="x", padx=14, pady=2)
        tk.Frame(action_card, bg=COLOR_CARD, height=6).pack()

        # --- Alt butonlar ---
        btn_row = tk.Frame(body, bg=COLOR_BG)
        btn_row.pack(fill="x", pady=(4, 0))

        self.start_stop_btn = self._make_button(
            btn_row, "Baslat", self.on_start_stop, COLOR_ACCENT, COLOR_ACCENT_HOVER)
        self.start_stop_btn.pack(fill="x", pady=(0, 8))

        small_row = tk.Frame(body, bg=COLOR_BG)
        small_row.pack(fill="x")

        self.resume_btn = self._make_button(
            small_row, "Devam Et", self.on_resume, COLOR_RESUME_BG, COLOR_RESUME_HOVER,
            fg=COLOR_RESUME_FG)
        self.resume_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.resume_btn.config(state="disabled")

        self.cancel_btn = self._make_button(
            small_row, "Iptal Et", self.on_cancel, COLOR_CANCEL_BG, COLOR_CANCEL_HOVER,
            fg=COLOR_CANCEL_FG)
        self.cancel_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))
        self.cancel_btn.config(state="disabled")

    def _make_spinbox(self, parent, var, lo, hi):
        sb = tk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=3,
                         font=("Segoe UI", 20, "bold"), justify="center",
                         format="%02.0f", relief="flat", bg=COLOR_INPUT_BG,
                         fg=COLOR_TEXT, buttonbackground=COLOR_ACCENT,
                         insertbackground=COLOR_TEXT,
                         disabledbackground=COLOR_INPUT_BG,
                         disabledforeground=COLOR_DISABLED_FG)
        col = parent.grid_size()[0]
        sb.grid(row=0, column=col, padx=2)
        return sb

    def _make_button(self, parent, text, command, bg, hover_bg, fg=COLOR_TEXT):
        btn = tk.Label(parent, text=text, bg=bg, fg=fg, font=("Segoe UI", 11, "bold"),
                        cursor="hand2", pady=10)

        def on_enter(_e):
            if btn.cget("state") if hasattr(btn, "cget") else True:
                btn.config(bg=hover_bg)

        def on_leave(_e):
            btn.config(bg=bg)

        def on_click(_e):
            if getattr(btn, "_disabled", False):
                return
            command()

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<Button-1>", on_click)
        btn._normal_bg = bg
        btn._hover_bg = hover_bg
        btn._disabled = False

        def config_state(state=None, **kwargs):
            if state == "disabled":
                btn._disabled = True
                btn.config(bg=COLOR_DISABLED_BG, fg=COLOR_DISABLED_FG, cursor="arrow")
            elif state == "normal":
                btn._disabled = False
                btn.config(bg=bg, fg=fg, cursor="hand2")

        btn.config = self._wrap_config(btn, config_state)
        return btn

    def _wrap_config(self, widget, custom_state_fn):
        original_config = tk.Label.config

        def new_config(*args, **kwargs):
            if "state" in kwargs and len(kwargs) == 1:
                custom_state_fn(state=kwargs["state"])
            else:
                original_config(widget, *args, **kwargs)
        return new_config

    # ------------------------------------------------------------------
    # Pencere kontrolleri
    # ------------------------------------------------------------------
    def minimize_window(self):
        # overrideredirect pencerelerde dogrudan iconify calismayabilir,
        # bu yuzden gecici olarak kaldirip geri veriyoruz.
        self.overrideredirect(False)
        self.iconify()

        def on_restore(event=None):
            if self.state() == "normal":
                self.overrideredirect(True)
                self.unbind("<Map>")

        self.bind("<Map>", on_restore)

    def minimize_to_tray(self):
        if not TRAY_AVAILABLE:
            messagebox.showinfo(
                "Bilgi",
                "Sistem tepsisi ozelligi icin 'pystray' ve 'pillow' "
                "kutuphaneleri gerekiyor.\n\npip install pystray pillow"
            )
            return
        self.withdraw()
        self._create_tray_icon()

    def _create_tray_icon(self):
        if self.tray_icon is not None:
            return
        try:
            image = Image.open(ICON_PATH)
        except Exception:
            image = Image.new("RGB", (64, 64), COLOR_ACCENT)

        menu = pystray.Menu(
            pystray.MenuItem("Ac", self._tray_restore, default=True),
            pystray.MenuItem("Kapat", self._tray_quit),
        )
        self.tray_icon = pystray.Icon("BilgisayarKapatici", image,
                                       "Bilgisayar Kapatici", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_restore(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_quit(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.after(0, self.destroy)

    def on_close(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()

    # ------------------------------------------------------------------
    # Geri sayim mantigi
    # ------------------------------------------------------------------
    def _read_time_inputs(self):
        try:
            h = int(self.hour_var.get())
            m = int(self.min_var.get())
            s = int(self.sec_var.get())
        except ValueError:
            h, m, s = 1, 0, 0
        return h * 3600 + m * 60 + s

    def _format_seconds(self, total):
        h, rem = divmod(max(total, 0), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def on_start_stop(self):
        if self.state_mode == "idle":
            total = self._read_time_inputs()
            if total <= 0:
                messagebox.showwarning("Uyari", "Lutfen 0'dan buyuk bir sure girin.")
                return
            self.total_seconds = total
            self.remaining_seconds = total
            self.state_mode = "running"
            self.start_stop_btn.config(text="Durdur")
            self.status_lbl.config(text=f"Calisiyor - {self._action_label()}")
            self.resume_btn.config(state="disabled")
            self.cancel_btn.config(state="normal")
            self._set_inputs_enabled(False)
            self._tick()

        elif self.state_mode == "running":
            # Durdur = duraklat
            self._cancel_job()
            self.state_mode = "paused"
            self.start_stop_btn.config(text="Baslat", state="disabled")
            self.resume_btn.config(state="normal")
            self.cancel_btn.config(state="normal")
            self.status_lbl.config(text="Duraklatildi")

    def on_resume(self):
        if self.state_mode != "paused":
            return
        self.state_mode = "running"
        self.start_stop_btn.config(text="Durdur", state="normal")
        self.resume_btn.config(state="disabled")
        self.status_lbl.config(text=f"Calisiyor - {self._action_label()}")
        self._tick()

    def on_cancel(self):
        self._cancel_job()
        self._stop_alarm()
        self.state_mode = "idle"
        self.remaining_seconds = 0
        total = self._read_time_inputs()
        self.countdown_lbl.config(text=self._format_seconds(total))
        self.status_lbl.config(text="Hazir")
        self.start_stop_btn.config(text="Baslat", state="normal")
        self.resume_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")
        self._set_inputs_enabled(True)

    def _set_inputs_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for sp in (self.hour_spin, self.min_spin, self.sec_spin):
            sp.config(state=state)

    def _action_label(self):
        labels = {
            "kapat": "Kapatma",
            "yeniden_baslat": "Yeniden Baslatma",
            "oturum_kapat": "Oturum Kapatma",
            "oturum_kilitle": "Kilitleme",
            "uyku": "Uyku Modu",
            "alarm": "Alarm",
        }
        return labels.get(self.action_var.get(), "")

    def _tick(self):
        self.countdown_lbl.config(text=self._format_seconds(self.remaining_seconds))
        if self.remaining_seconds <= 0:
            self._on_countdown_finished()
            return
        self.remaining_seconds -= 1
        self.countdown_job = self.after(1000, self._tick)

    def _cancel_job(self):
        if self.countdown_job is not None:
            self.after_cancel(self.countdown_job)
            self.countdown_job = None

    def _on_countdown_finished(self):
        action = self.action_var.get()
        self.status_lbl.config(text="Sure doldu!")

        if action == "alarm":
            self._play_alarm()
            self.state_mode = "idle"
            self.start_stop_btn.config(text="Baslat", state="normal")
            self.cancel_btn.config(state="normal")
            self.resume_btn.config(state="disabled")
            return

        self._execute_system_action(action)
        self.on_cancel()

    # ------------------------------------------------------------------
    # Alarm
    # ------------------------------------------------------------------
    def _play_alarm(self):
        self.alarm_playing = True

        def loop_beep():
            while self.alarm_playing:
                if IS_WINDOWS and winsound is not None:
                    try:
                        winsound.Beep(1000, 600)
                    except Exception:
                        pass
                else:
                    print("\a", end="", flush=True)
                import time
                time.sleep(0.3)

        threading.Thread(target=loop_beep, daemon=True).start()
        self.after(0, lambda: messagebox.showinfo(
            "Alarm", "Sure doldu! Alarmi durdurmak icin 'Iptal Et' butonuna basin."))

    def _stop_alarm(self):
        self.alarm_playing = False

    # ------------------------------------------------------------------
    # Sistem eylemleri (yalnizca Windows'ta gercekten calisir)
    # ------------------------------------------------------------------
    def _execute_system_action(self, action):
        commands = {
            "kapat": "shutdown /s /t 0",
            "yeniden_baslat": "shutdown /r /t 0",
            "oturum_kapat": "shutdown /l",
            "oturum_kilitle": "rundll32.exe user32.dll,LockWorkStation",
            "uyku": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
        }
        cmd = commands.get(action)
        if not cmd:
            return

        if IS_WINDOWS:
            try:
                subprocess.run(cmd, shell=True, check=False)
            except Exception as e:
                messagebox.showerror("Hata", f"Islem calistirilamadi:\n{e}")
        else:
            # Windows disinda test amacli sadece bilgi goster
            messagebox.showinfo(
                "Test Modu",
                f"(Windows disinda calistiginiz icin komut calistirilmadi)\n"
                f"Calistirilacak komut: {cmd}"
            )


if __name__ == "__main__":
    app = BilgisayarKapatici()
    app.mainloop()
