"""
Watch Dog — local screen-time tracker for Rex.

Tracks how long the active window on this PC belongs to each app. Click
any app row to drag it open and see:
  - for browsers: time spent per site (with a bar), and
  - for every app: the actual open/close time ranges for today
    (e.g. "12:47 PM – 12:51 PM"), including the session in progress
    right now if that app is currently active.

Windows only. Requires:
    pip install pywin32 psutil pillow

(Pillow is optional: with it the app list shows each app's real icon,
without it the list falls back to a coloured letter badge per app.)

Notes / limitations:
- Site detection reads the browser's window title text, not the actual
  URL or open-tab list — it can only "see" whichever tab was frontmost
  at a given moment, accumulated over the day.
- Idle time (no keyboard/mouse input for 60s) is not counted, and ends
  whatever session was in progress.
- Daily totals are saved in the user's Rex data folder so the weekly chart
  and "vs yesterday" comparison survive restarts without changing the repository.
"""

import customtkinter as ctk
import tkinter as tk
import ctypes
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta

try:
    import win32gui
    import win32process
    import psutil
    DEPENDENCIES_OK = True
except ImportError:
    DEPENDENCIES_OK = False

# Optional: real app icons in the list. Falls back to letter badges if unavailable.
ICON_IMPORT_ERROR = None        # why real icons are off, shown in the app header
try:
    import win32api
    import win32con
    import win32ui
    from PIL import Image
    ICONS_OK = DEPENDENCIES_OK
except ImportError as _icon_import_exc:
    ICONS_OK = False
    ICON_IMPORT_ERROR = str(_icon_import_exc)

ICON_PROBLEMS = {}              # exe_path -> why its icon couldn't be read


# =========================================================
# Config
# =========================================================

REX_DATA_DIR = os.path.join(
    os.getenv("APPDATA") or os.path.expanduser("~"), "Rex"
)
DB_PATH = os.path.join(REX_DATA_DIR, "rex.db")
LEGACY_DATA_FILE = os.path.join(REX_DATA_DIR, "watchdog_data.json")
LEGACY_HISTORY_FILE = os.path.join(REX_DATA_DIR, "watchdog_history.json")
HISTORY_KEEP_DAYS = 30

POLL_INTERVAL_MS = 1000        # how often we sample the active window
REORDER_EVERY_N_TICKS = 6      # re-sort the visible rows only this often
SAVE_EVERY_N_TICKS = 5         # write to disk / refresh summary + expanded panels
IDLE_THRESHOLD_SECONDS = 60    # stop counting after this long with no input

MIN_SESSION_SECONDS = 3        # ignore sub-3-second focus flickers
MAX_SESSIONS_PER_APP = 100     # cap stored session history per app, per day

BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"
}

BROWSER_TITLE_SUFFIXES = [
    " - Google Chrome",
    " - Microsoft Edge",
    " - Mozilla Firefox",
    " - Brave",
    " - Opera",
]


# Palette (matched to the Rex Watch Dog design)
BG = "#0d0d0d"
CARD = "#16171b"            # glassy total-time card
CARD_DARK = "#141416"       # app list + weekly chart cards
ROW = "#1b1b1e"             # one app row
ACCENT = "#ff5500"
BLUE = "#4d94ff"
TEXT = "#f2f2f2"
MUTED = "#8a8a92"
DIM = "#5d5d66"
BORDER_NEUTRAL = "#34353c"
BORDER_WARM = "#4a2f1f"
BUTTON_BORDER = "#3a3a40"

CHART_STEPS = [300, 600, 900, 1800, 3600, 7200, 14400, 28800, 43200]  # seconds

# Letter-badge colours, used when an app has no real icon
BADGE_COLORS = [
    "#c2410c", "#1d4ed8", "#15803d", "#7e22ce",
    "#be123c", "#0f766e", "#a16207", "#4338ca",
]


# =========================================================
# OS helpers
# =========================================================

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds():
    """Seconds since the last keyboard/mouse input, system-wide."""
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0


def extract_site_name(title):
    """Best-effort guess at a site name from a browser window title."""
    cleaned = title

    for suffix in BROWSER_TITLE_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break

    for delimiter in [" - ", " | ", " \u00b7 "]:
        if delimiter in cleaned:
            parts = [p.strip() for p in cleaned.split(delimiter) if p.strip()]
            if len(parts) >= 2:
                return parts[-1][:40]

    cleaned = cleaned.strip()
    return cleaned[:40] if cleaned else "Unknown site"


def get_active_window_info():
    """
    Returns (process_key, display_name, kind, site, exe_path) for the
    foreground window, or five Nones if it can't be determined.
    kind is "browser" or "app". site is only set when kind == "browser".
    exe_path is used to pull the app's icon (may be None).
    """
    if not DEPENDENCIES_OK:
        return None, None, None, None, None

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None, None, None, None

        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        process_name = proc.name()
        process_key = process_name.lower()

        try:
            exe_path = proc.exe()
        except Exception:
            exe_path = None

        display = process_name[:-4] if process_key.endswith(".exe") else process_name

        if process_key in BROWSER_PROCESSES:
            site = extract_site_name(title) if title else None
            return process_key, display, "browser", site, exe_path

        return process_key, display, "app", None, exe_path

    except Exception:
        return None, None, None, None, None


def format_duration(seconds):
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s" if secs else "0s"


