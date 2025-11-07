import tkinter as tk
from tkinter import ttk, filedialog
import os
import subprocess
import shutil
import json
from pathlib import Path
import tempfile
import threading
import math
import sys
from datetime import datetime
import multiprocessing
from multiprocessing import Pool, cpu_count
from PIL import Image, ImageTk

def _collect_files_chunk(args):
    """Helper function to collect files from a directory chunk (for multiprocessing)"""
    root_dir, subdirs, viewing_dir = args
    file_list = []
    
    for subdir in subdirs:
        dir_path = os.path.join(root_dir, subdir) if subdir else root_dir
        
        try:
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    if file.startswith('.'):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, viewing_dir)
                    try:
                        size = os.path.getsize(full_path)
                        file_list.append((rel_path, size))
                    except:
                        pass
        except:
            pass
    
    return file_list

class RotatingLoadingIcon(tk.Canvas):
    """Custom rotating loading icon widget"""
    
    def __init__(self, parent, background_path, rotating_path):
        from PIL import Image
        
        # Load images
        try:
            self.background_pil = Image.open(background_path)
        except Exception as e:
            print(f"Failed to load background: {background_path} - {e}")
            self.background_pil = Image.new('RGB', (64, 64), color='lightgray')
        
        try:
            self.rotating_pil = Image.open(rotating_path)
        except Exception as e:
            print(f"Failed to load rotating image: {rotating_path} - {e}")
            self.rotating_pil = Image.new('RGB', (64, 64), color='blue')
        
        # Set widget size to match images
        size = max(self.background_pil.width, self.background_pil.height)
        
        super().__init__(parent, width=size, height=size, bg="#1e1e1e", 
                        highlightthickness=0)
        
        self.size = size
        self.center = size // 2
        
        # Convert images to PhotoImage
        from PIL import ImageTk
        self.background_image = ImageTk.PhotoImage(self.background_pil)
        self.rotating_image = ImageTk.PhotoImage(self.rotating_pil)
        
        # Rotation angle
        self.rotation_angle = 0
        
        # Draw static background
        bg_x = (size - self.background_pil.width) // 2
        bg_y = (size - self.background_pil.height) // 2
        self.create_image(self.center, self.center, image=self.background_image)
        
        # Draw rotating image on top
        self.rotating_id = self.create_image(self.center, self.center, image=self.rotating_image)
        
        # Setup rotation timer
        self.timer_running = False
        self.timer_id = None

    def rotate(self):
        """Rotate the icon by 30 degrees (one clock position)"""
        if not self.timer_running:
            return
        
        from PIL import ImageTk
        
        self.rotation_angle = (self.rotation_angle + 30) % 360  # 30 degrees = 1/12 of circle
        
        # Rotate the image
        rotated = self.rotating_pil.rotate(-self.rotation_angle, expand=False)
        self.rotating_image = ImageTk.PhotoImage(rotated)
        self.itemconfig(self.rotating_id, image=self.rotating_image)
        
        # Schedule next rotation
        self.timer_id = self.after(100, self.rotate)  # Update every 100ms to match PyQt
    
    def start(self):
        """Start the rotation"""
        if not self.timer_running:
            self.timer_running = True
            self.rotate()
    
    def stop(self):
        """Stop the rotation"""
        self.timer_running = False
        if self.timer_id:
            self.after_cancel(self.timer_id)
            self.timer_id = None

class EnhancedProgressDialog(tk.Toplevel):
    """Enhanced progress dialog with file tracking and detailed log"""
    
    def __init__(self, parent, title="Processing"):
        super().__init__(parent)
        self.title(title)
        self.geometry("700x550")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()
        
        self.was_cancelled = False
        self.is_complete = False
        
        # Main frame
        main_frame = tk.Frame(self, bg="#1e1e1e")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header bar
        header = tk.Frame(main_frame, bg="#0d7377", height=4)
        header.pack(fill=tk.X)
        
        # Content area
        content = tk.Frame(main_frame, bg="#1e1e1e", padx=20, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Loading icon
        icon_frame = tk.Frame(content, bg="#1e1e1e")
        icon_frame.pack(pady=(0, 15))
        
        background_path = "default_i3.png"
        rotating_path = "default_i5.png"
        
        self.loading_icon = RotatingLoadingIcon(icon_frame, background_path, rotating_path)
        self.loading_icon.pack()
        self.loading_icon.start()
        
        # Status label
        self.status_label = tk.Label(content, text="Initializing, please wait...",
                                     bg="#1e1e1e", fg="#ffffff",
                                     font=("Segoe UI", 11, "bold"))
        self.status_label.pack(pady=(0, 10))
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(content, length=600, mode='determinate',
                                           variable=self.progress_var, maximum=100)
        self.progress_bar.pack(pady=(0, 5))
        
        # Progress percentage label
        self.progress_label = tk.Label(content, text="0%",
                                       bg="#1e1e1e", fg="#b0b0b0",
                                       font=("Segoe UI", 9))
        self.progress_label.pack(pady=(0, 15))
        
        # Log box label
        log_label = tk.Label(content, text="Operation Log:",
                            bg="#1e1e1e", fg="#ffffff",
                            font=("Segoe UI", 9, "bold"), anchor=tk.W)
        log_label.pack(fill=tk.X, pady=(0, 5))
        
        # Log box with scrollbar - STORE log_frame as instance variable
        self.log_frame = tk.Frame(content, bg="#2d2d2d")
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        self.scrollbar = tk.Scrollbar(self.log_frame, bg="#2d2d2d")
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(self.log_frame, bg="#2d2d2d", fg="#d4d4d4",
                               font=("Consolas", 9), wrap=tk.WORD,
                               yscrollcommand=self.scrollbar.set, relief=tk.FLAT,
                               highlightthickness=0, padx=10, pady=10)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.log_text.yview)
        
        # Cancel button
        self.cancel_button = tk.Button(content, text="Cancel",
                                       bg="#F44336", fg="#ffffff",
                                       font=("Segoe UI", 10, "bold"),
                                       relief=tk.FLAT, padx=30, pady=10,
                                       cursor="hand2", command=self.on_cancel,
                                       activebackground="#d32f2f",
                                       activeforeground="#ffffff")
        self.cancel_button.pack()
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        # Handle close button
        self.protocol("WM_DELETE_WINDOW", self.on_close_attempt)

    def on_close_attempt(self):
        """Handle window close button (X)"""
        if not self.was_cancelled and not self.is_complete:
            self.on_cancel()
        else:
            self.destroy()
    
    def on_cancel(self):
        """Handle cancel button"""
        if not self.was_cancelled and not self.is_complete:
            self.was_cancelled = True
            self.cancel_button.config(state=tk.DISABLED, text="Cancelling...",
                                     bg="#555555")
            self.append_log("❌ Cancellation requested...")
    
    def set_status(self, text):
        """Helper method to update status label"""
        self.status_label.config(text=text)
        self.update_idletasks()

    def set_progress(self, value):
        """Update progress bar (0-100)"""
        self.progress_var.set(value)
        self.progress_label.config(text=f"{int(value)}%")
        self.update_idletasks()
    
    def append_log(self, message):
        """Append message to log box"""
        if not message or not message.strip():
            return
        
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.update_idletasks()
    
    def mark_complete(self):
        """Mark operation as complete - allows dialog to close"""
        self.is_complete = True
        self.loading_icon.stop()
        self.cancel_button.config(text="Close", bg="#4CAF50",
                                 state=tk.NORMAL, command=self.destroy)
    
    def stop_icon(self):
        """Stop the rotating icon"""
        self.loading_icon.stop()

