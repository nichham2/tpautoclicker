import threading, time, random, json, os
import keyboard, mouse, winsound, requests
import tkinter as tk
from tkinter import ttk, messagebox
from plyer import notification
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

# ─── Global State ─────────────────────────────────────────────────────────────
clicking = False
afk_mode = False
click_thread = None
afk_thread = None
tray_icon = None
setting_hold_key = False
current_hotkey = None

VERSION = "3.3"
UPDATE_URL = "https://raw.githubusercontent.com/nichham2/auto-clicker/main/version.txt"
SETTINGS_FILE = "settings.json"

# ─── Core Logic ────────────────────────────────────────────────────────────────
def check_for_update():
    try:
        r = requests.get(UPDATE_URL, timeout=5)
        latest = r.text.strip()
        if latest != VERSION:
            messagebox.showinfo("Update Available", f"New version: {latest}")
        else:
            messagebox.showinfo("Up to Date", "You're on the latest version.")
    except:
        messagebox.showwarning("Update Failed", "Could not reach update server.")

def clicker(hold_key, mb, sp):
    global clicking
    while clicking:
        if hold_key:
            if not keyboard.is_pressed(hold_key):
                keyboard.press(hold_key)
        mouse.click(mb)
        time.sleep(sp)
    if hold_key and keyboard.is_pressed(hold_key):
        keyboard.release(hold_key)

def afk_mover():
    global afk_mode
    while afk_mode:
        mouse.move(random.randint(-5,5), random.randint(-5,5), absolute=False, duration=0.2)
        time.sleep(30)

def start_clicking():
    global clicking, click_thread
    hk = hold_key_var.get()
    mb = mouse_button_var.get().lower()
    try:
        sp = float(speed_var.get())
    except ValueError:
        return messagebox.showerror("Invalid Speed", "Speed must be a number.")
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
    else:        start_clicking()

def start_afk(): 
    global afk_mode, afk_thread
    afk_mode = True
    afk_thread = threading.Thread(target=afk_mover, daemon=True)
    afk_thread.start()
    status_var.set("Status: AFK Mode")

def stop_afk():  
    global afk_mode
    afk_mode = False
    status_var.set("Status: AFK Stopped")

def set_speed(v):
    speed_var.set(str(v))

# ─── Tray & Window ────────────────────────────────────────────────────────────
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
    img = Image.new('RGB',(64,64),color=(30,30,30))
    d   = ImageDraw.Draw(img)
    d.rectangle((8,8,56,56), fill=(200,200,200))
    menu = (item('Open', show_window), item('Exit', quit_app))
    return pystray.Icon("AutoClicker", img, "OP Auto Clicker", menu)

# ─── Persistence ───────────────────────────────────────────────────────────────
def save_settings():
    data = {
        "hold_key": hold_key_var.get(),
        "mouse_button": mouse_button_var.get(),
        "speed": speed_var.get(),
        "hotkey": hotkey_var.get()
    }
    with open(SETTINGS_FILE,'w') as f:
        json.dump(data, f)

def load_settings():
    global current_hotkey
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
            hold_key_var.set(s.get("hold_key",""))
            mouse_button_var.set(s.get("mouse_button","Left"))
            speed_var.set(s.get("speed","0.05"))
            hk = s.get("hotkey","F6")
            hotkey_var.set(hk)
            current_hotkey = hk
    else:
        # first run: use default F6
        current_hotkey = hotkey_var.get()
    setup_hotkey()

# ─── Hotkey Bind ───────────────────────────────────────────────────────────────
def setup_hotkey():
    try:
        keyboard.add_hotkey(current_hotkey.lower(), toggle_clicker)
    except Exception as e:
        messagebox.showerror("Hotkey Error", str(e))

def on_hotkey_change(*_):
    global current_hotkey
    new = hotkey_var.get()
    if current_hotkey:
        try: keyboard.remove_hotkey(current_hotkey.lower())
        except: pass
    current_hotkey = new
    setup_hotkey()

# ─── Hold-Key Capture ──────────────────────────────────────────────────────────
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
root.title("OP Auto Clicker 3.3")
root.geometry("420x500")
root.minsize(380,460)
root.configure(bg="#ececec")

