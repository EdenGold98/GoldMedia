# main.py
import os
import tkinter as tk
import webbrowser
from threading import Thread
import time

import pystray
from PIL import Image

# Import our refactored modules
import config
import web_server
import network_services
import system_utils
import media_manager
from settings_gui import SettingsWindow
# === THE FIX: Import the new file watcher module ===
import file_watcher

# Global Tkinter root for the settings window
root_tk = None
icon = None

def initial_setup():
    """Performs all necessary startup tasks."""
    print("--- GoldMedia Python Server Starting ---")
    
    os.makedirs(config.THUMBNAIL_DIR, exist_ok=True)

    config.settings.update(config.load_settings())
    config.load_playback_cache()
    config.load_media_info_cache()
    
    media_manager.find_ffmpeg_and_ffprobe()
    system_utils.setup_custom_icon()

def start_background_services():
    """Starts all background threads for networking and the web server."""
    # Start the background caching workers
    metadata_thread = Thread(target=media_manager.metadata_worker, daemon=True)
    metadata_thread.start()
    
    thumbnail_thread = Thread(target=media_manager.thumbnail_worker, daemon=True)
    thumbnail_thread.start()

    # === THE FIX: Perform an initial full scan, then start the real-time watcher ===
    # The periodic scanner is no longer needed.
    print("Performing initial library scan...")
    initial_scan_thread = Thread(target=media_manager.scan_all_media_folders, daemon=True)
    initial_scan_thread.start()
    file_watcher.start_watching()

    # Start the Flask web server
    server_thread = Thread(target=web_server.run_server, daemon=True)
    server_thread.start()
    print(f"Web server started on port {config.settings.get('server_port')}")

    # Start the SSDP discovery server
    ssdp_thread = Thread(target=network_services.run_ssdp_server, daemon=True)
    ssdp_thread.start()

    if config.settings.get("enable_upnp"):
        Thread(target=network_services.setup_upnp, daemon=True).start()

    time.sleep(2)
    network_services.trigger_ssdp_refresh()

def on_settings_saved():
    """Callback function for when settings are saved in the GUI."""
    print("Settings changed. Reloading and notifying network...")
    config.settings.clear()
    config.settings.update(config.load_settings())
    system_utils.setup_custom_icon()
    network_services.trigger_ssdp_refresh()
    
    # === THE FIX: Restart the watcher and trigger a new scan for new folders ===
    file_watcher.restart_watching()
    Thread(target=media_manager.scan_all_media_folders, daemon=True).start()

# --- System Tray Menu Functions ---
def open_web_ui(icon, item):
    webbrowser.open(f"http://127.0.0.1:{config.settings.get('server_port')}")

def open_settings_window(icon, item):
    global root_tk
    if root_tk is None: return
    if any(isinstance(x, tk.Toplevel) for x in root_tk.winfo_children() if x.winfo_exists()): return
    SettingsWindow(root_tk, on_save_callback=on_settings_saved)

def quit_app(icon, item):
    """Handles application shutdown."""
    print("Shutdown initiated...")
    file_watcher.stop_watching()
    icon.stop()
    for ip in network_services.get_all_local_ips():
        if ip != '127.0.0.1':
            Thread(target=network_services.send_ssdp_notifications, args=(ip, "byebye"), daemon=True).start()
    time.sleep(0.5)
    print("Shutdown notifications sent. Exiting.")
    if root_tk:
        root_tk.destroy()

def setup_system_tray():
    """Creates and runs the system tray icon and menu."""
    global root_tk, icon
    root_tk = tk.Tk()
    root_tk.withdraw()

    try:
        image = Image.open("assets/tray_icon.png")
    except FileNotFoundError:
        print("Warning: tray_icon.png not found. Using a blank icon.")
        image = Image.new('RGB', (64, 64), 'black')
    
    menu = (
        pystray.MenuItem('Open Web UI', open_web_ui, default=True),
        pystray.MenuItem('Settings', open_settings_window),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Quit', quit_app)
    )
    
    icon = pystray.Icon("GoldMediaPythonServer", image, "GoldMedia Python Server", menu)
    
    icon_thread = Thread(target=icon.run, daemon=True)
    icon_thread.start()

    root_tk.mainloop()

if __name__ == '__main__':
    initial_setup()
    start_background_services()
    setup_system_tray()