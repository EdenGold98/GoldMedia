# media_manager.py
import os
import hashlib
import re
import subprocess
import json
from threading import Thread
# === THE FIX: Moviepy is removed for performance ===
# from moviepy.video.io.VideoFileClip import VideoFileClip 
import queue

import config

# --- FFmpeg/FFprobe Paths ---
FFMPEG_PATH, FFPROBE_PATH = None, None

METADATA_QUEUE = queue.Queue()
THUMBNAIL_QUEUE = queue.Queue()

def find_ffmpeg_and_ffprobe():
    """Finds local or system-wide FFmpeg/FFprobe executables."""
    global FFMPEG_PATH, FFPROBE_PATH
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_ffmpeg_path = os.path.join(base_dir, 'ffmpeg', 'ffmpeg.exe')
    local_ffprobe_path = os.path.join(base_dir, 'ffmpeg', 'ffprobe.exe')

    FFMPEG_PATH = local_ffmpeg_path if os.path.exists(local_ffmpeg_path) else 'ffmpeg'
    FFPROBE_PATH = local_ffprobe_path if os.path.exists(local_ffprobe_path) else 'ffprobe'
    
    print(f"Using FFmpeg: {FFMPEG_PATH}")
    print(f"Using FFprobe: {FFPROBE_PATH}")

def _run_ffprobe_and_cache(video_path):
    """The actual blocking ffprobe call. Executed by the metadata_worker."""
    path_hash = hashlib.md5(video_path.encode()).hexdigest()
    with config.cache_lock:
        if path_hash in config.media_info_cache and config.media_info_cache[path_hash].get('duration', 0) > 0:
            return

    try:
        ffprobe_cmd = [FFPROBE_PATH, '-v', 'error', '-show_format', '-print_format', 'json', video_path]
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        format_info = json.loads(result.stdout).get('format', {})
        duration_str = format_info.get('duration', "0")
        
        metadata = {'duration': float(duration_str)}
        with config.cache_lock:
            config.media_info_cache[path_hash] = metadata
        config.save_media_info_cache()
        print(f"BG Metadata cached for: {os.path.basename(video_path)}")
    except Exception as e:
        print(f"Error getting metadata in background for {video_path}: {e}")
        with config.cache_lock:
            config.media_info_cache[path_hash] = {'duration': 0}
        config.save_media_info_cache()

# === THE FIX: Replaced slow moviepy with a direct, super-fast ffmpeg command ===
def _create_thumbnail_file(video_path):
    """The actual blocking thumbnail creation. Executed by the thumbnail_worker."""
    path_hash = hashlib.md5(video_path.encode()).hexdigest()
    thumbnail_path = os.path.join(config.THUMBNAIL_DIR, f"{path_hash}.jpg")
    if os.path.exists(thumbnail_path):
        return

    try:
        timestamp = config.settings.get("thumbnail_timestamp", 4)
        
        # Check cache for duration to avoid generating thumbnail past the end of the video
        with config.cache_lock:
            duration = config.media_info_cache.get(path_hash, {}).get('duration', timestamp + 1)
        
        if timestamp >= duration:
            timestamp = duration / 2

        # Using -ss before -i enables fast seeking, making this almost instantaneous.
        ffmpeg_cmd = [
            FFMPEG_PATH, 
            '-ss', str(timestamp),
            '-i', video_path,
            '-vframes', '1',
            '-q:v', '3', # Quality, 2-5 is a good range
            '-hide_banner', '-loglevel', 'error',
            '-y', # Overwrite if exists
            thumbnail_path
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"BG Thumbnail generated for: {os.path.basename(video_path)}")
    except Exception as e:
        print(f"Could not generate thumbnail in background for {video_path}: {e}")

def metadata_worker():
    """Worker thread that processes videos from the METADATA_QUEUE."""
    print("Metadata background worker started.")
    while True:
        try:
            video_path = METADATA_QUEUE.get()
            if video_path is None: break # Sentinel value to stop
            _run_ffprobe_and_cache(video_path)
            METADATA_QUEUE.task_done()
        except Exception as e:
            print(f"An error occurred in the metadata worker: {e}")

