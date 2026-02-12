import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import subprocess
import sys
import os
import ast
import json
import threading
import queue
import pkgutil
import shutil

# --- Configuration: The Hybrid Approach for cx_Freeze ---

# This dictionary maps the name used in an `import` statement to the
# name of the package that needs to be installed via Conda or Pip.
IMPORT_TO_PACKAGE_MAP = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "yaml": "pyyaml",
    "pandas": "pandas",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "scipy": "scipy",
    "requests": "requests",
    "selenium": "selenium",
    "flask": "flask",
    "waitress": "waitress",
    "psutil": "psutil",
    "watchdog": "watchdog",
    "pystray": "pystray",
    "miniupnpc": "miniupnpc",
    "webvtt": "webvtt-py"
}

# This set contains packages that are well-supported on Conda Forge.
# We will prioritize installing these with Conda/Mamba.
KNOWN_CONDA_PACKAGES = {
    "pillow",
    "flask",
    "psutil",
    "requests",
    "waitress",
    "watchdog",
    "pystray",
    "numpy",
    "pandas",
    "scipy"
}

# 'packages' is for top-level packages that cx_Freeze's static analysis might miss entirely.
PACKAGES_TO_FORCE_INCLUDE = [
    "jinja2", 
    "pkg_resources", 
    "asyncio"
]

# 'includes' is for specific sub-modules that are dynamically imported by other libraries.
# This is the most targeted way to fix "ModuleNotFound" errors for specific backends.
MODULES_TO_FORCE_INCLUDE = [
    "pystray.backends.win32" # Solves the ImportError from the last log.
]

