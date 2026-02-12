# system_utils.py
import os
import shutil
import ctypes
import sys
import subprocess

import config

def setup_custom_icon():
    """Copies the user-selected icon to the static directory for serving."""
    icon_source_path = config.settings.get("server_icon_path", "")
    icon_dest_dir = os.path.join('static', 'images')
    icon_dest_path = os.path.join(icon_dest_dir, config.CUSTOM_ICON_FILENAME)
    
    os.makedirs(icon_dest_dir, exist_ok=True)
    
    if icon_source_path and os.path.exists(icon_source_path):
        try:
            shutil.copy(icon_source_path, icon_dest_path)
            print(f"Custom server icon set from: {icon_source_path}")
            return True
        except Exception as e:
            print(f"Error copying custom icon: {e}")
            if os.path.exists(icon_dest_path): os.remove(icon_dest_path)
            return False
    else:
        if os.path.exists(icon_dest_path):
            os.remove(icon_dest_path)
            print("Custom server icon removed.")
        return False

def setup_windows_firewall():
    """Adds a firewall rule for the Python executable if running on Windows."""
    if os.name != 'nt':
        return

    rule_name = "GoldMedia Python Server (python.exe)"
    try:
        is_admin = (ctypes.windll.shell32.IsUserAnAdmin() != 0)
    except AttributeError:
        print("Could not check for admin rights (not on Windows?).")
        return

    if not is_admin:
        print("Admin rights needed to configure firewall. Please re-run as administrator.")
        return
    
    print("Running with admin privileges. Configuring firewall via PowerShell...")
    python_exe = sys.executable
    command = (
        f'powershell -Command "Remove-NetFirewallRule -DisplayName \'{rule_name}\' -ErrorAction SilentlyContinue; '
        f'New-NetFirewallRule -DisplayName \'{rule_name}\' -Direction Inbound -Action Allow -Program \'{python_exe}\' -Profile Any;"'
    )
    
    try:
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print("Firewall rule configured successfully via PowerShell.")
    except subprocess.CalledProcessError as e:
        print("!!! CRITICAL: Failed to set firewall rule. Manual configuration may be required.")
        print(f"!!! Stderr: {e.stderr.strip()}")