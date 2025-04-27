import threading
import time
import keyboard
import mouse
import tkinter as tk
from tkinter import ttk, messagebox
import random
import requests
import winsound
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
from plyer import notification
import json
import os

# ─── Global State ─────────────────────────────────────────────────────────────
clicking = False
afk_mode = False
click_thread = None
afk_thread = None
tray_icon = None
current_hotkey = None
setting_hold_key = False

VERSION = "3.1"
UPDATE_URL = "https://raw.githubusercontent.com/nichham2/auto-clicker/main/version.txt"
SETTINGS_FILE = "settings.json"

# ─── Core Functionality ────────────────────────────────────────────────────────
def check_for_update():
    try:
        r = requests.get(UPDATE_URL, timeout=5)
        latest = r.text.strip()
        if latest != VERSION:
            messagebox.showinfo("Update Available", f"New version: {latest}")
        else:
            messagebox.showinfo("Up to Date", "You're on the latest version.")
    except:
        messagebox.showwarning("Update Check Failed", "Could not reach update server.")

def clicker(hold_key, mouse_button, click_speed):
    global clicking
    while clicking:
        if not keyboard.is_pressed(hold_key):
            keyboard.press(hold_key)
        mouse.click(mouse_button)
        time.sleep(click_speed)
    if keyboard.is_pressed(hold_key):
        keyboard.release(hold_key)

def afk_mover():
    while afk_mode:
        mouse.move(random.randint(-5,5), random.randint(-5,5),
                   absolute=False, duration=0.2)
        time.sleep(30)

def start_clicking():
    global clicking, click_thread
    hk = hold_key_var.get()
    mb = mouse_button_var.get().lower()
    try:
        sp = float(speed_var.get())
    except ValueError:
        return messagebox.showerror("Invalid Speed", "Speed must be a number.")
    if not hk:
        return messagebox.showerror("Missing Info", "Set a Hold Key first.")
    clicking = True
    click_thread = threading.Thread(target=clicker, args=(hk, mb, sp), daemon=True)
    click_thread.start()
    status_var.set("Status: Clicking…")
    winsound.Beep(1000,150)
    notification.notify(title="Auto Clicker", message="Clicking Started", timeout=2)

def stop_clicking():
    global clicking
    clicking = False
    status_var.set("Status: Stopped")
    winsound.Beep(500,150)
    notification.notify(title="Auto Clicker", message="Clicking Stopped", timeout=2)

def toggle_clicker(e=None):
    if clicking: stop_clicking()
    else:       start_clicking()

def start_afk_mode():
    global afk_mode, afk_thread
    afk_mode = True
    afk_thread = threading.Thread(target=afk_mover, daemon=True)
    afk_thread.start()
    status_var.set("Status: AFK Mode")

def stop_afk_mode():
    global afk_mode
    afk_mode = False
    status_var.set("Status: AFK Stopped")

def set_speed(v):
    speed_var.set(str(v))

# ─── Tray & Window management ─────────────────────────────────────────────────
def hide_window():
    root.withdraw()
    notification.notify(title="Auto Clicker", message="Minimized to Tray", timeout=2)

def on_close():
    hide_window()

def show_window(icon, item):
    icon.stop()
    root.after(0, root.deiconify)

def quit_app(icon, item):
    icon.stop()
    root.destroy()

def create_tray_icon():
    img = Image.new('RGB', (64,64), color=(30,30,30))
    d  = ImageDraw.Draw(img)
    d.rectangle((8,8,56,56), fill=(200,200,200))
    menu = (item('Open', show_window), item('Exit', quit_app))
    icon = pystray.Icon("AutoClicker", img, "OP Auto Clicker", menu)
    return icon

# ─── Settings Persistence ─────────────────────────────────────────────────────
def save_settings():
    with open(SETTINGS_FILE,'w') as f:
        json.dump({
            "hold_key": hold_key_var.get(),
            "mouse_button": mouse_button_var.get(),
            "speed": speed_var.get(),
            "hotkey": hotkey_var.get()
        }, f)

def load_settings():
    global current_hotkey
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
            hold_key_var.set(s.get("hold_key",""))
            mouse_button_var.set(s.get("mouse_button","Left"))
            speed_var.set(s.get("speed","0.05"))
            hotkey = s.get("hotkey","F6")
            hotkey_var.set(hotkey)
            current_hotkey = hotkey
            setup_hotkey()

# ─── Hotkey Binding ────────────────────────────────────────────────────────────
def setup_hotkey():
    try:
        keyboard.add_hotkey(current_hotkey.lower(), toggle_clicker)
    except Exception as e:
        messagebox.showerror("Hotkey Error", str(e))

def on_hotkey_change(e=None):
    global current_hotkey
    new = hotkey_var.get()
    if current_hotkey:
        try: keyboard.remove_hotkey(current_hotkey.lower())
        except: pass
    current_hotkey = new
    setup_hotkey()

