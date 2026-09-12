import customtkinter as ctk
import subprocess
import os
import json
from tkinter import filedialog, messagebox


class QuickAppGroup(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="#0d0d0d", corner_radius=0)

        self.apps = []
        self.load_apps()
        self.build_ui()
        self.refresh_grid()

    def build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(22, 10))

        title = ctk.CTkLabel(
            header,
            text="Quick App Group",
            font=("Consolas", 26, "bold")
        )
        title.pack(side="left")

        add_btn = ctk.CTkButton(
            header,
            text="+ Add App",
            width=110,
            height=34,
            font=("Consolas", 13, "bold"),
            fg_color="#ff5500",
            hover_color="#cc4400",
            command=self.add_app
        )
        add_btn.pack(side="right")

        subtitle = ctk.CTkLabel(
            self,
            text="Click any card to launch the application",
            font=("Consolas", 13),
            text_color="#777777",
            anchor="w"
        )
        subtitle.pack(fill="x", padx=28, pady=(0, 15))

        self.grid_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#141414",
            corner_radius=12
        )
        self.grid_frame.pack(fill="both", expand=True, padx=28, pady=(0, 25))

        for i in range(3):
            self.grid_frame.grid_columnconfigure(i, weight=1)

    def get_default_apps(self):
        return [
            {"name": "VS Code", "path": "code", "icon": "💻"},
            {"name": "Chrome", "path": "chrome", "icon": "🌐"},
            {"name": "Terminal", "path": "wt", "icon": "⬛"},
            {"name": "File Explorer", "path": "explorer", "icon": "📁"},
            {"name": "Notepad", "path": "notepad", "icon": "📝"},
            {"name": "Calculator", "path": "calc", "icon": "🧮"},
        ]

    def load_apps(self):
        try:
            os.makedirs("data", exist_ok=True)
            if os.path.exists("data/apps.json"):
                with open("data/apps.json", "r", encoding="utf-8") as f:
                    self.apps = json.load(f)
            else:
                self.apps = self.get_default_apps()
                self.save_apps()
        except Exception:
            self.apps = self.get_default_apps()

    def save_apps(self):
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/apps.json", "w", encoding="utf-8") as f:
                json.dump(self.apps, f, indent=4)
        except Exception:
            pass

    def refresh_grid(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        if not self.apps:
            empty = ctk.CTkLabel(
                self.grid_frame,
                text="No apps added yet.\nClick '+ Add App' to get started.",
                font=("Consolas", 15),
                text_color="#555555",
                justify="center"
            )
            empty.pack(pady=70)
            return

        for index, app in enumerate(self.apps):
            row = index // 3
            col = index % 3
            self.create_app_card(app, row, col)

    def create_app_card(self, app, row, col):
        card = ctk.CTkFrame(
            self.grid_frame,
            fg_color="#1c1c1c",
            corner_radius=14,
            width=190,
            height=130,
            border_width=1,
            border_color="#2a2a2a"
        )
        card.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")
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
            font=("Segoe UI Emoji", 34)
        )
        icon.pack(pady=(22, 6))
        icon.bind("<Button-1>", lambda e, a=app: self.launch_app(a))

        name = ctk.CTkLabel(
            card,
            text=app["name"],
            font=("Consolas", 14, "bold"),
            text_color="#ffffff"
        )
        name.pack()
        name.bind("<Button-1>", lambda e, a=app: self.launch_app(a))

    def launch_app(self, app):
        path = app.get("path", "")

        try:
            if path.lower() in ["code", "code.cmd"]:
                subprocess.Popen(["code"], shell=True)
            elif path.lower() in ["chrome", "google-chrome", "chrome.exe"]:
                subprocess.Popen(["chrome"], shell=True)
            elif path.lower() in ["wt", "windows terminal"]:
                subprocess.Popen(["wt"], shell=True)
            elif path.lower() == "explorer":
                subprocess.Popen(["explorer"], shell=True)
            elif path.lower() == "notepad":
                subprocess.Popen(["notepad"], shell=True)
            elif path.lower() == "calc":
                subprocess.Popen(["calc"], shell=True)
            else:
                subprocess.Popen(path, shell=True)

        except Exception as e:
            messagebox.showerror(
                "Launch Failed",
                f"Could not launch {app['name']}\n\nError: {e}"
            )

    def add_app(self):
        path = filedialog.askopenfilename(
            title="Select Application",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )

        if not path:
            return

        name = os.path.splitext(os.path.basename(path))[0]

        new_app = {
            "name": name,
            "path": path,
            "icon": "📦"
        }

        self.apps.append(new_app)
        self.save_apps()
        self.refresh_grid()