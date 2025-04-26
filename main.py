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

clicking = False
afk_mode = False
click_thread = None
afk_thread = None
tray_icon = None

VERSION = "3.0"
UPDATE_URL = "https://example.com/version.txt"  # Replace with your link.
SETTINGS_FILE = "settings.json"

def check_for_update():
    try:
        response = requests.get(UPDATE_URL, timeout=5)
        latest_version = response.text.strip()
        if latest_version != VERSION:
            messagebox.showinfo("Update Available", f"A new version ({latest_version}) is available!")
        else:
            messagebox.showinfo("Up to Date", "You're using the latest version.")
    except Exception:
        messagebox.showwarning("Update Check Failed", "Could not check for updates.")

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
        mouse.move(random.randint(-5, 5), random.randint(-5, 5), absolute=False, duration=0.2)
        time.sleep(30)

def start_clicking():
    global clicking, click_thread
    hold_key = hold_key_var.get()
    mouse_button = mouse_button_var.get().lower()
    try:
        click_speed = float(speed_var.get())
    except ValueError:
        messagebox.showerror("Invalid Speed", "Click speed must be a number!")
        return

    if not hold_key or not mouse_button:
        messagebox.showerror("Missing Info", "Please fill in all fields.")
        return

    clicking = True
    click_thread = threading.Thread(target=clicker, args=(hold_key, mouse_button, click_speed), daemon=True)
    click_thread.start()
    status_var.set("Status: Clicking...")
    winsound.Beep(1000, 150)
    notification.notify(title="Auto Clicker", message="Clicking Started", timeout=2)

def stop_clicking():
    global clicking
    clicking = False
    status_var.set("Status: Stopped")
    winsound.Beep(500, 150)
    notification.notify(title="Auto Clicker", message="Clicking Stopped", timeout=2)

def toggle_clicker(e=None):
    if clicking:
        stop_clicking()
    else:
        start_clicking()

def start_afk_mode():
    global afk_mode, afk_thread
    afk_mode = True
    afk_thread = threading.Thread(target=afk_mover, daemon=True)
    afk_thread.start()
    status_var.set("Status: AFK Mode Active")

def stop_afk_mode():
    global afk_mode
    afk_mode = False
    status_var.set("Status: AFK Mode Stopped")

def set_speed(speed):
    speed_var.set(str(speed))

def on_close():
    hide_window()

def hide_window():
    root.withdraw()
    notification.notify(title="Auto Clicker", message="Running in background (Tray Icon)", timeout=2)

def show_window(icon, item):
    icon.stop()
    root.after(0, root.deiconify)

def quit_app(icon, item):
    icon.stop()
    root.destroy()

def create_tray_icon():
    image = Image.new('RGB', (64, 64), color=(73, 109, 137))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), fill=(255, 255, 255))
    
    menu = (item('Open', show_window), item('Exit', quit_app))
    icon = pystray.Icon("Minecraft AutoClicker", image, "Auto Clicker", menu)
    return icon

def save_settings():
    settings = {
        "hold_key": hold_key_var.get(),
        "mouse_button": mouse_button_var.get(),
        "speed": speed_var.get(),
        "hotkey": hotkey_var.get()
    }
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            settings = json.load(f)
            hold_key_var.set(settings.get("hold_key", ""))
            mouse_button_var.set(settings.get("mouse_button", "Left"))
            speed_var.set(settings.get("speed", "0.05"))
            hotkey_var.set(settings.get("hotkey", "F6"))
            setup_hotkey()

def change_hotkey():
    def set_new_hotkey(e):
        new_key = e.name
        hotkey_var.set(new_key.upper())
        keyboard.unhook_all_hotkeys()
        setup_hotkey()
        temp.destroy()
        
    temp = tk.Toplevel(root)
    temp.title("Press a new Hotkey")
    temp.geometry("300x100")
    temp.configure(bg="#1e1e1e")
    tk.Label(temp, text="Press any key...", bg="#1e1e1e", fg="white").pack(expand=True)
    temp.bind("<KeyPress>", set_new_hotkey)