def format_clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def find_running_exes(process_keys):
    """
    One pass over the running processes -> {process_key: exe_path} for the
    lower-case process names asked about (only those currently running).
    """
    found = {}
    wanted = set(process_keys)
    if not DEPENDENCIES_OK or not wanted:
        return found
    try:
        for proc in psutil.process_iter(["name", "exe"]):
            name = (proc.info.get("name") or "").lower()
            if name in wanted and name not in found and proc.info.get("exe"):
                found[name] = proc.info["exe"]
    except Exception:
        pass
    return found


def badge_color(process_key):
    """Stable colour for an app's letter badge (same app, same colour, every run)."""
    return BADGE_COLORS[sum(ord(c) for c in process_key) % len(BADGE_COLORS)]


def _draw_hicon(hicon, bg_rgb, size=32):
    """Draw an icon handle onto a bg_rgb square and return it as a PIL image."""
    hdc_screen = None
    hdc = mem = bmp = None

    try:
        hdc_screen = win32gui.GetDC(0)
        hdc = win32ui.CreateDCFromHandle(hdc_screen)
        mem = hdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(hdc, size, size)
        mem.SelectObject(bmp)
        mem.FillSolidRect((0, 0, size, size), win32api.RGB(*bg_rgb))
        win32gui.DrawIconEx(mem.GetSafeHdc(), 0, 0, hicon, size, size, 0, 0, win32con.DI_NORMAL)

        bits = bmp.GetBitmapBits(True)
        return Image.frombuffer("RGB", (size, size), bits, "raw", "BGRX", 0, 1)

    finally:
        try:
            if mem is not None:
                mem.DeleteDC()
            if hdc is not None:
                hdc.DeleteDC()
            if hdc_screen is not None:
                win32gui.ReleaseDC(0, hdc_screen)
            if bmp is not None:
                win32gui.DeleteObject(bmp.GetHandle())
        except Exception:
            pass


def _icon_from_exe(exe_path, bg_rgb):
    """Method 1: the icon embedded in the exe file."""
    large, small = win32gui.ExtractIconEx(exe_path, 0)
    hicons = list(large) + list(small)
    try:
        if not hicons:
            raise RuntimeError("no icon embedded in the exe")
        return _draw_hicon(hicons[0], bg_rgb)
    finally:
        for h in hicons:
            try:
                win32gui.DestroyIcon(h)
            except Exception:
                pass


def _icon_from_shell(exe_path, bg_rgb):
    """Method 2: ask the Windows shell for the file's icon (what Explorer shows)."""
    SHGFI_ICON = 0x100          # large icon is the default size
    _, info = win32gui.SHGetFileInfo(exe_path, 0, SHGFI_ICON)
    hicon = info[0]
    if not hicon:
        raise RuntimeError("the shell returned no icon")
    try:
        return _draw_hicon(hicon, bg_rgb)
    finally:
        try:
            win32gui.DestroyIcon(hicon)
        except Exception:
            pass


def extract_exe_icon(exe_path, bg_rgb=(27, 27, 30)):
    """
    Best-effort: returns a 32x32 PIL image of the app's icon drawn on
    bg_rgb (so no alpha handling is needed), or None if every method
    fails. The reasons are kept in ICON_PROBLEMS[exe_path] and printed.
    """
    if not ICONS_OK or not exe_path:
        return None

    if not os.path.exists(exe_path):
        ICON_PROBLEMS[exe_path] = "file not found"
        return None

    problems = []
    for name, method in (("exe", _icon_from_exe), ("shell", _icon_from_shell)):
        try:
            image = method(exe_path, bg_rgb)
            ICON_PROBLEMS.pop(exe_path, None)
            return image
        except Exception as exc:
            problems.append(f"{name}: {exc}")

    ICON_PROBLEMS[exe_path] = " | ".join(problems)
    print(f"[Watch Dog] couldn't read the icon of {exe_path} -> {ICON_PROBLEMS[exe_path]}")
    return None


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _blend(rgb_a, rgb_b, t):
    return "#%02x%02x%02x" % tuple(int(a + (b - a) * t) for a, b in zip(rgb_a, rgb_b))


def smooth_curve(points, steps=10):
    """Catmull-Rom spline through points -> dense list of (x, y)."""
    if len(points) < 3:
        return list(points)

    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


def _flatten(points):
    return [c for p in points for c in p]


def axis_label(seconds):
    if seconds == 0:
        return "0"
    if seconds >= 3600:
        return f"{seconds / 3600:g}h"
    return f"{seconds / 60:g}m"


def draw_gradient_bar(canvas, x0, y0, x1, y1, top_rgb, bottom_rgb, radius):
    """Vertical-gradient bar with rounded top corners, drawn as 1px rows."""
    y0, y1 = int(round(y0)), int(round(y1))
    height = y1 - y0
    if height <= 0:
        return
    for i in range(height):
        t = i / max(height - 1, 1)
        inset = 0.0
        if i < radius:
            inset = radius - math.sqrt(max(radius * radius - (radius - i - 0.5) ** 2, 0))
        canvas.create_line(x0 + inset, y0 + i, x1 - inset, y0 + i, fill=_blend(top_rgb, bottom_rgb, t))


# =========================================================
# Watch Dog page
# =========================================================

