# network_services.py
import socket
import psutil
import miniupnpc
import time
import random
from threading import Thread
from email.utils import formatdate

import config

def get_all_local_ips():
    """Gets all local IPs, prioritizing common private network ranges."""
    ips = []
    try:
        # Prioritize 192.168.x.x
        for _, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family == socket.AF_INET and snic.address.startswith("192.168."):
                    ips.append(snic.address)
        # Fallback to any non-local IP
        if not ips:
            for _, snics in psutil.net_if_addrs().items():
                for snic in snics:
                    if snic.family == socket.AF_INET and not snic.address.startswith("127."):
                        ips.append(snic.address)
        # Final fallback
        if not ips:
            print("WARNING: No suitable local IP found. Falling back to 127.0.0.1.")
            return ['127.0.0.1']
        return list(set(ips)) # Return unique IPs
    except Exception as e:
        print(f"ERROR: Could not get local IPs. Error: {e}")
        return ['127.0.0.1']

def setup_upnp():
    """Attempts to forward the server port using UPnP."""
    port = config.settings.get("server_port")
    print("Attempting UPnP port mapping...")
    try:
        upnp = miniupnpc.UPnP()
        upnp.discoverdelay = 200
        upnp.discover()
        upnp.selectigd()
        upnp.addportmapping(port, 'TCP', upnp.lanaddr, port, 'GoldMedia Server', '')
        print(f"UPnP: Successfully mapped external port {port} to local IP {upnp.lanaddr}")
    except Exception as e:
        print(f"UPnP Warning: Could not map port. Error: {e}")

def ssdp_listener(listen_ip, server_port, multicast_ip, multicast_port):
    """Listens for and responds to SSDP M-SEARCH requests."""
    responses = {
        'device': (
            'HTTP/1.1 200 OK\r\n'
            'ST: urn:schemas-upnp-org:device:MediaServer:1\r\n'
            'USN: uuid:{uuid}::urn:schemas-upnp-org:device:MediaServer:1\r\n'
            'Location: http://{listen_ip}:{server_port}/device.xml\r\n'
            'Cache-Control: max-age=900\r\n' 'Server: Microsoft-Windows/10.0 UPnP/1.0 WMP/12.0\r\n' 'Ext: \r\n' 'Date: {date}\r\n\r\n'
        ),
        'service': (
            'HTTP/1.1 200 OK\r\n'
            'ST: urn:schemas-upnp-org:service:ContentDirectory:1\r\n'
            'USN: uuid:{uuid}::urn:schemas-upnp-org:service:ContentDirectory:1\r\n'
            'Location: http://{listen_ip}:{server_port}/device.xml\r\n'
            'Cache-Control: max-age=900\r\n' 'Server: Microsoft-Windows/10.0 UPnP/1.0 WMP/12.0\r\n' 'Ext: \r\n' 'Date: {date}\r\n\r\n'
        ),
        'registrar': (
            'HTTP/1.1 200 OK\r\n'
            'ST: urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1\r\n'
            'USN: uuid:{uuid}::urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1\r\n'
            'Location: http://{listen_ip}:{server_port}/device.xml\r\n'
            'Cache-Control: max-age=900\r\n' 'Server: Microsoft-Windows/10.0 UPnP/1.0 WMP/12.0\r\n' 'Ext: \r\n' 'Date: {date}\r\n\r\n'
        )
    }

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', multicast_port))
        mreq = socket.inet_aton(multicast_ip) + socket.inet_aton(listen_ip)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        print(f"SSDP Multi-Listener on {listen_ip}: Success.")
    except Exception as e:
        print(f"!!! SSDP Listener on {listen_ip}: FAILED. Error: {e}")
        return

    while True:
        try:
            data, addr = sock.recvfrom(2048)
            current_date = formatdate(timeval=None, localtime=False, usegmt=True)
            
            def send_response(resp_type):
                formatted_resp = responses[resp_type].format(
                    uuid=config.SERVER_UUID, listen_ip=listen_ip, server_port=server_port, date=current_date
                ).encode('utf-8')
                sock.sendto(formatted_resp, addr)

            if b'urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1' in data:
                print(f"Discovery: Responding to MS MediaReceiverRegistrar from {addr}")
                send_response('registrar')
            elif b'urn:schemas-upnp-org:service:ContentDirectory:1' in data:
                print(f"Discovery: Responding to ContentDirectory from {addr}")
                send_response('service')
            elif b'urn:schemas-upnp-org:device:MediaServer:1' in data:
                print(f"Discovery: Responding to MediaServer from {addr}")
                send_response('device')
            elif b'ssdp:discover' in data or b'ssdp:all' in data:
                 print(f"Discovery: Responding to generic 'discover' from {addr}")
                 send_response('device')
                 time.sleep(random.uniform(0.1, 0.3))
                 send_response('service')
                 time.sleep(random.uniform(0.1, 0.3))
                 send_response('registrar')
        except Exception as e:
            print(f"Error in SSDP listener loop: {e}")

