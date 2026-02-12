# GoldMedia Server

GoldMedia Server is a lightweight, multi-threaded DLNA/UPnP media server architecture written in Python. It allows for the streaming of local video content to DLNA-compliant devices (Smart TVs, AV Receivers, Media Players like VLC) without the overhead of heavy media center applications.

The server implements the UPnP ContentDirectory service, handling real-time SSDP discovery, event subscriptions, and HTTP video streaming with support for on-the-fly transcoding.

## Core Capabilities

### Networking & Protocols
*   **SSDP Discovery:** Implements a multi-threaded Simple Service Discovery Protocol listener to announce the server on the local network (Multicast 239.255.255.250).
*   **UPnP Eventing:** Supports `SUBSCRIBE` and `NOTIFY` methods. When files are added or removed, the server pushes an update event to connected clients (TVs), eliminating the need to manually refresh the client.
*   **ContentDirectory Service:** Generates compliant DIDL-Lite XML metadata for browsing folder structures and media files.

### Media Handling
*   **HTTP Streaming:** Utilizes the Waitress WSGI server to handle concurrent connections. Supports HTTP `Range` headers for seeking (skipping forward/backward) in video files.
*   **On-the-Fly Transcoding:** Automatically detects incompatible file formats and uses FFmpeg to transcode video streams to MPEG-TS (MPEG2 Video/AC3 Audio) in real-time.
*   **Subtitle Support:** Extracts embedded subtitles or serves external `.srt` files as WebVTT streams compatible with most HTML5 and DLNA players.
*   **Metadata Extraction:** Uses direct FFmpeg/FFprobe calls to extract duration and stream information efficiently, avoiding heavy wrapper libraries.

### System Integration
*   **Real-Time Monitoring:** Integrates `watchdog` to monitor configured directories. File system events (creation, deletion, movement) trigger immediate library updates.
*   **Playback State Persistence:** Maintains a database of playback positions. Supports "Global" caching (resume anywhere) or "Per-IP" caching (resume per device).
*   **System Tray Management:** Runs as a background process with a lightweight system tray icon for configuration and server management.
*   **Custom Compiler:** Includes a specialized build tool (`gui_compiler.py`) to compile the Python environment and scripts into a standalone Windows executable.

## Prerequisites & Installation

To run GoldMedia Server from the source code, the following dependencies are required.

### 1. System Requirements
*   **Operating System:** Windows 10/11 (Recommended for System Tray and Compiler support), Linux (Headless/Server mode supported if GUI code is disabled).
*   **Python:** Version 3.8 or higher.

### 2. External Dependencies (FFmpeg)
This software relies on **FFmpeg** for thumbnail generation, metadata extraction, and transcoding. This is not included in the repository to reduce size.

1.  Download the latest FFmpeg build (essentials or full) from the official FFmpeg website.
2.  Extract the archive.
3.  Locate `ffmpeg.exe` and `ffprobe.exe`.
4.  **Option A (Recommended):** Create a folder named `ffmpeg` inside the root directory of this project and place the two executable files there.
5.  **Option B:** Ensure both executables are added to your system's `PATH` environment variable.

### 3. Python Libraries
Install the required Python modules using `pip`:

```bash
pip install -r requirements.txt
Required Modules:
flask: Web framework for serving the API and content.
waitress: Production-quality WSGI server for concurrent streaming.
requests: Used for sending UPnP NOTIFY packets.
miniupnpc: For automatic router port forwarding (UPnP IGD).
pystray: For system tray icon integration.
Pillow: Image processing for the tray icon.
watchdog: For monitoring file system changes.
psutil: For network interface discovery.
webvtt-py: For converting SRT subtitles to VTT.
Directory Structure
Ensure the following folders exist in the application directory before running:
assets/ - Must contain tray_icon.png.
templates/ - Must contain index.html, device.xml, and the servicedescriptions/ folder containing UPnP XML definitions.
static/images/ - Used for serving the custom server icon.
Usage
Running from Source
Execute the main entry script:
code
Bash
python GoldMedia_main.py
The server will initialize, bind to the local network IP, and minimize to the system tray. Right-click the tray icon to access Settings, where you can configure media folders, server name, and cache behavior.
Compiling to Executable
To create a standalone distribution without requiring Python installed on the target machine:
Run python gui_compiler.py.
Select GoldMedia_main.py as the script.
Add the templates, static, and assets folders to the data files list.
Click Create Environment & Compile.
Known Limitations & Troubleshooting
While GoldMedia Server is robust, users should be aware of the following limitations:
Metadata is Local Only: The server does not scrape the internet (IMDB/TMDB) for movie posters or plot summaries. It uses the file name and generates thumbnails from the video file itself.
Firewall Configuration: SSDP Discovery relies on UDP Multicast. Windows Firewall or third-party antivirus software may block this traffic. The included system_utils.py attempts to add a firewall rule, but manual configuration may be required on strict networks.
Transcoding Profiles: The current transcoding logic converts non-native formats to a standard MPEG-TS stream. It does not currently support Adaptive Bitrate Streaming (HLS/DASH) to adjust quality based on bandwidth.
Subtitle Compatibility: While most modern DLNA clients support external subtitles, some older Smart TVs may strictly require subtitles to be burned into the video stream, which this server does not currently perform.
License
This project is licensed under the GNU General Public License v3.0 (GPLv3).
You are free to use, modify, and distribute this software. If you distribute modified versions of this application, you must release the source code under the same license. Closing the source code for commercial distribution is prohibited.
See the LICENSE file for more details.