style = ttk.Style(root)
style.theme_use("clam")
style.configure(".", background="#ececec", foreground="#000", fieldbackground="#fff")
style.map("TButton", background=[('active','#ddd')])

# Variables
hold_key_var     = tk.StringVar()
mouse_button_var = tk.StringVar(value="Left")
speed_var        = tk.StringVar(value="0.05")
hotkey_var       = tk.StringVar(value="F6")
status_var       = tk.StringVar(value="Status: Stopped")

# Notebook
nb = ttk.Notebook(root)
ctl = ttk.Frame(nb);  nb.add(ctl, text="Controls")
stg = ttk.Frame(nb);  nb.add(stg, text="Settings")
nb.pack(expand=True, fill="both", padx=10, pady=10)

# — Controls Tab —
cf = ctl
bf = ttk.Frame(cf); bf.pack(fill="x", pady=10)
ttk.Button(bf, text="Start Clicking", command=start_clicking)\
    .grid(row=0,column=0,sticky="ew",padx=5)
ttk.Button(bf, text="Stop Clicking",  command=stop_clicking)\
    .grid(row=0,column=1,sticky="ew",padx=5)
bf.columnconfigure(0,weight=1); bf.columnconfigure(1,weight=1)

af = ttk.Frame(cf); af.pack(fill="x", pady=5)
ttk.Button(af, text="Start AFK", command=start_afk).grid(row=0,column=0,sticky="ew",padx=5)
ttk.Button(af, text="Stop AFK",  command=stop_afk).grid(row=0,column=1,sticky="ew",padx=5)
af.columnconfigure(0,weight=1); af.columnconfigure(1,weight=1)

ttk.Label(cf, textvariable=status_var, font=('Segoe UI',12,'bold')).pack(pady=20)

# — Settings Tab —
sf = stg

# Hold Key
hkf = ttk.LabelFrame(sf, text="Hold Key (optional)")
hkf.pack(fill="x", pady=5)
ttk.Entry(hkf, textvariable=hold_key_var).pack(side="left",expand=True,fill="x",padx=5,pady=5)
ttk.Button(hkf, text="Set Key", command=start_set_hold_key).pack(side="right",padx=5,pady=5)

# Mouse Button
mbf = ttk.Frame(sf); mbf.pack(fill="x", pady=5)
ttk.Label(mbf, text="Mouse Button:").pack(side="left", padx=5)
ttk.Combobox(mbf, textvariable=mouse_button_var,
             values=["Left","Right","Middle"], state="readonly")\
    .pack(side="right",expand=True,fill="x",padx=5)

# Click Speed + Presets
spf = ttk.LabelFrame(sf, text="Click Speed (seconds)")
spf.pack(fill="x", pady=5)
ttk.Entry(spf, textvariable=speed_var, width=10).pack(side="left",padx=5,pady=5)
pf = ttk.Frame(spf); pf.pack(side="right",padx=5)
for t,v in [("Slow",0.2),("Med",0.1),("Fast",0.05)]:
    ttk.Button(pf, text=t, width=6, command=lambda vv=v: set_speed(vv))\
        .pack(side="left",padx=2)

# Hotkey Dropdown
hkdf = ttk.LabelFrame(sf, text="Toggle Hotkey")
hkdf.pack(fill="x", pady=5)
opts = ["F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
        "Space","Ctrl","Alt","Shift","Enter","Esc"]
cb = ttk.Combobox(hkdf, textvariable=hotkey_var, values=opts,
                  state="readonly")
cb.pack(fill="x",padx=5,pady=5)
hotkey_var.trace_add("write", on_hotkey_change)

# Updates & Save
ttk.Button(sf, text="Check for Updates", command=check_for_update).pack(fill="x", pady=5, padx=5)
ttk.Button(sf, text="Save Settings",      command=save_settings).pack(fill="x", pady=5, padx=5)

# Final
root.protocol("WM_DELETE_WINDOW", on_close)
tray_icon = create_tray_icon()
threading.Thread(target=tray_icon.run, daemon=True).start()
load_settings()
root.mainloop()