class App:
    """
    A Tkinter GUI to automate Conda environment creation and Python project
    compilation into a distributable package using cx_Freeze.
    """
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Conda Env & cx_Freeze GUI (Final Version)")
        self.root.geometry("850x700")
        self.root.minsize(700, 600)

        # --- State Variables ---
        self.script_path = tk.StringVar()
        self.env_option = tk.StringVar(value="create")
        self.new_env_name = tk.StringVar()
        self.existing_env = tk.StringVar()
        self.is_windowed = tk.BooleanVar(value=False)
        self.create_zip = tk.BooleanVar(value=True)
        self.process_running = False
        self.data_files = []

        # --- Threading & Communication ---
        self.queue = queue.Queue()

        # --- System Detection ---
        self.package_manager = "mamba" if shutil.which("mamba") else "conda"
        
        # --- Build the UI ---
        self.create_widgets()
        
        # --- Initial Setup ---
        self.populate_existing_envs()
        self.process_queue()
        
        self.log(f"Using '{self.package_manager}' as the package manager.", "INFO")
        if self.package_manager == "conda":
            self.log("Tip: For much faster environment solving, install mamba: 'conda install -n base -c conda-forge mamba'", "INFO")

    def create_widgets(self):
        """Creates and arranges all the widgets in the main window."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(9, weight=1) # Log area row

        # --- 1. File Selection ---
        ttk.Label(main_frame, text="1. Select Main Python Script", font=("Helvetica", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=1, column=0, sticky="ew")
        file_frame.columnconfigure(0, weight=1)

        self.file_entry = ttk.Entry(file_frame, textvariable=self.script_path, state="readonly")
        self.file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        self.browse_button = ttk.Button(file_frame, text="Browse...", command=self.select_file)
        self.browse_button.grid(row=0, column=1, sticky="e")

        # --- 2. Environment Options ---
        ttk.Label(main_frame, text="2. Anaconda Environment Option", font=("Helvetica", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(15, 5))

        radio_frame = ttk.Frame(main_frame)
        radio_frame.grid(row=3, column=0, sticky="w")
        
        create_radio = ttk.Radiobutton(radio_frame, text="Create New Environment", variable=self.env_option, value="create", command=self.toggle_env_options)
        create_radio.pack(side=tk.LEFT, padx=(0, 20))
        
        existing_radio = ttk.Radiobutton(radio_frame, text="Use Existing Environment", variable=self.env_option, value="existing", command=self.toggle_env_options)
        existing_radio.pack(side=tk.LEFT)

        # Frame for "Create New Environment" options
        self.create_frame = ttk.Labelframe(main_frame, text="New Environment Details", padding="10")
        self.create_frame.grid(row=4, column=0, sticky="ew", pady=5)
        self.create_frame.columnconfigure(1, weight=1)

        ttk.Label(self.create_frame, text="Environment Name:").grid(row=0, column=0, sticky="w")
        self.new_env_entry = ttk.Entry(self.create_frame, textvariable=self.new_env_name)
        self.new_env_entry.grid(row=0, column=1, sticky="ew")

        # Frame for "Use Existing Environment" options
        self.existing_frame = ttk.Labelframe(main_frame, text="Select Environment", padding="10")
        self.existing_frame.columnconfigure(1, weight=1)

        ttk.Label(self.existing_frame, text="Environment:").grid(row=0, column=0, sticky="w")
        self.env_combo = ttk.Combobox(self.existing_frame, textvariable=self.existing_env, state="readonly")
        self.env_combo.grid(row=0, column=1, sticky="ew")
        
        # --- 3. Manual Data File/Folder Selection ---
        data_files_frame = ttk.Labelframe(main_frame, text="3. Add Data Files & Folders (e.g., assets, templates)", padding="10")
        data_files_frame.grid(row=5, column=0, sticky="ew", pady=(15, 5))
        data_files_frame.columnconfigure(0, weight=1)

        listbox_frame = ttk.Frame(data_files_frame)
        listbox_frame.grid(row=0, column=0, sticky="nsew")
        listbox_frame.columnconfigure(0, weight=1)

        self.data_listbox = tk.Listbox(listbox_frame, height=4)
        self.data_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.data_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.data_listbox.config(yscrollcommand=scrollbar.set)
        
        button_frame = ttk.Frame(data_files_frame)
        button_frame.grid(row=1, column=0, sticky="w", pady=(5,0))

        add_file_btn = ttk.Button(button_frame, text="Add File...", command=self.add_data_file)
        add_file_btn.pack(side=tk.LEFT, padx=(0, 5))
        add_folder_btn = ttk.Button(button_frame, text="Add Folder...", command=self.add_data_folder)
        add_folder_btn.pack(side=tk.LEFT, padx=5)
        remove_btn = ttk.Button(button_frame, text="Remove Selected", command=self.remove_data_item)
        remove_btn.pack(side=tk.LEFT, padx=5)

        # --- 4. Compilation Options ---
        compile_frame = ttk.Labelframe(main_frame, text="4. cx_Freeze Options", padding="10")
        compile_frame.grid(row=6, column=0, sticky="ew", pady=(15, 5))
        
        windowed_check = ttk.Checkbutton(compile_frame, text="GUI Application (no console window)", variable=self.is_windowed)
        windowed_check.pack(side=tk.LEFT, padx=5)
        
        zip_check = ttk.Checkbutton(compile_frame, text="Create Single Distributable File (.zip)", variable=self.create_zip)
        zip_check.pack(side=tk.LEFT, padx=5)

        # --- 5. Action Button ---
        self.action_button = ttk.Button(main_frame, text="Create Environment & Compile", command=self.start_process)
        self.action_button.grid(row=7, column=0, sticky="ew", pady=10)

        # --- 6. Progress & Log ---
        self.progress = ttk.Progressbar(main_frame, orient="horizontal", mode="indeterminate")
        self.progress.grid(row=8, column=0, sticky="ew", pady=(5, 0))
        
        self.log_area = scrolledtext.ScrolledText(main_frame, height=10, state="disabled", wrap=tk.WORD, bg="#f0f0f0", relief="solid", borderwidth=1)
        self.log_area.grid(row=9, column=0, sticky="nsew")

        self.toggle_env_options()

    def toggle_env_options(self):
        """Shows or hides the environment option frames based on the radio button selection."""
        if self.env_option.get() == "create":
            self.existing_frame.grid_forget()
            self.create_frame.grid(row=4, column=0, sticky="ew", pady=5)
            self.action_button.config(text="Create Environment & Compile")
        else:
            self.create_frame.grid_forget()
            self.existing_frame.grid(row=4, column=0, sticky="nsew", pady=5)
            self.action_button.config(text="Compile in Existing Environment")

    def select_file(self):
        """Opens a file dialog to select the main Python script."""
        path = filedialog.askopenfilename(title="Select main Python script", filetypes=[("Python Files", "*.py")])
        if path:
            self.script_path.set(path)
            base_name = os.path.basename(path)
            project_name = os.path.splitext(base_name)[0]
            self.new_env_name.set(f"{project_name}-env")

    def add_data_file(self):
        """Opens a file dialog to select a single data file."""
        if not self.script_path.get():
            messagebox.showerror("Error", "Please select the main Python script first.")
            return
        
        path = filedialog.askopenfilename(title="Select a Data File")
        if path:
            project_root = os.path.dirname(self.script_path.get())
            relative_path = os.path.relpath(path, project_root)
            if relative_path not in self.data_files:
                self.data_files.append(relative_path)
                self.data_listbox.insert(tk.END, relative_path)

    def add_data_folder(self):
        """Opens a directory dialog to select a data folder."""
        if not self.script_path.get():
            messagebox.showerror("Error", "Please select the main Python script first.")
            return
        
        path = filedialog.askdirectory(title="Select a Data Folder")
        if path:
            project_root = os.path.dirname(self.script_path.get())
            relative_path = os.path.relpath(path, project_root)
            if relative_path not in self.data_files:
                self.data_files.append(relative_path)
                self.data_listbox.insert(tk.END, relative_path + os.sep)

    def remove_data_item(self):
        """Removes the selected item from the data files list."""
        selected_indices = self.data_listbox.curselection()
        if not selected_indices:
            return
        
        for index in reversed(selected_indices):
            self.data_listbox.delete(index)
            self.data_files.pop(index)

    def populate_existing_envs(self):
        """Starts a background thread to fetch the list of existing Conda environments."""
        self.log("Fetching conda environments...")
        thread = threading.Thread(target=self._get_conda_envs_thread, daemon=True)
        thread.start()

    def _get_conda_envs_thread(self):
        """The actual logic to get environments, designed to run in a thread."""
        try:
            command = ["conda", "env", "list", "--json"]
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(command, capture_output=True, text=True, check=True, creationflags=creation_flags)
            data = json.loads(result.stdout)
            env_paths = data.get("envs", [])
            env_names = [os.path.basename(p) for p in env_paths]
            self.queue.put(("ENVS_LIST", sorted(env_names)))
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
            self.queue.put(("LOG", ("Could not find 'conda' or list environments.", "ERROR")))

    def log(self, message, level="INFO"):
        """Appends a message to the log area in a thread-safe way."""
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, f"[{level}] {message}\n")
        self.log_area.config(state="disabled")
        self.log_area.see(tk.END)

    def process_queue(self):
        """Checks the queue for messages from background threads and updates the GUI."""
        try:
            while True:
                task, data = self.queue.get_nowait()
                if task == "LOG":
                    self.log(data[0], data[1])
                elif task == "ENVS_LIST":
                    self.env_combo['values'] = data
                    self.log("Successfully fetched conda environments.")
                elif task == "PROCESS_START":
                    self.progress.start()
                    self.action_button.config(state="disabled")
                    self.browse_button.config(state="disabled")
                    self.process_running = True
                elif task == "PROCESS_END":
                    self.progress.stop()
                    self.action_button.config(state="normal")
                    self.browse_button.config(state="normal")
                    self.process_running = False
                    if data == "SUCCESS":
                        messagebox.showinfo("Success", "Process completed successfully!")
                    else:
                        messagebox.showerror("Error", "Process failed. Check the log for details.")
        except queue.Empty:
            self.root.after(100, self.process_queue)

    def start_process(self):
        """Validates user input and starts the main background process."""
        if self.process_running:
            return
        script = self.script_path.get()
        if not script or not os.path.exists(script):
            messagebox.showerror("Error", "Please select a valid Python script.")
            return
        if self.env_option.get() == "create":
            env_name = self.new_env_name.get().strip()
            if not env_name:
                messagebox.showerror("Error", "Please provide a name for the new environment.")
                return
        else:
            env_name = self.existing_env.get()
            if not env_name:
                messagebox.showerror("Error", "Please select an existing environment.")
                return
        thread = threading.Thread(target=self.run_background_tasks, args=(script, env_name), daemon=True)
        thread.start()

    def _env_exists(self, env_name):
        """Checks if a conda environment exists by name."""
        try:
            command = ['conda', 'env', 'list', '--json']
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(command, capture_output=True, text=True, check=True, creationflags=creation_flags)
            envs_data = json.loads(result.stdout)
            env_paths = envs_data.get('envs', [])
            return env_name in {os.path.basename(path) for path in env_paths}
        except Exception:
            return False

    def run_background_tasks(self, script_path, env_name):
        """Handles the main logic for creating environments and compiling."""
        self.queue.put(("PROCESS_START", None))
        project_dir = os.path.dirname(script_path)
        script_filename = os.path.basename(script_path)
        project_name = os.path.splitext(script_filename)[0]
        setup_file_path = os.path.join(project_dir, "temp_setup.py")

        try:
            if self.env_option.get() == "create":
                # Step 0: Clean slate
                if self._env_exists(env_name):
                    self.queue.put(("LOG", (f"Environment '{env_name}' already exists. Removing for a clean build.", "WARN")))
                    if not self._run_command_streamed(["conda", "env", "remove", "-n", env_name, "-y"]):
                        raise Exception(f"Failed to remove existing environment '{env_name}'.")

                # Step 1: Create minimal environment
                self.queue.put(("LOG", ("Step 1: Creating minimal environment...", "INFO")))
                py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
                create_cmd = [self.package_manager, "create", "-n", env_name, "-c", "conda-forge", f"python={py_version}", "pip", "-y"]
                if not self._run_command_streamed(create_cmd):
                    raise Exception("Failed to create minimal environment.")

                # Step 2: Partition and install dependencies
                all_deps = self._get_project_dependencies(script_path)
                all_deps.add("cx-freeze")
                conda_deps = {dep for dep in all_deps if dep in KNOWN_CONDA_PACKAGES}
                pip_deps = all_deps - conda_deps

                if conda_deps:
                    log_msg = f"Step 2a: Installing Conda packages: {', '.join(sorted(conda_deps))}"
                    self.queue.put(("LOG", (log_msg, "INFO")))
                    install_cmd = [self.package_manager, "install", "-n", env_name, "-c", "conda-forge"] + sorted(list(conda_deps)) + ["-y"]
                    if not self._run_command_streamed(install_cmd):
                        raise Exception("Failed to install Conda packages.")
                
                if pip_deps:
                    log_msg = f"Step 2b: Installing Pip packages: {', '.join(sorted(pip_deps))}"
                    self.queue.put(("LOG", (log_msg, "INFO")))
                    pip_install_cmd = ["conda", "run", "-n", env_name, "python", "-m", "pip", "install"] + sorted(list(pip_deps))
                    if not self._run_command_streamed(pip_install_cmd):
                        raise Exception("Failed to install Pip packages.")

            # --- cx_Freeze Compilation Step ---
            self.queue.put(("LOG", ("Step 3: Cleaning old build/dist directories...", "INFO")))
            build_dir = os.path.join(project_dir, 'build')
            dist_zip_path = os.path.join(project_dir, f"{project_name}-dist.zip")
            if os.path.isdir(build_dir): shutil.rmtree(build_dir)
            if os.path.isfile(dist_zip_path): os.remove(dist_zip_path)

            self.queue.put(("LOG", ("Step 4: Generating setup script for cx_Freeze...", "INFO")))
            
            base = "Win32GUI" if self.is_windowed.get() and sys.platform == "win32" else None
            
            files_to_include_set = set(self.data_files)
            for folder in ['templates', 'static', 'assets']:
                if os.path.isdir(os.path.join(project_dir, folder)):
                    files_to_include_set.add(folder)
                    self.queue.put(("LOG", (f"Auto-detected data folder '{folder}', adding to build.", "INFO")))
            
            files_to_include = [(path, path) for path in files_to_include_set]
            
            setup_script_content = f"""