def thumbnail_worker():
    """Worker thread that processes videos from the THUMBNAIL_QUEUE."""
    print("Thumbnail background worker started.")
    while True:
        try:
            video_path = THUMBNAIL_QUEUE.get()
            if video_path is None: break # Sentinel value to stop
            _create_thumbnail_file(video_path)
            THUMBNAIL_QUEUE.task_done()
        except Exception as e:
            print(f"An error occurred in the thumbnail worker: {e}")

def get_video_metadata(video_path):
    """Non-blocking. Checks cache, if not found, queues for background processing."""
    path_hash = hashlib.md5(video_path.encode()).hexdigest()
    
    with config.cache_lock:
        metadata = config.media_info_cache.get(path_hash)
    
    if metadata and metadata.get('duration', 0) > 0:
        return metadata
    else:
        METADATA_QUEUE.put(video_path)
        return {'duration': 0}

def generate_thumbnail(video_path):
    """Non-blocking. Checks if thumbnail exists, if not, queues for background processing."""
    if not config.settings.get("generate_thumbnails"):
        return
    path_hash = hashlib.md5(video_path.encode()).hexdigest()
    thumbnail_path = os.path.join(config.THUMBNAIL_DIR, f"{path_hash}.jpg")
    if not os.path.exists(thumbnail_path):
        THUMBNAIL_QUEUE.put(video_path)

def scan_all_media_folders():
    """
    Proactively scans all configured media folders and subdirectories, queuing
    any uncached files for metadata and thumbnail generation.
    """
    print("Starting proactive library scan...")
    media_folders = config.settings.get("media_folders", [])
    valid_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.webm')
    found_count = 0
    
    for folder in media_folders:
        if os.path.exists(folder):
            for root, _, files in os.walk(folder):
                for name in files:
                    if name.lower().endswith(valid_extensions):
                        full_path = os.path.join(root, name)
                        # These functions will check the cache and queue if needed
                        get_video_metadata(full_path)
                        generate_thumbnail(full_path)
                        found_count += 1
    print(f"Proactive scan complete. Found {found_count} media files.")

# === THE FIX: New function to handle file deletion ===
def remove_file_from_cache(file_path):
    """Removes a file's metadata, playback progress, and thumbnail from all caches."""
    print(f"File deleted or moved. Removing from cache: {os.path.basename(file_path)}")
    path_hash = hashlib.md5(file_path.encode()).hexdigest()
    
    with config.cache_lock:
        # Remove from media info cache
        config.media_info_cache.pop(path_hash, None)
        
        # Remove from playback cache (both Global and Per IP modes)
        if path_hash in config.playback_cache:
            config.playback_cache.pop(path_hash, None) # Global mode
        else:
            # Per IP mode
            ips_to_clean = [ip for ip, data in config.playback_cache.items() if path_hash in data]
            for ip in ips_to_clean:
                config.playback_cache[ip].pop(path_hash, None)
    
    # Save the updated caches
    config.save_media_info_cache()
    config.save_playback_cache()

    # Delete the thumbnail file
    thumbnail_path = os.path.join(config.THUMBNAIL_DIR, f"{path_hash}.jpg")
    if os.path.exists(thumbnail_path):
        try:
            os.remove(thumbnail_path)
            print(f"Deleted thumbnail for: {os.path.basename(file_path)}")
        except OSError as e:
            print(f"Error deleting thumbnail file {thumbnail_path}: {e}")

