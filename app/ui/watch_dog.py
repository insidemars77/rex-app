"""
Watch Dog — local screen-time tracker for Rex.

Tracks how long the active window on this PC belongs to each app. Click
any app row to drag it open and see:
  - for browsers: time spent per site (with a bar), and
  - for every app: the actual open/close time ranges for today
    (e.g. "12:47 PM – 12:51 PM"), including the session in progress
    right now if that app is currently active.

Windows only. Requires:
    pip install pywin32 psutil

Notes / limitations:
- Site detection reads the browser's window title text, not the actual
  URL or open-tab list — it can only "see" whichever tab was frontmost
  at a given moment, accumulated over the day.
- Idle time (no keyboard/mouse input for 60s) is not counted, and ends
  whatever session was in progress.
- Daily totals are saved to watchdog_history.json so the weekly chart
  and "vs yesterday" comparison survive restarts.
"""

import customtkinter as ctk
import tkinter as tk
import ctypes
import json
import os
from datetime import datetime, timedelta

try:
    import win32gui
    import win32process
    import psutil
    DEPENDENCIES_OK = True
except ImportError:
    DEPENDENCIES_OK = False


# =========================================================
# Config
# =========================================================

DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "watchdog_data.json"
)
HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "watchdog_history.json"
)
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
    Returns (process_key, display_name, kind, site) for the foreground
    window, or (None, None, None, None) if it can't be determined.
    kind is "browser" or "app". site is only set when kind == "browser".
    """
    if not DEPENDENCIES_OK:
        return None, None, None, None

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None, None, None

        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process_name = psutil.Process(pid).name()
        process_key = process_name.lower()

        display = process_name[:-4] if process_key.endswith(".exe") else process_name

        if process_key in BROWSER_PROCESSES:
            site = extract_site_name(title) if title else None
            return process_key, display, "browser", site

        return process_key, display, "app", None

    except Exception:
        return None, None, None, None


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


# =========================================================
# Watch Dog page
# =========================================================

class WatchDog(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(
            master,
            fg_color="#0d0d0d",
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

        self.load_data()
        self.history = self.load_history()

        self.build_ui()
        self.refresh_summary()

        if DEPENDENCIES_OK:
            self.tick()
        else:
            self.show_dependency_warning()

    # ---------------------------------------------------
    # UI scaffolding
    # ---------------------------------------------------

    def build_ui(self):

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(25, 5))

        ctk.CTkLabel(
            header, text="Watch Dog", font=("Consolas", 28, "bold")
        ).pack(side="left")

        self.pause_button = ctk.CTkButton(
            header, text="⏸ Pause", width=100, font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333", command=self.toggle_tracking
        )
        self.pause_button.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            header, text="Reset Today", width=110, font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333", command=self.reset_today
        ).pack(side="right")

        sub = ctk.CTkFrame(self, fg_color="transparent")
        sub.pack(fill="x", padx=30, pady=(0, 10))

        ctk.CTkLabel(
            sub, text=datetime.now().strftime("%A, %d %b %Y"),
            font=("Consolas", 13), text_color="#777777"
        ).pack(side="left")

        self.status_label = ctk.CTkLabel(
            sub, text="● Tracking", font=("Consolas", 13), text_color="#ff5500"
        )
        self.status_label.pack(side="right")

        totals_card = ctk.CTkFrame(self, fg_color="#161616", corner_radius=10)
        totals_card.pack(fill="x", padx=30, pady=(0, 15))

        ctk.CTkLabel(
            totals_card, text="Total screen time today",
            font=("Consolas", 13), text_color="#888888"
        ).pack(anchor="w", padx=20, pady=(15, 0))

        self.total_label = ctk.CTkLabel(
            totals_card, text="0s", font=("Consolas", 26, "bold"), text_color="#ff5500"
        )
        self.total_label.pack(anchor="w", padx=20, pady=(0, 15))

        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color="#161616", corner_radius=10, height=230
        )
        self.list_frame.pack(fill="x", padx=30, pady=(0, 15))

        self.render_rows()

        self.build_summary_card()

    def show_dependency_warning(self):
        warning = ctk.CTkLabel(
            self.list_frame,
            text=(
                "Missing dependencies.\n\n"
                "Run:  pip install pywin32 psutil\n"
                "then restart Rex."
            ),
            font=("Consolas", 14), text_color="#ff5500", justify="left"
        )
        warning.pack(pady=40)
        self.status_label.configure(text="● Not tracking", text_color="#666666")

    def build_summary_card(self):
        card = ctk.CTkFrame(
            self, fg_color="#141414", corner_radius=18,
            border_width=1, border_color="#2a2a2a"
        )
        card.pack(fill="both", expand=True, padx=30, pady=(0, 30))

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=22, pady=(18, 0))

        ctk.CTkLabel(
            top_row, text="SCREEN TIME", font=("Consolas", 11, "bold"), text_color="#666666"
        ).pack(side="left")

        self.updated_label = ctk.CTkLabel(
            top_row, text="", font=("Consolas", 11), text_color="#555555"
        )
        self.updated_label.pack(side="right")

        number_row = ctk.CTkFrame(card, fg_color="transparent")
        number_row.pack(fill="x", padx=22, pady=(4, 0))

        self.summary_total_label = ctk.CTkLabel(
            number_row, text="0s", font=("Consolas", 32, "bold"), text_color="#ffffff"
        )
        self.summary_total_label.pack(side="left")

        self.summary_change_label = ctk.CTkLabel(
            number_row, text="", font=("Consolas", 12, "bold"), text_color="#666666"
        )
        self.summary_change_label.pack(side="left", padx=(12, 0), pady=(10, 0))

        # Weekly bar chart — proper axes now (hours on Y, day names on X)
        self.chart_canvas = tk.Canvas(
            card, width=490, height=160, bg="#141414", highlightthickness=0
        )
        self.chart_canvas.pack(fill="x", padx=22, pady=(14, 4))

        self.category_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.category_frame.pack(fill="x", padx=22, pady=(10, 4))

        _, self.apps_time_label = self.create_category_row(self.category_frame, "#ff5500", "Apps")
        _, self.web_time_label = self.create_category_row(self.category_frame, "#4d94ff", "Web")

        ctk.CTkFrame(card, height=1, fg_color="#262626").pack(fill="x", padx=22, pady=(10, 0))

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(10, 18))

        ctk.CTkLabel(
            footer, text="Weekly Total", font=("Consolas", 13), text_color="#999999"
        ).pack(side="left")

        self.weekly_total_label = ctk.CTkLabel(
            footer, text="0s", font=("Consolas", 13, "bold"), text_color="#ffffff"
        )
        self.weekly_total_label.pack(side="right")

    def create_category_row(self, parent, color, label_text):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)

        ctk.CTkLabel(row, text="●", font=("Consolas", 13), text_color=color, width=18).pack(side="left")
        ctk.CTkLabel(
            row, text=label_text, font=("Consolas", 13), text_color="#dddddd", anchor="w"
        ).pack(side="left")

        time_label = ctk.CTkLabel(row, text="0s", font=("Consolas", 13, "bold"), text_color="#ffffff")
        time_label.pack(side="right")

        return row, time_label

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
            self.entries = {}
            self.clear_all_rows()
            self.save_data()

        if self.tracking and get_idle_seconds() < IDLE_THRESHOLD_SECONDS:
            key, display, kind, site = get_active_window_info()

            if key:
                if key != self.active_key:
                    self._end_active_session(now)
                    self.active_key = key
                    self.active_since = now

                entry = self.entries.setdefault(
                    key, {"display": display, "kind": kind, "seconds": 0, "sites": {}, "sessions": []}
                )
                entry["seconds"] += POLL_INTERVAL_MS / 1000
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

        if self.tracking:
            self.pause_button.configure(text="⏸ Pause")
            self.status_label.configure(text="● Tracking", text_color="#ff5500")
        else:
            self._end_active_session(datetime.now())
            self.pause_button.configure(text="▶ Resume")
            self.status_label.configure(text="● Paused", text_color="#666666")

    def reset_today(self):
        self.active_key = None
        self.active_since = None
        self.entries = {}
        self.save_data()
        self.clear_all_rows()
        self.save_history()
        self.refresh_summary()

    # ---------------------------------------------------
    # Persistence — today's live data
    # ---------------------------------------------------

    def today_str(self):
        return datetime.now().strftime("%Y-%m-%d")

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("date") == self.today:
                entries = data.get("entries", {})
                valid = all("sites" in e and "kind" in e and "sessions" in e for e in entries.values())
                self.entries = entries if valid else {}

        except (json.JSONDecodeError, OSError):
            self.entries = {}

    def save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"date": self.today, "entries": self.entries}, f, indent=2)
        except OSError:
            pass

    # ---------------------------------------------------
    # Persistence — daily history (yesterday + weekly chart)
    # ---------------------------------------------------

    def load_history(self):
        if not os.path.exists(HISTORY_FILE):
            return {}

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save_history(self):
        if len(self.history) > HISTORY_KEEP_DAYS:
            for old_date in sorted(self.history.keys())[:-HISTORY_KEEP_DAYS]:
                del self.history[old_date]

        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except OSError:
            pass

    def commit_today_to_history(self):
        app_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "app")
        web_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "browser")
        self.history[self.today] = {
            "total_seconds": app_seconds + web_seconds,
            "app_seconds": app_seconds,
            "web_seconds": web_seconds,
        }

    # ---------------------------------------------------
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
                self.row_widgets[key]["frame"].pack(fill="x", padx=5, pady=5)
            self._order = sorted_keys

    def create_row(self, key, entry):
        frame = ctk.CTkFrame(self.list_frame, fg_color="#1d1d1d", corner_radius=8)
        frame.pack(fill="x", padx=5, pady=5)
        frame.configure(cursor="hand2")

        top_line = ctk.CTkFrame(frame, fg_color="transparent")
        top_line.pack(fill="x")

        icon = "🌐" if entry["kind"] == "browser" else "🖥️"
        ctk.CTkLabel(
            top_line, text=icon, font=("Consolas", 16), width=30
        ).pack(side="left", padx=(12, 2), pady=12)

        arrow_label = ctk.CTkLabel(
            top_line, text="▸", font=("Consolas", 12), text_color="#666666", width=16
        )
        arrow_label.pack(side="left")

        name_label = ctk.CTkLabel(
            top_line, text=entry["display"], font=("Consolas", 13, "bold"), anchor="w", width=150
        )
        name_label.pack(side="left", padx=(4, 10), pady=12)

        bar = ctk.CTkProgressBar(top_line, height=10, progress_color="#ff5500", fg_color="#2a2a2a")
        bar.set(0)
        bar.pack(side="left", fill="x", expand=True, padx=10, pady=12)

        time_label = ctk.CTkLabel(
            top_line, text="0s", font=("Consolas", 13), text_color="#ff5500", width=70, anchor="e"
        )
        time_label.pack(side="right", padx=(10, 15), pady=12)

        # Expanded panel — created now, only packed (shown) once the row is clicked
        details_frame = ctk.CTkFrame(frame, fg_color="transparent")

        self.row_widgets[key] = {
            "frame": frame,
            "top_line": top_line,
            "name_label": name_label,
            "bar": bar,
            "time_label": time_label,
            "arrow_label": arrow_label,
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

    def toggle_expand(self, key):
        widgets = self.row_widgets[key]

        if key in self.expanded:
            self.expanded.discard(key)
            widgets["details_frame"].pack_forget()
            widgets["arrow_label"].configure(text="▸")
        else:
            self.expanded.add(key)
            widgets["details_frame"].pack(fill="x", padx=(46, 12), pady=(0, 10))
            widgets["arrow_label"].configure(text="▾")
            self.render_expanded_details(key, self.entries.get(key, {"sites": {}, "sessions": [], "kind": "app"}))

    def render_expanded_details(self, key, entry):
        container = self.row_widgets[key]["details_frame"]

        for child in container.winfo_children():
            child.destroy()

        # --- By site (browsers only) ---
        if entry.get("kind") == "browser":
            ctk.CTkLabel(
                container, text="BY SITE", font=("Consolas", 10, "bold"), text_color="#555555"
            ).pack(anchor="w", pady=(2, 4))

            sites = entry.get("sites", {})
            if not sites:
                ctk.CTkLabel(
                    container, text="No sites recorded yet.", font=("Consolas", 11), text_color="#555555"
                ).pack(anchor="w", pady=(0, 8))
            else:
                max_site_seconds = max(sites.values()) or 1
                for site, seconds in sorted(sites.items(), key=lambda kv: kv[1], reverse=True):
                    row = ctk.CTkFrame(container, fg_color="transparent")
                    row.pack(fill="x", pady=3)

                    ctk.CTkLabel(
                        row, text=site, font=("Consolas", 12), text_color="#cccccc", anchor="w", width=130
                    ).pack(side="left")

                    mini_bar = ctk.CTkProgressBar(row, height=6, progress_color="#4d94ff", fg_color="#262626")
                    mini_bar.set(seconds / max_site_seconds)
                    mini_bar.pack(side="left", fill="x", expand=True, padx=8)

                    ctk.CTkLabel(
                        row, text=format_duration(seconds), font=("Consolas", 11),
                        text_color="#888888", width=55, anchor="e"
                    ).pack(side="right")

        # --- Sessions (every app) ---
        ctk.CTkLabel(
            container, text="OPEN TIMES TODAY", font=("Consolas", 10, "bold"), text_color="#555555"
        ).pack(anchor="w", pady=(8, 4))

        sessions = list(entry.get("sessions", []))
        if self.active_key == key and self.active_since is not None:
            sessions.append({"start": self.active_since.isoformat(), "end": None})

        if not sessions:
            ctk.CTkLabel(
                container, text="No open times recorded yet.", font=("Consolas", 11), text_color="#555555"
            ).pack(anchor="w", pady=(0, 6))
            return

        for session in reversed(sessions[-20:]):
            start_dt = datetime.fromisoformat(session["start"])
            start_text = format_clock(start_dt)

            if session["end"] is None:
                end_text = "now"
                end_color = "#ff5500"
            else:
                end_text = format_clock(datetime.fromisoformat(session["end"]))
                end_color = "#aaaaaa"

            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text="•", font=("Consolas", 11), text_color="#555555", width=14).pack(side="left")
            ctk.CTkLabel(
                row, text=start_text, font=("Consolas", 12), text_color="#aaaaaa"
            ).pack(side="left")
            ctk.CTkLabel(row, text="–", font=("Consolas", 12), text_color="#555555").pack(side="left", padx=6)
            ctk.CTkLabel(
                row, text=end_text, font=("Consolas", 12), text_color=end_color
            ).pack(side="left")

    # ---------------------------------------------------
    # Rendering — screen-time summary card
    # ---------------------------------------------------

    def refresh_summary(self):
        self.commit_today_to_history()

        dates = [datetime.now().date() - timedelta(days=i) for i in range(6, -1, -1)]
        totals = [self.history.get(d.strftime("%Y-%m-%d"), {}).get("total_seconds", 0) for d in dates]

        today_total = totals[-1]
        yesterday_total = totals[-2] if len(totals) >= 2 else 0

        self.summary_total_label.configure(text=format_duration(today_total))

        if yesterday_total > 0:
            pct = round((today_total - yesterday_total) / yesterday_total * 100)
            if pct >= 0:
                self.summary_change_label.configure(text=f"▲ {pct}% from yesterday", text_color="#ff5500")
            else:
                self.summary_change_label.configure(text=f"▼ {abs(pct)}% from yesterday", text_color="#4d94ff")
        else:
            self.summary_change_label.configure(text="No data for yesterday yet", text_color="#666666")

        self.updated_label.configure(text=f"Updated {datetime.now().strftime('%H:%M')}")

        self.draw_weekly_chart(dates, totals)

        app_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "app")
        web_seconds = sum(e["seconds"] for e in self.entries.values() if e["kind"] == "browser")
        self.apps_time_label.configure(text=format_duration(app_seconds))
        self.web_time_label.configure(text=format_duration(web_seconds))

        self.weekly_total_label.configure(text=format_duration(sum(totals)))

    def draw_weekly_chart(self, dates, totals):
        canvas = self.chart_canvas
        canvas.delete("all")

        width = int(canvas["width"])
        height = int(canvas["height"])

        left_margin = 38
        bottom_margin = 26
        top_margin = 10
        right_margin = 10

        plot_width = width - left_margin - right_margin
        plot_height = height - top_margin - bottom_margin

        hours = [t / 3600 for t in totals]
        max_hours = max(hours) if hours else 0

        # Pick a "nice" step for the hour gridlines based on the data range
        if max_hours <= 1:
            step = 0.5
        elif max_hours <= 4:
            step = 1
        elif max_hours <= 8:
            step = 2
        else:
            step = 4

        scale_max = step
        while scale_max < max_hours:
            scale_max += step

        # Gridlines + Y-axis hour labels
        grid_count = int(round(scale_max / step))
        for g in range(grid_count + 1):
            value = g * step
            y = top_margin + plot_height - (value / scale_max) * plot_height
            canvas.create_line(left_margin, y, left_margin + plot_width, y, fill="#232323")
            label = f"{value:g}h"
            canvas.create_text(
                left_margin - 8, y, text=label, fill="#666666",
                font=("Consolas", 9), anchor="e"
            )

        # X axis baseline
        base_y = top_margin + plot_height
        canvas.create_line(left_margin, base_y, left_margin + plot_width, base_y, fill="#333333")

        n = len(dates)
        gap = 12
        bar_width = (plot_width - gap * (n + 1)) / n

        for i, (d, total_h) in enumerate(zip(dates, hours)):
            x0 = left_margin + gap + i * (bar_width + gap)
            x1 = x0 + bar_width
            bar_h = (total_h / scale_max) * plot_height if scale_max else 0
            bar_h = max(bar_h, 2) if total_h > 0 else 0
            y1 = base_y
            y0 = y1 - bar_h

            is_today = (i == n - 1)
            color = "#ff5500" if is_today else "#3a3a3a"

            if bar_h > 0:
                canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

            canvas.create_text(
                (x0 + x1) / 2, base_y + 13,
                text=d.strftime("%a"),
                fill="#ff5500" if is_today else "#888888",
                font=("Consolas", 9, "bold" if is_today else "normal")
            )