# ─── Hold-Key Capture (in-window) ─────────────────────────────────────────────
def on_key_press(e):
    global setting_hold_key
    if setting_hold_key:
        hold_key_var.set(e.keysym.upper())
        setting_hold_key = False
        root.unbind("<KeyPress>")

def start_set_hold_key():
    global setting_hold_key
    setting_hold_key = True
    root.bind("<KeyPress>", on_key_press)

# ─── GUI ──────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("OP Auto Clicker 3.1")
root.geometry("400x480")
root.minsize(360,440)
root.configure(bg="#ececec")

style = ttk.Style(root)
style.theme_use("clam")
style.configure(".", background="#ececec", foreground="#000", fieldbackground="#fff")
style.map("TButton", background=[('active','#ddd')])

hold_key_var   = tk.StringVar()
mouse_button_var = tk.StringVar(value="Left")
speed_var      = tk.StringVar(value="0.05")
status_var     = tk.StringVar(value="Status: Stopped")
hotkey_var     = tk.StringVar(value="F6")

main = ttk.Frame(root)
main.pack(expand=True, fill="both", padx=15, pady=15)

# — Hold Key —
hkf = ttk.Frame(main); hkf.pack(fill="x", pady=5)
ttk.Label(hkf, text="Hold Key:").pack(side="left")
ttk.Entry(hkf, textvariable=hold_key_var).pack(side="left", expand=True, fill="x", padx=5)
ttk.Button(hkf, text="Set Key",   command=start_set_hold_key).pack(side="right")

# — Mouse Button —
mbf = ttk.Frame(main); mbf.pack(fill="x", pady=5)
ttk.Label(mbf, text="Mouse Button:").pack(side="left")
ttk.Combobox(
    mbf,
    textvariable=mouse_button_var,
    values=["Left","Right","Middle"],
    state="readonly"
).pack(side="right", expand=True, fill="x")

# — Click Speed —
spf = ttk.Frame(main); spf.pack(fill="x", pady=5)
ttk.Label(spf, text="Click Speed (s):").pack(side="left")
ttk.Entry(spf, textvariable=speed_var, width=8).pack(side="right")

# — Presets —
prf = ttk.Frame(main); prf.pack(fill="x", pady=10)
ttk.Label(prf, text="Presets:").grid(row=0,column=0, sticky="w")
for i,(t,v) in enumerate([("Slow",0.2),("Med",0.1),("Fast",0.05)]):
    ttk.Button(prf, text=t, command=lambda vv=v: set_speed(vv))\
        .grid(row=0, column=i+1, padx=5, sticky="ew")
prf.columnconfigure(1, weight=1); prf.columnconfigure(2, weight=1); prf.columnconfigure(3, weight=1)

# — Hotkey Dropdown —
hkdf = ttk.LabelFrame(main, text="Toggle Hotkey")
hkdf.pack(fill="x", pady=10)
options = ["F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
           "Space","Ctrl","Alt","Shift","Enter","Esc"]
ttk.Combobox(
    hkdf,
    textvariable=hotkey_var,
    values=options,
    state="readonly"
).pack(fill="x", padx=5, pady=5)
hotkey_var.trace_add("write", lambda *a: on_hotkey_change())

# — Control Buttons —
btnf = ttk.Frame(main); btnf.pack(fill="x", pady=10)
ttk.Button(btnf, text="Start Clicking", command=start_clicking)\
    .grid(row=0,column=0,sticky="ew", padx=5)
ttk.Button(btnf, text="Stop Clicking",  command=stop_clicking)\
    .grid(row=0,column=1,sticky="ew", padx=5)
btnf.columnconfigure(0,weight=1); btnf.columnconfigure(1,weight=1)

# — AFK Buttons —
afkf = ttk.Frame(main); afkf.pack(fill="x", pady=5)
ttk.Button(afkf, text="Start AFK", command=start_afk_mode)\
    .grid(row=0,column=0,sticky="ew", padx=5)
ttk.Button(afkf, text="Stop AFK",  command=stop_afk_mode)\
    .grid(row=0,column=1,sticky="ew", padx=5)
afkf.columnconfigure(0,weight=1); afkf.columnconfigure(1,weight=1)

# — Other Actions & Status —
ttk.Button(main, text="Check for Updates", command=check_for_update).pack(fill="x", pady=5)
ttk.Button(main, text="Save Settings",      command=save_settings).pack(fill="x", pady=5)
ttk.Label(main, textvariable=status_var, font=('Segoe UI',10,'bold'))\
    .pack(pady=10)

# — Final Setup —
root.protocol("WM_DELETE_WINDOW", on_close)
tray_icon = create_tray_icon()
threading.Thread(target=tray_icon.run, daemon=True).start()
load_settings()
root.mainloop()
