# web_server.py
import os
import re
import time
import hashlib
import mimetypes
import subprocess
import webvtt
from flask import (Flask, Response, jsonify, make_response, render_template,
                   send_from_directory, request, g)
from waitress import serve

import config
import media_manager
import upnp_handler
import network_services

app = Flask(__name__)

@app.before_request
def before_request():
    g.settings = config.settings

@app.route('/')
def index():
    return render_template('index.html', server_name=g.settings.get("server_name"))

@app.route('/device.xml')
def device_xml():
    primary_ip = network_services.get_all_local_ips()[0]
    custom_icon_path = os.path.join('static', 'images', config.CUSTOM_ICON_FILENAME)
    xml_content = render_template('device.xml', server_name=g.settings.get("server_name"), server_uuid=config.SERVER_UUID, server_ip=primary_ip, server_port=g.settings.get("server_port"), custom_icon_exists=os.path.exists(custom_icon_path))
    return Response(xml_content, mimetype='application/xml')

@app.route('/stream/<path:filepath>', methods=['GET', 'HEAD'])
def stream_file(filepath):
    if not media_manager.is_safe_path(filepath): return "Access Denied", 403
    if not os.path.exists(filepath): return "Not Found", 404
    if request.args.get('transcode') == 'true':
        ffmpeg_cmd = [media_manager.FFMPEG_PATH, '-i', filepath, '-c:v', 'mpeg2video', '-q:v', '4', '-c:a', 'ac3', '-b:a', '192k', '-f', 'mpegts', '-']
        try:
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return Response(iter(lambda: process.stdout.read(8192), b''), mimetype='video/mpeg')
        except Exception as e: return f"Error starting transcoder: {e}", 500
    else:
        range_header = request.headers.get('Range', None); file_size = os.path.getsize(filepath); mime_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
        seeking_flags = "01700000000000000000000000000000"; dlna_features = f"DLNA.ORG_PN=MPEG_PS_NTSC;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS={seeking_flags}"
        headers = {"Content-Type": mime_type, "Accept-Ranges": "bytes", "Server": upnp_handler.WMP_SERVER_STRING, "contentFeatures.dlna.org": dlna_features, "transferMode.dlna.org": "Streaming"}
        if request.method == 'HEAD':
            resp = make_response(""); resp.headers.extend(headers); resp.headers['Content-Length'] = str(file_size)
            return resp
        if not range_header:
            resp = Response(iter(lambda: open(filepath, "rb").read(65536), b''), mimetype=mime_type); resp.headers.extend(headers); resp.headers['Content-Length'] = str(file_size)
            return resp
        else:
            byte1, byte2 = 0, None; match = re.search(r'(\d+)-(\d*)', range_header)
            if match: groups = match.groups(); byte1 = int(groups[0]); byte2 = int(groups[1]) if groups[1] else file_size - 1
            if byte2 >= file_size: byte2 = file_size - 1
            length = (byte2 - byte1) + 1
            def generate_range():
                with open(filepath, 'rb') as f:
                    f.seek(byte1); bytes_to_read = length
                    while bytes_to_read > 0:
                        chunk = f.read(min(bytes_to_read, 65536))
                        if not chunk: break
                        yield chunk; bytes_to_read -= len(chunk)
            resp = Response(generate_range(), 206, mimetype=mime_type, direct_passthrough=True)
            resp.headers.extend(headers); resp.headers['Content-Range'] = f'bytes {byte1}-{byte2}/{file_size}'; resp.headers['Content-Length'] = str(length)
            return resp

@app.route('/subtitle/<path:sub_path>')
def serve_subtitle(sub_path):
    if not media_manager.is_safe_path(sub_path): return "Access Denied", 403
    try:
        return Response(webvtt.from_srt(sub_path).content if sub_path.lower().endswith('.srt') else send_from_directory(os.path.dirname(sub_path), os.path.basename(sub_path), mimetype='text/vtt'), mimetype='text/vtt')
    except Exception as e: return f"Error processing subtitle: {e}", 500

@app.route('/subtitle/embedded/<path:video_path>/<int:stream_index>')
def stream_embedded_subtitle(video_path, stream_index):
    if not media_manager.is_safe_path(video_path): return "Access Denied", 403
    cmd = [media_manager.FFMPEG_PATH, '-i', video_path, '-map', f'0:s:{stream_index}', '-f', 'webvtt', '-']
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return Response(iter(process.stdout.readline, b''), mimetype='text/vtt')
    except Exception as e: return f"Error extracting subtitle: {e}", 500

@app.route('/images/<path:filename>')
def serve_images(filename): return send_from_directory(os.path.join(app.root_path, 'static', 'images'), filename)

