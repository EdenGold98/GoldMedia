# upnp_handler.py
import os
import xml.etree.ElementTree as ET
import html
import base64
import hashlib
import time
from urllib.parse import quote
from threading import Thread
from flask import make_response
import requests

import config
import media_manager
import network_services

# Constants
WMP_SERVER_STRING = 'Microsoft-Windows/10.0 UPnP/1.0 WMP/12.0'

def _send_upnp_notification(sid):
    """Sends a single NOTIFY message to a subscriber in a background thread."""
    with config.upnp_state_lock:
        sub = config.subscriptions.get(sid)
        if not sub:
            return
        
        callback_url = sub['callback']
        seq = sub['seq']
        current_update_id = config.system_update_id
    
    # === THE FIX: A more verbose and spec-compliant XML payload ===
    # This structure is better understood by a wider range of DLNA clients.
    last_change_xml = (
        '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/">'
        '<InstanceID val="0">'
        f'<SystemUpdateID val="{current_update_id}"/>'
        '<ContainerUpdateIDs val=""/>'
        '<TransferIDs val=""/>'
        '</InstanceID>'
        '</Event>'
    )

    body = (
        '<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">'
        f'<e:property><LastChange>{html.escape(last_change_xml)}</LastChange></e:property>'
        '</e:propertyset>'
    ).encode('utf-8')

    headers = {
        'HOST': f'{network_services.get_all_local_ips()[0]}:{config.settings.get("server_port")}',
        'CONTENT-TYPE': 'text/xml; charset="utf-8"',
        'NT': 'upnp:event',
        'NTS': 'upnp:propchange',
        'SID': sid,
        'SEQ': str(seq)
    }
    
    try:
        requests.request('NOTIFY', callback_url, headers=headers, data=body, timeout=2)
        print(f"UPnP Event: Sent NOTIFY to {callback_url} (SID: {sid}, SEQ: {seq}, ID: {current_update_id})")
        # === THE FIX: Increment sequence number for the next notification ===
        with config.upnp_state_lock:
            if sid in config.subscriptions:
                config.subscriptions[sid]['seq'] += 1
    except requests.exceptions.RequestException as e:
        print(f"!!! UPnP Event Error: Failed to send NOTIFY to {callback_url}: {e}")
        with config.upnp_state_lock:
            config.subscriptions.pop(sid, None)

def trigger_upnp_refresh():
    """Increments the update ID and notifies all subscribers."""
    with config.upnp_state_lock:
        config.system_update_id += 1
        print(f"UPnP Event: Content changed. SystemUpdateID is now {config.system_update_id}")
        subs_to_notify = dict(config.subscriptions)

    for sid in subs_to_notify:
        Thread(target=_send_upnp_notification, args=(sid,), daemon=True).start()

def handle_upnp_control(request, service_name):
    namespaces = {'s': 'http://schemas.xmlsoap.org/soap/envelope/', 'u': f'urn:schemas-upnp-org:service:{service_name}:1'}
    if "X_MS" in service_name: namespaces['u'] = f'urn:microsoft.com:service:{service_name}:1'
    try:
        root = ET.fromstring(request.get_data())
        action_node = root.find(f'.//u:*', namespaces)
        action_name = action_node.tag.split('}')[-1] if action_node is not None else ''
        print(f"SOAP: Received action '{action_name}' for service '{service_name}'")
        client_ip = request.remote_addr
        response_body = ""
        if action_name == 'Browse':
            response_body = _handle_browse(action_node, client_ip)
        elif action_name == 'X_SetBookmark':
            _handle_set_bookmark(action_node, client_ip)
            response_body = f'<u:{action_name}Response xmlns:u="{namespaces["u"]}"></u:{action_name}Response>'
        elif action_name == 'GetSystemUpdateID':
            with config.upnp_state_lock: current_id = config.system_update_id
            response_body = f'<u:GetSystemUpdateIDResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1"><Id>{current_id}</Id></u:GetSystemUpdateIDResponse>'
        elif action_name == 'GetProtocolInfo':
            info = "http-get:*:video/mp4:*,http-get:*:video/x-matroska:*,http-get:*:video/mpeg:*"
            response_body = f'<u:GetProtocolInfoResponse xmlns:u="urn:schemas-upnp-org:service:ConnectionManager:1"><Source></Source><Sink>{info}</Sink></u:GetProtocolInfoResponse>'
        else:
            if action_name: print(f"!!! WARNING: Received unrecognized SOAP action: '{action_name}'")
            response_body = f'<u:{action_name}Response xmlns:u="{namespaces["u"]}"></u:{action_name}Response>' if action_name else ''
        response_xml = f'<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>{response_body}</s:Body></s:Envelope>'
        response = make_response(response_xml.encode('utf-8'))
        response.headers['Content-Type'] = 'text/xml; charset="utf-8"'; response.headers['Server'] = WMP_SERVER_STRING
        return response
    except Exception as e:
        print(f"!!! SOAP Error processing action '{action_name}': {e}"); return "Internal Server Error", 500

