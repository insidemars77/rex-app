"""
Notification Centre for Rex.

The central inbox for everything Rex wants to tell the user.

Other modules push notifications with:

    from ui.notification_centre import NotificationCentre
    NotificationCentre.push("Commit done", "main updated", "Git")

push() is thread-safe and works even before the page has been created (the
notification is stored and shown when the page loads). An identical unread
notification pushed again within DEDUPE_SECONDS only refreshes its time, so a
noisy module cannot flood the inbox.

For a badge on the side panel:

    NotificationCentre.unread_count()                  # current number
    NotificationCentre.subscribe(lambda n: ...)        # called on the UI thread
                                                       # whenever the page refreshes

Storage: SQLite table `notifications` in %APPDATA%\\Rex\\rex.db.
Older / incomplete schemas are migrated automatically without data loss.
"""

import json
import os
import sqlite3
import threading
import time
import uuid
import zlib
from contextlib import contextmanager
from datetime import datetime

import customtkinter as ctk

try:
    import winsound
except ImportError:  # not Windows
    winsound = None


class NotificationCentre(ctk.CTkFrame):

    # ---- shared instance (set while a page exists) ----
    instance = None

    # ---- behaviour ----
    DEDUPE_SECONDS = 10          # identical unread push inside this window is merged
    ALERT_SOUND = True           # system beep for "Alert" notifications (Windows)
    AUTO_REFRESH_MS = 30000      # keeps "5m ago" labels fresh while the page is visible
    UNDO_SECONDS = 8
    LONG_MESSAGE_CHARS = 160

    # ---- storage ----
    DB_DIR = os.path.join(
        os.getenv("APPDATA") or os.path.expanduser("~"), "Rex"
    )
    DB_PATH = os.path.join(DB_DIR, "rex.db")
    LEGACY_FILES = [
        os.path.join("data", "notifications.json"),
        os.path.join(DB_DIR, "notifications.json"),
    ]
    MAX_STORED = 1000
    MAX_DISPLAYED = 200

    REQUIRED_COLUMNS = ("id", "title", "message", "type", "time", "read", "timestamp")
    CREATE_SQL = """
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'System',
            time TEXT NOT NULL DEFAULT '',
            read INTEGER NOT NULL DEFAULT 0,
            timestamp REAL NOT NULL DEFAULT 0
        )
    """
    INSERT_SQL = (
        "INSERT OR IGNORE INTO notifications "
        "(id, title, message, type, time, read, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    SELECT_COLUMNS = ("id", "title", "message", "type", "time", "read", "timestamp")

    _schema_lock = threading.Lock()
    _schema_ready = False
    _listeners = []

    # ---- look & feel ----
    BG = "#0d0d0d"
    PANEL = "#141414"
    CARD_UNREAD = "#252525"
    CARD_READ = "#1a1a1a"
    BORDER = "#2a2a2a"
    ACCENT = "#ff5500"
    ACCENT_HOVER = "#cc4400"

    FILTERS = ["All", "System", "Git", "Workspace", "Browser", "Calendar", "Alert"]
    TYPE_COLORS = {
        "System": "#ff5500",
        "Git": "#a855f7",
        "Workspace": "#22c55e",
        "Browser": "#3b82f6",
        "Calendar": "#eab308",
        "Alert": "#ef4444",
    }
    CUSTOM_PALETTE = ["#14b8a6", "#ec4899", "#f97316", "#06b6d4", "#84cc16", "#8b5cf6"]

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self, master):
        super().__init__(master, fg_color=self.BG, corner_radius=0)

        self.filter_type = "All"
        self.search_text = ""
        self.unread_only = False
        self.filter_buttons = {}
        self.db_error = ""

        self._expanded = set()
        self._undo_records = []
        self._undo_after = None
        self._search_after = None
        self._tick_id = None

        try:
            self.setup_database()
            self.import_legacy_files()
        except (sqlite3.Error, OSError) as error:
            self.db_error = str(error)

        self.build_ui()
        self.refresh_list(keep_scroll=False)

        NotificationCentre.instance = self
        self._tick_id = self.after(self.AUTO_REFRESH_MS, self._tick)

    def destroy(self):
        if NotificationCentre.instance is self:
            NotificationCentre.instance = None
        for attr in ("_undo_after", "_search_after", "_tick_id"):
            handle = getattr(self, attr, None)
            if handle is not None:
                try:
                    self.after_cancel(handle)
                except Exception:
                    pass
        super().destroy()

    def _tick(self):
        self._tick_id = None
        try:
            if not self.winfo_exists():
                return
            if self.winfo_ismapped():
                self.refresh_list()
            self._tick_id = self.after(self.AUTO_REFRESH_MS, self._tick)
        except Exception:
            pass

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
        """Create the table, or migrate an older/incomplete one safely."""
        with cls._schema_lock:
            if cls._schema_ready and os.path.exists(cls.DB_PATH):
                return

            with cls._db() as conn:
                info = conn.execute("PRAGMA table_info(notifications)").fetchall()
                if not info:
                    conn.execute(cls.CREATE_SQL)
                elif cls._needs_rebuild(info):
                    cls._rebuild_table(conn)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_notifications_timestamp "
                    "ON notifications(timestamp DESC)"
                )

            cls._schema_ready = True

    @classmethod
    def _needs_rebuild(cls, info):
        names = {row[1] for row in info}
        if not set(cls.REQUIRED_COLUMNS).issubset(names):
            return True
        id_row = next((row for row in info if row[1] == "id"), None)
        if id_row is None or not id_row[5]:          # id must be the primary key
            return True
        id_type = (id_row[2] or "").upper()
        return not ("TEXT" in id_type or "CHAR" in id_type)

    @classmethod
    def _rebuild_table(cls, conn):
        """Copy every old row into a fresh table. The old table is dropped only
        after the copy succeeded, all inside one transaction."""
        conn.execute("BEGIN IMMEDIATE")
        legacy = f"notifications_legacy_{int(time.time())}"
        conn.execute(f"ALTER TABLE notifications RENAME TO {legacy}")
        conn.execute(cls.CREATE_SQL)

        old = conn.execute(f"SELECT * FROM {legacy}")
        columns = [d[0] for d in old.description]
        seen = set()
        for values in old.fetchall():
            record = cls._normalize(dict(zip(columns, values)))
            if record["id"] in seen:
                record["id"] = str(uuid.uuid4())
            seen.add(record["id"])
            conn.execute(cls.INSERT_SQL, cls._record_tuple(record))

        conn.execute(f"DROP TABLE {legacy}")

    # =========================================================
    # RECORD HELPERS
    # =========================================================

    @staticmethod
    def _first(raw, *keys):
        for key in keys:
            if key in raw and raw[key] is not None and raw[key] != "":
                return raw[key]
        return None

    @staticmethod
    def _parse_timestamp(value):
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value) if value > 0 else None
        text = str(value).strip()
        if not text:
            return None
        try:
            number = float(text)
            return number if number > 0 else None
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(text, fmt).timestamp()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return None

    @staticmethod
    def _to_bool(value):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "y", "read")
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return bool(value)

    @classmethod
    def _normalize(cls, raw):
        """Turn any dict-like legacy/partial row into a valid record."""
        title = cls._first(raw, "title", "subject", "name")
        message = cls._first(raw, "message", "body", "text", "content", "description")
        type_ = cls._first(raw, "type", "category", "kind")
        time_text = cls._first(raw, "time", "created_at", "date")
        stamp = cls._parse_timestamp(cls._first(raw, "timestamp", "created", "ts"))
        if stamp is None:
            stamp = cls._parse_timestamp(time_text)
        if stamp is None:
            stamp = 0.0

        time_text = str(time_text) if time_text is not None else ""
        if not time_text and stamp > 0:
            time_text = datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")

        record_id = cls._first(raw, "id", "uuid")
        return {
            "id": str(record_id) if record_id is not None else str(uuid.uuid4()),
            "title": str(title) if title is not None else "Notification",
            "message": str(message) if message is not None else "",
            "type": cls._canonical_type(type_),
            "time": time_text,
            "read": cls._to_bool(cls._first(raw, "read", "is_read", "seen") or 0),
            "timestamp": float(stamp),
        }

    @classmethod
    def _canonical_type(cls, value):
        text = str(value).strip() if value is not None else ""
        if not text:
            return "System"
        for known in cls.TYPE_COLORS:
            if known.lower() == text.lower():
                return known
        return text[:30]

    @staticmethod
    def _record_tuple(record):
        return (
            record["id"], record["title"], record["message"], record["type"],
            record["time"], int(bool(record["read"])), float(record["timestamp"]),
        )

    @classmethod
    def _new_record(cls, title, message, type_):
        now = datetime.now()
        return {
            "id": str(uuid.uuid4()),
            "title": (str(title).strip() or "Notification") if title is not None else "Notification",
            "message": str(message) if message is not None else "",
            "type": cls._canonical_type(type_),
            "time": now.strftime("%Y-%m-%d %H:%M"),
            "read": False,
            "timestamp": now.timestamp(),
        }

    # =========================================================
    # PUBLIC API
    # =========================================================

    @classmethod
    def push(cls, title, message="", type_="System", dedupe_seconds=None):
        """Add a notification. Safe to call from any module or thread.
        Returns the notification id, or None if it could not be stored."""
        window = cls.DEDUPE_SECONDS if dedupe_seconds is None else dedupe_seconds
        record = cls._new_record(title, message, type_)
        is_new = True

        try:
            cls.setup_database()
            with cls._db() as conn:
                existing = None
                if window and window > 0:
                    existing = conn.execute(
                        "SELECT id FROM notifications "
                        "WHERE title = ? AND message = ? AND type = ? COLLATE NOCASE "
                        "AND (read = 0 OR read IS NULL) AND timestamp >= ? "
                        "ORDER BY timestamp DESC LIMIT 1",
                        (record["title"], record["message"], record["type"],
                         record["timestamp"] - window),
                    ).fetchone()

                if existing:
                    is_new = False
                    record["id"] = existing[0]
                    conn.execute(
                        "UPDATE notifications SET timestamp = ?, time = ? WHERE id = ?",
                        (record["timestamp"], record["time"], record["id"]),
                    )
                else:
                    conn.execute(cls.INSERT_SQL, cls._record_tuple(record))
                    conn.execute(
                        "DELETE FROM notifications WHERE id NOT IN ("
                        "SELECT id FROM notifications "
                        "ORDER BY timestamp DESC, rowid DESC LIMIT ?)",
                        (cls.MAX_STORED,),
                    )
        except (sqlite3.Error, OSError):
            return None

        if is_new and cls.ALERT_SOUND and winsound is not None and record["type"] == "Alert":
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

        page = cls.instance
        if page is not None:
            try:
                page.after(0, page._refresh_from_push)
            except Exception:
                pass
        return record["id"]

    @classmethod
    def unread_count(cls):
        try:
            cls.setup_database()
            with cls._db() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM notifications WHERE read = 0 OR read IS NULL"
                ).fetchone()
            return int(row[0])
        except (sqlite3.Error, OSError):
            return 0

    @classmethod
    def subscribe(cls, callback):
        """callback(unread_count) runs on the UI thread whenever the page refreshes."""
        if callback not in cls._listeners:
            cls._listeners.append(callback)

    @classmethod
    def unsubscribe(cls, callback):
        if callback in cls._listeners:
            cls._listeners.remove(callback)

    @classmethod
    def _notify_listeners(cls, unread):
        for callback in list(cls._listeners):
            try:
                callback(unread)
            except Exception:
                pass

    def _refresh_from_push(self):
        try:
            if self.winfo_exists():
                self.refresh_list()
        except Exception:
            pass

    # =========================================================
    # LEGACY JSON IMPORT
    # =========================================================

    def import_legacy_files(self):
        for path in self.LEGACY_FILES:
            if not os.path.isfile(path):
                continue

            items = None
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    data = data.get("notifications", [])
                if isinstance(data, list):
                    items = [item for item in data if isinstance(item, dict)]
            except (OSError, ValueError):
                items = None

            # Rename first: if that works the file can never be imported twice.
            suffix = ".imported" if items is not None else ".corrupt"
            try:
                os.replace(path, path + suffix)
            except OSError:
                continue

            if not items:
                continue

            try:
                with self._db() as conn:
                    for item in items:
                        record = self._normalize(item)
                        conn.execute(self.INSERT_SQL, self._record_tuple(record))
            except sqlite3.Error:
                pass

    # =========================================================
    # QUERIES / ACTIONS
    # =========================================================

    def _build_where(self):
        conditions, params = [], []
        if self.filter_type != "All":
            conditions.append("type = ? COLLATE NOCASE")
            params.append(self.filter_type)
        if self.unread_only:
            conditions.append("(read = 0 OR read IS NULL)")
        if self.search_text:
            escaped = (self.search_text.replace("\\", "\\\\")
                       .replace("%", "\\%").replace("_", "\\_"))
            like = f"%{escaped}%"
            conditions.append(
                "(title LIKE ? ESCAPE '\\' OR message LIKE ? ESCAPE '\\' "
                "OR type LIKE ? ESCAPE '\\')"
            )
            params.extend([like, like, like])
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return where, tuple(params)

    def query_state(self):
        """Returns (total, unread, showing, unread_by_type, notifications)."""
        self.setup_database()
        where, params = self._build_where()
        with self._db() as conn:
            total, unread = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(CASE WHEN read = 0 OR read IS NULL "
                "THEN 1 ELSE 0 END), 0) FROM notifications"
            ).fetchone()

            unread_by_type = {}
            for type_, count in conn.execute(
                "SELECT type, COUNT(*) FROM notifications "
                "WHERE read = 0 OR read IS NULL GROUP BY type COLLATE NOCASE"
            ).fetchall():
                unread_by_type[str(type_).lower()] = count

            showing = conn.execute(
                f"SELECT COUNT(*) FROM notifications {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                "SELECT id, title, message, type, time, read, timestamp "
                f"FROM notifications {where} "
                "ORDER BY timestamp DESC, rowid DESC LIMIT ?",
                params + (self.MAX_DISPLAYED,),
            ).fetchall()

        notifications = [self._normalize(dict(zip(self.SELECT_COLUMNS, row))) for row in rows]
        return total, unread, showing, unread_by_type, notifications

    def fetch_all_records(self):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT id, title, message, type, time, read, timestamp "
                "FROM notifications ORDER BY timestamp DESC, rowid DESC"
            ).fetchall()
        return [self._normalize(dict(zip(self.SELECT_COLUMNS, row))) for row in rows]

    def _execute(self, sql, params=()):
        try:
            self.setup_database()
            with self._db() as conn:
                conn.execute(sql, params)
            return True
        except sqlite3.Error as error:
            self.db_error = str(error)
            return False

    def mark_as_read(self, notif):
        self._execute("UPDATE notifications SET read = 1 WHERE id = ?", (notif["id"],))
        self.refresh_list()

    def mark_all_read(self):
        self._execute("UPDATE notifications SET read = 1")
        self.refresh_list()

    def delete_notification(self, notif):
        if self._execute("DELETE FROM notifications WHERE id = ?", (notif["id"],)):
            self.show_undo("Notification deleted", [notif])
        self.refresh_list()

    def clear_all(self):
        try:
            records = self.fetch_all_records()
        except sqlite3.Error:
            return
        if not records:
            return
        if self._execute("DELETE FROM notifications"):
            count = len(records)
            self.show_undo(
                f"Cleared {count} notification{'s' if count != 1 else ''}", records
            )
        self.refresh_list(keep_scroll=False)

    # ---------- undo ----------

    def show_undo(self, text, records):
        self._undo_records = records
        self.snackbar_label.configure(text=text)
        if self._undo_after is not None:
            try:
                self.after_cancel(self._undo_after)
            except Exception:
                pass
        self.snackbar.pack(
            side="bottom", fill="x", padx=28, pady=(0, 14), before=self.list_frame
        )
        self._undo_after = self.after(self.UNDO_SECONDS * 1000, self.hide_undo)

    def hide_undo(self):
        self._undo_after = None
        self._undo_records = []
        try:
            self.snackbar.pack_forget()
        except Exception:
            pass

    def undo(self):
        records = list(self._undo_records)
        if records:
            try:
                with self._db() as conn:
                    for record in records:
                        conn.execute(self.INSERT_SQL, self._record_tuple(record))
            except sqlite3.Error as error:
                self.db_error = str(error)
        if self._undo_after is not None:
            try:
                self.after_cancel(self._undo_after)
            except Exception:
                pass
        self.hide_undo()
        self.refresh_list()

    # =========================================================
    # TIME FORMATTING
    # =========================================================

    @staticmethod
    def format_time(timestamp, fallback=""):
        if not timestamp or timestamp <= 0:
            return fallback
        diff = time.time() - timestamp
        if diff < 0:
            return fallback
        if diff < 60:
            return "just now"
        if diff < 3600:
            return f"{int(diff // 60)}m ago"
        if diff < 86400:
            return f"{int(diff // 3600)}h ago"
        return datetime.fromtimestamp(timestamp).strftime("%d %b, %H:%M")

    @staticmethod
    def day_label(timestamp):
        if not timestamp or timestamp <= 0:
            return "Earlier"
        day = datetime.fromtimestamp(timestamp).date()
        today = datetime.now().date()
        delta = (today - day).days
        if delta == 0:
            return "Today"
        if delta == 1:
            return "Yesterday"
        if day.year == today.year:
            return datetime.fromtimestamp(timestamp).strftime("%A, %d %b")
        return datetime.fromtimestamp(timestamp).strftime("%d %b %Y")

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):
        # ---------- header ----------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(22, 8))

        ctk.CTkLabel(
            header, text="Notification Centre", font=("Consolas", 26, "bold"),
            text_color="#ffffff"
        ).pack(side="left")

        ctk.CTkLabel(
            header, text="Stay on top of what Rex is doing",
            font=("Consolas", 12), text_color="#777777"
        ).pack(side="left", padx=(16, 0), pady=(7, 0))

        button_row = ctk.CTkFrame(header, fg_color="transparent")
        button_row.pack(side="right")

        self.mark_all_btn = ctk.CTkButton(
            button_row, text="Mark all read", width=120, height=32,
            font=("Consolas", 12), fg_color="#222222", hover_color="#333333",
            command=self.mark_all_read
        )
        self.mark_all_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = ctk.CTkButton(
            button_row, text="Clear all", width=90, height=32,
            font=("Consolas", 12), fg_color="#222222", hover_color="#ef4444",
            command=self.clear_all
        )
        self.clear_btn.pack(side="left")

        # ---------- search + unread toggle ----------
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", padx=28, pady=(0, 8))

        self.search_entry = ctk.CTkEntry(
            search_row, height=32, font=("Consolas", 13),
            placeholder_text="Search notifications…"
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        self.unread_switch = ctk.CTkSwitch(
            search_row, text="Unread only", font=("Consolas", 12),
            progress_color=self.ACCENT, command=self._toggle_unread
        )
        self.unread_switch.pack(side="right", padx=(16, 0))

        # ---------- filters ----------
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(fill="x", padx=28, pady=(0, 8))

        for name in self.FILTERS:
            button = ctk.CTkButton(
                filter_row, text=name, width=84, height=28,
                font=("Consolas", 11), fg_color="#1a1a1a", hover_color="#2a2a2a",
                command=lambda value=name: self.set_filter(value)
            )
            button.pack(side="left", padx=(0, 6))
            self.filter_buttons[name] = button
        self.update_filter_buttons({}, 0)

        # ---------- stats ----------
        self.stats_label = ctk.CTkLabel(
            self, text="", font=("Consolas", 12), text_color="#888888", anchor="w"
        )
        self.stats_label.pack(fill="x", padx=30, pady=(0, 8))

        # ---------- undo bar (shown on demand, above the list) ----------
        self.snackbar = ctk.CTkFrame(
            self, fg_color="#222222", corner_radius=10,
            border_width=1, border_color="#333333"
        )
        self.snackbar_label = ctk.CTkLabel(
            self.snackbar, text="", font=("Consolas", 12), text_color="#dddddd"
        )
        self.snackbar_label.pack(side="left", padx=16, pady=10)
        ctk.CTkButton(
            self.snackbar, text="Undo", width=70, height=28,
            font=("Consolas", 12, "bold"), fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER, command=self.undo
        ).pack(side="right", padx=12, pady=8)

        # ---------- list ----------
        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color=self.PANEL, corner_radius=14,
            border_width=1, border_color="#252525"
        )
        self.list_frame.pack(fill="both", expand=True, padx=28, pady=(0, 20))

    # ---------- search / filters ----------

    def _on_search_key(self, event):
        if getattr(event, "keysym", "") == "Escape":
            self.search_entry.delete(0, "end")
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(220, self._apply_search)

    def _apply_search(self):
        self._search_after = None
        text = self.search_entry.get().strip()
        if text == self.search_text:
            return
        self.search_text = text
        self.refresh_list(keep_scroll=False)

    def _toggle_unread(self):
        self.unread_only = bool(self.unread_switch.get())
        self.refresh_list(keep_scroll=False)

    def set_filter(self, filter_type):
        self.filter_type = filter_type
        self.refresh_list(keep_scroll=False)

    def update_filter_buttons(self, unread_by_type, total_unread):
        for name, button in self.filter_buttons.items():
            count = total_unread if name == "All" else unread_by_type.get(name.lower(), 0)
            label = f"{name} {count}" if count else name
            if name == self.filter_type:
                button.configure(text=label, fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER)
            else:
                button.configure(text=label, fg_color="#1a1a1a", hover_color="#2a2a2a")

    def accent_for(self, type_):
        if type_ in self.TYPE_COLORS:
            return self.TYPE_COLORS[type_]
        index = zlib.crc32(type_.lower().encode("utf-8")) % len(self.CUSTOM_PALETTE)
        return self.CUSTOM_PALETTE[index]

    # ---------- list rendering ----------

    def refresh_list(self, keep_scroll=True):
        saved_position = 0.0
        canvas = getattr(self.list_frame, "_parent_canvas", None)
        if keep_scroll and canvas is not None:
            try:
                saved_position = canvas.yview()[0]
            except Exception:
                saved_position = 0.0

        try:
            total, unread, showing, unread_by_type, notifications = self.query_state()
            error = ""
        except sqlite3.Error as db_error:
            total = unread = showing = 0
            unread_by_type = {}
            notifications = []
            error = str(db_error)

        for widget in self.list_frame.winfo_children():
            widget.destroy()

        self.update_filter_buttons(unread_by_type, unread)

        if error:
            self.stats_label.configure(text="Notification database unavailable")
            self._build_empty_state("Could not read notifications.", error[:120])
            return

        self.stats_label.configure(
            text=f"{total} total  •  {unread} unread  •  showing {showing}"
        )
        self.mark_all_btn.configure(state="normal" if unread else "disabled")
        self.clear_btn.configure(state="normal" if total else "disabled")
        self._notify_listeners(unread)

        if not notifications:
            if self.search_text:
                self._build_empty_state("No matches", f"Nothing found for “{self.search_text}”.")
            elif self.unread_only:
                self._build_empty_state("No unread notifications", "You're all caught up.")
            elif self.filter_type != "All":
                self._build_empty_state(
                    f"No {self.filter_type} notifications", "Nothing in this category yet."
                )
            else:
                self._build_empty_state(
                    "You're all caught up", "New notifications from Rex will appear here."
                )
            return

        last_day = None
        for notif in notifications:
            day = self.day_label(notif["timestamp"])
            if day != last_day:
                ctk.CTkLabel(
                    self.list_frame, text=day.upper(), font=("Consolas", 10, "bold"),
                    text_color="#666666", anchor="w"
                ).pack(fill="x", padx=10, pady=(10, 0))
                last_day = day
            self.create_notification_card(notif)

        if showing > len(notifications):
            ctk.CTkLabel(
                self.list_frame,
                text=f"Showing the newest {len(notifications)} of {showing}",
                font=("Consolas", 11), text_color="#666666"
            ).pack(pady=(8, 12))

        if keep_scroll and saved_position > 0 and canvas is not None:
            self.after(20, lambda: self._restore_scroll(canvas, saved_position))

    @staticmethod
    def _restore_scroll(canvas, position):
        try:
            canvas.yview_moveto(position)
        except Exception:
            pass

    def _build_empty_state(self, title, subtitle):
        box = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        box.pack(pady=70)
        ctk.CTkLabel(
            box, text="✦", font=("Consolas", 30, "bold"), text_color=self.ACCENT
        ).pack()
        ctk.CTkLabel(
            box, text=title, font=("Consolas", 16, "bold"), text_color="#dddddd"
        ).pack(pady=(6, 2))
        ctk.CTkLabel(
            box, text=subtitle, font=("Consolas", 12), text_color="#666666"
        ).pack()

    def _short_text(self, message):
        lines = message.splitlines()
        short = "\n".join(lines[:3])
        if len(short) > self.LONG_MESSAGE_CHARS:
            short = short[: self.LONG_MESSAGE_CHARS].rstrip()
        return short + "…"

    def create_notification_card(self, notif):
        is_read = notif["read"]
        accent = self.accent_for(notif["type"])
        notif_id = notif["id"]

        card = ctk.CTkFrame(
            self.list_frame,
            fg_color=self.CARD_READ if is_read else self.CARD_UNREAD,
            corner_radius=10, border_width=1, border_color=self.BORDER
        )
        card.pack(fill="x", padx=6, pady=5)

        ctk.CTkFrame(card, width=5, fg_color=accent, corner_radius=0).pack(
            side="left", fill="y", padx=(1, 0), pady=1
        )

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=14, pady=12)

        top = ctk.CTkFrame(content, fg_color="transparent")
        top.pack(fill="x")

        title_text = notif["title"] if is_read else f"●  {notif['title']}"
        ctk.CTkLabel(
            top, text=title_text, font=("Consolas", 14, "bold"), anchor="w",
            text_color="#cccccc" if is_read else "#ffffff"
        ).pack(side="left")

        ctk.CTkLabel(
            top, text=self.format_time(notif["timestamp"], notif["time"]),
            font=("Consolas", 11), text_color="#777777"
        ).pack(side="right")

        full_message = notif["message"] or "(no message)"
        is_long = len(full_message) > self.LONG_MESSAGE_CHARS or full_message.count("\n") >= 3
        expanded = notif_id in self._expanded

        message = ctk.CTkLabel(
            content,
            text=full_message if (expanded or not is_long) else self._short_text(full_message),
            font=("Consolas", 12), text_color="#8a8a8a" if is_read else "#aaaaaa",
            anchor="w", justify="left", wraplength=520
        )
        message.pack(fill="x", pady=(5, 8))

        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(fill="x")

        ctk.CTkLabel(
            bottom, text=notif["type"].upper(), font=("Consolas", 10, "bold"),
            text_color=accent
        ).pack(side="left")

        if is_long:
            toggle = ctk.CTkButton(
                bottom, text="Show less" if expanded else "Show more", width=80, height=22,
                font=("Consolas", 11), fg_color="transparent", hover_color="#333333",
                text_color=self.ACCENT
            )
            toggle.pack(side="left", padx=(10, 0))

            def toggle_message(n_id=notif_id, label=message, button=toggle, text=full_message):
                if n_id in self._expanded:
                    self._expanded.discard(n_id)
                    label.configure(text=self._short_text(text))
                    button.configure(text="Show more")
                else:
                    self._expanded.add(n_id)
                    label.configure(text=text)
                    button.configure(text="Show less")

            toggle.configure(command=toggle_message)

        ctk.CTkButton(
            bottom, text="✕", width=28, height=24, font=("Consolas", 12),
            fg_color="#333333", hover_color="#ef4444",
            command=lambda n=notif: self.delete_notification(n)
        ).pack(side="right")

        if not is_read:
            ctk.CTkButton(
                bottom, text="Mark read", width=84, height=24,
                font=("Consolas", 11), fg_color="#333333", hover_color="#444444",
                command=lambda n=notif: self.mark_as_read(n)
            ).pack(side="right", padx=(0, 8))

        # keep message wrapping in step with the card width
        def on_resize(event, label=message):
            wrap = max(220, event.width - 90)
            if abs(wrap - getattr(label, "_last_wrap", 0)) > 8:
                label._last_wrap = wrap
                try:
                    label.configure(wraplength=wrap)
                except Exception:
                    pass

        card.bind("<Configure>", on_resize)

        # hover highlight (checks the pointer so moving between children doesn't flicker)
        def on_enter(_event):
            card.configure(border_color=accent)

        def on_leave(_event):
            try:
                pointer = card.winfo_containing(*card.winfo_pointerxy())
            except Exception:
                pointer = None
            if pointer is not None and str(pointer).startswith(str(card)):
                return
            card.configure(border_color=self.BORDER)

        self._bind_tree(card, "<Enter>", on_enter, skip_buttons=False)
        self._bind_tree(card, "<Leave>", on_leave, skip_buttons=False)

        # clicking anywhere on an unread card marks it as read
        if not is_read:
            self._bind_tree(card, "<Button-1>", lambda _e, n=notif: self.mark_as_read(n))

    def _bind_tree(self, widget, sequence, handler, skip_buttons=True):
        if skip_buttons and isinstance(widget, ctk.CTkButton):
            return
        widget.bind(sequence, handler)
        for child in widget.winfo_children():
            self._bind_tree(child, sequence, handler, skip_buttons)