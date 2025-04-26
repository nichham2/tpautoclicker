import threading
import time
import keyboard
import mouse
import tkinter as tk
from tkinter import ttk, messagebox

clicking = False
click_thread = None

def clicker(hold_key, mouse_button, click_speed):
    global clicking
    while clicking:
        if not keyboard.is_pressed(hold_key):
            keyboard.press(hold_key)
        mouse.click(mouse_button)
        time.sleep(click_speed)
    if keyboard.is_pressed(hold_key):
        keyboard.release(hold_key)

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

def on_close():
    stop_clicking()
    root.destroy()

root = tk.Tk()
root.title("Minecraft Auto Clicker")
root.geometry("300x250")
root.resizable(False, False)

style = ttk.Style(root)
style.theme_use("clam")

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

ttk.Button(root, text="Start", command=start_clicking).pack(pady=5)
ttk.Button(root, text="Stop", command=stop_clicking).pack(pady=5)

ttk.Label(root, textvariable=status_var, font=('Segoe UI', 10)).pack(pady=5)

ttk.Label(root, text="Press hotkey to toggle:").pack()
ttk.Entry(root, textvariable=hotkey_var, state="readonly", justify="center").pack()

# Bind hotkey
def setup_hotkey():
    try:
        keyboard.add_hotkey(hotkey_var.get().lower(), toggle_clicker)
    except Exception as e:
        messagebox.showerror("Error", f"Hotkey binding failed: {e}")

setup_hotkey()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