def _handle_browse(action_node, client_ip):
    object_id = action_node.find('ObjectID').text
    browse_flag = action_node.find('BrowseFlag').text
    didl_items, item_count = "", 0
    if browse_flag == 'BrowseDirectChildren': didl_items, item_count = _browse_direct_children(object_id, client_ip)
    elif browse_flag == 'BrowseMetadata': didl_items, item_count = _browse_metadata(object_id, client_ip)
    didl_lite_string = f'<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/" xmlns:sec="http://www.sec.co.kr/dlna/">{didl_items}</DIDL-Lite>'
    result_xml = html.escape(didl_lite_string)
    # === THE FIX: Use the live system_update_id instead of a hardcoded '1' ===
    with config.upnp_state_lock:
        current_update_id = config.system_update_id
    return f'<u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1"><Result>{result_xml}</Result><NumberReturned>{item_count}</NumberReturned><TotalMatches>{item_count}</TotalMatches><UpdateID>{current_update_id}</UpdateID></u:BrowseResponse>'

# --- UNCHANGED HELPER FUNCTIONS ---
def _format_dlna_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0: return "00:00:00.000"
    hours, rem = divmod(seconds, 3600); minutes, secs_float = divmod(rem, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs_float:06.3f}"
def _format_upnp_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds <= 0: return "0:00:00"
    seconds = int(seconds); hours, rem = divmod(seconds, 3600); minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"
def _handle_set_bookmark(action_node, client_ip):
    cache_mode = config.settings.get("cache_mode", "Global")
    if cache_mode == "Off": return
    try:
        object_id_node = action_node.find('ObjectID'); position_node = action_node.find('PosSecond') 
        if object_id_node is None or position_node is None: return
        object_id, position_str = object_id_node.text, position_node.text
        position_sec = float(position_str) / 1000.0
        video_path = base64.b64decode(object_id).decode(); video_hash = hashlib.md5(video_path.encode()).hexdigest()
        with config.cache_lock:
            if cache_mode == "Global": config.playback_cache[video_hash] = {"last_position": position_sec, "timestamp": time.time()}
            elif cache_mode == "Per IP": config.playback_cache.setdefault(client_ip, {})[video_hash] = {"last_position": position_sec, "timestamp": time.time()}
        config.save_playback_cache()
    except Exception as e: print(f"!!! Error processing X_SetBookmark: {e}")
def _browse_direct_children(object_id, client_ip):
    items, count = "", 0
    if object_id == '0':
        for folder_path in config.settings.get("media_folders", []):
            if os.path.exists(folder_path):
                folder_name = os.path.basename(folder_path.strip('\\/'))
                item_id = base64.b64encode(folder_path.encode()).decode()
                items += f'<container id="{item_id}" parentID="0" restricted="1"><dc:title>{html.escape(folder_name)}</dc:title><upnp:class>object.container.storageFolder</upnp:class></container>'
                count += 1
    else:
        try:
            current_path = base64.b64decode(object_id).decode()
            if not media_manager.is_safe_path(current_path): return "", 0
            contents = media_manager.scan_directory(current_path)
            for folder in contents['folders']:
                item_id = base64.b64encode(folder['path'].encode()).decode()
                items += f'<container id="{item_id}" parentID="{object_id}" restricted="1"><dc:title>{html.escape(folder["name"])}</dc:title><upnp:class>object.container.storageFolder</upnp:class></container>'
                count += 1
            for video in contents['files']: items += _create_video_item_xml(video, object_id, client_ip); count += 1
        except Exception as e: print(f"Error browsing children of '{object_id}': {e}"); return "", 0
    return items, count
