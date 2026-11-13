"""
Quick App Groups for Rex.

Left side: folders (groups). Right side: the apps in the selected folder.
Click an app card to launch it. Right-click a card for more actions.

Highlights
  - Search across every folder; press Enter to launch the first match
  - "Launch All" starts every app in a folder (a one-click workspace)
  - Apps missing on this PC are detected and marked "not found"
  - Add apps by browsing, typing a command, or picking from the Start Menu
  - Edit, move between folders, reorder, open file location, remove
  - Launch failures are also sent to the Notification Centre (if present)

Storage: SQLite table `quick_app_groups` in %APPDATA%\\Rex\\rex.db
(group_name TEXT PRIMARY KEY, apps_json TEXT). Folder order = row order.

Each app is {"name": str, "path": str, "icon": str} where `path` is either a
command name ("code", "chrome", "winword", "ms-settings:") or a full path
("C:\\Program Files\\...\\app.exe", or a .lnk shortcut).
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
from contextlib import contextmanager
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

try:
    import winreg
except ImportError:  # not Windows
    winreg = None


# =============================================================
# Helpers
# =============================================================

ICON_HINTS = [
    ("chrome", "🌐"), ("edge", "🔷"), ("firefox", "🦊"), ("brave", "🦁"), ("opera", "🌐"),
    ("code", "💻"), ("studio", "💻"), ("pycharm", "💻"), ("intellij", "💻"),
    ("terminal", "⬛"), ("powershell", "⬛"), ("command", "⌨️"), ("cmd", "⌨️"),
    ("git", "🐙"), ("docker", "🐳"), ("postman", "🚀"), ("python", "🐍"),
    ("word", "📘"), ("excel", "📗"), ("powerpoint", "📙"), ("onenote", "📓"),
    ("outlook", "📧"), ("mail", "📧"), ("teams", "💬"), ("slack", "💬"),
    ("discord", "🎮"), ("steam", "🎮"), ("spotify", "🎵"), ("vlc", "🎬"),
    ("photo", "🖼️"), ("paint", "🎨"), ("calc", "🧮"), ("notepad", "📝"),
    ("zoom", "📹"), ("explorer", "📁"), ("settings", "⚙️"), ("arduino", "🔌"),
]


def guess_icon(name):
    lowered = str(name).lower()
    for keyword, icon in ICON_HINTS:
        if re.search(r"\b" + re.escape(keyword), lowered):
            return icon
    return "📦"


def expand_target(raw):
    return os.path.expandvars(os.path.expanduser(str(raw).strip().strip('"').strip("'")))


# =============================================================
# Add / edit app dialog
# =============================================================

class AppDialog(ctk.CTkToplevel):
    """Modal dialog that asks for an app's name, path/command and icon."""

    def __init__(self, parent, title="Add App", name="", path="", icon="📦",
                 confirm_text="Save"):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.configure(fg_color="#0d0d0d")
        self.resizable(False, False)
        self.geometry("520x340")
        try:
            self.transient(parent.winfo_toplevel())
        except tk.TclError:
            pass

        body = ctk.CTkFrame(self, fg_color="#161616", corner_radius=12,
                            border_width=1, border_color="#292929")
        body.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(body, text=title, font=("Consolas", 18, "bold"),
                     text_color="#ff5500").pack(anchor="w", padx=18, pady=(16, 10))

        ctk.CTkLabel(body, text="Name", font=("Consolas", 12),
                     text_color="#888888").pack(anchor="w", padx=18)
        self.name_entry = ctk.CTkEntry(body, font=("Consolas", 13), height=34,
                                       placeholder_text="e.g. Visual Studio Code")
        self.name_entry.pack(fill="x", padx=18, pady=(2, 10))
        if name:
            self.name_entry.insert(0, name)

        ctk.CTkLabel(body, text="Program path or command", font=("Consolas", 12),
                     text_color="#888888").pack(anchor="w", padx=18)
        path_row = ctk.CTkFrame(body, fg_color="transparent")
        path_row.pack(fill="x", padx=18, pady=(2, 10))
        self.path_entry = ctk.CTkEntry(
            path_row, font=("Consolas", 13), height=34,
            placeholder_text="C:\\Program Files\\App\\app.exe   or   code"
        )
        self.path_entry.pack(side="left", fill="x", expand=True)
        if path:
            self.path_entry.insert(0, path)
        ctk.CTkButton(path_row, text="Browse…", width=90, height=34,
                      font=("Consolas", 12), fg_color="#222222",
                      hover_color="#333333", command=self.browse).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(body, text="Icon (emoji)", font=("Consolas", 12),
                     text_color="#888888").pack(anchor="w", padx=18)
        self.icon_entry = ctk.CTkEntry(body, font=("Segoe UI Emoji", 14), height=34, width=90)
        self.icon_entry.pack(anchor="w", padx=18, pady=(2, 12))
        self.icon_entry.insert(0, icon or "📦")

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(buttons, text=confirm_text, width=100, font=("Consolas", 13, "bold"),
                      fg_color="#ff5500", hover_color="#cc4400",
                      command=self.submit).pack(side="right")
        ctk.CTkButton(buttons, text="Cancel", width=90, font=("Consolas", 13),
                      fg_color="#222222", hover_color="#333333",
                      command=self.destroy).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _e: self.submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(150, self._show)

    def _show(self):
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.name_entry.focus_set()
            self.grab_set()
        except tk.TclError:
            pass

    def browse(self):
        selected = filedialog.askopenfilename(
            parent=self,
            title="Choose a program",
            filetypes=[("Programs and shortcuts", "*.exe *.lnk *.bat *.cmd"),
                       ("All files", "*.*")]
        )
        if not selected:
            return
        selected = os.path.normpath(selected)
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, selected)
        stem = os.path.splitext(os.path.basename(selected))[0]
        if not self.name_entry.get().strip():
            self.name_entry.insert(0, stem)
        if self.icon_entry.get().strip() in ("", "📦"):
            self.icon_entry.delete(0, "end")
            self.icon_entry.insert(0, guess_icon(stem))

    def submit(self):
        name = self.name_entry.get().strip()
        path = self.path_entry.get().strip().strip('"').strip("'")
        icon = self.icon_entry.get().strip() or "📦"

        if not name:
            messagebox.showwarning("Quick App Groups", "Please enter a name.", parent=self)
            return
        if not path:
            messagebox.showwarning("Quick App Groups",
                                   "Please enter a program path or command.", parent=self)
            return

        looks_like_path = os.path.isabs(expand_target(path)) or "\\" in path or "/" in path
        if looks_like_path and not os.path.exists(expand_target(path)):
            if not messagebox.askyesno(
                "Quick App Groups",
                "That file was not found on this PC.\n\nSave it anyway?",
                parent=self
            ):
                return

        self.result = {"name": name[:40], "path": path, "icon": icon[:8]}
        self.destroy()


