import threading
import time
import keyboard
import mouse
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import random

clicking = False
afk_mode = False
click_thread = None
afk_thread = None

VERSION = "1.0"
UPDATE_URL = "https://github.com/nichham2/auto-clicker/blob/0dd6c8b56a01d4239bd82ea6174cd2523d4218d3/version.txt"  # Replace this

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
        time.sleep(30)  # Move mouse every 30 seconds

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

def stop_clicking():
    global clicking
    clicking = False
    status_var.set("Status: Stopped")

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
    stop_clicking()
    stop_afk_mode()
    root.destroy()

root = tk.Tk()
root.title("Minecraft Auto Clicker Ultimate")
root.geometry("350x400")
root.resizable(False, False)

# Set a dark theme manually
root.configure(bg="#1e1e1e")
style = ttk.Style(root)
style.theme_use("clam")
style.configure(".", background="#1e1e1e", foreground="#ffffff", fieldbackground="#2d2d2d")
style.map("TButton", background=[('active', '#3e3e3e')])

# Variables
hold_key_var = tk.StringVar()
mouse_button_var = tk.StringVar(value="Left")
speed_var = tk.StringVar(value="0.05")
status_var = tk.StringVar(value="Status: Stopped")
hotkey_var = tk.StringVar(value="F6")

# UI Elements
ttk.Label(root, text="Hold Key:").pack(pady=5)
ttk.Entry(root, textvariable=hold_key_var).pack()

ttk.Label(root, text="Mouse Button:").pack(pady=5)
ttk.Combobox(root, textvariable=mouse_button_var, values=["Left", "Right", "Middle"], state="readonly").pack()

ttk.Label(root, text="Click Speed (seconds):").pack(pady=5)
ttk.Entry(root, textvariable=speed_var).pack()

ttk.Label(root, text="Presets:").pack(pady=5)
preset_frame = ttk.Frame(root)
preset_frame.pack(pady=5)

ttk.Button(preset_frame, text="Slow", command=lambda: set_speed(0.2)).pack(side="left", padx=5)
ttk.Button(preset_frame, text="Medium", command=lambda: set_speed(0.1)).pack(side="left", padx=5)
ttk.Button(preset_frame, text="Fast", command=lambda: set_speed(0.05)).pack(side="left", padx=5)

ttk.Button(root, text="Start Clicking", command=start_clicking).pack(pady=5)
ttk.Button(root, text="Stop Clicking", command=stop_clicking).pack(pady=5)

ttk.Button(root, text="Start AFK Mode", command=start_afk_mode).pack(pady=5)
ttk.Button(root, text="Stop AFK Mode", command=stop_afk_mode).pack(pady=5)

ttk.Label(root, textvariable=status_var, font=('Segoe UI', 10)).pack(pady=5)

ttk.Label(root, text="Press hotkey to toggle clicking:").pack()
ttk.Entry(root, textvariable=hotkey_var, state="readonly", justify="center").pack()

ttk.Button(root, text="Check for Updates", command=check_for_update).pack(pady=5)

# Bind hotkey
def setup_hotkey():
    try:
        keyboard.add_hotkey(hotkey_var.get().lower(), toggle_clicker)
    except Exception as e:
        messagebox.showerror("Error", f"Hotkey binding failed: {e}")

setup_hotkey()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