# (The rest of the file: scan_directory, get_full_structure, etc. remains the same)
def scan_directory(path):
    """Scans a single directory for immediate display, queuing files as needed."""
    items = {'folders': [], 'files': []}
    try:
        for item in os.scandir(path):
            if item.is_dir():
                items['folders'].append({'name': item.name, 'path': item.path})
            elif item.is_file() and item.name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
                generate_thumbnail(item.path)
                metadata = get_video_metadata(item.path)
                
                thumb_hash = hashlib.md5(item.path.encode()).hexdigest()
                items['files'].append({
                    'name': os.path.splitext(item.name)[0], 
                    'path': item.path, 
                    'thumb_hash': thumb_hash,
                    'duration': metadata.get('duration', 0)
                })
    except Exception as e:
        print(f"Error scanning directory {path}: {e}")
        
    items['folders'].sort(key=lambda x: x['name'].lower())
    items['files'].sort(key=lambda x: x['name'].lower())
    return items

def get_full_structure():
    """Builds a nested dictionary of all media folders and their subdirectories."""
    structure = []
    for root_folder in config.settings.get("media_folders", []):
        if os.path.exists(root_folder):
            structure.append({
                'name': os.path.basename(root_folder), 
                'path': root_folder, 
                'children': get_subfolders(root_folder)
            })
    return structure

def get_subfolders(path):
    """Recursively gets subfolders for the directory structure."""
    subfolders = []
    try:
        for item in os.scandir(path):
            if item.is_dir():
                subfolders.append({
                    'name': item.name, 
                    'path': item.path, 
                    'children': get_subfolders(item.path)
                })
        subfolders.sort(key=lambda x: x['name'].lower())
    except Exception:
        pass
    return subfolders

def get_media_tracks(video_path):
    """Uses ffprobe to get audio and subtitle tracks from a video file."""
    from urllib.parse import quote
    tracks = {'audio': [], 'subtitles': []}
    try:
        ffprobe_cmd = [FFPROBE_PATH, '-v', 'quiet', '-print_format', 'json', '-show_streams', video_path]
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        streams = json.loads(result.stdout).get('streams', [])
        
        internal_subtitle_index = 0
        for stream in streams:
            if stream.get('codec_type') == 'audio':
                tracks['audio'].append({
                    'id': stream['index'],
                    'label': stream.get('tags', {}).get('title', f"Track {stream['index']}"),
                    'lang': stream.get('tags', {}).get('language', 'unknown')
                })
            elif stream.get('codec_type') == 'subtitle':
                safe_video_path = quote(video_path)
                tracks['subtitles'].append({
                    'lang': stream.get('tags', {}).get('language', 'eng'),
                    'label': f"(Emb) {stream.get('tags', {}).get('title', 'Track {}'.format(stream['index']))}",
                    'path': f"/subtitle/embedded/{safe_video_path}/{internal_subtitle_index}"
                })
                internal_subtitle_index += 1

        video_basename = os.path.splitext(os.path.basename(video_path))[0]
        video_dir = os.path.dirname(video_path)
        for sub_file in os.listdir(video_dir):
            if sub_file.lower().startswith(video_basename.lower()) and sub_file.lower().endswith(('.srt', '.vtt')):
                lang_match = re.search(r'\.([a-zA-Z]{2,3})\.(srt|vtt)$', sub_file, re.IGNORECASE)
                lang = lang_match.group(1) if lang_match else 'unknown'
                tracks['subtitles'].append({
                    'lang': lang,
                    'label': f"(Ext) {lang}",
                    'path': os.path.join(video_dir, sub_file)
                })
    except Exception as e:
        print(f"Track Scan Error for {video_path}: {e}")
    return tracks

def is_safe_path(path):
    """Security check to ensure file access is within allowed media folders."""
    abs_path = os.path.abspath(path)
    for safe_folder in config.settings.get("media_folders", []):
        if os.path.abspath(safe_folder).startswith(abs_path):
             return True
        if abs_path.startswith(os.path.abspath(safe_folder)):
            return True
    print(f"!!! SECURITY ALERT: Denied access to unsafe path: {abs_path}")
    return False

def get_mime_type_from_extension(filepath):
    """Determines the MIME type based on file extension for DLNA compatibility."""
    ext = os.path.splitext(filepath)[1].lower()
    return {
        '.mp4': 'video/mp4',
        '.mkv': 'video/x-matroska',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.webm': 'video/webm',
    }.get(ext, 'video/mp4')