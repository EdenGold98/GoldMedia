import socket

# --- IMPORTANT: Manually set this to the IP of your server PC ---
# You can find this from the server's startup log (e.g., '192.168.1.136')
LOCAL_IP = "192.168.1.136" 
# ----------------------------------------------------------------

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900

MS = (
    'M-SEARCH * HTTP/1.1\r\n'
    'HOST: 239.255.255.250:1900\r\n'
    'MAN: "ssdp:discover"\r\n'
    'MX: 2\r\n'
    'ST: urn:schemas-upnp-org:device:MediaServer:1\r\n'
    '\r\n'
).encode('utf-8')

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Bind the socket to the correct local IP and an ephemeral port
# This is the crucial step to ensure the OS uses the right network interface
try:
    sock.bind((LOCAL_IP, 0))
    print(f"Tester successfully bound to {LOCAL_IP}")
except OSError as e:
    print(f"!!! ERROR: Could not bind to IP {LOCAL_IP}. Is it correct? Error: {e}")
    sock.close()
    exit()

sock.settimeout(3) 

print("Sending M-SEARCH discovery packet...")
sock.sendto(MS, (SSDP_ADDR, SSDP_PORT))

print("Listening for responses for 3 seconds...")
try:
    while True:
        data, addr = sock.recvfrom(1024)
        print(f"\n--- SUCCESS! RESPONSE RECEIVED FROM: {addr} ---")
        print(data.decode('utf-8', errors='ignore'))
        print("--------------------------------------------------")
except socket.timeout:
    print("\nTest complete. No more responses.")
finally:
    sock.close()