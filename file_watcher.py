# file_watcher.py
import os
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import config
import media_manager
import upnp_handler # <-- New import

observer = None

class MediaFolderEventHandler(FileSystemEventHandler):
    """Handles file system events for media folders."""
    
    def __init__(self):
        super().__init__()
        self.valid_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.webm')

    def _is_valid_video(self, path):
        if os.path.isdir(path) or not path.lower().endswith(self.valid_extensions):
            return False
        if os.path.basename(path).startswith('.'):
            return False
        return True

    def on_created(self, event):
        if self._is_valid_video(event.src_path):
            print(f"Watcher: New file detected: {os.path.basename(event.src_path)}")
            media_manager.get_video_metadata(event.src_path)
            media_manager.generate_thumbnail(event.src_path)
            # === THE FIX: Trigger the UPnP refresh ===
            upnp_handler.trigger_upnp_refresh()

    def on_deleted(self, event):
        if self._is_valid_video(event.src_path):
            media_manager.remove_file_from_cache(event.src_path)
            # === THE FIX: Trigger the UPnP refresh ===
            upnp_handler.trigger_upnp_refresh()

    def on_moved(self, event):
        if self._is_valid_video(event.src_path):
            media_manager.remove_file_from_cache(event.src_path)
        
        if self._is_valid_video(event.dest_path):
            print(f"Watcher: File moved/renamed to: {os.path.basename(event.dest_path)}")
            media_manager.get_video_metadata(event.dest_path)
            media_manager.generate_thumbnail(event.dest_path)
        
        # === THE FIX: Trigger the UPnP refresh (only once for a move) ===
        upnp_handler.trigger_upnp_refresh()

# (The rest of the file remains unchanged)
def start_watching():
    global observer
    if observer and observer.is_alive(): return
    event_handler = MediaFolderEventHandler()
    observer = Observer()
    media_folders = config.settings.get("media_folders", [])
    for path in media_folders:
        if os.path.exists(path):
            observer.schedule(event_handler, path, recursive=True)
            print(f"Watcher: Monitoring folder '{path}' for changes.")
        else: print(f"Watcher Warning: Folder not found, cannot monitor: '{path}'")
    if media_folders: observer.start()

def stop_watching():
    global observer
    if observer and observer.is_alive():
        observer.stop()
        observer.join()
        print("Watcher: Monitoring stopped.")
    observer = None

def restart_watching():
    print("Watcher: Restarting to apply new folder settings...")
    stop_watching()
    Thread(target=start_watching, daemon=True).start()