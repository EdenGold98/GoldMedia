# config.py
import os
import json
import hashlib
import socket
from threading import Lock

# --- Constants ---
DEFAULT_SETTINGS = {
    "server_name": "GoldMedia Python Server", "server_port": 9005, "media_folders": ["C:\\Users\\Public\\Videos"],
    "start_on_startup": False, "generate_thumbnails": True, "thumbnail_timestamp": 4, "enable_upnp": True,
    "server_icon_path": "assets/tray_icon.png", "cache_mode": "Global",
    "enable_transcoding": False, "transcode_formats": ".mkv,.avi,.webm,.mov"
}
SETTINGS_FILE = "settings.json"
PLAYBACK_CACHE_FILE = "playback_cache.json"
MEDIA_INFO_CACHE_FILE = "media_info_cache.json"
THUMBNAIL_DIR = os.path.join('static', '.thumbnails')
CUSTOM_ICON_FILENAME = "custom_icon.png"
SERVER_UUID = hashlib.md5(socket.gethostname().encode()).hexdigest()

# --- Global State and Locks ---
settings = {}
playback_cache = {}
media_info_cache = {}
cache_lock = Lock()

# === THE FIX: State for UPnP Eventing ===
# A single lock to manage all UPNP state (update ID and subscriptions)
upnp_state_lock = Lock()
# The master counter for content changes. Starts at 1.
system_update_id = 1
# Dictionary to store active client subscriptions.
# Format: { 'sid': {'callback': 'url', 'expiry': timestamp} }
subscriptions = {}


# --- Functions ---
# (The rest of the file remains unchanged)
def load_settings():
    """Loads settings from JSON file, using defaults for missing keys."""
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4)
        return DEFAULT_SETTINGS.copy()
    else:
        with open(SETTINGS_FILE, 'r') as f:
            try:
                s = json.load(f)
                for key, value in DEFAULT_SETTINGS.items():
                    s.setdefault(key, value)
                return s
            except json.JSONDecodeError:
                print("ERROR: Could not read settings.json. Using default settings.")
                return DEFAULT_SETTINGS.copy()

def load_playback_cache():
    """Loads the playback position cache from its file."""
    global playback_cache
    with cache_lock:
        if os.path.exists(PLAYBACK_CACHE_FILE):
            try:
                with open(PLAYBACK_CACHE_FILE, 'r') as f:
                    playback_cache = json.load(f)
                    print("Playback cache loaded.")
            except json.JSONDecodeError:
                print("Warning: Could not decode playback cache. Starting fresh.")
                playback_cache = {}
        else:
            playback_cache = {}

def save_playback_cache():
    """Saves the current playback cache to its file."""
    with cache_lock:
        try:
            with open(PLAYBACK_CACHE_FILE, 'w') as f:
                json.dump(playback_cache, f, indent=2)
        except Exception as e:
            print(f"Error saving playback cache: {e}")
            
def load_media_info_cache():
    """Loads the media metadata cache (e.g., duration) from its file."""
    global media_info_cache
    with cache_lock:
        if os.path.exists(MEDIA_INFO_CACHE_FILE):
            try:
                with open(MEDIA_INFO_CACHE_FILE, 'r') as f:
                    media_info_cache = json.load(f)
                    print("Media info cache loaded.")
            except json.JSONDecodeError:
                print("Warning: Could not decode media info cache. Starting fresh.")
                media_info_cache = {}
        else:
            media_info_cache = {}

def save_media_info_cache():
    """Saves the current media info cache to its file."""
    with cache_lock:
        try:
            with open(MEDIA_INFO_CACHE_FILE, 'w') as f:
                json.dump(media_info_cache, f, indent=2)
        except Exception as e:
            print(f"Error saving media info cache: {e}")