def setup_hotkey():
    try:
        keyboard.add_hotkey(hotkey_var.get().lower(), toggle_clicker)
    except Exception as e:
        messagebox.showerror("Error", f"Hotkey binding failed: {e}")

# GUI setup
root = tk.Tk()
root.title("Minecraft Auto Clicker Ultimate v3")
root.geometry("400x500")
root.configure(bg="#1e1e1e")
root.minsize(350, 400)

# Dark Theme Style
style = ttk.Style(root)
style.theme_use("clam")
style.configure(".", background="#1e1e1e", foreground="#ffffff", fieldbackground="#2d2d2d", font=('Segoe UI', 10))
style.map("TButton", background=[('active', '#3e3e3e')])

# Variables
hold_key_var = tk.StringVar()
mouse_button_var = tk.StringVar(value="Left")
speed_var = tk.StringVar(value="0.05")
status_var = tk.StringVar(value="Status: Stopped")
hotkey_var = tk.StringVar(value="F6")

main_frame = ttk.Frame(root)
main_frame.pack(expand=True, fill="both", padx=20, pady=20)

# Layout
def add_label_entry(label, var):
    frame = ttk.Frame(main_frame)
    frame.pack(fill="x", pady=5)
    ttk.Label(frame, text=label).pack(side="left")
    ttk.Entry(frame, textvariable=var).pack(side="right", expand=True, fill="x")

add_label_entry("Hold Key:", hold_key_var)
add_label_entry("Mouse Button:", mouse_button_var)
add_label_entry("Click Speed (seconds):", speed_var)

# Presets
preset_frame = ttk.Frame(main_frame)
preset_frame.pack(fill="x", pady=10)
ttk.Label(preset_frame, text="Presets:").pack(anchor="w")
ttk.Button(preset_frame, text="Slow", command=lambda: set_speed(0.2)).pack(side="left", expand=True, fill="x", padx=2)
ttk.Button(preset_frame, text="Medium", command=lambda: set_speed(0.1)).pack(side="left", expand=True, fill="x", padx=2)
ttk.Button(preset_frame, text="Fast", command=lambda: set_speed(0.05)).pack(side="left", expand=True, fill="x", padx=2)

# Buttons
btn_frame = ttk.Frame(main_frame)
btn_frame.pack(fill="x", pady=10)
ttk.Button(btn_frame, text="Start Clicking", command=start_clicking).pack(side="left", expand=True, fill="x", padx=2)
ttk.Button(btn_frame, text="Stop Clicking", command=stop_clicking).pack(side="left", expand=True, fill="x", padx=2)

afk_frame = ttk.Frame(main_frame)
afk_frame.pack(fill="x", pady=10)
ttk.Button(afk_frame, text="Start AFK", command=start_afk_mode).pack(side="left", expand=True, fill="x", padx=2)
ttk.Button(afk_frame, text="Stop AFK", command=stop_afk_mode).pack(side="left", expand=True, fill="x", padx=2)

# Hotkey and Update
ttk.Label(main_frame, text="Toggle Hotkey:").pack(pady=(10, 2))
ttk.Entry(main_frame, textvariable=hotkey_var, state="readonly", justify="center").pack(fill="x")
ttk.Button(main_frame, text="Change Hotkey", command=change_hotkey).pack(pady=5, fill="x")

ttk.Button(main_frame, text="Check for Updates", command=check_for_update).pack(pady=5, fill="x")
ttk.Button(main_frame, text="Save Settings", command=save_settings).pack(pady=5, fill="x")

ttk.Label(main_frame, textvariable=status_var, font=('Segoe UI', 10, 'bold')).pack(pady=10)

# Start Tray Icon
root.protocol("WM_DELETE_WINDOW", on_close)

tray_icon = create_tray_icon()
tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
tray_thread.start()

load_settings()
root.mainloop()
