import customtkinter as ctk
import subprocess
import os
import json
from tkinter import filedialog, messagebox


class QuickAppGroup2(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="#0d0d0d", corner_radius=0)

        self.groups = self.get_default_groups()
        self.current_group = list(self.groups.keys())[0]

        self.build_ui()
        self.show_group(self.current_group)

    # =========================================================
    # Default Groups (Folders)
    # =========================================================

    def get_default_groups(self):
        return {
            "Development": [
                {"name": "VS Code", "path": "code", "icon": "💻"},
                {"name": "Terminal", "path": "wt", "icon": "⬛"},
                {"name": "GitHub Desktop", "path": "github", "icon": "🐙"},
                {"name": "Postman", "path": "postman", "icon": "🚀"},
                {"name": "Docker", "path": "docker", "icon": "🐳"},
                {"name": "Notepad++", "path": "notepad++", "icon": "📝"},
            ],
            "Browsers": [
                {"name": "Chrome", "path": "chrome", "icon": "🌐"},
                {"name": "Edge", "path": "msedge", "icon": "🔷"},
                {"name": "Firefox", "path": "firefox", "icon": "🦊"},
                {"name": "Brave", "path": "brave", "icon": "🦁"},
            ],
            "System": [
                {"name": "File Explorer", "path": "explorer", "icon": "📁"},
                {"name": "Notepad", "path": "notepad", "icon": "📄"},
                {"name": "Calculator", "path": "calc", "icon": "🧮"},
                {"name": "Task Manager", "path": "taskmgr", "icon": "📊"},
                {"name": "Settings", "path": "ms-settings:", "icon": "⚙️"},
            ],
            "Media": [
                {"name": "Spotify", "path": "spotify", "icon": "🎵"},
                {"name": "VLC", "path": "vlc", "icon": "🎬"},
                {"name": "Photos", "path": "ms-photos:", "icon": "🖼️"},
            ],
            "Office": [
                {"name": "Word", "path": "winword", "icon": "📘"},
                {"name": "Excel", "path": "excel", "icon": "📗"},
                {"name": "PowerPoint", "path": "powerpnt", "icon": "📙"},
                {"name": "OneNote", "path": "onenote", "icon": "📓"},
            ],
            "Utilities": [
                {"name": "Paint", "path": "mspaint", "icon": "🎨"},
                {"name": "Snipping Tool", "path": "snippingtool", "icon": "✂️"},
                {"name": "Command Prompt", "path": "cmd", "icon": "⌨️"},
                {"name": "Control Panel", "path": "control", "icon": "🛠️"},
            ]
        }

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        title = ctk.CTkLabel(
            header,
            text="Quick App Groups",
            font=("Consolas", 26, "bold")
        )
        title.pack(side="left")

        self.group_summary = ctk.CTkLabel(
            header,
            text="",
            font=("Consolas", 12),
            text_color="#777777"
        )
        self.group_summary.pack(side="left", padx=(16, 0), pady=(7, 0))

        # ========== Main Layout ==========
        main_layout = ctk.CTkFrame(self, fg_color="transparent")
        main_layout.pack(fill="both", expand=True, padx=25, pady=(5, 20))

        # Left Side - Folders
        self.sidebar = ctk.CTkFrame(
            main_layout,
            width=180,
            fg_color="#161616",
            corner_radius=12
        )
        self.sidebar.pack(side="left", fill="y", padx=(0, 15))
        self.sidebar.pack_propagate(False)

        sidebar_title = ctk.CTkLabel(
            self.sidebar,
            text="Folders",
            font=("Consolas", 14, "bold"),
            text_color="#ff5500"
        )
        sidebar_title.pack(pady=(15, 10))

        ctk.CTkLabel(
            self.sidebar,
            text="Choose a collection",
            font=("Consolas", 10),
            text_color="#666666"
        ).pack(pady=(0, 12))

        self.folder_buttons = {}

        for group_name in self.groups.keys():
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"📁  {group_name}",
                font=("Consolas", 13),
                fg_color="transparent",
                hover_color="#2a2a2a",
                anchor="w",
                height=38,
                command=lambda name=group_name: self.show_group(name)
            )
            btn.pack(fill="x", padx=10, pady=3)
            self.folder_buttons[group_name] = btn

        # Right Side - Apps Grid
        self.apps_container = ctk.CTkScrollableFrame(
            main_layout,
            fg_color="#141414",
            corner_radius=12
        )
        self.apps_container.pack(side="left", fill="both", expand=True)

        for i in range(3):
            self.apps_container.grid_columnconfigure(i, weight=1)

    # =========================================================
    # Show Group
    # =========================================================

    def show_group(self, group_name):
        self.current_group = group_name

        # Update folder button colors
        for name, btn in self.folder_buttons.items():
            if name == group_name:
                btn.configure(fg_color="#ff5500", hover_color="#cc4400")
            else:
                btn.configure(fg_color="transparent", hover_color="#2a2a2a")

        # Clear previous apps
        for widget in self.apps_container.winfo_children():
            widget.destroy()

        apps = self.groups.get(group_name, [])
        self.group_summary.configure(
            text=f"{len(apps)} app{'s' if len(apps) != 1 else ''} in {group_name}"
        )

        if not apps:
            empty = ctk.CTkLabel(
                self.apps_container,
                text="No apps in this folder",
                font=("Consolas", 15),
                text_color="#555555"
            )
            empty.pack(pady=60)
            return

        for index, app in enumerate(apps):
            row = index // 3
            col = index % 3
            self.create_app_card(app, row, col)

    # =========================================================
    # App Card
    # =========================================================

    def create_app_card(self, app, row, col):

        card = ctk.CTkFrame(
            self.apps_container,
            fg_color="#1c1c1c",
            corner_radius=14,
            width=180,
            height=132,
            border_width=1,
            border_color="#2a2a2a"
        )
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        card.grid_propagate(False)

        def on_enter(e):
            card.configure(fg_color="#252525", border_color="#ff5500")

        def on_leave(e):
            card.configure(fg_color="#1c1c1c", border_color="#2a2a2a")

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
        card.bind("<Button-1>", lambda e, a=app: self.launch_app(a))

        icon = ctk.CTkLabel(
            card,
            text=app.get("icon", "📦"),
            font=("Segoe UI Emoji", 32)
        )
        icon.pack(pady=(18, 5))
        icon.bind("<Button-1>", lambda e, a=app: self.launch_app(a))

        name = ctk.CTkLabel(
            card,
            text=app["name"],
            font=("Consolas", 13, "bold")
        )
        name.pack()
        name.bind("<Button-1>", lambda e, a=app: self.launch_app(a))

    # =========================================================
    # Launch App
    # =========================================================

    def launch_app(self, app):
        path = app.get("path", "")

        try:
            if path.lower() in ["code", "code.cmd"]:
                subprocess.Popen(["code"], shell=True)
            elif path.lower() in ["chrome", "google-chrome"]:
                subprocess.Popen(["chrome"], shell=True)
            elif path.lower() in ["wt", "windows terminal"]:
                subprocess.Popen(["wt"], shell=True)
            elif path.lower() == "explorer":
                subprocess.Popen(["explorer"], shell=True)
            elif path.lower() == "notepad":
                subprocess.Popen(["notepad"], shell=True)
            elif path.lower() == "calc":
                subprocess.Popen(["calc"], shell=True)
            elif path.lower() == "cmd":
                subprocess.Popen(["cmd"], shell=True)
            elif path.lower() == "taskmgr":
                subprocess.Popen(["taskmgr"], shell=True)
            else:
                subprocess.Popen(path, shell=True)

        except Exception as e:
            messagebox.showerror(
                "Launch Failed",
                f"Could not launch {app['name']}\n\n{e}"
            )