class WatchDog(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(
            master,
            fg_color=BG,
            corner_radius=0
        )

        self.today = self.today_str()
        self.entries = {}       # process_key -> {"display","kind","seconds","sites","sessions"}
        self.history = {}       # date_str -> {"total_seconds","app_seconds","web_seconds"}
        self.row_widgets = {}   # process_key -> widget refs, so updates don't rebuild the list
        self.expanded = set()   # process_keys currently expanded
        self._order = []        # last-applied sort order of process_keys
        self.tracking = True
        self.tick_count = 0
        self.empty_label = None

        self.active_key = None      # process_key currently in the foreground
        self.active_since = None    # datetime it became the foreground window

        self.exe_paths = {}         # process_key -> exe path (for icons)
        self.icon_cache = {}        # process_key -> CTkImage (successful lookups only)
        self.icon_failed = set()    # process_keys whose icon couldn't be extracted
        self._chart_data = None     # (dates, totals) for redraws on resize
        self._chart_job = None

        self.setup_database()
        self.history = {}
        self.migrate_legacy_data()
        self.load_data()
        self.resolve_missing_exe_paths()
        self.history = self.load_history()

        self.build_ui()
        self.refresh_summary()

        if DEPENDENCIES_OK:
            self.tick()
        else:
            self.show_dependency_warning()

    def today_str(self):
        return datetime.now().strftime("%Y-%m-%d")

    # ---------------------------------------------------
    # UI scaffolding
    # ---------------------------------------------------

    def build_ui(self):

        # ---- Header: title + date on the left, actions + status on the right
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(24, 16))

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left")

        ctk.CTkLabel(
            title_col, text="Watch Dog", font=("Consolas", 28, "bold"), text_color=TEXT
        ).pack(anchor="w")

        self.date_label = ctk.CTkLabel(
            title_col, text=datetime.now().strftime("%A, %d %b %Y"),
            font=("Consolas", 12), text_color=MUTED
        )
        self.date_label.pack(anchor="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right")

        button_row = ctk.CTkFrame(actions, fg_color="transparent")
        button_row.pack(anchor="e")

        button_style = dict(
            height=30, font=("Consolas", 12), text_color="#e6e6e8",
            fg_color="#141416", hover_color="#232326",
            border_width=1, border_color=BUTTON_BORDER, corner_radius=8,
        )

        self.pause_button = ctk.CTkButton(
            button_row, text="\u23f8 Pause", width=88, command=self.toggle_tracking, **button_style
        )
        self.pause_button.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            button_row, text="Reset Today", width=104, command=self.reset_today, **button_style
        ).pack(side="right")

        self.status_label = ctk.CTkLabel(
            actions, text="\u25cf Tracking", font=("Consolas", 12), text_color=ACCENT
        )
        self.status_label.pack(anchor="e", pady=(8, 0))

        # ---- Body: [total | weekly chart] on top, full-width app list underneath
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=(0, 28))

        body.grid_columnconfigure(0, weight=5, uniform="top")
        body.grid_columnconfigure(1, weight=8, uniform="top")
        body.grid_rowconfigure(0, weight=0, minsize=250)
        body.grid_rowconfigure(1, weight=1)

        self.build_total_card(body)
        self.build_list_card(body)
        self.render_rows()
        self.build_summary_card(body)

    def _apply_tracking_state(self):
        if self.tracking:
            self.pause_button.configure(text="\u23f8 Pause")
            self.status_label.configure(text="\u25cf Tracking", text_color=ACCENT)
            self.status_pill.configure(text_color=ACCENT)
        else:
            self.pause_button.configure(text="\u25b6 Resume")
            self.status_label.configure(text="\u25cf Paused", text_color="#666666")
            self.status_pill.configure(text_color="#666666")

    def show_dependency_warning(self):
        warning = ctk.CTkLabel(
            self.list_frame,
            text=(
                "Missing dependencies.\n\n"
                "Run:  pip install pywin32 psutil\n"
                "then restart Rex."
            ),
            font=("Consolas", 14), text_color=ACCENT, justify="left"
        )
        warning.pack(pady=40)
        self.status_label.configure(text="\u25cf Not tracking", text_color="#666666")
        self.status_pill.configure(text_color="#666666")

    def show_card_menu(self):
        menu = tk.Menu(
            self, tearoff=0, bg=ROW, fg="#e6e6e8", bd=0, relief="flat",
            activebackground=ACCENT, activeforeground="#0d0d0d", font=("Consolas", 11)
        )
        menu.add_command(
            label="Pause tracking" if self.tracking else "Resume tracking",
            command=self.toggle_tracking
        )
        menu.add_command(label="Reset today", command=self.reset_today)

        x = self.menu_button.winfo_rootx()
        y = self.menu_button.winfo_rooty() + self.menu_button.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ---- Card 1: total screen time (big orange number + sparkline)

    def build_total_card(self, parent):
        card = ctk.CTkFrame(
            parent, fg_color=CARD, corner_radius=20,
            border_width=1, border_color=BORDER_NEUTRAL
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 14))

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(18, 0))

        ctk.CTkLabel(
            top, text="Total screen time today", font=("Consolas", 14), text_color="#b4b4bc"
        ).pack(side="left")

        self.menu_button = ctk.CTkButton(
            top, text="\u00b7\u00b7\u00b7", width=34, height=26, corner_radius=8,
            font=("Consolas", 13, "bold"), text_color="#c8c8d0",
            fg_color="#1d1d21", hover_color="#2a2a30",
            border_width=1, border_color=BUTTON_BORDER, command=self.show_card_menu
        )
        self.menu_button.pack(side="right")

        self.status_pill = ctk.CTkLabel(
            top, text="\u25cf", width=30, height=26, corner_radius=8,
            font=("Consolas", 12), text_color=ACCENT, fg_color="#1d1d21"
        )
        self.status_pill.pack(side="right", padx=(0, 6))

        number_row = ctk.CTkFrame(card, fg_color="transparent")
        number_row.pack(fill="x", padx=22, pady=(14, 0))

        self.total_label = ctk.CTkLabel(
            number_row, text="0s", font=("Consolas", 60, "bold"), text_color=ACCENT
        )
        self.total_label.pack(side="left")

        # time spent in browsers, shown in brackets next to the total
        self.total_web_label = ctk.CTkLabel(
            number_row, text="", font=("Consolas", 30, "bold"), text_color="#77706c"
        )
        self.total_web_label.pack(side="left", padx=(10, 0), pady=(24, 0))

        ctk.CTkLabel(
            card, text="active time, idle excluded", font=("Consolas", 12), text_color="#6f6f78"
        ).pack(anchor="w", padx=22)

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="both", expand=True, padx=22, pady=(4, 16))

        legend = ctk.CTkFrame(bottom, fg_color="transparent")
        legend.pack(side="left", anchor="s")

        for color, name in ((ACCENT, "Status"), ("#6b6b3a", "Trend"), ("#4cae6a", "Sparks")):
            row = ctk.CTkFrame(legend, fg_color="transparent")
            row.pack(anchor="w", pady=1)
            ctk.CTkLabel(row, text="\u25cf", font=("Consolas", 11), text_color=color, width=16).pack(side="left")
            ctk.CTkLabel(row, text=name, font=("Consolas", 12), text_color="#a8a8b0").pack(side="left")

        self.spark_canvas = tk.Canvas(
            bottom, width=170, height=80, bg=CARD, highlightthickness=0
        )
        self.spark_canvas.pack(side="right", anchor="s")

    # ---- Card 3: full-width "App Usage History" list (header + scrollable rows)

    def build_list_card(self, parent):
        card = ctk.CTkFrame(
            parent, fg_color=CARD_DARK, corner_radius=20,
            border_width=1, border_color=BORDER_NEUTRAL
        )
        card.grid(row=1, column=0, columnspan=2, sticky="nsew")

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 6))

        ctk.CTkLabel(
            header, text="App Usage History", font=("Consolas", 15, "bold"), text_color="#e6e6e8"
        ).pack(side="left")

        self.updated_label = ctk.CTkLabel(
            header, text="", font=("Consolas", 10), text_color="#6f6f78"
        )
        self.updated_label.pack(side="right")

        # Says why real icons aren't showing (empty when everything works)
        self.icon_hint = ctk.CTkLabel(
            header, text="", font=("Consolas", 10), text_color=ACCENT
        )
        self.icon_hint.pack(side="right", padx=(0, 14))

        if DEPENDENCIES_OK and not ICONS_OK:
            reason = ICON_IMPORT_ERROR or "a module is missing"
            fix = "pip install pillow" if "PIL" in reason else "pip install pywin32"
            self.icon_hint.configure(text=f"Real icons off: {reason} -> {fix}"[:110])

        self.list_frame = ctk.CTkScrollableFrame(
            card, fg_color="transparent", corner_radius=0,
            scrollbar_fg_color=CARD_DARK,
            scrollbar_button_color="#2c2c31",
            scrollbar_button_hover_color="#44444b"
        )
        self.list_frame.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 12))

    # ---- Card 2: weekly chart with legend (top right)

    def build_summary_card(self, parent):
        card = ctk.CTkFrame(
            parent, fg_color=CARD_DARK, corner_radius=20,
            border_width=1, border_color=BORDER_NEUTRAL
        )
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 14))

        legend = ctk.CTkFrame(card, fg_color="transparent")
        legend.pack(pady=(16, 0))

        def legend_item(color):
            ctk.CTkLabel(
                legend, text="\u25cf", font=("Consolas", 11), text_color=color, width=16
            ).pack(side="left", padx=(10, 0))
            label = ctk.CTkLabel(legend, text="", font=("Consolas", 12), text_color="#b4b4bc")
            label.pack(side="left", padx=(2, 10))
            return label

        self.weekly_total_label = legend_item(ACCENT)
        self.apps_time_label = legend_item(ACCENT)
        self.web_time_label = legend_item(BLUE)

        self.chart_canvas = tk.Canvas(
            card, width=520, height=170, bg=CARD_DARK, highlightthickness=0
        )
        self.chart_canvas.pack(fill="both", expand=True, padx=(16, 22), pady=(6, 14))
        self.chart_canvas.bind("<Configure>", self._on_chart_resize)

    # ---------------------------------------------------
    # Tracking loop
    # ---------------------------------------------------

    def tick(self):

        if not self.winfo_exists():
            return

        now = datetime.now()
        today_now = self.today_str()

        if today_now != self.today:
            self._end_active_session(now)
            self.commit_today_to_history()
            self.save_history()
            self.today = today_now
            self.date_label.configure(text=datetime.now().strftime("%A, %d %b %Y"))
            self.entries = {}
            self.clear_all_rows()
            self.save_data()

        if self.tracking and get_idle_seconds() < IDLE_THRESHOLD_SECONDS:
            key, display, kind, site, exe = get_active_window_info()

            if key:
                if exe:
                    self.exe_paths[key] = exe

                if key != self.active_key:
                    self._end_active_session(now)
                    self.active_key = key
                    self.active_since = now

                entry = self.entries.setdefault(
                    key, {"display": display, "kind": kind, "seconds": 0, "sites": {}, "sessions": []}
                )
                entry["seconds"] += POLL_INTERVAL_MS / 1000
                if exe:
                    entry["exe"] = exe      # saved with the entry so icons survive restarts
                if site:
                    entry["sites"][site] = entry["sites"].get(site, 0) + POLL_INTERVAL_MS / 1000
            else:
                self._end_active_session(now)
        else:
            self._end_active_session(now)

        self.tick_count += 1
        self.render_rows()

        if self.tick_count % SAVE_EVERY_N_TICKS == 0:
            self.save_data()
            self.save_history()
            self.refresh_summary()
            for key in list(self.expanded):
                if key in self.entries:
                    self.render_expanded_details(key, self.entries[key])

        self.after(POLL_INTERVAL_MS, self.tick)

    def _end_active_session(self, now):
        if self.active_key is None or self.active_since is None:
            return

        duration = (now - self.active_since).total_seconds()
        if duration >= MIN_SESSION_SECONDS:
            entry = self.entries.get(self.active_key)
            if entry is not None:
                sessions = entry.setdefault("sessions", [])
                sessions.append({"start": self.active_since.isoformat(), "end": now.isoformat()})
                if len(sessions) > MAX_SESSIONS_PER_APP:
                    del sessions[: len(sessions) - MAX_SESSIONS_PER_APP]

        self.active_key = None
        self.active_since = None

    def toggle_tracking(self):
        self.tracking = not self.tracking

        if not self.tracking:
            self._end_active_session(datetime.now())

        self._apply_tracking_state()

    def reset_today(self):
        self.active_key = None
        self.active_since = None
        self.entries = {}
        self.save_data()
        self.clear_all_rows()
        self.save_history()
        self.refresh_summary()

    # ---------------------------------------------------
    # Persistence - SQLite database

    def get_connection(self):
        return sqlite3.connect(DB_PATH)

    def setup_database(self):
        os.makedirs(REX_DATA_DIR, exist_ok=True)
        with self.get_connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS watchdog_entries (
                date TEXT NOT NULL, process_key TEXT NOT NULL, display TEXT NOT NULL,
                kind TEXT NOT NULL, seconds REAL NOT NULL, sites_json TEXT NOT NULL,
                sessions_json TEXT NOT NULL, exe_path TEXT, PRIMARY KEY (date, process_key)
            )""")
            # Databases created before icons were stored don't have exe_path yet
            columns = {row[1] for row in conn.execute("PRAGMA table_info(watchdog_entries)")}
            if "exe_path" not in columns:
                conn.execute("ALTER TABLE watchdog_entries ADD COLUMN exe_path TEXT")
            conn.execute("""CREATE TABLE IF NOT EXISTS watchdog_history (
                date TEXT PRIMARY KEY, total_seconds REAL NOT NULL,
                app_seconds REAL NOT NULL, web_seconds REAL NOT NULL
            )""")

    def migrate_legacy_data(self):
        if os.path.exists(LEGACY_DATA_FILE):
            try:
                with open(LEGACY_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == self.today:
                    self.entries = data.get("entries", {})
                    self.save_data()
                os.remove(LEGACY_DATA_FILE)
            except (json.JSONDecodeError, OSError):
                pass
        if os.path.exists(LEGACY_HISTORY_FILE):
            try:
                with open(LEGACY_HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                self.save_history()
                os.remove(LEGACY_HISTORY_FILE)
            except (json.JSONDecodeError, OSError):
                pass

    def load_data(self):
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT process_key, display, kind, seconds, sites_json, sessions_json, exe_path "
                "FROM watchdog_entries WHERE date = ?", (self.today,)
            ).fetchall()
        self.entries = {
            key: {"display": display, "kind": kind, "seconds": seconds,
                  "sites": json.loads(sites_json), "sessions": json.loads(sessions_json),
                  "exe": exe_path}
            for key, display, kind, seconds, sites_json, sessions_json, exe_path in rows
        }

    def resolve_missing_exe_paths(self):
        """
        Make sure every loaded entry has an exe path for its icon. Saved
        paths are used first; entries from before paths were stored are
        looked up from running processes in a single pass.
        """
        for key, entry in self.entries.items():
            if entry.get("exe"):
                self.exe_paths[key] = entry["exe"]

        missing = [key for key in self.entries if key not in self.exe_paths]
        for key, exe in find_running_exes(missing).items():
            self.exe_paths[key] = exe
            self.entries[key]["exe"] = exe

    def save_data(self):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM watchdog_entries WHERE date = ?", (self.today,))
            conn.executemany(
                "INSERT INTO watchdog_entries (date, process_key, display, kind, seconds, sites_json, sessions_json, exe_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(self.today, key, entry["display"], entry["kind"], entry["seconds"],
                  json.dumps(entry.get("sites", {})), json.dumps(entry.get("sessions", [])),
                  entry.get("exe"))
                 for key, entry in self.entries.items()]
            )

    def load_history(self):
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT date, total_seconds, app_seconds, web_seconds FROM watchdog_history ORDER BY date"
            ).fetchall()
        return {date: {"total_seconds": total, "app_seconds": app, "web_seconds": web}
                for date, total, app, web in rows}

    def save_history(self):
        if len(self.history) > HISTORY_KEEP_DAYS:
            for old_date in sorted(self.history.keys())[:-HISTORY_KEEP_DAYS]:
                del self.history[old_date]
        with self.get_connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO watchdog_history (date, total_seconds, app_seconds, web_seconds) "
                "VALUES (?, ?, ?, ?)",
                [(date, values["total_seconds"], values["app_seconds"], values["web_seconds"])
                 for date, values in self.history.items()]
            )

    def commit_today_to_history(self):
        app_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "app")
        web_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "browser")
        self.history[self.today] = {"total_seconds": app_seconds + web_seconds,
                                    "app_seconds": app_seconds, "web_seconds": web_seconds}

    # Rendering — app list (in-place updates, no destroy/rebuild)
    # ---------------------------------------------------

    def clear_all_rows(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.row_widgets = {}
        self.expanded = set()
        self._order = []
        self.empty_label = None

    def render_rows(self):

        total_seconds = sum(e["seconds"] for e in self.entries.values())
        self.total_label.configure(text=format_duration(total_seconds))

        web_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "browser")
        self.total_web_label.configure(
            text=f"({format_duration(web_seconds)})" if web_seconds > 0 else ""
        )

        if not self.entries:
            if self.row_widgets:
                self.clear_all_rows()
            if self.empty_label is None:
                self.empty_label = ctk.CTkLabel(
                    self.list_frame, text="No activity recorded yet.",
                    font=("Consolas", 14), text_color="#666666"
                )
                self.empty_label.pack(pady=40)
            return

        if self.empty_label is not None:
            self.empty_label.destroy()
            self.empty_label = None

        sorted_items = sorted(self.entries.items(), key=lambda kv: kv[1]["seconds"], reverse=True)
        sorted_keys = [k for k, _ in sorted_items]
        max_seconds = max((e["seconds"] for _, e in sorted_items), default=1) or 1

        for key, entry in sorted_items:
            if key not in self.row_widgets:
                self.create_row(key, entry)
            self.update_row(key, entry, max_seconds)

        if not self._order:
            self._order = sorted_keys
        elif sorted_keys != self._order and self.tick_count % REORDER_EVERY_N_TICKS == 0:
            for key in sorted_keys:
                self.row_widgets[key]["frame"].pack_forget()
            for key in sorted_keys:
                self.row_widgets[key]["frame"].pack(fill="x", padx=8, pady=4)
            self._order = sorted_keys

    def get_icon(self, key):
        """
        CTkImage of the app's real icon, or None (-> letter badge).
        Only successes are cached: while the exe path is still unknown we
        return None without giving up, so a later call can still succeed.
        """
        cached = self.icon_cache.get(key)
        if cached is not None:
            return cached

        if not ICONS_OK or key in self.icon_failed:
            return None

        exe = self.exe_paths.get(key)
        if not exe:
            return None

        pil_image = extract_exe_icon(exe, bg_rgb=_hex_to_rgb(ROW))
        if pil_image is None:
            self.icon_failed.add(key)
            # Only shout about it while no app has shown a real icon yet
            if not self.icon_cache:
                reason = ICON_PROBLEMS.get(exe, "unknown error")
                self.icon_hint.configure(text=f"Icon lookup failed for {key}: {reason}"[:110])
            return None

        image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(22, 22))
        self.icon_cache[key] = image
        if self.icon_hint.cget("text").startswith("Icon lookup failed"):
            self.icon_hint.configure(text="")
        return image

    def _show_icon(self, label, image):
        label.configure(image=image, text="", fg_color="transparent", width=34, height=28)

    def _show_badge(self, label, key, display):
        letter = (display[:1] or "?").upper()
        label.configure(
            text=letter, fg_color=badge_color(key), text_color="#ffffff",
            font=("Consolas", 14, "bold"), width=28, height=28, corner_radius=8
        )

    def create_row(self, key, entry):
        frame = ctk.CTkFrame(self.list_frame, fg_color=ROW, corner_radius=10)
        frame.pack(fill="x", padx=8, pady=4)
        frame.configure(cursor="hand2")

        top_line = ctk.CTkFrame(frame, fg_color="transparent")
        top_line.pack(fill="x")

        # Fixed-size slot so rows line up whether they show a real icon or a badge
        icon_slot = ctk.CTkFrame(top_line, fg_color="transparent", width=34, height=28)
        icon_slot.pack_propagate(False)
        icon_slot.pack(side="left", padx=(14, 4), pady=11)

        icon_label = ctk.CTkLabel(icon_slot, text="")
        icon_label.place(relx=0.5, rely=0.5, anchor="center")

        icon_image = self.get_icon(key)
        if icon_image is not None:
            self._show_icon(icon_label, icon_image)
        else:
            self._show_badge(icon_label, key, entry["display"])

        name_label = ctk.CTkLabel(
            top_line, text=entry["display"], font=("Consolas", 13, "bold"),
            text_color="#ececef", anchor="w", width=130
        )
        name_label.pack(side="left", padx=(6, 10), pady=11)

        time_label = ctk.CTkLabel(
            top_line, text="0s", font=("Consolas", 13), text_color=ACCENT, width=60, anchor="e"
        )
        time_label.pack(side="right", padx=(10, 16), pady=11)

        bar = ctk.CTkProgressBar(
            top_line, height=6, corner_radius=3, progress_color=ACCENT, fg_color="#2a2a2f"
        )
        bar.set(0)
        bar.pack(side="left", fill="x", expand=True, padx=10, pady=11)

        # Expanded panel — created now, only packed (shown) once the row is clicked
        details_frame = ctk.CTkFrame(frame, fg_color="transparent")

        self.row_widgets[key] = {
            "frame": frame,
            "top_line": top_line,
            "icon_label": icon_label,
            "has_icon": icon_image is not None,
            "name_label": name_label,
            "bar": bar,
            "time_label": time_label,
            "details_frame": details_frame,
        }

        self._bind_toggle(top_line, key)

    def _bind_toggle(self, widget, key):
        widget.bind("<Button-1>", lambda e: self.toggle_expand(key))
        for child in widget.winfo_children():
            self._bind_toggle(child, key)

    def update_row(self, key, entry, max_seconds):
        widgets = self.row_widgets[key]
        widgets["bar"].set(entry["seconds"] / max_seconds)
        widgets["time_label"].configure(text=format_duration(entry["seconds"]))

        # A row that started out with a badge switches to the real icon as soon as
        # we learn the app's exe path (e.g. the app comes to the foreground).
        if (not widgets["has_icon"] and ICONS_OK
                and key in self.exe_paths and key not in self.icon_failed):
            image = self.get_icon(key)
            if image is not None:
                self._show_icon(widgets["icon_label"], image)
                widgets["has_icon"] = True

    def toggle_expand(self, key):
        widgets = self.row_widgets[key]

        if key in self.expanded:
            self.expanded.discard(key)
            widgets["details_frame"].pack_forget()
        else:
            self.expanded.add(key)
            widgets["details_frame"].pack(fill="x", padx=(56, 16), pady=(0, 12))
            self.render_expanded_details(key, self.entries.get(key, {"sites": {}, "sessions": [], "kind": "app"}))

    def render_expanded_details(self, key, entry):
        container = self.row_widgets[key]["details_frame"]

        for child in container.winfo_children():
            child.destroy()

        # --- By site (browsers only) ---
        if entry.get("kind") == "browser":
            ctk.CTkLabel(
                container, text="By site", font=("Consolas", 11, "bold"), text_color=DIM
            ).pack(anchor="w", pady=(0, 4))

            sites = entry.get("sites", {})
            if not sites:
                ctk.CTkLabel(
                    container, text="No sites recorded yet.", font=("Consolas", 11), text_color=DIM
                ).pack(anchor="w", pady=(0, 8))
            else:
                max_site_seconds = max(sites.values()) or 1
                for site, seconds in sorted(sites.items(), key=lambda kv: kv[1], reverse=True):
                    row = ctk.CTkFrame(container, fg_color="transparent")
                    row.pack(fill="x", pady=3)

                    ctk.CTkLabel(
                        row, text=site, font=("Consolas", 12), text_color="#d0d0d6", anchor="w", width=130
                    ).pack(side="left")

                    ctk.CTkLabel(
                        row, text=format_duration(seconds), font=("Consolas", 12),
                        text_color="#7f93b8", width=55, anchor="e"
                    ).pack(side="right")

                    mini_bar = ctk.CTkProgressBar(
                        row, height=5, corner_radius=3, progress_color=BLUE, fg_color="#2a2a30"
                    )
                    mini_bar.set(seconds / max_site_seconds)
                    mini_bar.pack(side="left", fill="x", expand=True, padx=10)

        # --- Sessions (every app) ---
        ctk.CTkLabel(
            container, text="Open times today", font=("Consolas", 11, "bold"), text_color=DIM
        ).pack(anchor="w", pady=(8, 4))

        sessions = list(entry.get("sessions", []))
        if self.active_key == key and self.active_since is not None:
            sessions.append({"start": self.active_since.isoformat(), "end": None})

        if not sessions:
            ctk.CTkLabel(
                container, text="No open times recorded yet.", font=("Consolas", 11), text_color=DIM
            ).pack(anchor="w", pady=(0, 6))
            return

        for session in reversed(sessions[-20:]):
            start_dt = datetime.fromisoformat(session["start"])
            start_text = format_clock(start_dt)

            if session["end"] is None:
                end_text = "now"
                end_color = ACCENT
            else:
                end_text = format_clock(datetime.fromisoformat(session["end"]))
                end_color = "#aaaaaa"

            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text="\u2022", font=("Consolas", 11), text_color=DIM, width=14).pack(side="left")
            ctk.CTkLabel(
                row, text=start_text, font=("Consolas", 12), text_color="#aaaaaa"
            ).pack(side="left")
            ctk.CTkLabel(row, text="\u2013", font=("Consolas", 12), text_color=DIM).pack(side="left", padx=6)
            ctk.CTkLabel(
                row, text=end_text, font=("Consolas", 12), text_color=end_color
            ).pack(side="left")

    # ---------------------------------------------------
    # Rendering — summary card + charts
    # ---------------------------------------------------

    def refresh_summary(self):
        self.commit_today_to_history()

        dates = [datetime.now().date() - timedelta(days=i) for i in range(6, -1, -1)]
        totals = [self.history.get(d.strftime("%Y-%m-%d"), {}).get("total_seconds", 0) for d in dates]

        self.updated_label.configure(text=f"Updated {datetime.now().strftime('%H:%M')}")

        self.draw_weekly_chart(dates, totals)
        self.draw_sparkline(self.hourly_buckets())

        app_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "app")
        web_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "browser")
        self.apps_time_label.configure(text=f"Apps ({format_duration(app_seconds)})")
        self.web_time_label.configure(text=f"Web ({format_duration(web_seconds)})")

        self.weekly_total_label.configure(text=f"{format_duration(sum(totals))} total")

    def hourly_buckets(self, hours=12):
        """Seconds of activity in each of the last `hours` clock hours (oldest first)."""
        now = datetime.now()
        first = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1)
        buckets = [0.0] * hours

        spans = []
        for entry in self.entries.values():
            for session in entry.get("sessions", []):
                spans.append((session.get("start"), session.get("end")))
        if self.active_key is not None and self.active_since is not None:
            spans.append((self.active_since.isoformat(), now.isoformat()))

        for start_iso, end_iso in spans:
            try:
                start = datetime.fromisoformat(start_iso)
                end = datetime.fromisoformat(end_iso)
            except (TypeError, ValueError):
                continue
            for i in range(hours):
                hour_start = first + timedelta(hours=i)
                hour_end = hour_start + timedelta(hours=1)
                overlap = (min(end, hour_end) - max(start, hour_start)).total_seconds()
                if overlap > 0:
                    buckets[i] += overlap

        return buckets

    def draw_sparkline(self, values):
        canvas = self.spark_canvas
        canvas.delete("all")

        width = int(canvas["width"])
        height = int(canvas["height"])
        pad_x, pad_top, pad_bottom = 8, 12, 8
        base = height - pad_bottom

        n = len(values)
        if n < 2:
            return

        peak = max(values)
        points = []
        for i, value in enumerate(values):
            x = pad_x + i * (width - 2 * pad_x) / (n - 1)
            y = base - (value / peak * (height - pad_top - pad_bottom) if peak > 0 else 0)
            points.append((x, y))

        curve = [(x, min(max(y, pad_top), base)) for x, y in smooth_curve(points, 8)]

        area = _flatten(curve) + [curve[-1][0], base, curve[0][0], base]
        canvas.create_polygon(area, fill="#2a1608", outline="")
        canvas.create_line(
            _flatten(curve), fill=ACCENT if peak > 0 else "#3a3a40",
            width=2, capstyle="round", joinstyle="round"
        )

        if peak > 0:
            ex, ey = curve[-1]
            canvas.create_oval(ex - 6, ey - 6, ex + 6, ey + 6, fill="#3a1a08", outline="")
            canvas.create_oval(ex - 3, ey - 3, ex + 3, ey + 3, fill=ACCENT, outline="")

    def draw_weekly_chart(self, dates, totals):
        self._chart_data = (dates, totals)
        self._draw_chart_now()

    def _on_chart_resize(self, _event=None):
        if self._chart_job is not None:
            self.after_cancel(self._chart_job)
        self._chart_job = self.after(80, self._draw_chart_now)

    def _draw_chart_now(self):
        self._chart_job = None
        if not self._chart_data:
            return

        dates, totals = self._chart_data
        canvas = self.chart_canvas
        canvas.delete("all")

        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 100 or height < 80:       # not laid out yet
            width = int(canvas["width"])
            height = int(canvas["height"])

        left_margin, right_margin, top_margin, bottom_margin = 42, 8, 12, 28
        plot_width = width - left_margin - right_margin
        plot_height = height - top_margin - bottom_margin
        base_y = top_margin + plot_height

        # Y scale: pick a gridline step so there are at most ~4 lines
        max_seconds = max(totals) if totals else 0
        step = next((s for s in CHART_STEPS if max_seconds / s <= 3), CHART_STEPS[-1])
        scale_max = (int(max_seconds // step) + 1) * step

        for g in range(int(round(scale_max / step)) + 1):
            value = g * step
            y = base_y - (value / scale_max) * plot_height
            if g == 0:
                canvas.create_line(left_margin, y, left_margin + plot_width, y, fill="#303036")
            else:
                canvas.create_line(left_margin, y, left_margin + plot_width, y, fill="#25252a", dash=(2, 5))
            canvas.create_text(
                left_margin - 10, y, text=axis_label(value), fill="#6a6a72",
                font=("Consolas", 9), anchor="e"
            )

        n = len(dates)
        gap = max(10, plot_width * 0.035)
        bar_width = (plot_width - gap * (n + 1)) / n

        bars = []
        for i, seconds in enumerate(totals):
            x0 = left_margin + gap + i * (bar_width + gap)
            bar_h = (seconds / scale_max) * plot_height
            if seconds > 0:
                bar_h = max(bar_h, 3)
            bars.append((x0, x0 + bar_width, bar_h))

        # Bars (today's last, so its glow sits on top)
        for i, (x0, x1, bar_h) in enumerate(bars):
            if bar_h <= 0 or i == n - 1:
                continue
            draw_gradient_bar(canvas, x0, base_y - bar_h, x1, base_y, (96, 58, 36), (38, 29, 26), 6)

        if bars and bars[-1][2] > 0:
            x0, x1, bar_h = bars[-1]
            bg = _hex_to_rgb(CARD_DARK)
            for k in range(5, 0, -1):
                canvas.create_rectangle(
                    x0 - k * 2, base_y - bar_h - k * 2, x1 + k * 2, base_y,
                    fill=_blend(bg, (90, 36, 6), (6 - k) / 7), outline=""
                )
            draw_gradient_bar(canvas, x0, base_y - bar_h, x1, base_y, (255, 106, 26), (214, 64, 0), 8)

            r = min((x1 - x0) * 0.28, 14, bar_h * 0.25)
            if bar_h > 36 and r >= 5:
                cx, cy = (x0 + x1) / 2, base_y - bar_h / 2
                inner = r * 0.28
                canvas.create_polygon(
                    cx, cy - r, cx + inner, cy - inner, cx + r, cy, cx + inner, cy + inner,
                    cx, cy + r, cx - inner, cy + inner, cx - r, cy, cx - inner, cy - inner,
                    fill="#ff9d66", outline=""
                )

        # Day labels
        for i, (d, (x0, x1, _)) in enumerate(zip(dates, bars)):
            is_today = (i == n - 1)
            canvas.create_text(
                (x0 + x1) / 2, base_y + 14, text=d.strftime("%a"),
                fill=ACCENT if is_today else "#888890",
                font=("Consolas", 9, "bold" if is_today else "normal")
            )