from cx_Freeze import setup, Executable

base = "{base}" if {repr(base)} is not None else None
include_files = {repr(files_to_include)}

# Explicitly tell cx_Freeze to include these packages.
packages_to_include = {repr(PACKAGES_TO_FORCE_INCLUDE)}

# Explicitly tell cx_Freeze to include these hidden modules.
modules_to_include = {repr(MODULES_TO_FORCE_INCLUDE)}

build_exe_options = {{
    "packages": packages_to_include,
    "includes": modules_to_include,
    "excludes": [],
    "include_files": include_files
}}

setup(
    name="{project_name}", version="1.0", description="Application compiled by the GUI tool",
    options={{"build_exe": build_exe_options}},
    executables=[Executable("{script_filename}", base=base)]
)
"""
            with open(setup_file_path, "w", encoding='utf-8') as f:
                f.write(setup_script_content.strip())

            self.queue.put(("LOG", ("Step 5: Starting cx_Freeze compilation...", "INFO")))
            compile_cmd = ["conda", "run", "-n", env_name, "python", "temp_setup.py", "build"]
            if not self._run_command_streamed(compile_cmd, workdir=project_dir):
                raise Exception("cx_Freeze compilation failed.")
            
            final_artifact_path = build_dir
            if self.create_zip.get():
                self.queue.put(("LOG", ("Step 6: Creating single-file distributable (.zip)...", "INFO")))
                output_dir_name = next((d for d in os.listdir(build_dir) if d.startswith('exe.')), None)
                if not output_dir_name:
                    raise Exception("Could not find cx_Freeze output directory inside 'build'.")

                source_dir_to_zip = os.path.join(build_dir, output_dir_name)
                zip_output_path = os.path.join(project_dir, f"{project_name}-dist")
                shutil.make_archive(zip_output_path, 'zip', source_dir_to_zip)
                final_artifact_path = f"{zip_output_path}.zip"
                self.queue.put(("LOG", (f"Successfully created {os.path.basename(final_artifact_path)}", "INFO")))

            final_message = f"\n✅ SUCCESS! Your application is ready in: {final_artifact_path}"
            self.queue.put(("LOG", (final_message, "INFO")))
            self.queue.put(("PROCESS_END", "SUCCESS"))

        except Exception as e:
            self.queue.put(("LOG", (str(e), "ERROR")))
            self.queue.put(("PROCESS_END", "FAILURE"))
        finally:
            if os.path.exists(setup_file_path):
                os.remove(setup_file_path)
                self.queue.put(("LOG", ("Cleaned up temporary setup script.", "INFO")))

    def _run_command_streamed(self, command, workdir=None):
        self.queue.put(("LOG", (f"Executing: {' '.join(command)}", "CMD")))
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', cwd=workdir, creationflags=creation_flags)
        for line in iter(process.stdout.readline, ''):
            self.queue.put(("LOG", (line.strip(), "SUBPROCESS")))
        return process.wait() == 0
    
    def _get_std_lib_modules(self):
        if hasattr(sys, 'stdlib_module_names'):
            return sys.stdlib_module_names
        else:
            return {mod[1] for mod in pkgutil.iter_modules()}

    def _is_local_import(self, module_name, project_root):
        path_to_check = os.path.join(project_root, module_name)
        return os.path.exists(f"{path_to_check}.py") or os.path.isdir(path_to_check)

    def _parse_imports_recursive(self, file_path, project_root, all_imports, std_lib, processed_files):
        if file_path in processed_files:
            return
        processed_files.add(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=file_path)
        except Exception as e:
            self.queue.put(("LOG", (f"Skipping unparsable file {os.path.basename(file_path)}: {e}", "WARN")))
            return
        for node in ast.walk(tree):
            module_name = None
            if isinstance(node, ast.Import):
                module_name = node.names[0].name.split('.')[0]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                module_name = node.module.split('.')[0]
            if module_name and module_name not in std_lib:
                if self._is_local_import(module_name, project_root):
                    local_py_path = os.path.join(project_root, f"{module_name}.py")
                    if os.path.exists(local_py_path):
                        self._parse_imports_recursive(local_py_path, project_root, all_imports, std_lib, processed_files)
                else:
                    all_imports.add(module_name)
    
    def _get_project_dependencies(self, main_script_path):
        project_root = os.path.dirname(main_script_path)
        all_imports = set()
        std_lib = self._get_std_lib_modules()
        processed_files = set()
        self._parse_imports_recursive(main_script_path, project_root, all_imports, std_lib, processed_files)
        return {IMPORT_TO_PACKAGE_MAP.get(dep, dep) for dep in all_imports}

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()