class ModernMessageBox(tk.Toplevel):
    def __init__(self, parent, title, message, msg_type="info"):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        
        # Colors
        colors = {
            "info": "#2196F3",
            "success": "#4CAF50",
            "warning": "#FF9800",
            "error": "#F44336"
        }
        
        # Center window
        self.transient(parent)
        self.grab_set()
        
        # Main frame
        main_frame = tk.Frame(self, bg="#1e1e1e")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header with colored bar
        header = tk.Frame(main_frame, bg=colors.get(msg_type, "#2196F3"), height=4)
        header.pack(fill=tk.X)
        
        # Content
        content_frame = tk.Frame(main_frame, bg="#1e1e1e", padx=30, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Message
        msg_label = tk.Label(content_frame, text=message, bg="#1e1e1e", fg="#ffffff",
                            font=("Segoe UI", 10), wraplength=350, justify=tk.LEFT)
        msg_label.pack(pady=(0, 20))
        
        # Button frame
        btn_frame = tk.Frame(content_frame, bg="#1e1e1e")
        btn_frame.pack()
        
        # OK Button
        ok_btn = tk.Button(btn_frame, text="OK", command=self.on_ok,
                          bg=colors.get(msg_type, "#2196F3"), fg="#ffffff",
                          font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
                          padx=30, pady=8, cursor="hand2",
                          activebackground=self._darken_color(colors.get(msg_type, "#2196F3")),
                          activeforeground="#ffffff", bd=0)
        ok_btn.pack()
        
        # Bind events
        self.bind("<Return>", lambda e: self.on_ok())
        self.bind("<Escape>", lambda e: self.on_ok())
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        ok_btn.focus_set()
    
    def _darken_color(self, hex_color):
        # Simple color darkening
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r, g, b = max(0, r-30), max(0, g-30), max(0, b-30)
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def on_ok(self):
        self.result = True
        self.destroy()

class MergeCompleteMessageBox(tk.Toplevel):
    """Message box with 'Open Folder' button for merge completion"""
    def __init__(self, parent, title, message, folder_path):
        super().__init__(parent)
        self.result = None
        self.folder_path = folder_path
        self.title(title)
        self.resizable(False, False)
        
        # Center window
        self.transient(parent)
        self.grab_set()
        
        # Main frame
        main_frame = tk.Frame(self, bg="#1e1e1e")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header with colored bar (success green)
        header = tk.Frame(main_frame, bg="#4CAF50", height=4)
        header.pack(fill=tk.X)
        
        # Content
        content_frame = tk.Frame(main_frame, bg="#1e1e1e", padx=30, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Message
        msg_label = tk.Label(content_frame, text=message, bg="#1e1e1e", fg="#ffffff",
                            font=("Segoe UI", 10), wraplength=350, justify=tk.LEFT)
        msg_label.pack(pady=(0, 20))
        
        # Button frame
        btn_frame = tk.Frame(content_frame, bg="#1e1e1e")
        btn_frame.pack()
        
        # Open Folder Button
        open_btn = tk.Button(btn_frame, text="📁 Open Folder", command=self.on_open_folder,
                            bg="#2196F3", fg="#ffffff",
                            font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
                            padx=20, pady=8, cursor="hand2",
                            activebackground="#1976D2", activeforeground="#ffffff", bd=0)
        open_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # OK Button
        ok_btn = tk.Button(btn_frame, text="OK", command=self.on_ok,
                          bg="#4CAF50", fg="#ffffff",
                          font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
                          padx=30, pady=8, cursor="hand2",
                          activebackground="#45a049", activeforeground="#ffffff", bd=0)
        ok_btn.pack(side=tk.LEFT)
        
        # Bind events
        self.bind("<Return>", lambda e: self.on_ok())
        self.bind("<Escape>", lambda e: self.on_ok())
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        ok_btn.focus_set()
    
    def on_open_folder(self):
        """Open the merged folder in file explorer"""
        try:
            if sys.platform == 'win32':
                os.startfile(self.folder_path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', self.folder_path])
            else:  # linux
                subprocess.Popen(['xdg-open', self.folder_path])
        except Exception as e:
            print(f"Failed to open folder: {e}")
    
    def on_ok(self):
        self.result = True
        self.destroy()

class ModernConfirmBox(tk.Toplevel):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        
        # Center window
        self.transient(parent)
        self.grab_set()
        
        # Main frame
        main_frame = tk.Frame(self, bg="#1e1e1e")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header with colored bar
        header = tk.Frame(main_frame, bg="#FF9800", height=4)
        header.pack(fill=tk.X)
        
        # Content
        content_frame = tk.Frame(main_frame, bg="#1e1e1e", padx=30, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Message
        msg_label = tk.Label(content_frame, text=message, bg="#1e1e1e", fg="#ffffff",
                            font=("Segoe UI", 10), wraplength=350, justify=tk.LEFT)
        msg_label.pack(pady=(0, 20))
        
        # Button frame
        btn_frame = tk.Frame(content_frame, bg="#1e1e1e")
        btn_frame.pack()
        
        # Yes Button
        yes_btn = tk.Button(btn_frame, text="Yes", command=self.on_yes,
                           bg="#4CAF50", fg="#ffffff",
                           font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
                           padx=25, pady=8, cursor="hand2",
                           activebackground="#45a049", activeforeground="#ffffff", bd=0)
        yes_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # No Button
        no_btn = tk.Button(btn_frame, text="No", command=self.on_no,
                          bg="#555555", fg="#ffffff",
                          font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
                          padx=25, pady=8, cursor="hand2",
                          activebackground="#444444", activeforeground="#ffffff", bd=0)
        no_btn.pack(side=tk.LEFT)
        
        # Bind events
        self.bind("<Return>", lambda e: self.on_yes())
        self.bind("<Escape>", lambda e: self.on_no())
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        yes_btn.focus_set()
    
    def on_yes(self):
        self.result = True
        self.destroy()
    
    def on_no(self):
        self.result = False
        self.destroy()

class ModManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Avatar: The Game Mod Manager | Made By: Jasper_Zebra | Version 1.0")
        self.root.geometry("1600x1000")
        
        # Modern dark theme colors
        self.bg_dark = "#1e1e1e"
        self.bg_medium = "#2d2d2d"
        self.bg_light = "#3d3d3d"
        self.accent_blue = "#0d7377"
        self.accent_hover = "#14a085"
        self.text_color = "#ffffff"
        self.text_secondary = "#b0b0b0"
        
        self.root.configure(bg=self.bg_dark)
        
        # Configuration
        self.config_file = "mod_manager_config.json"
        self.pak_tool_path = "Avatar_Dunia_PAK_archive_tool.exe"
        
        # Handle both frozen (exe) and unfrozen (script) execution
        if getattr(sys, 'frozen', False):
            self.script_dir = os.path.dirname(sys.executable)
        else:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Create merged folder if it doesn't exist
        self.merged_folder = os.path.join(self.script_dir, "merged")
        os.makedirs(self.merged_folder, exist_ok=True)
        
        self.output_path = os.path.join(self.merged_folder, "patch.pak")
        self.backup_path = "patch.pak.backup"
        self.mods = []
        self.mod_enabled = {}
        self.temp_dir = None
        self.pak_contents_cache = {}  # ADD THIS - Cache PAK file contents
        
        self.load_config()
        self.setup_styles()
        self.create_ui()
        self.setup_tooltips()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure(".", background=self.bg_dark, foreground=self.text_color,
                    fieldbackground=self.bg_medium, borderwidth=0)
        
        style.configure("TFrame", background=self.bg_dark)
        style.configure("TLabel", background=self.bg_dark, foreground=self.text_color,
                    font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 12, "bold"),
                    foreground=self.accent_blue)
        style.configure("TEntry", fieldbackground=self.bg_medium, foreground=self.text_color,
                    borderwidth=1, relief=tk.FLAT)
        style.map("TEntry", fieldbackground=[("focus", self.bg_light)])
        
        # Modern button style
        style.configure("Accent.TButton", background=self.accent_blue, foreground=self.text_color,
                    borderwidth=0, focuscolor=self.accent_blue, font=("Segoe UI", 10, "bold"),
                    padding=(20, 10))
        style.map("Accent.TButton",
                background=[("active", self.accent_hover), ("pressed", self.accent_blue)])
        
        style.configure("TButton", background=self.bg_light, foreground=self.text_color,
                    borderwidth=0, font=("Segoe UI", 9), padding=(15, 8))
        style.map("TButton",
                background=[("active", self.bg_medium)])
        
        style.configure("TLabelframe", background=self.bg_dark, foreground=self.text_color,
                    borderwidth=1, relief=tk.FLAT)
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"),
                    foreground=self.text_secondary)
        
        # Treeview styles
        style.configure("Treeview",
                    background=self.bg_medium,
                    foreground=self.text_color,
                    fieldbackground=self.bg_medium,
                    borderwidth=0,
                    relief=tk.FLAT,
                    font=("Segoe UI", 9),
                    rowheight=25)  # ADD THIS - Make rows taller for checkboxes
        style.configure("Treeview.Heading",
                    background=self.bg_light,
                    foreground=self.text_color,
                    borderwidth=0,
                    relief=tk.FLAT,
                    font=("Segoe UI", 9, "bold"))
        style.map("Treeview",
                background=[("selected", self.accent_blue)],
                foreground=[("selected", self.text_color)])
        style.map("Treeview.Heading",
                background=[("active", self.bg_medium)])
            
    def create_ui(self):
        # Main container with padding
        main_container = tk.Frame(self.root, bg=self.bg_dark)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_frame = tk.Frame(main_container, bg=self.bg_dark)
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        title = ttk.Label(title_frame, text="🎮 Avatar Mod Manager", style="Title.TLabel")
        title.pack(side=tk.LEFT)
        
        subtitle = ttk.Label(title_frame, text="Merge multiple patch.pak mods with load order",
                            font=("Segoe UI", 9), foreground=self.text_secondary)
        subtitle.pack(side=tk.LEFT, padx=(15, 0))
        
        # Main content - split into left (list) and right (details)
        content_paned = tk.PanedWindow(main_container, orient=tk.HORIZONTAL, 
                                    bg=self.bg_dark, sashwidth=5, 
                                    sashrelief=tk.FLAT, bd=0)
        content_paned.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # LEFT SIDE - Mod List
        left_frame = tk.Frame(content_paned, bg=self.bg_dark)
        content_paned.add(left_frame, width=900)
        
        list_frame = self.create_section_frame(left_frame, "Load Order (Top = Highest Priority)")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create Treeview
        tree_container = tk.Frame(list_frame, bg=self.bg_medium)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(10, 10))
        
        # Scrollbars
        vsb = tk.Scrollbar(tree_container, orient="vertical", bg=self.bg_medium, 
                        troughcolor=self.bg_dark, activebackground=self.accent_blue)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = tk.Scrollbar(tree_container, orient="horizontal", bg=self.bg_medium,
                        troughcolor=self.bg_dark, activebackground=self.accent_blue)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview for mod list with columns
        self.mod_listbox = ttk.Treeview(tree_container, 
                                        columns=("enabled", "priority", "name", "type", "size", "modified"),
                                        show="headings",
                                        yscrollcommand=vsb.set,
                                        xscrollcommand=hsb.set,
                                        selectmode="browse",
                                        height=15)
        
        # Configure columns
        self.mod_listbox.heading("enabled", text="✓", anchor=tk.CENTER)
        self.mod_listbox.heading("priority", text="#", anchor=tk.W)
        self.mod_listbox.heading("name", text="Mod Name", anchor=tk.W)
        self.mod_listbox.heading("type", text="Type", anchor=tk.W)
        self.mod_listbox.heading("size", text="Size", anchor=tk.W)
        self.mod_listbox.heading("modified", text="Date Modified", anchor=tk.W)
        
        self.mod_listbox.column("enabled", width=50, minwidth=50, stretch=False, anchor=tk.CENTER)
        self.mod_listbox.column("priority", width=50, minwidth=50, stretch=False)
        self.mod_listbox.column("name", width=350, minwidth=250, stretch=True)
        self.mod_listbox.column("type", width=120, minwidth=100, stretch=False)
        self.mod_listbox.column("size", width=120, minwidth=100, stretch=False)
        self.mod_listbox.column("modified", width=180, minwidth=150, stretch=False)
        
        self.mod_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self.mod_listbox.yview)
        hsb.config(command=self.mod_listbox.xview)

        # Bind events for drag & drop and toggle
        self.mod_listbox.bind('<Button-1>', self.on_treeview_click)
        self.mod_listbox.bind('<ButtonRelease-1>', self.on_drag_release)
        self.mod_listbox.bind('<B1-Motion>', self.on_drag_motion)
        self.mod_listbox.bind('<<TreeviewSelect>>', self.on_mod_select)
        
        # Store drag state
        self.drag_data = {"item": None, "y": 0}
        
        # List Control Buttons
        list_btn_frame = tk.Frame(list_frame, bg=self.bg_dark)
        list_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        self.add_btn = ttk.Button(list_btn_frame, text="➕ Add Mod", command=self.add_mod)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.remove_btn = ttk.Button(list_btn_frame, text="🗑️ Remove", command=self.remove_mod)
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.move_up_btn = ttk.Button(list_btn_frame, text="⬆️ Move Up", command=self.move_up)
        self.move_up_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.move_down_btn = ttk.Button(list_btn_frame, text="⬇️ Move Down", command=self.move_down)
        self.move_down_btn.pack(side=tk.LEFT)
        
        # RIGHT SIDE - Details Panel with Notebook (tabs)
        right_frame = tk.Frame(content_paned, bg=self.bg_dark)
        content_paned.add(right_frame, width=350)
        
        details_frame = self.create_section_frame(right_frame, "Mod Details")
        details_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(details_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Tab 1: Info
        info_tab = tk.Frame(notebook, bg=self.bg_medium)
        notebook.add(info_tab, text="Info")
        
        # Details text widget with scrollbar
        details_scroll = tk.Scrollbar(info_tab, bg=self.bg_medium)
        details_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.details_text = tk.Text(info_tab, bg=self.bg_medium, fg=self.text_color,
                                font=("Segoe UI", 9), wrap=tk.WORD,
                                yscrollcommand=details_scroll.set, relief=tk.FLAT,
                                highlightthickness=0, padx=10, pady=10,
                                state=tk.DISABLED)
        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        details_scroll.config(command=self.details_text.yview)
        
        # Configure text tags for styling
        self.details_text.tag_configure("heading", font=("Segoe UI", 10, "bold"), 
                                    foreground=self.accent_blue)
        self.details_text.tag_configure("label", font=("Segoe UI", 9, "bold"), 
                                    foreground=self.text_secondary)
        self.details_text.tag_configure("value", font=("Segoe UI", 9))
        self.details_text.tag_configure("warning", foreground="#FF9800")
        
        # Tab 2: File Tree
        tree_tab = tk.Frame(notebook, bg=self.bg_medium)
        notebook.add(tree_tab, text="Files")

        # Search bar for file tree
        search_frame = tk.Frame(tree_tab, bg=self.bg_medium)
        search_frame.pack(fill=tk.X, padx=10, pady=10)

        search_label = tk.Label(search_frame, text="🔍 Search:", bg=self.bg_medium, 
                            fg=self.text_color, font=("Segoe UI", 9))
        search_label.pack(side=tk.LEFT, padx=(0, 5))

        self.file_search_var = tk.StringVar()
        self.file_search_var.trace('w', lambda *args: self.filter_file_tree())

        search_entry = tk.Entry(search_frame, textvariable=self.file_search_var,
                            bg=self.bg_light, fg=self.text_color,
                            font=("Segoe UI", 9), relief=tk.FLAT,
                            insertbackground=self.text_color)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        clear_btn = tk.Button(search_frame, text="✖", command=lambda: self.file_search_var.set(""),
                            bg=self.bg_light, fg=self.text_secondary,
                            font=("Segoe UI", 8), relief=tk.FLAT, padx=5,
                            cursor="hand2", activebackground=self.bg_medium)
        clear_btn.pack(side=tk.LEFT)

        # Expand/Collapse buttons frame
        expand_frame = tk.Frame(tree_tab, bg=self.bg_medium)
        expand_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        expand_all_btn = tk.Button(expand_frame, text="➕ Expand All", 
                                command=self.expand_all_tree,
                                bg=self.bg_light, fg=self.text_color,
                                font=("Segoe UI", 8), relief=tk.FLAT, padx=10, pady=4,
                                cursor="hand2", activebackground=self.bg_medium)
        expand_all_btn.pack(side=tk.LEFT, padx=(0, 5))

        collapse_all_btn = tk.Button(expand_frame, text="➖ Collapse All", 
                                    command=self.collapse_all_tree,
                                    bg=self.bg_light, fg=self.text_color,
                                    font=("Segoe UI", 8), relief=tk.FLAT, padx=10, pady=4,
                                    cursor="hand2", activebackground=self.bg_medium)
        collapse_all_btn.pack(side=tk.LEFT)

        # File count label
        self.file_count_label = tk.Label(tree_tab, text="", bg=self.bg_medium,
                                        fg=self.text_secondary, font=("Segoe UI", 8),
                                        anchor=tk.W)
        self.file_count_label.pack(fill=tk.X, padx=10, pady=(5, 5))

        # File tree with scrollbars
        tree_container = tk.Frame(tree_tab, bg=self.bg_medium)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        tree_vsb = tk.Scrollbar(tree_container, orient="vertical", bg=self.bg_medium,
                            troughcolor=self.bg_dark, activebackground=self.accent_blue)
        tree_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        tree_hsb = tk.Scrollbar(tree_container, orient="horizontal", bg=self.bg_medium,
                            troughcolor=self.bg_dark, activebackground=self.accent_blue)
        tree_hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self.file_tree = ttk.Treeview(tree_container,
                                    columns=("size",),
                                    yscrollcommand=tree_vsb.set,
                                    xscrollcommand=tree_hsb.set,
                                    selectmode="browse")

        self.file_tree.heading("#0", text="File Path", anchor=tk.W)
        self.file_tree.heading("size", text="Size", anchor=tk.W)

        self.file_tree.column("#0", width=250, minwidth=150, stretch=True)
        self.file_tree.column("size", width=80, minwidth=60, stretch=False)

        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_vsb.config(command=self.file_tree.yview)
        tree_hsb.config(command=self.file_tree.xview)

        # Action Buttons
        action_frame = tk.Frame(main_container, bg=self.bg_dark)
        action_frame.pack(fill=tk.X, pady=(0, 10))

        self.merge_btn = ttk.Button(action_frame, text="🚀 Merge Mods", command=self.merge_mods,
                style="Accent.TButton")
        self.merge_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.save_btn = ttk.Button(action_frame, text="💾 Save Load Order", command=self.save_config)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.backup_btn = ttk.Button(action_frame, text="📦 Backup Original", command=self.backup_original)
        self.backup_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.restore_btn = ttk.Button(action_frame, text="🔄 Restore Backup", command=self.restore_backup)
        self.restore_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.cleanup_btn = ttk.Button(action_frame, text="🧹 Clean Temp Files", command=self.cleanup_temp)
        self.cleanup_btn.pack(side=tk.LEFT)
        
        # Status Bar
        status_frame = tk.Frame(main_container, bg=self.bg_medium, height=40)
        status_frame.pack(fill=tk.X)
        status_frame.pack_propagate(False)

        # Use Entry widget instead of Label for copyable text
        self.status_var = tk.StringVar(value="Ready")
        status_entry = tk.Entry(status_frame, textvariable=self.status_var,
                            bg=self.bg_medium, fg=self.text_secondary,
                            font=("Segoe UI", 9), relief=tk.FLAT,
                            bd=0, readonlybackground=self.bg_medium,
                            state='readonly', disabledforeground=self.text_secondary,
                            disabledbackground=self.bg_medium,
                            insertbackground=self.bg_medium,
                            highlightthickness=0)
        status_entry.pack(fill=tk.BOTH, expand=True, padx=15)

        self.refresh_listbox()
        self.update_details_panel()

    def expand_all_tree(self):
        """Expand all nodes in the file tree"""
        def expand_recursive(item):
            self.file_tree.item(item, open=True)
            children = self.file_tree.get_children(item)
            for child in children:
                expand_recursive(child)
        
        # Expand all top-level items
        for item in self.file_tree.get_children():
            expand_recursive(item)
        
        self.status_var.set("✓ Expanded all folders")

    def collapse_all_tree(self):
        """Collapse all nodes in the file tree"""
        def collapse_recursive(item):
            children = self.file_tree.get_children(item)
            for child in children:
                collapse_recursive(child)
            self.file_tree.item(item, open=False)
        
        # Collapse all top-level items
        for item in self.file_tree.get_children():
            collapse_recursive(item)
        
        self.status_var.set("✓ Collapsed all folders")

    def setup_tooltips(self):
        """Setup tooltips for all buttons"""
        self.create_tooltip(self.add_btn, "Add a new mod to the load order")
        self.create_tooltip(self.remove_btn, "Remove the selected mod from the list")
        self.create_tooltip(self.move_up_btn, "Move selected mod up (higher priority)")
        self.create_tooltip(self.move_down_btn, "Move selected mod down (lower priority)")
        self.create_tooltip(self.merge_btn, "Merge all enabled mods into a single patch.pak")
        self.create_tooltip(self.save_btn, "Save the current load order to config file")
        self.create_tooltip(self.backup_btn, "Create a backup of the original patch.pak")
        self.create_tooltip(self.restore_btn, "Restore patch.pak from backup")

    def create_tooltip(self, widget, text):
        """Create a tooltip for a widget"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(tooltip, text=text, background="#323232", 
                            foreground="#ffffff", relief=tk.SOLID, 
                            borderwidth=1, font=("Segoe UI", 9), 
                            padx=8, pady=4)
            label.pack()
            
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)

    def cleanup_temp(self):
        """Manually clean up temporary extraction files"""
        # Handle both frozen (exe) and unfrozen (script) execution
        if getattr(sys, 'frozen', False):
            script_dir = os.path.dirname(sys.executable)
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        
        temp_dir = os.path.join(script_dir, "temp_merge")
        viewing_dir = os.path.join(script_dir, "mod_viewing")
        
        has_temp = os.path.exists(temp_dir)
        has_viewing = os.path.exists(viewing_dir)
        
        if not has_temp and not has_viewing:
            ModernMessageBox(self.root, "No Temp Files",
                        "No temporary files found to clean up.", "info")
            return
        
        message = "This will delete:\n"
        if has_temp:
            message += "• Merge temporary files\n"
        if has_viewing:
            message += "• Extracted mod viewing files\n"
        message += "\nYou'll need to add mods again or run 'Merge Mods' to re-extract.\n\nContinue?"
        
        confirm = ModernConfirmBox(self.root, "Clean Temp Files", message)
        confirm.wait_window()
        
        if not confirm.result:
            return
        
        try:
            if has_temp:
                shutil.rmtree(temp_dir)
            if has_viewing:
                shutil.rmtree(viewing_dir)
            
            self.pak_contents_cache.clear()
            self.clear_file_tree()
            self.status_var.set("✓ Temporary files cleaned up")
            ModernMessageBox(self.root, "Cleanup Complete",
                        "Temporary files have been deleted successfully.", "success")
        except Exception as e:
            ModernMessageBox(self.root, "Cleanup Failed",
                        f"Failed to clean up temporary files:\n\n{str(e)}", "error")
        
    def on_treeview_click(self, event):
        """Handle clicks on treeview - for checkbox toggle and drag start"""
        region = self.mod_listbox.identify_region(event.x, event.y)
        
        if region == "cell":
            column = self.mod_listbox.identify_column(event.x)
            item = self.mod_listbox.identify_row(event.y)
            
            if item:
                # If clicked on enabled column (checkbox)
                if column == "#1":  # First column is enabled
                    self.toggle_mod(item)
                else:
                    # Start drag
                    self.drag_data["item"] = item
                    self.drag_data["y"] = event.y

    def on_drag_motion(self, event):
        """Handle drag motion"""
        if self.drag_data["item"]:
            # Could add visual feedback here if desired
            pass

    def on_drag_release(self, event):
        """Handle drag release - reorder mods"""
        if self.drag_data["item"]:
            target_item = self.mod_listbox.identify_row(event.y)
            source_item = self.drag_data["item"]
            
            if target_item and source_item != target_item:
                source_idx = int(source_item)
                target_idx = int(target_item)
                
                # Reorder mods list
                mod = self.mods.pop(source_idx)
                self.mods.insert(target_idx, mod)
                
                self.refresh_listbox()
                self.mod_listbox.selection_set(str(target_idx))
                self.mod_listbox.see(str(target_idx))
                self.update_details_panel()
            
            # Reset drag data
            self.drag_data["item"] = None

    def toggle_mod(self, item):
        """Toggle mod enabled/disabled state"""
        idx = int(item)
        mod_path = self.mods[idx]
        
        # Toggle state
        current_state = self.mod_enabled.get(mod_path, True)
        self.mod_enabled[mod_path] = not current_state
        
        self.refresh_listbox()
        self.status_var.set(f"{'Enabled' if not current_state else 'Disabled'}: {os.path.basename(mod_path)}")

    def on_mod_select(self, event):
        """Handle mod selection - update details panel"""
        self.update_details_panel()

    def get_viewing_dir_for_mod(self, mod_path):
        """Get the extraction directory for viewing a specific mod"""
        # Handle both frozen (exe) and unfrozen (script) execution
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            script_dir = os.path.dirname(sys.executable)
        else:
            # Running as script
            script_dir = os.path.dirname(os.path.abspath(__file__))
        
        viewing_dir = os.path.join(script_dir, "mod_viewing")
        
        # Find the index of this mod in the list
        try:
            mod_idx = self.mods.index(mod_path)
            folder_name = f"mod{mod_idx + 1}"
        except ValueError:
            # If mod not in list anymore, return None
            return None
        
        return os.path.join(viewing_dir, folder_name)

    def unpack_mod_for_viewing(self, mod_path):
        """Unpack a mod for viewing in the file tree (in background thread)"""
        if not os.path.exists(mod_path):
            return
        
        if not os.path.exists(self.pak_tool_path):
            return
        
        viewing_dir = self.get_viewing_dir_for_mod(mod_path)
        
        # If already extracted, skip
        if os.path.exists(viewing_dir):
            return
        
        # Show status
        self.status_var.set(f"Extracting {os.path.basename(mod_path)} for viewing...")
        
        # Run extraction in thread
        thread = threading.Thread(target=self._unpack_for_viewing_worker,
                                args=(mod_path, viewing_dir), daemon=True)
        thread.start()

    def _unpack_for_viewing_worker(self, mod_path, viewing_dir):
        """Worker thread to unpack mod for viewing"""
        import time
        
        try:
            # Create viewing directory
            os.makedirs(viewing_dir, exist_ok=True)
            
            # Create marker file to track which mod this folder belongs to
            marker_file = os.path.join(viewing_dir, ".mod_source")
            with open(marker_file, 'w') as f:
                f.write(mod_path)
            
            # Unpack
            cmd = [self.pak_tool_path, mod_path, viewing_dir]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE)
            
            # Monitor extraction progress
            last_file_count = 0
            last_update_time = time.time()
            update_interval = 1.5  # Update every 1.5 seconds
            
            mod_name = os.path.basename(mod_path)
            
            while process.poll() is None:
                current_time = time.time()
                
                # Update every 1.5 seconds
                if current_time - last_update_time >= update_interval:
                    try:
                        if os.path.exists(viewing_dir):
                            file_count = sum(1 for _, _, files in os.walk(viewing_dir) 
                                        for _ in files if not _.startswith('.'))
                            
                            if file_count != last_file_count:
                                last_file_count = file_count
                                
                                # Update status bar
                                self.root.after(0, lambda fc=file_count, mn=mod_name: 
                                            self.status_var.set(f"Extracting {mn}... {fc} files"))
                                
                                # Check if this mod is currently selected
                                selection = self.mod_listbox.selection()
                                if selection:
                                    idx = int(selection[0])
                                    if idx < len(self.mods) and self.mods[idx] == mod_path:
                                        # Update file tree in background
                                        self.root.after(0, lambda mp=mod_path, vd=viewing_dir: 
                                                    self._update_file_tree_async(mp, vd))
                            
                            last_update_time = current_time
                    except Exception as e:
                        pass
                
                time.sleep(0.2)  # Check every 200ms
            
            # Wait for process to complete
            process.wait()
            
            if process.returncode == 0:
                # Final count
                file_count = sum(1 for _, _, files in os.walk(viewing_dir) 
                            for _ in files if not _.startswith('.'))
                
                self.root.after(0, lambda fc=file_count, mn=mod_name: 
                            self.status_var.set(f"✓ Extracted {mn} ({fc} files)"))
                
                # Clear cache
                if mod_path in self.pak_contents_cache:
                    del self.pak_contents_cache[mod_path]
                
                # Final refresh
                selection = self.mod_listbox.selection()
                if selection:
                    idx = int(selection[0])
                    if idx < len(self.mods) and self.mods[idx] == mod_path:
                        self.root.after(0, lambda mp=mod_path, vd=viewing_dir: 
                                    self._update_file_tree_async(mp, vd))
            else:
                self.root.after(0, lambda mn=mod_name: 
                            self.status_var.set(f"⚠️ Failed to extract {mn}"))
        
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda msg=error_msg: 
                        self.status_var.set(f"⚠️ Extraction error: {msg}"))
        
    def _update_file_tree_async(self, mod_path, viewing_dir):
        """Update file tree asynchronously without blocking UI"""
        # Quick check if we should update
        selection = self.mod_listbox.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        if idx >= len(self.mods) or self.mods[idx] != mod_path:
            return
        
        # Run file collection in a separate thread
        thread = threading.Thread(target=self._collect_and_update_files,
                                args=(mod_path, viewing_dir), daemon=True)
        thread.start()

    def _collect_and_update_files(self, mod_path, viewing_dir):
        """Collect files in background thread and update UI"""
        try:
            # Get top-level subdirectories
            top_level_items = []
            try:
                items = os.listdir(viewing_dir)
                for item in items:
                    if item.startswith('.'):
                        continue
                    item_path = os.path.join(viewing_dir, item)
                    if os.path.isdir(item_path):
                        top_level_items.append(item)
            except:
                return
            
            # Check if there are files in root
            root_files = []
            try:
                for item in os.listdir(viewing_dir):
                    if item.startswith('.'):
                        continue
                    item_path = os.path.join(viewing_dir, item)
                    if os.path.isfile(item_path):
                        rel_path = os.path.relpath(item_path, viewing_dir)
                        size = os.path.getsize(item_path)
                        root_files.append((rel_path, size))
            except:
                pass
            
            # Use multiprocessing for large directories
            num_workers = min(cpu_count(), max(1, len(top_level_items)), 4)
            
            if num_workers > 1 and len(top_level_items) > 1:
                # Parallel processing
                chunk_size = max(1, len(top_level_items) // num_workers)
                chunks = []
                
                for i in range(0, len(top_level_items), chunk_size):
                    chunk = top_level_items[i:i + chunk_size]
                    chunks.append((viewing_dir, chunk, viewing_dir))
                
                with Pool(processes=num_workers) as pool:
                    results = pool.map(_collect_files_chunk, chunks)
                
                file_list = root_files.copy()
                for result in results:
                    file_list.extend(result)
            else:
                # Single-threaded
                file_list = []
                for root, dirs, files in os.walk(viewing_dir):
                    for file in files:
                        if file.startswith('.'):
                            continue
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, viewing_dir)
                        try:
                            size = os.path.getsize(full_path)
                            file_list.append((rel_path, size))
                        except:
                            pass
            
            if not file_list:
                return
            
            # Update UI in main thread
            self.root.after(0, lambda fl=file_list: self._apply_file_list_to_tree(fl))
            
        except Exception as e:
            pass

    def _apply_file_list_to_tree(self, file_list):
        """Apply collected file list to tree (runs in main thread)"""
        # Check if still showing the same mod
        selection = self.mod_listbox.selection()
        if not selection:
            return
        
        self.populate_file_tree(file_list)
        
        # Update file count
        total_size = sum(size for _, size in file_list)
        size_mb = total_size / (1024 * 1024)
        
        # Check if extraction is complete
        current_status = self.status_var.get()
        if "Extracting" in current_status:
            self.file_count_label.config(text=f"{len(file_list)} files ({size_mb:.2f} MB) - Extracting...")
        else:
            self.file_count_label.config(text=f"{len(file_list)} files ({size_mb:.2f} MB)")

    def reorganize_viewing_folders(self):
        """Reorganize mod_viewing folders to match current load order"""
        # Handle both frozen (exe) and unfrozen (script) execution
        if getattr(sys, 'frozen', False):
            script_dir = os.path.dirname(sys.executable)
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        
        viewing_dir = os.path.join(script_dir, "mod_viewing")
        
        if not os.path.exists(viewing_dir):
            return
        
        # Build a map of mod_path -> current folder location
        folder_map = {}
        for i in range(1, 1000):  # Check up to mod999
            folder_path = os.path.join(viewing_dir, f"mod{i}")
            marker_file = os.path.join(folder_path, ".mod_source")  # NO .txt extension
            
            if os.path.exists(marker_file):
                try:
                    with open(marker_file, 'r') as f:
                        mod_path = f.read().strip()
                        folder_map[mod_path] = folder_path
                except:
                    pass
        
        # Step 1: Rename all to temporary names
        temp_map = {}
        for mod_path, folder_path in folder_map.items():
            temp_name = folder_path + "_temp"
            try:
                os.rename(folder_path, temp_name)
                temp_map[mod_path] = temp_name
            except Exception as e:
                print(f"Error creating temp: {e}")
        
        # Step 2: Rename to correct positions based on current mod order
        for new_idx, mod_path in enumerate(self.mods, 1):
            if mod_path in temp_map:
                temp_path = temp_map[mod_path]
                final_path = os.path.join(viewing_dir, f"mod{new_idx}")
                
                try:
                    os.rename(temp_path, final_path)
                except Exception as e:
                    print(f"Error renaming to final position: {e}")

    def update_details_panel(self):
        """Update the details panel with selected mod info"""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)
        
        selection = self.mod_listbox.selection()
        if not selection:
            self.details_text.insert(tk.END, "No mod selected\n\n", "heading")
            self.details_text.insert(tk.END, "Select a mod from the list to view details.")
            self.details_text.config(state=tk.DISABLED)
            self.clear_file_tree()
            return
        
        idx = int(selection[0])
        mod_path = self.mods[idx]
        
        # Basic info
        self.details_text.insert(tk.END, f"{os.path.basename(mod_path)}\n\n", "heading")
        
        # Status
        enabled = self.mod_enabled.get(mod_path, True)
        status_text = "✓ Enabled" if enabled else "✗ Disabled"
        status_color = "value" if enabled else "warning"
        self.details_text.insert(tk.END, "Status: ", "label")
        self.details_text.insert(tk.END, f"{status_text}\n\n", status_color)
        
        # Priority
        self.details_text.insert(tk.END, "Load Priority: ", "label")
        self.details_text.insert(tk.END, f"#{idx + 1} of {len(self.mods)}\n\n", "value")
        
        # File path
        self.details_text.insert(tk.END, "File Path:\n", "label")
        self.details_text.insert(tk.END, f"{mod_path}\n\n", "value")
        
        # File info
        if os.path.exists(mod_path):
            size_str, date_str = self.get_file_info(mod_path)
            
            self.details_text.insert(tk.END, "File Size: ", "label")
            self.details_text.insert(tk.END, f"{size_str}\n", "value")
            
            self.details_text.insert(tk.END, "Modified: ", "label")
            self.details_text.insert(tk.END, f"{date_str}\n\n", "value")
            
            # Full path details
            self.details_text.insert(tk.END, "Location:\n", "label")
            self.details_text.insert(tk.END, f"Directory: {os.path.dirname(mod_path)}\n", "value")
            self.details_text.insert(tk.END, f"Filename: {os.path.basename(mod_path)}\n", "value")
        else:
            self.details_text.insert(tk.END, "\n⚠️ Warning: File not found!\n", "warning")
            self.details_text.insert(tk.END, "This mod file no longer exists at the specified location.", "warning")
        
        self.details_text.config(state=tk.DISABLED)
        
        # Update file tree
        self.load_pak_contents(mod_path)

    def load_pak_contents(self, pak_path):
        """Load and display contents of a PAK file from extracted folders"""
        self.clear_file_tree()
        
        if not os.path.exists(pak_path):
            self.file_count_label.config(text="File not found")
            return
        
        # Check cache first
        if pak_path in self.pak_contents_cache:
            file_list = self.pak_contents_cache[pak_path]
            self.populate_file_tree(file_list)
            return
        
        # Get the viewing directory for this mod
        viewing_dir = self.get_viewing_dir_for_mod(pak_path)
        
        if viewing_dir is None:
            self.file_count_label.config(text="Mod not in list")
            return
        
        if not os.path.exists(viewing_dir):
            # Try to unpack it now
            self.file_count_label.config(text="Extracting PAK file... (check status bar)")
            self.root.update_idletasks()
            self.unpack_mod_for_viewing(pak_path)
            return  # Let the worker thread handle the updates
        
        # Check if extraction is still in progress (check for .mod_source marker)
        marker_file = os.path.join(viewing_dir, ".mod_source")
        if not os.path.exists(marker_file):
            self.file_count_label.config(text="Extraction in progress...")
            return
        
        # Collect file list from extracted directory
        self.file_count_label.config(text="Loading files...")
        self.root.update_idletasks()
        
        file_list = []
        for root, dirs, files in os.walk(viewing_dir):
            for file in files:
                if file.startswith('.'):  # Skip marker files
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, viewing_dir)
                try:
                    size = os.path.getsize(full_path)
                    file_list.append((rel_path, size))
                except:
                    pass
        
        if not file_list:
            self.file_count_label.config(text="No files found or still extracting...")
            return
        
        # Cache the results
        self.pak_contents_cache[pak_path] = file_list
        
        # Populate tree
        self.populate_file_tree(file_list)

    def populate_file_tree(self, file_list):
        """Populate the file tree with file list"""
        self.clear_file_tree()
        
        if not file_list:
            self.file_count_label.config(text="No files found")
            return
        
        # Sort by path
        file_list = sorted(file_list, key=lambda x: x[0].lower())
        
        # Build tree structure
        tree_dict = {}
        
        for file_path, size in file_list:
            parts = file_path.replace('\\', '/').split('/')
            
            current_dict = tree_dict
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # It's a file
                    current_dict[part] = ('file', size)
                else:
                    # It's a directory
                    if part not in current_dict:
                        current_dict[part] = ('dir', {})
                    current_dict = current_dict[part][1]
        
        # Insert into treeview
        self._insert_tree_items("", tree_dict)
        
        # Update count (only if not currently extracting)
        current_label = self.file_count_label.cget("text")
        if "Extracting..." not in current_label:
            total_size = sum(size for _, size in file_list)
            size_mb = total_size / (1024 * 1024)
            self.file_count_label.config(text=f"{len(file_list)} files ({size_mb:.2f} MB)")
        
        # Store for filtering
        self.current_file_list = file_list

    def _insert_tree_items(self, parent, tree_dict):
        """Recursively insert items into tree"""
        # Sort: directories first, then files
        items = sorted(tree_dict.items(), 
                    key=lambda x: (x[1][0] == 'file', x[0].lower()))
        
        for name, (item_type, data) in items:
            if item_type == 'dir':
                # Insert directory
                node = self.file_tree.insert(parent, tk.END, text=f"📁 {name}", 
                                            values=("",), open=False)
                # Recursively insert children
                self._insert_tree_items(node, data)
            else:
                # Insert file
                size = data
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.2f} MB"
                
                self.file_tree.insert(parent, tk.END, text=f"📄 {name}", 
                                    values=(size_str,))

    def clear_file_tree(self):
        """Clear the file tree"""
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        self.file_count_label.config(text="")
        self.current_file_list = []

    def filter_file_tree(self):
        """Filter file tree based on search"""
        search_term = self.file_search_var.get().lower()
        
        if not hasattr(self, 'current_file_list') or not self.current_file_list:
            return
        
        self.clear_file_tree()
        
        if not search_term:
            # Show all files
            self.populate_file_tree(self.current_file_list)
            return
        
        # Filter files
        filtered = [(path, size) for path, size in self.current_file_list 
                    if search_term in path.lower()]
        
        if not filtered:
            self.file_count_label.config(text="No matching files")
            return
        
        # Show filtered results (flat list, no tree structure)
        for file_path, size in filtered:
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.2f} MB"
            
            self.file_tree.insert("", tk.END, text=f"📄 {file_path}", 
                                values=(size_str,))
        
        total_size = sum(size for _, size in filtered)
        size_mb = total_size / (1024 * 1024)
        self.file_count_label.config(text=f"{len(filtered)} matching files ({size_mb:.2f} MB)")

    def backup_original(self):
        """Backup the original patch.pak file"""
        if not os.path.exists(self.output_path):
            ModernMessageBox(self.root, "File Not Found",
                        f"No {self.output_path} file found to backup!", "warning")
            return
        
        try:
            shutil.copy2(self.output_path, self.backup_path)
            self.status_var.set(f"✓ Backup created: {self.backup_path}")
            ModernMessageBox(self.root, "Backup Created",
                        f"Original patch.pak backed up successfully!\n\nBackup: {self.backup_path}", "success")
        except Exception as e:
            ModernMessageBox(self.root, "Backup Failed",
                        f"Failed to create backup:\n\n{str(e)}", "error")

    def restore_backup(self):
        """Restore patch.pak from backup"""
        if not os.path.exists(self.backup_path):
            ModernMessageBox(self.root, "No Backup Found",
                        f"No backup file found at {self.backup_path}", "warning")
            return
        
        # Confirm with user
        confirm = ModernConfirmBox(self.root, "Restore Backup",
                                f"This will replace the current {self.output_path} with the backup.\n\nContinue?")
        confirm.wait_window()
        
        if not confirm.result:
            return
        
        try:
            shutil.copy2(self.backup_path, self.output_path)
            self.status_var.set(f"✓ Restored from backup")
            ModernMessageBox(self.root, "Restore Complete",
                        f"patch.pak restored from backup successfully!", "success")
        except Exception as e:
            ModernMessageBox(self.root, "Restore Failed",
                        f"Failed to restore backup:\n\n{str(e)}", "error")

    def create_section_frame(self, parent, title):
        """Create a modern section frame"""
        frame = tk.Frame(parent, bg=self.bg_medium, relief=tk.FLAT)
        
        # Title bar
        title_bar = tk.Frame(frame, bg=self.bg_light, height=35)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        
        title_label = tk.Label(title_bar, text=title, bg=self.bg_light,
                              fg=self.text_color, font=("Segoe UI", 10, "bold"),
                              anchor=tk.W, padx=15)
        title_label.pack(fill=tk.BOTH, expand=True)
        
        return frame
    
    def get_file_info(self, filepath):
        """Get file information: size and modified date"""
        try:
            stat_info = os.stat(filepath)
            size_bytes = stat_info.st_size
            
            # Format size
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
            
            # Format date
            modified_time = datetime.fromtimestamp(stat_info.st_mtime)
            date_str = modified_time.strftime("%m/%d/%Y %I:%M %p")
            
            return size_str, date_str
        except Exception as e:
            return "Unknown", "Unknown"

    def add_mod(self):
        filename = filedialog.askopenfilename(
            title="Select Mod patch.pak File",
            filetypes=[("PAK Archive", "*.pak"), ("All Files", "*.*")]
        )
        if filename:
            if filename not in self.mods:
                self.mods.append(filename)
                self.mod_enabled[filename] = True
                self.refresh_listbox()
                self.status_var.set(f"Added: {os.path.basename(filename)}")
                
                # Auto-unpack the mod for viewing
                self.unpack_mod_for_viewing(filename)
            else:
                ModernMessageBox(self.root, "Duplicate Mod",
                            "This mod is already in the list!", "warning")
                        
    def remove_mod(self):
        selection = self.mod_listbox.selection()
        if selection:
            idx = int(selection[0])
            removed = self.mods.pop(idx)
            if removed in self.mod_enabled:
                del self.mod_enabled[removed]
            
            # Remove the extracted folder
            viewing_dir = self.get_viewing_dir_for_mod(removed)
            if viewing_dir and os.path.exists(viewing_dir):
                try:
                    shutil.rmtree(viewing_dir)
                except:
                    pass
            
            self.refresh_listbox()
            self.update_details_panel()
            self.status_var.set(f"Removed: {os.path.basename(removed)}")
            
            # Reorganize remaining folders
            self.reorganize_viewing_folders()
            
    def move_up(self):
        selection = self.mod_listbox.selection()
        if selection:
            idx = int(selection[0])
            if idx > 0:
                self.mods[idx], self.mods[idx-1] = self.mods[idx-1], self.mods[idx]
                self.refresh_listbox()
                self.mod_listbox.selection_set(str(idx-1))
                self.mod_listbox.see(str(idx-1))
                self.reorganize_viewing_folders()

    def move_down(self):
        selection = self.mod_listbox.selection()
        if selection:
            idx = int(selection[0])
            if idx < len(self.mods) - 1:
                self.mods[idx], self.mods[idx+1] = self.mods[idx+1], self.mods[idx]
                self.refresh_listbox()
                self.mod_listbox.selection_set(str(idx+1))
                self.mod_listbox.see(str(idx+1))
                self.reorganize_viewing_folders()

    def refresh_listbox(self):
        # Clear existing items
        for item in self.mod_listbox.get_children():
            self.mod_listbox.delete(item)
        
        # Add mods to treeview
        for i, mod in enumerate(self.mods, 1):
            filename = os.path.basename(mod)
            file_ext = os.path.splitext(filename)[1].upper()
            if file_ext:
                file_type = f"{file_ext[1:]} File"
            else:
                file_type = "File"
            
            size_str, date_str = self.get_file_info(mod)
            
            # Get enabled state
            enabled = self.mod_enabled.get(mod, True)
            enabled_symbol = "✓" if enabled else "✗"
            
            # Insert with enabled state
            self.mod_listbox.insert("", tk.END, iid=str(i-1),
                                values=(enabled_symbol, i, filename, file_type, size_str, date_str))
            
            # Change text color if disabled
            if not enabled:
                self.mod_listbox.item(str(i-1), tags=('disabled',))
        
        # Configure disabled tag
        self.mod_listbox.tag_configure('disabled', foreground=self.text_secondary)

    def merge_mods(self):
        # Filter only enabled mods
        enabled_mods = [mod for mod in self.mods if self.mod_enabled.get(mod, True)]
        
        if not enabled_mods:
            ModernMessageBox(self.root, "No Mods Enabled",
                        "Please enable at least one mod to merge!", "warning")
            return
        
        if not os.path.exists(self.pak_tool_path):
            ModernMessageBox(self.root, "Tool Not Found",
                        f"PAK tool executable not found!\n\nMake sure '{self.pak_tool_path}' is in the same folder as this program.", "error")
            return
        
        # Create and show progress dialog
        progress_dialog = EnhancedProgressDialog(self.root, "Merging Mods")
        
        # Run merge in separate thread
        thread = threading.Thread(target=self._merge_worker, 
                                args=(progress_dialog, enabled_mods), daemon=True)
        thread.start()

    def _merge_worker(self, progress_dialog, enabled_mods):
        """Worker thread for merging mods - now takes enabled_mods parameter"""
        try:
            progress_dialog.append_log("🚀 Starting merge process, please wait.")
            progress_dialog.set_status("Preparing, please wait.")
            progress_dialog.set_progress(0)
            
            # Create temporary directory in the program's root directory
            # Handle both frozen (exe) and unfrozen (script) execution
            if getattr(sys, 'frozen', False):
                script_dir = os.path.dirname(sys.executable)
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            
            self.temp_dir = os.path.join(script_dir, "temp_merge")
            viewing_dir = os.path.join(script_dir, "mod_viewing")
            
            # Remove old temp directory if it exists
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            
            os.makedirs(self.temp_dir, exist_ok=True)
            merge_dir = os.path.join(self.temp_dir, "merge")
            os.makedirs(merge_dir, exist_ok=True)
            
            progress_dialog.append_log(f"📁 Created temporary directory: {self.temp_dir}")
            progress_dialog.append_log(f"ℹ️  Merging {len(enabled_mods)} enabled mods (skipping {len(self.mods) - len(enabled_mods)} disabled)")
            
            total_mods = len(enabled_mods)
            files_copied = 0
            total_files = 0
            
            # Copy from mod_viewing folders (reverse order, so lowest priority first)
            for i, mod_path in enumerate(reversed(enabled_mods), 1):
                if progress_dialog.was_cancelled:
                    progress_dialog.append_log("⚠️ Merge cancelled by user")
                    self.root.after(0, lambda: self._cleanup_and_close(progress_dialog, cancelled=True))
                    return
                
                mod_name = os.path.basename(mod_path)
                progress = (i - 1) / (total_mods + 1) * 100
                
                # Find the mod's index in the full mod list to get correct folder name
                try:
                    mod_idx = self.mods.index(mod_path)
                    source_folder = os.path.join(viewing_dir, f"mod{mod_idx + 1}")
                except ValueError:
                    progress_dialog.append_log(f"⚠️ Skipping {mod_name} - not found in mod list")
                    continue
                
                # Check if the viewing folder exists
                if not os.path.exists(source_folder):
                    progress_dialog.append_log(f"⚠️ [{i}/{total_mods}] {mod_name} not extracted yet - skipping")
                    progress_dialog.append_log(f"   💡 Tip: View this mod in the 'Files' tab first to extract it")
                    continue
                
                progress_dialog.set_status(f"Copying mod {i}/{total_mods}: {mod_name}, please wait.")
                progress_dialog.set_progress(progress)
                progress_dialog.append_log(f"\n📋 [{i}/{total_mods}] Copying: {mod_name}")
                
                # Count files in the source folder
                mod_files = sum(1 for _, _, files in os.walk(source_folder) for _ in files)
                total_files += mod_files
                progress_dialog.append_log(f"   ℹ️  Found {mod_files} files in {os.path.basename(source_folder)}")
                
                # Copy files to merged directory
                new_files = self.copy_tree_tracked(source_folder, merge_dir, progress_dialog)
                files_copied += new_files
                progress_dialog.append_log(f"   ✓ Copied {new_files} files to merge folder")
            
            if progress_dialog.was_cancelled:
                progress_dialog.append_log("⚠️ Merge cancelled by user")
                self.root.after(0, lambda: self._cleanup_and_close(progress_dialog, cancelled=True))
                return
            
            # Check if any files were actually copied
            if files_copied == 0:
                raise Exception("No mod files were copied! Make sure to view your mods in the 'Files' tab first to extract them.")
            
            # Pack the merged directory
            progress_dialog.set_status("Creating final patch.pak, please wait.")
            progress_dialog.set_progress(90)
            progress_dialog.append_log(f"\n📦 Packing merged files into {self.output_path}...")
            
            try:
                self.pack_pak(merge_dir, self.output_path, progress_dialog)
            except Exception as e:
                raise Exception(f"Failed to create patch.pak: {str(e)}")
            
            progress_dialog.append_log(f"   ✓ Created {self.output_path}")
            
            # Clear cache so it will reload from disk
            self.pak_contents_cache.clear()
            
            # Success
            progress_dialog.set_status("Complete!")
            progress_dialog.set_progress(100)
            progress_dialog.append_log(f"\n✅ SUCCESS! Merged {total_mods} mods with {files_copied} total files")
            progress_dialog.append_log(f"📄 Output: {self.output_path}")
            
            # Update main window status
            self.root.after(0, lambda: self.status_var.set(f"✅ Success! Merged patch.pak created"))
            
            # Mark complete and show success message
            progress_dialog.mark_complete()
            self.root.after(0, lambda: MergeCompleteMessageBox(self.root, "Success",
                        f"Merged patch.pak created successfully!\n\n{total_mods} mods merged\n{files_copied} files processed\n\nFile: {self.output_path}", 
                        self.merged_folder))
            
        except Exception as e:
            error_msg = str(e)
            progress_dialog.append_log(f"\n❌ ERROR: {error_msg}")
            progress_dialog.set_status("Error occurred")
            progress_dialog.mark_complete()
            
            self.root.after(0, lambda: self.status_var.set("❌ Error occurred during merge"))
            self.root.after(0, lambda msg=error_msg: ModernMessageBox(self.root, "Error",
                        f"An error occurred:\n\n{msg}", "error"))
            
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def _cleanup_and_close(self, progress_dialog, cancelled=False):
        """Cleanup after cancellation"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
        
        if cancelled:
            self.status_var.set("⚠️ Merge cancelled")
        
        progress_dialog.mark_complete()
    
    def copy_tree_tracked(self, src, dst, progress_dialog=None, _accumulated_count=0):
        """Recursively copy files with tracking for progress dialog"""
        files_copied = 0
        
        for item in os.listdir(src):
            src_path = os.path.join(src, item)
            dst_path = os.path.join(dst, item)
            
            if os.path.isdir(src_path):
                os.makedirs(dst_path, exist_ok=True)
                files_copied += self.copy_tree_tracked(src_path, dst_path, progress_dialog, _accumulated_count + files_copied)
            else:
                shutil.copy2(src_path, dst_path)
                files_copied += 1
                
                # Calculate total files copied so far
                total_copied = _accumulated_count + files_copied
                
                # Log every 500 files
                if progress_dialog and total_copied % 500 == 0:
                    progress_dialog.append_log(f"      Copying {total_copied} files merge folder.")
        
        return files_copied

    def unpack_pak(self, pak_path, output_dir, progress_dialog=None):
        import time
        import os
        
        cmd = [self.pak_tool_path, pak_path, output_dir]
        
        if progress_dialog:
            progress_dialog.append_log(f"      Unpacking: {os.path.basename(pak_path)}")
            progress_dialog.append_log(f"      Destination: {output_dir}")
        
        process = subprocess.Popen(cmd)
        
        # Monitor the output directory
        last_file_count = 0
        check_interval = 0.10
        min_file_increment = 99  # Log every 500 files
        
        while process.poll() is None:
            try:
                if os.path.exists(output_dir):
                    file_count = sum(1 for _, _, files in os.walk(output_dir) for _ in files)
                    
                    # Only log if file count increased by at least min_file_increment
                    if file_count >= last_file_count + min_file_increment:
                        # Calculate total size
                        total_size = 0
                        for dirpath, dirnames, filenames in os.walk(output_dir):
                            for filename in filenames:
                                filepath = os.path.join(dirpath, filename)
                                try:
                                    total_size += os.path.getsize(filepath)
                                except:
                                    pass
                        
                        size_mb = total_size / (1024 * 1024)
                        if progress_dialog:
                            progress_dialog.append_log(f"      Unpacking files: {file_count} / {size_mb:.2f} MB")
                        last_file_count = file_count
            except Exception as e:
                pass
            
            time.sleep(check_interval)
        
        # Final count
        if os.path.exists(output_dir) and progress_dialog:
            file_count = sum(1 for _, _, files in os.walk(output_dir) for _ in files)
            total_size = sum(os.path.getsize(os.path.join(dirpath, filename)) 
                            for dirpath, dirnames, filenames in os.walk(output_dir) 
                            for filename in filenames)
            size_mb = total_size / (1024 * 1024)
            progress_dialog.append_log(f"      ✅ Unpacked {file_count}/{file_count} ... {size_mb:.2f} MB")
        
        return_code = process.wait()
        
        if return_code != 0:
            raise Exception(f"Failed to unpack {pak_path}")

    def pack_pak(self, source_dir, output_pak, progress_dialog=None):
        import time
        import os
        
        cmd = [self.pak_tool_path, source_dir, output_pak, "-c"]
        
        if progress_dialog:
            progress_dialog.append_log(f"   Packing: {os.path.basename(output_pak)}")
            
            # Count source files
            if os.path.exists(source_dir):
                source_file_count = sum(1 for _, _, files in os.walk(source_dir) for _ in files)
                source_size = sum(os.path.getsize(os.path.join(dirpath, filename)) 
                                for dirpath, dirnames, filenames in os.walk(source_dir) 
                                for filename in filenames)
                source_size_mb = source_size / (1024 * 1024)
                progress_dialog.append_log(f"   Source: {source_file_count} files ({source_size_mb:.2f} MB)")
        
        process = subprocess.Popen(cmd)
        
        # Monitor the output file
        last_pak_size = 0
        last_logged_mb = 0
        check_interval = 0.10
        size_increment_mb = 10  # Log every 50 MB instead of 5 MB
        
        while process.poll() is None:
            try:
                if os.path.exists(output_pak):
                    pak_size = os.path.getsize(output_pak)
                    size_mb = pak_size / (1024 * 1024)
                    
                    # Log every 50 MB increment
                    if size_mb >= last_logged_mb + size_increment_mb:
                        if progress_dialog:
                            progress_dialog.append_log(f"   {size_mb:.2f} MB of files repacked.")
                        last_logged_mb = size_mb
            except Exception as e:
                pass
            
            time.sleep(check_interval)
        
        # Final size and file count
        if os.path.exists(output_pak) and progress_dialog:
            pak_size = os.path.getsize(output_pak)
            size_mb = pak_size / (1024 * 1024)
            
            # Count files that were packed (from source)
            file_count = sum(1 for _, _, files in os.walk(source_dir) for _ in files)
            
            progress_dialog.append_log(f"   ✅ Created {os.path.basename(output_pak)}")
            progress_dialog.append_log(f"   Packed {file_count} files → {size_mb:.2f} MB")
        
        return_code = process.wait()
        
        if return_code != 0:
            raise Exception(f"Failed to pack {output_pak}")
    
    def save_config(self):
        config = {
            "mods": self.mods,
            "mod_enabled": self.mod_enabled  # ADD THIS - Save enabled state
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
        self.status_var.set("💾 Configuration saved")
        ModernMessageBox(self.root, "Saved",
                    "Load order saved successfully!", "success")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                self.mods = config.get("mods", [])
                self.mod_enabled = config.get("mod_enabled", {})
                
                # Ensure all mods have an enabled state
                for mod in self.mods:
                    if mod not in self.mod_enabled:
                        self.mod_enabled[mod] = True
                
                # Auto-extract mods that haven't been extracted yet
                self.root.after(1000, self.auto_extract_mods)
            except Exception as e:
                print(f"Failed to load config: {e}")

    def auto_extract_mods(self):
        """Auto-extract all mods that haven't been extracted yet"""
        for mod_path in self.mods:
            if os.path.exists(mod_path):
                viewing_dir = self.get_viewing_dir_for_mod(mod_path)
                if not os.path.exists(viewing_dir):
                    self.unpack_mod_for_viewing(mod_path)

if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for Windows
    root = tk.Tk()
    app = ModManager(root)
    root.mainloop()