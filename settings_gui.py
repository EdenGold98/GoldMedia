# settings_gui.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
from PIL import Image, ImageTk

import config # Use the config module for constants

class SettingsWindow:
    def __init__(self, parent, on_save_callback=None):
        self.parent = parent
        self.on_save_callback = on_save_callback
        self.win = tk.Toplevel(parent)
        self.win.title("Server Settings")
        self.win.resizable(False, False)
        # Load settings via config module to ensure defaults are applied
        self.settings = config.load_settings()
        self.preview_image = None # To prevent garbage collection

        main_frame = ttk.Frame(self.win, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # --- Server Settings Section ---
        server_frame = ttk.LabelFrame(main_frame, text="Server", padding="10")
        server_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        server_frame.columnconfigure(1, weight=1)

        ttk.Label(server_frame, text="Server Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.server_name_var = tk.StringVar(value=self.settings.get("server_name"))
        ttk.Entry(server_frame, textvariable=self.server_name_var, width=40).grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(server_frame, text="Server Port:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.server_port_var = tk.StringVar(value=self.settings.get("server_port"))
        ttk.Entry(server_frame, textvariable=self.server_port_var, width=10).grid(row=1, column=1, sticky=tk.W)

        # --- Server Icon ---
        ttk.Label(server_frame, text="Server Icon:").grid(row=2, column=0, sticky=tk.W, pady=2)
        icon_entry_frame = ttk.Frame(server_frame)
        icon_entry_frame.grid(row=2, column=1, sticky=tk.EW)
        icon_entry_frame.columnconfigure(0, weight=1)
        
        initial_icon_path = self.settings.get("server_icon_path", "")
        if not initial_icon_path or not os.path.exists(initial_icon_path):
            initial_icon_path = config.DEFAULT_SETTINGS["server_icon_path"]

        self.server_icon_path_var = tk.StringVar(value=initial_icon_path)
        ttk.Entry(icon_entry_frame, textvariable=self.server_icon_path_var, width=30, state="readonly").grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(icon_entry_frame, text="Browse...", command=self.select_icon).grid(row=0, column=1, padx=(5,0))

        icon_preview_frame = ttk.Frame(server_frame)
        icon_preview_frame.grid(row=3, column=1, sticky=tk.W, pady=(5,0))
        self.icon_preview_label = ttk.Label(icon_preview_frame, text="Preview:")
        self.icon_preview_label.pack(side=tk.LEFT, padx=(0, 5))
        self.icon_canvas = ttk.Label(icon_preview_frame, relief="sunken")
        self.icon_canvas.pack(side=tk.LEFT)
        ttk.Button(icon_preview_frame, text="Set Default", command=self.set_default_icon).pack(side=tk.LEFT, padx=(10,0))
        
        # --- UPnP Checkbox ---
        self.enable_upnp_var = tk.BooleanVar(value=self.settings.get("enable_upnp"))
        ttk.Checkbutton(server_frame, text="Attempt UPnP Port Forwarding on startup", variable=self.enable_upnp_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=5)

        # --- Folders Section ---
        folder_frame = ttk.LabelFrame(main_frame, text="Media Folders", padding="10")
        folder_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(0, weight=1)
        
        self.folder_listbox = tk.Listbox(folder_frame, height=5)
        self.folder_listbox.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E))
        for folder in self.settings.get("media_folders", []):
            self.folder_listbox.insert(tk.END, folder)
        
        folder_button_frame = ttk.Frame(folder_frame)
        folder_button_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5,0))
        ttk.Button(folder_button_frame, text="Add Folder", command=self.add_folder).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(folder_button_frame, text="Remove Selected", command=self.remove_folder).pack(side=tk.LEFT)
        
        # --- Thumbnail Section ---
        thumb_frame = ttk.LabelFrame(main_frame, text="Thumbnails", padding="10")
        thumb_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        thumb_frame.columnconfigure(1, weight=1)

        self.generate_thumbnails_var = tk.BooleanVar(value=self.settings.get("generate_thumbnails"))
        ttk.Checkbutton(thumb_frame, text="Generate video thumbnails on scan", variable=self.generate_thumbnails_var).grid(row=0, column=0, columnspan=2, sticky=tk.W)

        ttk.Label(thumb_frame, text="Timestamp (seconds):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.thumbnail_timestamp_var = tk.StringVar(value=self.settings.get("thumbnail_timestamp"))
        ttk.Entry(thumb_frame, textvariable=self.thumbnail_timestamp_var, width=10).grid(row=1, column=1, sticky=tk.W)
        
        # --- Cache Section (Clarified) ---
        cache_frame = ttk.LabelFrame(main_frame, text="Playback Cache (Web UI Only)", padding="10")
        cache_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)
        cache_frame.columnconfigure(1, weight=1)

        ttk.Label(cache_frame, text="Cache Mode:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.cache_mode_var = tk.StringVar(value=self.settings.get("cache_mode", "Global"))
        cache_combo = ttk.Combobox(cache_frame, textvariable=self.cache_mode_var, values=["Off", "Global", "Per IP"], state="readonly", width=15)
        cache_combo.grid(row=0, column=1, sticky=tk.W)

        # === THE FIX: Add Transcoding Section ===
        transcode_frame = ttk.LabelFrame(main_frame, text="Transcoding (for DLNA)", padding="10")
        transcode_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)
        transcode_frame.columnconfigure(1, weight=1)

        self.enable_transcoding_var = tk.BooleanVar(value=self.settings.get("enable_transcoding", False))
        ttk.Checkbutton(transcode_frame, text="Enable on-the-fly transcoding for incompatible formats", variable=self.enable_transcoding_var).grid(row=0, column=0, columnspan=2, sticky=tk.W)

        ttk.Label(transcode_frame, text="Transcode formats (comma-separated):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.transcode_formats_var = tk.StringVar(value=self.settings.get("transcode_formats", ".mkv,.avi,.webm,.mov"))
        ttk.Entry(transcode_frame, textvariable=self.transcode_formats_var, width=40).grid(row=1, column=1, sticky=tk.EW)
        
        # --- General Options Section ---
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=5)

        self.start_on_startup_var = tk.BooleanVar(value=self.settings.get("start_on_startup"))
        ttk.Checkbutton(options_frame, text="Start when PC is starting", variable=self.start_on_startup_var).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        
        # --- Save/Cancel Buttons ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0), sticky=tk.E)
        ttk.Button(button_frame, text="Save", command=self.save_and_close).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.win.destroy).pack(side=tk.LEFT)
        
        self.update_icon_preview()

    def update_icon_preview(self):
        try:
            path = self.server_icon_path_var.get()
            if path and os.path.exists(path):
                img = Image.open(path)
                img.thumbnail((48, 48))
                self.preview_image = ImageTk.PhotoImage(img)
                self.icon_canvas.config(image=self.preview_image)
            else:
                 self.icon_canvas.config(image='')
        except Exception as e:
            print(f"Error updating icon preview: {e}")
            self.icon_canvas.config(image='')

    def select_icon(self):
        filepath = filedialog.askopenfilename(
            title="Select Server Icon",
            filetypes=(("Image Files", "*.png *.jpg *.jpeg"), ("All files", "*.*"))
        )
        if filepath:
            self.server_icon_path_var.set(filepath)
            self.update_icon_preview()

    def set_default_icon(self):
        default_path = config.DEFAULT_SETTINGS["server_icon_path"]
        self.server_icon_path_var.set(default_path)
        self.update_icon_preview()

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_listbox.insert(tk.END, folder)

    def remove_folder(self):
        for i in reversed(self.folder_listbox.curselection()):
            self.folder_listbox.delete(i)

    def save_and_close(self):
        new_settings = {}
        new_settings["server_name"] = self.server_name_var.get()
        new_settings["server_port"] = int(self.server_port_var.get())
        new_settings["media_folders"] = list(self.folder_listbox.get(0, tk.END))
        new_settings["start_on_startup"] = self.start_on_startup_var.get()
        new_settings["generate_thumbnails"] = self.generate_thumbnails_var.get()
        new_settings["thumbnail_timestamp"] = int(self.thumbnail_timestamp_var.get())
        new_settings["enable_upnp"] = self.enable_upnp_var.get()
        new_settings["server_icon_path"] = self.server_icon_path_var.get()
        new_settings["cache_mode"] = self.cache_mode_var.get()

        # === THE FIX: Save transcoding settings ===
        new_settings["enable_transcoding"] = self.enable_transcoding_var.get()
        new_settings["transcode_formats"] = self.transcode_formats_var.get()
        
        with open(config.SETTINGS_FILE, 'w') as f:
            json.dump(new_settings, f, indent=4)
        
        if self.on_save_callback:
            self.on_save_callback()
            
        messagebox.showinfo("Settings Saved", "Settings have been saved. Your library will now be refreshed.")
        self.win.destroy()