# =============================================================
# Start Menu picker
# =============================================================

class StartMenuDialog(ctk.CTkToplevel):
    """Lists installed apps (Start Menu shortcuts) so they can be added in one click."""

    MAX_SHOWN = 60
    SKIP_WORDS = ("uninstall", "readme", "release notes", "documentation",
                  "license", "website", "manual", "help")

    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.entries = []
        self.selected = {}
        self._search_after = None

        self.title("Add from Start Menu")
        self.configure(fg_color="#0d0d0d")
        self.geometry("540x620")
        try:
            self.transient(parent.winfo_toplevel())
        except tk.TclError:
            pass

        body = ctk.CTkFrame(self, fg_color="#161616", corner_radius=12,
                            border_width=1, border_color="#292929")
        body.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(body, text="Installed apps", font=("Consolas", 18, "bold"),
                     text_color="#ff5500").pack(anchor="w", padx=18, pady=(16, 8))

        self.search_entry = ctk.CTkEntry(body, height=34, font=("Consolas", 13),
                                         placeholder_text="Search installed apps…")
        self.search_entry.pack(fill="x", padx=18, pady=(0, 8))
        self.search_entry.bind("<KeyRelease>", self._on_key)

        self.status_label = ctk.CTkLabel(body, text="Scanning Start Menu…",
                                         font=("Consolas", 11), text_color="#777777")
        self.status_label.pack(anchor="w", padx=18)

        self.list_frame = ctk.CTkScrollableFrame(body, fg_color="#101010", corner_radius=8)
        self.list_frame.pack(fill="both", expand=True, padx=18, pady=(6, 10))

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 14))
        self.add_btn = ctk.CTkButton(buttons, text="Add selected (0)", width=150,
                                     font=("Consolas", 13, "bold"), fg_color="#ff5500",
                                     hover_color="#cc4400", command=self.submit)
        self.add_btn.pack(side="right")
        ctk.CTkButton(buttons, text="Cancel", width=90, font=("Consolas", 13),
                      fg_color="#222222", hover_color="#333333",
                      command=self.destroy).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(150, self._show)
        threading.Thread(target=self._scan, daemon=True).start()

    def _show(self):
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.search_entry.focus_set()
            self.grab_set()
        except tk.TclError:
            pass

    @classmethod
    def scan_start_menu(cls):
        roots = []
        for env in ("ProgramData", "APPDATA"):
            base = os.getenv(env)
            if base:
                roots.append(os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs"))

        found = {}
        for root in roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                for filename in files:
                    if not filename.lower().endswith(".lnk"):
                        continue
                    name = filename[:-4]
                    lowered = name.lower()
                    if any(word in lowered for word in cls.SKIP_WORDS):
                        continue
                    found.setdefault(lowered, (name, os.path.join(dirpath, filename)))
        return sorted(found.values(), key=lambda item: item[0].lower())

    def _scan(self):
        try:
            entries = self.scan_start_menu()
        except Exception:
            entries = []
        try:
            self.after(0, lambda: self._loaded(entries))
        except (RuntimeError, tk.TclError):
            pass

    def _loaded(self, entries):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.entries = entries
        self.render()

    def _on_key(self, _event):
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(180, self.render)

    def render(self):
        self._search_after = None
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not self.entries:
            self.status_label.configure(
                text="No Start Menu apps found on this PC. Use Browse instead."
            )
            return

        query = self.search_entry.get().strip().lower()
        matches = [e for e in self.entries if query in e[0].lower()] if query else self.entries
        shown = matches[: self.MAX_SHOWN]
        extra = len(matches) - len(shown)
        self.status_label.configure(
            text=f"{len(matches)} app{'s' if len(matches) != 1 else ''}"
                 + (f" — showing {len(shown)}, type to narrow down" if extra > 0 else "")
        )

        for name, path in shown:
            var = ctk.BooleanVar(value=name in self.selected)
            box = ctk.CTkCheckBox(
                self.list_frame, text=name, variable=var, font=("Consolas", 12),
                fg_color="#ff5500", hover_color="#cc4400",
                command=lambda n=name, p=path, v=var: self._toggle(n, p, v)
            )
            box._rex_var = var  # keep a reference so it isn't garbage collected
            box.pack(anchor="w", padx=10, pady=5)

    def _toggle(self, name, path, var):
        if var.get():
            self.selected[name] = path
        else:
            self.selected.pop(name, None)
        self.add_btn.configure(text=f"Add selected ({len(self.selected)})")

    def submit(self):
        self.result = [
            {"name": name[:40], "path": path, "icon": guess_icon(name)}
            for name, path in self.selected.items()
        ]
        self.destroy()


# =============================================================
# Quick App Groups page
# =============================================================

class QuickAppGroup2(ctk.CTkFrame):

    DB_DIR = os.path.join(
        os.getenv("APPDATA") or os.path.expanduser("~"), "Rex"
    )
    DB_PATH = os.path.join(DB_DIR, "rex.db")
    TABLE = "quick_app_groups"
    LEGACY_DATA_FILE = os.path.join("data", "apps.json")

    COLUMNS = 3
    MAX_FOLDER_NAME = 28
    LAUNCH_ALL_DELAY = 0.4          # seconds between apps in "Launch All"

    BG = "#0d0d0d"
    PANEL = "#161616"
    GRID_BG = "#141414"
    CARD = "#1c1c1c"
    CARD_HOVER = "#252525"
    BORDER = "#2a2a2a"
    ACCENT = "#ff5500"
    ACCENT_HOVER = "#cc4400"
    DANGER = "#ef4444"
    OK = "#22c55e"
    WARN = "#eab308"

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self, master):
        super().__init__(master, fg_color=self.BG, corner_radius=0)

        self.remove_mode = False
        self.search_text = ""
        self.folder_buttons = {}
        self.storage_error = ""

        self._render_id = 0
        self._cards = []
        self._visible_items = []
        self._availability = {}
        self._search_after = None

        try:
            self.setup_database()
            self.groups = self.load_groups()
        except (sqlite3.Error, OSError) as error:
            self.storage_error = str(error)
            self.groups = self.get_default_groups()

        if not self.groups:
            self.groups = self.get_default_groups()
        self.current_group = next(iter(self.groups))

        self.build_ui()
        self.rebuild_sidebar()
        self.show_group(self.current_group)

        if self.storage_error:
            self.after(
                400,
                lambda: messagebox.showwarning(
                    "Quick App Groups",
                    "Your app groups could not be loaded from the database, so the "
                    "defaults are shown and changes may not be saved.\n\n"
                    + self.storage_error,
                    parent=self.winfo_toplevel()
                )
            )

    def destroy(self):
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        super().destroy()

    # =========================================================
    # DATABASE
    # =========================================================

    @classmethod
    @contextmanager
    def _db(cls):
        os.makedirs(cls.DB_DIR, exist_ok=True)
        conn = sqlite3.connect(cls.DB_PATH, timeout=10)
        try:
            with conn:  # commit on success, rollback on error
                yield conn
        finally:
            conn.close()

    @classmethod
    def get_connection(cls):
        os.makedirs(cls.DB_DIR, exist_ok=True)
        return sqlite3.connect(cls.DB_PATH, timeout=10)

    @classmethod
    def setup_database(cls):
        with cls._db() as conn:
            info = conn.execute(f"PRAGMA table_info({cls.TABLE})").fetchall()
            columns = {row[1] for row in info}

            # An unexpected old layout is kept (renamed), never deleted.
            if info and not {"group_name", "apps_json"}.issubset(columns):
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    f"ALTER TABLE {cls.TABLE} RENAME TO {cls.TABLE}_legacy_{int(time.time())}"
                )
                info = []

            if not info:
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {cls.TABLE} (
                        group_name TEXT PRIMARY KEY,
                        apps_json TEXT NOT NULL
                    )
                    """
                )

    @staticmethod
    def _clean_apps(value):
        """Keep only well-formed app entries."""
        if not isinstance(value, list):
            return []
        apps = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            path = str(item.get("path") or "").strip()
            if not name or not path:
                continue
            apps.append({
                "name": name,
                "path": path,
                "icon": str(item.get("icon") or "📦"),
            })
        return apps

    def load_groups(self):
        with self._db() as conn:
            rows = conn.execute(
                f"SELECT group_name, apps_json FROM {self.TABLE} ORDER BY rowid"
            ).fetchall()

        groups = {}
        for group_name, apps_json in rows:
            if not isinstance(group_name, str) or not group_name.strip():
                continue
            try:
                apps = json.loads(apps_json)
            except (TypeError, ValueError):
                apps = []
            groups[group_name] = self._clean_apps(apps)

        if groups:
            return groups

        # Empty database: seed defaults once (plus any old apps.json)
        groups = self.get_default_groups()
        legacy_apps = self.read_legacy_apps()
        if legacy_apps:
            groups["Custom"] = legacy_apps
        self.save_groups(groups)
        return groups

    def read_legacy_apps(self):
        path = self.LEGACY_DATA_FILE
        if not os.path.isfile(path):
            return []
        apps = []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                apps = self._clean_apps(json.load(handle))
        except (OSError, ValueError):
            apps = []
        try:
            os.replace(path, path + ".imported")
        except OSError:
            pass
        return apps

    def save_groups(self, groups=None):
        """Write every group to the database. Returns True on success."""
        groups = self.groups if groups is None else groups
        try:
            with self._db() as conn:
                conn.execute(f"DELETE FROM {self.TABLE}")
                conn.executemany(
                    f"INSERT INTO {self.TABLE} (group_name, apps_json) VALUES (?, ?)",
                    [(name, json.dumps(apps, ensure_ascii=False))
                     for name, apps in groups.items()]
                )
            return True
        except sqlite3.Error as error:
            messagebox.showerror(
                "Quick App Groups",
                f"Could not save your changes.\n\n{error}",
                parent=self.winfo_toplevel()
            )
            return False

    # =========================================================
    # DEFAULTS
    # =========================================================

    @staticmethod
    def get_default_groups():
        return {
            "Development": [
                {"name": "VS Code", "path": "code", "icon": "💻"},
                {"name": "Terminal", "path": "wt", "icon": "⬛"},
                {"name": "GitHub Desktop", "path": "github", "icon": "🐙"},
                {"name": "Postman", "path": "postman", "icon": "🚀"},
                {"name": "Docker Desktop",
                 "path": "%ProgramFiles%\\Docker\\Docker\\Docker Desktop.exe", "icon": "🐳"},
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
                {"name": "Spotify", "path": "spotify:", "icon": "🎵"},
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
            ],
        }

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):
        # ---------- Header ----------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 2))

        ctk.CTkLabel(
            header, text="Quick App Groups",
            font=("Consolas", 26, "bold"), text_color="#ffffff"
        ).pack(side="left")

        self.search_entry = ctk.CTkEntry(
            header, width=230, height=34, font=("Consolas", 13),
            placeholder_text="Search all apps…"
        )
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        self.search_entry.bind("<Return>", self._on_search_enter)

        self.group_summary = ctk.CTkLabel(
            self, text="", font=("Consolas", 12), text_color="#777777", anchor="w"
        )
        self.group_summary.pack(fill="x", padx=27, pady=(0, 8))

        # ---------- Toolbar ----------
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=25, pady=(0, 8))

        self.add_btn = ctk.CTkButton(
            toolbar, text="+ Add App ▾", width=120, height=32,
            font=("Consolas", 12, "bold"), fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER, command=self.show_add_menu
        )
        self.add_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            toolbar, text="+ Add Folder", width=115, height=32,
            font=("Consolas", 12), fg_color="#222222",
            hover_color="#333333", command=self.add_folder
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            toolbar, text="▶ Launch All", width=115, height=32,
            font=("Consolas", 12), fg_color="#222222",
            hover_color="#333333", command=self.launch_all
        ).pack(side="left", padx=(0, 8))

        self.remove_btn = ctk.CTkButton(
            toolbar, text="Remove App", width=115, height=32,
            font=("Consolas", 12), fg_color="#222222",
            hover_color="#333333", command=self.toggle_remove_mode
        )
        self.remove_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            toolbar, text="Reset Defaults", width=125, height=32,
            font=("Consolas", 12), fg_color="#222222",
            hover_color="#333333", command=self.reset_defaults
        ).pack(side="left")

        # ---------- Main layout ----------
        main_layout = ctk.CTkFrame(self, fg_color="transparent")
        main_layout.pack(fill="both", expand=True, padx=25, pady=(4, 20))

        # Sidebar (folders)
        self.sidebar = ctk.CTkFrame(
            main_layout, width=200, fg_color=self.PANEL, corner_radius=12,
            border_width=1, border_color="#292929"
        )
        self.sidebar.pack(side="left", fill="y", padx=(0, 15))
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(
            self.sidebar, text="Folders", font=("Consolas", 14, "bold"),
            text_color=self.ACCENT
        ).pack(pady=(14, 0))
        ctk.CTkLabel(
            self.sidebar, text="Choose a collection", font=("Consolas", 10),
            text_color="#666666"
        ).pack(pady=(0, 8))

        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=10, pady=(4, 12))

        top_row = ctk.CTkFrame(footer, fg_color="transparent")
        top_row.pack(fill="x")
        ctk.CTkButton(
            top_row, text="Rename", height=30, font=("Consolas", 12),
            fg_color="#222222", hover_color="#333333", command=self.rename_folder
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            top_row, text="Delete", height=30, font=("Consolas", 12),
            fg_color="#222222", hover_color=self.DANGER, command=self.delete_folder
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        order_row = ctk.CTkFrame(footer, fg_color="transparent")
        order_row.pack(fill="x", pady=(6, 0))
        ctk.CTkButton(
            order_row, text="▲ Up", height=28, font=("Consolas", 11),
            fg_color="#1d1d1d", hover_color="#333333",
            command=lambda: self.move_folder(-1)
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            order_row, text="▼ Down", height=28, font=("Consolas", 11),
            fg_color="#1d1d1d", hover_color="#333333",
            command=lambda: self.move_folder(1)
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.folder_list = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.folder_list.pack(side="top", fill="both", expand=True, padx=4)

        # Apps grid
        self.apps_container = ctk.CTkScrollableFrame(
            main_layout, fg_color=self.GRID_BG, corner_radius=12,
            border_width=1, border_color="#252525"
        )
        self.apps_container.pack(side="left", fill="both", expand=True)
        for column in range(self.COLUMNS):
            self.apps_container.grid_columnconfigure(column, weight=1, uniform="apps")

    # =========================================================
    # SIDEBAR
    # =========================================================

    def rebuild_sidebar(self):
        for widget in self.folder_list.winfo_children():
            widget.destroy()
        self.folder_buttons = {}

        for group_name in self.groups:
            label = group_name if len(group_name) <= 18 else group_name[:17] + "…"
            button = ctk.CTkButton(
                self.folder_list, text=f"📁  {label}", font=("Consolas", 13),
                fg_color="transparent", hover_color="#2a2a2a", anchor="w",
                height=38, command=lambda name=group_name: self.show_group(name)
            )
            button.pack(fill="x", padx=4, pady=3)
            self.folder_buttons[group_name] = button
        self.highlight_folders()

    def highlight_folders(self):
        for name, button in self.folder_buttons.items():
            if name == self.current_group and not self.search_text:
                button.configure(fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER)
            else:
                button.configure(fg_color="transparent", hover_color="#2a2a2a")

    # =========================================================
    # SEARCH
    # =========================================================

    def _on_search_key(self, event):
        if getattr(event, "keysym", "") == "Escape":
            self.search_entry.delete(0, "end")
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(150, self._apply_search)

    def _apply_search(self):
        self._search_after = None
        text = self.search_entry.get().strip()
        if text == self.search_text:
            return
        self.search_text = text
        self.highlight_folders()
        self.render()

    def _on_search_enter(self, _event):
        # make sure the list reflects exactly what is typed, then launch the top hit
        text = self.search_entry.get().strip()
        if text != self.search_text:
            self.search_text = text
            self.highlight_folders()
            self.render()
        if self.search_text and self._visible_items:
            group, app = self._visible_items[0]
            self.launch_app(app)

    # =========================================================
    # SHOW GROUP / RENDER
    # =========================================================

    def show_group(self, group_name):
        if group_name not in self.groups:
            group_name = next(iter(self.groups))
        self.current_group = group_name

        # leaving search mode
        self.search_text = ""
        if self.search_entry.get():
            self.search_entry.delete(0, "end")

        # re-check availability each time a folder is opened (apps may have been installed)
        for app in self.groups[group_name]:
            self._availability.pop(app["path"], None)

        self.highlight_folders()
        self.render()

    def render(self):
        self._render_id += 1
        self._cards = []

        for widget in self.apps_container.winfo_children():
            widget.destroy()

        searching = bool(self.search_text)
        if searching:
            query = self.search_text.lower()
            items = [
                (group, app)
                for group, apps in self.groups.items() for app in apps
                if query in app["name"].lower() or query in app["path"].lower()
                or query in group.lower()
            ]
        else:
            items = [(self.current_group, app) for app in self.groups[self.current_group]]
        self._visible_items = items

        if searching:
            summary = f"{len(items)} result{'s' if len(items) != 1 else ''} for “{self.search_text}”"
            if items:
                summary += "  •  Enter launches the first one"
        else:
            count = len(items)
            summary = f"{count} app{'s' if count != 1 else ''} in {self.current_group}"
        if self.remove_mode:
            summary += "  •  click an app to remove it"
        self.group_summary.configure(text=summary)

        if not items:
            box = ctk.CTkFrame(self.apps_container, fg_color="transparent")
            box.grid(row=0, column=0, columnspan=self.COLUMNS, pady=60)
            if searching:
                title, hint = "No apps match your search", "Try a different name."
            else:
                title, hint = "No apps in this folder", "Use “+ Add App” to put something here."
            ctk.CTkLabel(box, text=title, font=("Consolas", 15, "bold"),
                         text_color="#777777").pack()
            ctk.CTkLabel(box, text=hint, font=("Consolas", 12),
                         text_color="#555555").pack(pady=(4, 0))
            return

        for index, (group, app) in enumerate(items):
            self.create_app_card(app, group, index // self.COLUMNS, index % self.COLUMNS)

        self.start_availability_scan()

    # =========================================================
    # APP CARD
    # =========================================================

    def _info(self, group, available):
        if self.remove_mode:
            return "✕ remove", self.DANGER
        if available is False:
            return "not found on this PC", self.WARN
        if self.search_text:
            return group, "#666666"
        return " ", "#666666"

    def create_app_card(self, app, group, row, col):
        base_border = self.DANGER if self.remove_mode else self.BORDER
        available = self._availability.get(app["path"])

        card = ctk.CTkFrame(
            self.apps_container, fg_color=self.CARD, corner_radius=14,
            height=130, border_width=1, border_color=base_border
        )
        card.grid(row=row, column=col, padx=8, pady=8, sticky="ew")
        card.pack_propagate(False)

        name = app["name"] if len(app["name"]) <= 24 else app["name"][:23] + "…"

        ctk.CTkLabel(
            card, text=app.get("icon", "📦"), font=("Segoe UI Emoji", 30)
        ).pack(pady=(16, 4))
        name_label = ctk.CTkLabel(
            card, text=name, font=("Consolas", 13, "bold"),
            text_color="#777777" if available is False else "#ffffff"
        )
        name_label.pack()
        info_text, info_color = self._info(group, available)
        info_label = ctk.CTkLabel(
            card, text=info_text, font=("Consolas", 10), text_color=info_color
        )
        info_label.pack(pady=(2, 0))

        self._cards.append(
            {"app": app, "group": group, "name": name_label, "info": info_label}
        )

        def on_enter(_event):
            card.configure(fg_color=self.CARD_HOVER,
                           border_color=self.DANGER if self.remove_mode else self.ACCENT)

        def on_leave(_event):
            try:
                pointer = card.winfo_containing(*card.winfo_pointerxy())
            except Exception:
                pointer = None
            if pointer is not None and str(pointer).startswith(str(card)):
                return  # still inside the card (moved onto a child widget)
            card.configure(fg_color=self.CARD, border_color=base_border)

        self._bind_recursive(card, "<Enter>", on_enter)
        self._bind_recursive(card, "<Leave>", on_leave)
        self._bind_recursive(
            card, "<Button-1>",
            lambda _e, a=app, c=card: self.on_app_clicked(a, c)
        )
        self._bind_recursive(
            card, "<Button-3>",
            lambda e, a=app, g=group: self.show_context_menu(e, a, g)
        )
        card.configure(cursor="hand2")

    def _bind_recursive(self, widget, sequence, handler):
        widget.bind(sequence, handler)
        for child in widget.winfo_children():
            self._bind_recursive(child, sequence, handler)

    def on_app_clicked(self, app, card=None):
        if self.remove_mode:
            self.remove_app(app)
        else:
            self.launch_app(app, card)

    # =========================================================
    # AVAILABILITY (is the app actually on this PC?)
    # =========================================================

    @classmethod
    def check_available(cls, raw):
        target = expand_target(raw)
        if not target:
            return False
        if os.path.exists(target):
            return True

        # URI scheme such as ms-settings: or spotify:
        if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]+:", target) and not re.match(r"^[A-Za-z]:[\\/]", target):
            if winreg is None:
                return True
            scheme = target.split(":", 1)[0]
            try:
                winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, scheme))
                return True
            except OSError:
                return False

        if shutil.which(target):
            return True
        return cls._in_app_paths(target)

    @staticmethod
    def _in_app_paths(target):
        """Windows 'App Paths' registry: how winword, excel, firefox... are found."""
        if winreg is None:
            return False
        exe = target if target.lower().endswith(".exe") else target + ".exe"
        locations = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        ]
        for hive, base in locations:
            try:
                winreg.CloseKey(winreg.OpenKey(hive, base + "\\" + exe))
                return True
            except OSError:
                continue
        return False

    def start_availability_scan(self):
        render_id = self._render_id
        pending = {c["app"]["path"] for c in self._cards
                   if c["app"]["path"] not in self._availability}
        if not pending:
            return

        def worker():
            for path in pending:
                try:
                    self._availability[path] = self.check_available(path)
                except Exception:
                    self._availability[path] = True
            self.run_on_ui(lambda: self.apply_availability(render_id))

        threading.Thread(target=worker, daemon=True).start()

    def apply_availability(self, render_id):
        if render_id != self._render_id:
            return  # the grid was rebuilt in the meantime
        for card in self._cards:
            available = self._availability.get(card["app"]["path"])
            try:
                card["name"].configure(
                    text_color="#777777" if available is False else "#ffffff"
                )
                text, color = self._info(card["group"], available)
                card["info"].configure(text=text, text_color=color)
            except Exception:
                continue

    # =========================================================
    # LAUNCH
    # =========================================================

    @staticmethod
    def _shell_open(target):
        if hasattr(os, "startfile"):
            os.startfile(target)          # Windows ShellExecute: App Paths, URIs, files, folders
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])

    @classmethod
    def launch_target(cls, raw_target):
        target = expand_target(raw_target)
        if not target:
            raise ValueError("No path or command is set for this app.")

        # 1) full path to an existing file / folder / shortcut
        if os.path.exists(target):
            cls._shell_open(target)
            return

        # 2) command found on PATH
        resolved = shutil.which(target)
        if resolved:
            if resolved.lower().endswith((".cmd", ".bat")):
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(["cmd.exe", "/c", resolved], creationflags=flags)
            else:
                cls._shell_open(resolved)
            return

        # 3) let Windows resolve it (registered app names like "winword",
        #    URI schemes like "ms-settings:")
        if not hasattr(os, "startfile"):
            raise FileNotFoundError(target)
        os.startfile(target)

    def launch_app(self, app, card=None):
        name = app.get("name", "App")
        target = app.get("path", "")
        if card is not None:
            self.flash_card(card)

        def worker():
            try:
                self.launch_target(target)
            except Exception as error:
                message = self.friendly_error(name, target, error)
                self.run_on_ui(
                    lambda: messagebox.showerror(
                        "Launch Failed", message, parent=self.winfo_toplevel()
                    )
                )
                self.notify(f"Could not launch {name}", self.short_error(target, error))

        threading.Thread(target=worker, daemon=True).start()

    def flash_card(self, card):
        try:
            card.configure(border_color=self.OK)
            card.after(500, lambda: self._unflash(card))
        except Exception:
            pass

    def _unflash(self, card):
        try:
            card.configure(border_color=self.DANGER if self.remove_mode else self.BORDER)
        except Exception:
            pass

    def launch_all(self):
        apps = list(self.groups.get(self.current_group, []))
        if not apps:
            messagebox.showinfo("Quick App Groups", "This folder has no apps yet.",
                                parent=self.winfo_toplevel())
            return
        if not messagebox.askyesno(
            "Launch All",
            f"Launch all {len(apps)} app{'s' if len(apps) != 1 else ''} in “{self.current_group}”?",
            parent=self.winfo_toplevel()
        ):
            return

        folder = self.current_group

        def worker():
            failures = []
            for app in apps:
                try:
                    self.launch_target(app.get("path", ""))
                except Exception as error:
                    failures.append(f"• {app.get('name', 'App')}: {self.short_error(app.get('path', ''), error)}")
                time.sleep(self.LAUNCH_ALL_DELAY)
            if failures:
                text = f"{len(failures)} of {len(apps)} apps in “{folder}” could not be started:\n\n" + "\n".join(failures)
                self.run_on_ui(
                    lambda: messagebox.showwarning(
                        "Launch All", text, parent=self.winfo_toplevel()
                    )
                )
                self.notify(f"Launch All: {len(failures)} failed in {folder}", "\n".join(failures))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def short_error(target, error):
        winerror = getattr(error, "winerror", None)
        if isinstance(error, FileNotFoundError) or winerror in (2, 3):
            return f"not found ({target})"
        return str(error) or error.__class__.__name__

    @staticmethod
    def friendly_error(name, target, error):
        winerror = getattr(error, "winerror", None)
        if isinstance(error, FileNotFoundError) or winerror in (2, 3):
            return (
                f"Could not find “{name}” on this PC.\n\n"
                f"It may not be installed, or its location is different here.\n"
                f"Right-click it and choose Edit to point to its program file, "
                f"or remove it.\n\n"
                f"Path / command: {target}"
            )
        return f"Could not launch {name}.\n\n{error}"

    @staticmethod
    def notify(title, message):
        """Send a message to the Notification Centre when that module is available."""
        try:
            try:
                from ui.notification_centre import NotificationCentre
            except ImportError:
                from notification_centre import NotificationCentre
            NotificationCentre.push(title, message, "Alert")
        except Exception:
            pass

    def run_on_ui(self, callback):
        try:
            self.after(0, callback)
        except (RuntimeError, tk.TclError):
            pass

    # =========================================================
    # CONTEXT MENU
    # =========================================================

    def _make_menu(self):
        return tk.Menu(
            self, tearoff=0, bg="#1c1c1c", fg="#dddddd", activebackground=self.ACCENT,
            activeforeground="#ffffff", bd=0, relief="flat", font=("Consolas", 11)
        )

    @staticmethod
    def _index_of(apps, app):
        for index, item in enumerate(apps):
            if item is app:
                return index
        return -1

    def show_context_menu(self, event, app, group):
        menu = self._make_menu()
        menu.add_command(label="Launch", command=lambda: self.launch_app(app))
        menu.add_command(label="Edit…", command=lambda: self.edit_app(app))

        other_groups = [g for g in self.groups if g != group]
        if other_groups:
            move_menu = self._make_menu()
            for target in other_groups:
                move_menu.add_command(
                    label=target, command=lambda t=target: self.move_app(app, group, t)
                )
            menu.add_cascade(label="Move to folder", menu=move_menu)

        if not self.search_text:
            menu.add_separator()
            menu.add_command(label="Move earlier", command=lambda: self.shift_app(app, -1))
            menu.add_command(label="Move later", command=lambda: self.shift_app(app, 1))

        menu.add_separator()
        menu.add_command(label="Open file location", command=lambda: self.open_location(app))
        menu.add_command(label="Remove", command=lambda: self.remove_app(app))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def edit_app(self, app):
        dialog = AppDialog(
            self, title="Edit App", name=app["name"], path=app["path"],
            icon=app.get("icon", "📦"), confirm_text="Save"
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        self._availability.pop(app["path"], None)
        app.update(dialog.result)
        self.save_groups()
        self.render()

    def move_app(self, app, source, target):
        apps = self.groups.get(source, [])
        index = self._index_of(apps, app)
        if index < 0 or target not in self.groups:
            return
        apps.pop(index)
        self.groups[target].append(app)
        self.save_groups()
        self.render()

    def shift_app(self, app, delta):
        apps = self.groups.get(self.current_group, [])
        index = self._index_of(apps, app)
        new_index = index + delta
        if index < 0 or not 0 <= new_index < len(apps):
            return
        apps[index], apps[new_index] = apps[new_index], apps[index]
        self.save_groups()
        self.render()

    def open_location(self, app):
        target = expand_target(app["path"])
        if not os.path.exists(target):
            resolved = shutil.which(target)
            if resolved:
                target = resolved
        if not os.path.exists(target):
            messagebox.showinfo(
                "Quick App Groups",
                "This app is started by name, so there is no file location to open.",
                parent=self.winfo_toplevel()
            )
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", f"/select,{os.path.normpath(target)}"])
            else:
                self._shell_open(os.path.dirname(target))
        except Exception as error:
            messagebox.showerror("Quick App Groups", str(error), parent=self.winfo_toplevel())

    # =========================================================
    # APP MANAGEMENT
    # =========================================================

    def show_add_menu(self):
        menu = self._make_menu()
        menu.add_command(label="Browse for a program / type a command…", command=self.add_app)
        menu.add_command(label="Pick from Start Menu…", command=self.add_from_start_menu)
        x = self.add_btn.winfo_rootx()
        y = self.add_btn.winfo_rooty() + self.add_btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _is_duplicate(self, group, candidate):
        return any(
            a["name"].lower() == candidate["name"].lower()
            and a["path"].lower() == candidate["path"].lower()
            for a in self.groups[group]
        )

    def add_app(self):
        dialog = AppDialog(self, title=f"Add App to {self.current_group}",
                           confirm_text="Add App")
        self.wait_window(dialog)
        result = dialog.result
        if not result:
            return

        if self._is_duplicate(self.current_group, result):
            messagebox.showinfo("Quick App Groups",
                                "That app is already in this folder.",
                                parent=self.winfo_toplevel())
            return

        self.groups[self.current_group].append(result)
        self.save_groups()
        self.show_group(self.current_group)

    def add_from_start_menu(self):
        dialog = StartMenuDialog(self)
        self.wait_window(dialog)
        results = dialog.result
        if not results:
            return

        added = 0
        for item in results:
            if not self._is_duplicate(self.current_group, item):
                self.groups[self.current_group].append(item)
                added += 1
        if added:
            self.save_groups()
        self.show_group(self.current_group)

    def toggle_remove_mode(self):
        self.remove_mode = not self.remove_mode
        if self.remove_mode:
            self.remove_btn.configure(text="Done", fg_color=self.DANGER, hover_color="#c53030")
        else:
            self.remove_btn.configure(text="Remove App", fg_color="#222222", hover_color="#333333")
        self.render()

    def remove_app(self, app):
        if not messagebox.askyesno(
            "Remove App",
            f"Remove “{app['name']}”?",
            parent=self.winfo_toplevel()
        ):
            return
        for apps in self.groups.values():
            index = self._index_of(apps, app)
            if index >= 0:
                apps.pop(index)
                break
        self.save_groups()
        self.render()

    # =========================================================
    # FOLDER MANAGEMENT
    # =========================================================

    def ask_folder_name(self, title, prompt, initial=""):
        name = simpledialog.askstring(
            title, prompt, initialvalue=initial, parent=self.winfo_toplevel()
        )
        if name is None:
            return None
        name = name.strip()
        if not name:
            messagebox.showwarning("Quick App Groups", "Folder name cannot be empty.",
                                   parent=self.winfo_toplevel())
            return None
        if len(name) > self.MAX_FOLDER_NAME:
            messagebox.showwarning(
                "Quick App Groups",
                f"Folder name must be {self.MAX_FOLDER_NAME} characters or fewer.",
                parent=self.winfo_toplevel()
            )
            return None
        for existing in self.groups:
            if existing.lower() == name.lower() and existing != initial:
                messagebox.showwarning("Quick App Groups",
                                       f"A folder named “{existing}” already exists.",
                                       parent=self.winfo_toplevel())
                return None
        return name

    def add_folder(self):
        name = self.ask_folder_name("New Folder", "Folder name:")
        if not name:
            return
        self.groups[name] = []
        self.save_groups()
        self.rebuild_sidebar()
        self.show_group(name)

    def rename_folder(self):
        old_name = self.current_group
        new_name = self.ask_folder_name("Rename Folder", "New name:", initial=old_name)
        if not new_name or new_name == old_name:
            return
        self.groups = {
            (new_name if key == old_name else key): value
            for key, value in self.groups.items()
        }
        self.save_groups()
        self.rebuild_sidebar()
        self.show_group(new_name)

    def move_folder(self, delta):
        names = list(self.groups)
        index = names.index(self.current_group)
        new_index = index + delta
        if not 0 <= new_index < len(names):
            return
        names[index], names[new_index] = names[new_index], names[index]
        self.groups = {name: self.groups[name] for name in names}
        self.save_groups()
        self.rebuild_sidebar()
        self.show_group(self.current_group)

    def delete_folder(self):
        if len(self.groups) <= 1:
            messagebox.showinfo("Quick App Groups",
                                "You need at least one folder. Add another one first.",
                                parent=self.winfo_toplevel())
            return
        name = self.current_group
        count = len(self.groups[name])
        if not messagebox.askyesno(
            "Delete Folder",
            f"Delete “{name}” and its {count} app{'s' if count != 1 else ''}?",
            parent=self.winfo_toplevel()
        ):
            return
        names = list(self.groups)
        index = names.index(name)
        del self.groups[name]
        self.save_groups()
        names.remove(name)
        self.rebuild_sidebar()
        self.show_group(names[min(index, len(names) - 1)])

    def reset_defaults(self):
        if not messagebox.askyesno(
            "Reset Defaults",
            "Replace all folders and apps with the defaults?\n\n"
            "Your custom folders and apps will be removed.",
            parent=self.winfo_toplevel()
        ):
            return
        self.groups = self.get_default_groups()
        self._availability.clear()
        self.save_groups()
        if self.remove_mode:
            self.toggle_remove_mode()
        self.rebuild_sidebar()
        self.show_group(next(iter(self.groups)))