def _browse_metadata(object_id, client_ip):
    if object_id == '0': return '<container id="0" parentID="-1" restricted="1"><dc:title>Root</dc:title><upnp:class>object.container.storageFolder</upnp:class></container>', 1
    try:
        current_path = base64.b64decode(object_id).decode()
        if not media_manager.is_safe_path(current_path): return "", 0
        if os.path.isfile(current_path):
            parent_path = os.path.dirname(current_path); parent_id_b64 = base64.b64encode(parent_path.encode()).decode()
            metadata = media_manager.get_video_metadata(current_path); thumb_hash = hashlib.md5(current_path.encode()).hexdigest()
            video_info = {'path': current_path, 'name': os.path.splitext(os.path.basename(current_path))[0], 'thumb_hash': thumb_hash, 'duration': metadata.get('duration', 0)}
            item = _create_video_item_xml(video_info, parent_id_b64, client_ip)
            return item, 1
        else:
            folder_name = os.path.basename(current_path.strip('/\\')); parent_path = os.path.dirname(current_path); parent_id_b64 = '0'
            is_parent_a_root_folder = any(os.path.samefile(parent_path, p) for p in config.settings.get("media_folders", []))
            if not is_parent_a_root_folder: parent_id_b64 = base64.b64encode(parent_path.encode()).decode()
            item = f'<container id="{object_id}" parentID="{parent_id_b64}" restricted="1"><dc:title>{html.escape(folder_name)}</dc:title><upnp:class>object.container.storageFolder</upnp:class></container>'
            return item, 1
    except Exception as e: print(f"Error getting metadata for '{object_id}': {e}"); return "", 0
def _create_video_item_xml(video, parent_object_id, client_ip):
    primary_ip = network_services.get_all_local_ips()[0]; server_port = config.settings.get("server_port"); cache_mode = config.settings.get("cache_mode", "Global")
    item_id = base64.b64encode(video['path'].encode()).decode(); stream_url = f"http://{primary_ip}:{server_port}/stream/{quote(video['path'])}"
    file_extension = os.path.splitext(video['path'])[1].lower(); transcode_formats_str = config.settings.get("transcode_formats", ""); transcode_formats = [f.strip() for f in transcode_formats_str.split(',') if f.strip()]
    needs_transcoding = (config.settings.get("enable_transcoding", False) and file_extension in transcode_formats)
    if needs_transcoding:
        mime_type = "video/mpeg"; protocol_info = f"http-get:*:{mime_type}:DLNA.ORG_OP=01;DLNA.ORG_CI=1"
        stream_url += "?transcode=true"; size_attr = "" 
    else:
        mime_type = media_manager.get_mime_type_from_extension(video['path']); seeking_flags = "DLNA.ORG_FLAGS=01700000000000000000000000000000"
        protocol_info = f"http-get:*:{mime_type}:DLNA.ORG_OP=01;DLNA.ORG_CI=0;{seeking_flags}"; size_attr = f' size="{os.path.getsize(video["path"])}"'
    duration_str = _format_upnp_duration(video.get('duration', 0)); thumbnail_tag = ""
    if config.settings.get("generate_thumbnails") and video.get('thumb_hash'):
        thumb_url = f"http://{primary_ip}:{server_port}/static/.thumbnails/{video['thumb_hash']}.jpg"; thumbnail_tag = f'<upnp:albumArtURI>{thumb_url}</upnp:albumArtURI>'
    resume_res_attrs, dcm_info_tag = "", ""
    if cache_mode != "Off":
        video_hash = hashlib.md5(video['path'].encode()).hexdigest(); position = 0
        with config.cache_lock:
            if cache_mode == "Global": position = config.playback_cache.get(video_hash, {}).get("last_position", 0)
            elif cache_mode == "Per IP": position = config.playback_cache.get(client_ip, {}).get(video_hash, {}).get("last_position", 0)
        if position > 1: resume_res_attrs = f' resumePosition="{_format_dlna_duration(position)}"' ; dcm_info_tag = f'<sec:dcmInfo>BM={int(position * 1000)}</sec:dcmInfo>'
    return (f'<item id="{item_id}" parentID="{parent_object_id}" restricted="1"><dc:title>{html.escape(video["name"])}</dc:title><upnp:class>object.item.videoItem</upnp:class>{thumbnail_tag}{dcm_info_tag}<res protocolInfo="{protocol_info}"{size_attr} duration="{duration_str}"{resume_res_attrs}>{stream_url}</res></item>')