# --- API Routes ---
@app.route('/api/report_progress', methods=['POST'])
def api_report_progress():
    cache_mode = g.settings.get("cache_mode", "Global")
    if cache_mode == "Off": return jsonify({"status": "cache_disabled"})
    data = request.json; video_path, position = data.get('path'), data.get('position')
    if not video_path or position is None: return jsonify({"status": "error", "message": "Missing path or position"}), 400
    video_hash = hashlib.md5(video_path.encode()).hexdigest()
    with config.cache_lock:
        if cache_mode == "Global": config.playback_cache[video_hash] = {"last_position": position, "timestamp": time.time()}
        elif cache_mode == "Per IP": config.playback_cache.setdefault(request.remote_addr, {})[video_hash] = {"last_position": position, "timestamp": time.time()}
    config.save_playback_cache(); return jsonify({"status": "ok"})
@app.route('/api/get_progress', methods=['POST'])
def api_get_progress():
    cache_mode = g.settings.get("cache_mode", "Global")
    if cache_mode == "Off": return jsonify({"position": 0})
    video_path = request.json.get('path')
    if not video_path: return jsonify({"status": "error", "message": "Missing path"}), 400
    video_hash = hashlib.md5(video_path.encode()).hexdigest(); position = 0
    with config.cache_lock:
        if cache_mode == "Global": position = config.playback_cache.get(video_hash, {}).get("last_position", 0)
        elif cache_mode == "Per IP": position = config.playback_cache.get(request.remote_addr, {}).get(video_hash, {}).get("last_position", 0)
    return jsonify({"position": position})
@app.route('/api/get_tracks/<path:video_path>')
def api_get_tracks(video_path):
    if not media_manager.is_safe_path(video_path): return jsonify({"error": "Access Denied"}), 403
    return jsonify(media_manager.get_media_tracks(video_path))
@app.route('/api/get_structure')
def api_get_structure(): return jsonify(media_manager.get_full_structure())
@app.route('/api/browse/')
def api_browse_root(): return jsonify({'folders': [{'name': os.path.basename(p), 'path': p} for p in g.settings.get("media_folders", [])], 'files': []})
@app.route('/api/browse/<path:subpath>')
def api_browse_subpath(subpath):
    if not media_manager.is_safe_path(subpath): return jsonify({"error": "Access Denied"}), 403
    return jsonify(media_manager.scan_directory(subpath))

# --- UPNP/DLNA Routes ---
@app.route('/scpd/<service_name>.xml')
def serve_scpd(service_name):
    allowed = {'ContentDirectory', 'ConnectionManager', 'X_MS_MediaReceiverRegistrar'}
    if service_name not in allowed: return "Not Found", 404
    return send_from_directory(os.path.join(app.root_path, 'templates', 'servicedescriptions'), f"{service_name}.xml", mimetype='application/xml')

@app.route('/upnp/control/<service_name>', methods=['POST'])
def upnp_control(service_name): return upnp_handler.handle_upnp_control(request, service_name)

@app.route('/upnp/event/<service_name>', methods=['SUBSCRIBE', 'UNSUBSCRIBE'])
def upnp_event(service_name):
    if service_name != "ContentDirectory": return "", 200
    if request.method == 'SUBSCRIBE':
        callback = request.headers.get('CALLBACK', '').strip('<>')
        timeout_header = request.headers.get('TIMEOUT', 'Second-1800')
        if not callback: return "Missing CALLBACK header", 412
        try: timeout_sec = int(timeout_header.split('-')[1])
        except (IndexError, ValueError): timeout_sec = 1800
        sid = f'uuid:{hashlib.md5(str(time.time()).encode() + callback.encode()).hexdigest()}'
        expiry = time.time() + timeout_sec
        with config.upnp_state_lock:
            # === THE FIX: Store the sequence number, starting at 0 ===
            config.subscriptions[sid] = {'callback': callback, 'expiry': expiry, 'seq': 0}
        print(f"UPnP Event: New subscription from {callback} (SID: {sid})")
        resp = make_response("")
        resp.headers['SID'] = sid; resp.headers['TIMEOUT'] = f'Second-{timeout_sec}'
        # === THE FIX: Send the initial notification with SEQ: 0 ===
        upnp_handler._send_upnp_notification(sid) 
        return resp
    elif request.method == 'UNSUBSCRIBE':
        sid = request.headers.get('SID')
        if not sid: return "Missing SID header", 412
        with config.upnp_state_lock:
            if sid in config.subscriptions:
                del config.subscriptions[sid]
                print(f"UPnP Event: Unsubscribed SID: {sid}")
        return "", 200

# --- Server Runner ---
def run_server():
    port = config.settings.get("server_port")
    serve(app, host='0.0.0.0', port=port, threads=8)