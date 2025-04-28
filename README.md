TP Auto Clicker
TP Auto Clicker is a customizable auto-clicking application designed for tasks requiring repetitive mouse clicks, such as in games like Minecraft or other applications. It features a user-friendly interface, system tray integration, and configurable settings for click speed, mouse buttons, hotkeys, and AFK (Away From Keyboard) mode.
Features

Auto Clicking: Start/stop clicking with customizable mouse buttons (Left, Right, Middle) and click speeds (0.01s to 5s).
Hold Key: Optionally set a key to hold during clicking.
Toggle Hotkey: Assign a hotkey (default: F6) to toggle clicking on/off.
AFK Mode: Simulates small random mouse movements to prevent idle detection.
System Tray: Minimize to tray with notifications and quick access menu.
Settings Persistence: Save and load settings in a settings.json file.
Customizable UI: Light/dark theme support based on system settings.
Sound Feedback: Optional beeps for start/stop actions.
Update Checker: Check for new versions via GitHub.

Installation

Ensure you have Python 3.8+ installed.
Install required dependencies:pip install PySide6 keyboard mouse requests


Download or clone the source code from this repository.
Run the application:python auto_clicker.py



Usage

Launch the Application: Run the script to open the TP Auto Clicker window.
Controls Tab:
Click Start Clicking to begin auto-clicking.
Click Stop Clicking to stop.
Use Start AFK to enable random mouse movements for AFK mode.
Stop AFK mode with Stop AFK.


Settings Tab:
Hold Key: Click "Set Hold Key" and press a key to set (e.g., Ctrl, Shift, or any letter).
Mouse Button: Select Left, Right, or Middle from the dropdown.
Click Speed: Adjust using the spin box, +/- buttons, or presets (Slow: 0.2s, Med: 0.1s, Fast: 0.05s).
Toggle Hotkey: Click "Set Hotkey" and press a key combination (e.g., F6 or Ctrl+Alt+A).
Features: Enable/disable tray minimization, notifications, and sounds.
Actions: Check for updates, save settings, or reset to defaults.


System Tray: Right-click the tray icon to show the window or exit the app.
Hotkey: Press the configured hotkey (default: F6) to toggle clicking without the UI.

Configuration
Settings are saved in settings.json in the same directory as the script. Default settings:

Hold Key: None
Mouse Button: Left
Click Speed: 0.05s
Toggle Hotkey: F6
Minimize to Tray: Enabled
Notifications: Enabled
Sounds: Enabled

Notes

Compatibility: Tested on Windows. The keyboard and mouse libraries may require root/admin privileges on some systems.
Usage in Games: Use responsibly. Some games, including Minecraft, may have rules against automation tools. Check the game's terms of service.
Updates: The app checks for updates by querying a version file hosted on GitHub.
Dependencies: Requires PySide6 for the UI, keyboard and mouse for input simulation, and requests for update checks.

Troubleshooting

Hotkey Errors: If a hotkey fails to bind, try a different key or ensure no conflicts with other applications.
No Clicks: Ensure the mouse button is correctly set and the hold key (if set) is valid.
App Not Starting: Verify all dependencies are installed and Python is correctly set up.
Tray Issues: Disable "Minimize to tray" in settings if the tray icon causes problems.

License
This project is licensed under the MIT License. See the LICENSE file for details.
Disclaimer
TP Auto Clicker is provided as-is. The developer is not responsible for any consequences from its use, including bans in games or system issues. Use at your own risk.
