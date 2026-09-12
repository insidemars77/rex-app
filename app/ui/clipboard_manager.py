import customtkinter as ctk
import tkinter as tk
import sqlite3
import os


class ClipboardManager(ctk.CTkFrame):

    MAX_ITEMS = 10

    # =========================================================
    # Database location
    # =========================================================

    DB_DIR = os.path.join(os.getenv("APPDATA"), "Rex")
    DB_PATH = os.path.join(DB_DIR, "rex.db")

    def __init__(self, master):
        super().__init__(
            master,
            fg_color="#0d0d0d",
            corner_radius=0
        )

        self.last_clipboard = ""

        self.setup_database()
        self.build_ui()

        # Load existing clipboard history
        self.refresh_list()

        # Start monitoring clipboard
        self.monitor_clipboard()

    # =========================================================
    # DATABASE
    # =========================================================

    def get_connection(self):
        return sqlite3.connect(self.DB_PATH)

    def setup_database(self):

        os.makedirs(self.DB_DIR, exist_ok=True)

        conn = self.get_connection()
        cursor = conn.cursor()

        # Create table with UNIQUE constraint on content
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clipboard_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL UNIQUE,
                copied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):

        # Header
        header = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )

        header.pack(
            fill="x",
            padx=30,
            pady=(25, 15)
        )

        title = ctk.CTkLabel(
            header,
            text="Clipboard Manager",
            font=("Consolas", 28, "bold")
        )

        title.pack(side="left")

        clear_button = ctk.CTkButton(
            header,
            text="Clear",
            width=90,
            font=("Consolas", 13),
            fg_color="#222222",
            hover_color="#333333",
            command=self.clear_history
        )

        clear_button.pack(side="right")

        # Information
        self.info_label = ctk.CTkLabel(
            self,
            text="Last 10 clipboard copies",
            font=("Consolas", 13),
            text_color="#777777",
            anchor="w"
        )

        self.info_label.pack(
            fill="x",
            padx=30,
            pady=(0, 10)
        )

        # Clipboard list
        self.list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#161616",
            corner_radius=10
        )

        self.list_frame.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=(0, 30)
        )

    # =========================================================
    # CLIPBOARD MONITOR
    # =========================================================

    def monitor_clipboard(self):

        try:

            current = self.clipboard_get()

            if current != self.last_clipboard:

                self.last_clipboard = current

                if current.strip():
                    self.add_clipboard_item(current)

        except tk.TclError:
            # Clipboard contains something that isn't text
            pass

        # Check again after 250ms
        self.after(250, self.monitor_clipboard)

    # =========================================================
    # ADD CLIPBOARD ITEM
    # =========================================================

    def add_clipboard_item(self, text):

        text = text.strip()
        if not text:
            return

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Try to insert. If it's a duplicate, just ignore it
            cursor.execute(
                "INSERT INTO clipboard_history (content) VALUES (?)",
                (text,)
            )
        except sqlite3.IntegrityError:
            # Duplicate → just update the timestamp so it becomes the newest
            cursor.execute(
                "UPDATE clipboard_history SET copied_at = CURRENT_TIMESTAMP WHERE content = ?",
                (text,)
            )

        # Keep only the newest 10
        cursor.execute("""
            DELETE FROM clipboard_history
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id FROM clipboard_history
                    ORDER BY copied_at DESC
                    LIMIT 10
                )
            )
        """)

        conn.commit()
        conn.close()
        self.refresh_list()
    # =========================================================
    # GET LAST 10 ITEMS
    # =========================================================

    def get_clipboard_history(self):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, content, copied_at
            FROM clipboard_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (self.MAX_ITEMS,)
        )

        items = cursor.fetchall()

        conn.close()

        return items

    # =========================================================
    # REFRESH UI
    # =========================================================

    def refresh_list(self):

        for widget in self.list_frame.winfo_children():
            widget.destroy()

        items = self.get_clipboard_history()

        if not items:

            empty = ctk.CTkLabel(
                self.list_frame,
                text="No clipboard history yet.",
                font=("Consolas", 14),
                text_color="#666666"
            )

            empty.pack(
                pady=40
            )

            return

        for index, item in enumerate(items):

            record_id = item[0]
            text = item[1]

            self.create_clipboard_item(
                index,
                record_id,
                text
            )

    # =========================================================
    # CLIPBOARD ITEM
    # =========================================================

    def create_clipboard_item(self, index, record_id, text):

        item = ctk.CTkFrame(
            self.list_frame,
            fg_color="#1d1d1d",
            corner_radius=8
        )
        item.pack(fill="x", padx=5, pady=5)

        # Number
        number = ctk.CTkLabel(
            item,
            text=f"{index + 1:02}",
            width=35,
            font=("Consolas", 13, "bold"),
            text_color="#ff5500"
        )
        number.pack(side="left", padx=(10, 5), pady=10)

        # Text with real line breaks
        text_frame = ctk.CTkFrame(item, fg_color="transparent")
        text_frame.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        display_text = text
        lines = display_text.splitlines()
        if len(lines) > 4:
            display_text = "\n".join(lines[:4]) + "\n..."

        text_label = ctk.CTkLabel(
            text_frame,
            text=display_text,
            font=("Consolas", 13),
            anchor="nw",
            justify="left",
            wraplength=550
        )
        text_label.pack(fill="both", expand=True)

        # Copy button fixed on the right
        copy_button = ctk.CTkButton(
            item,
            text="Copy",
            width=70,
            height=30,
            font=("Consolas", 11),
            fg_color="#ff5500",
            hover_color="#cc4400",
            command=lambda value=text: self.copy_to_clipboard(value)
        )
        copy_button.pack(side="right", padx=10, pady=10)
    # =========================================================
    # COPY ITEM BACK TO CLIPBOARD
    # =========================================================

    def copy_to_clipboard(self, text):
        self.last_clipboard = text          # set this FIRST
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    # =========================================================
    # CLEAR HISTORY
    # =========================================================

    def clear_history(self):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM clipboard_history")
        conn.commit()
        conn.close()

        # Clear the system clipboard as well
        self.clipboard_clear()
        self.last_clipboard = ""

        self.refresh_list()