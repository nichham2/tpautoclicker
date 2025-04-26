import threading
import time
import keyboard  # pip install keyboard
import mouse     # pip install mouse

clicking = False
hold_key = 'shift'     # Change this to any key you want to hold
mouse_button = 'left'  # 'left', 'right', or 'middle'
click_speed = 0.05     # Time between clicks (lower = faster)

def clicker():
    global clicking
    while True:
        if clicking:
            if not keyboard.is_pressed(hold_key):
                keyboard.press(hold_key)
            mouse.click(mouse_button)
            time.sleep(click_speed)
        else:
            if keyboard.is_pressed(hold_key):
                keyboard.release(hold_key)
            time.sleep(0.1)

def toggle_clicker(e):
    global clicking
    clicking = not clicking
    print(f"Clicking: {clicking}")

# Bind F6 to toggle clicker
keyboard.on_press_key("f6", toggle_clicker)

# Start the clicking thread
threading.Thread(target=clicker, daemon=True).start()

print("Auto Clicker running. Press F6 to toggle clicking. Press ESC to exit.")
keyboard.wait('esc')
keyboard.unhook_all()  # Unhook all keyboard events when exiting