def run_ssdp_server():
    """Starts SSDP listener threads for each local IP address."""
    ssdp_ip, ssdp_port = "239.255.255.250", 1900
    server_port = config.settings.get("server_port")
    all_ips = get_all_local_ips()
    
    if not all_ips or all_ips == ['127.0.0.1']:
        print("!!! FATAL SSDP ERROR: No suitable local network IP found. Discovery will not work.")
        return
        
    for ip in all_ips:
        Thread(target=ssdp_listener, args=(ip, server_port, ssdp_ip, ssdp_port), daemon=True).start()

def send_ssdp_notifications(listen_ip, nts_type):
    """Proactively sends 'alive' or 'byebye' notifications."""
    print(f"Discovery: Sending '{nts_type}' notifications on {listen_ip}...")
    server_port = config.settings.get("server_port")
    
    notify_template = (
        'NOTIFY * HTTP/1.1\r\n'
        'HOST: 239.255.255.250:1900\r\n'
        'CACHE-CONTROL: max-age=900\r\n'
        'LOCATION: http://{listen_ip}:{server_port}/device.xml\r\n'
        'NT: {nt}\r\n' f'NTS: ssdp:{nts_type}\r\n' 'Server: Microsoft-Windows/10.0 UPnP/1.0 WMP/12.0\r\n'
        'USN: uuid:{uuid}::{usn_suffix}\r\n\r\n'
    )
    
    notifications = {
        "mediaserver": ("urn:schemas-upnp-org:device:MediaServer:1", "urn:schemas-upnp-org:device:MediaServer:1"),
        "contentdirectory": ("urn:schemas-upnp-org:service:ContentDirectory:1", "urn:schemas-upnp-org:service:ContentDirectory:1"),
        "ms_registrar": ("urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1", "urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1")
    }

    ssdp_addr = ("239.255.255.250", 1900)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((listen_ip, 0))
    except Exception as e:
        print(f"!!! NOTIFY Error: Could not bind socket on {listen_ip}. Error: {e}")
        return

    for name, (nt, usn_suffix) in notifications.items():
        packet = notify_template.format(
            listen_ip=listen_ip, server_port=server_port, nt=nt,
            uuid=config.SERVER_UUID, usn_suffix=usn_suffix
        ).encode('utf-8')
        try:
            sock.sendto(packet, ssdp_addr)
        except Exception as e:
            print(f"!!! NOTIFY Error: Failed to send {name} packet. Error: {e}")
        if nts_type == "alive":
            time.sleep(0.1)
    
    sock.close()
    print(f"Discovery: '{nts_type}' notifications complete for {listen_ip}.")

def trigger_ssdp_refresh():
    """Sends ssdp:alive notifications from all relevant IPs."""
    print("Settings changed, triggering SSDP refresh...")
    for ip in get_all_local_ips():
        if ip != '127.0.0.1':
            Thread(target=send_ssdp_notifications, args=(ip, "alive"), daemon=True).start()