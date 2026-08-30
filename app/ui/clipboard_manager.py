import customtkinter as ctk
import tkinter as tk


class ClipboardManager(ctk.CTkFrame):

    MAX_ITEMS = 10

    def __init__(self, master):
        super().__init__(
            master,
            fg_color="#0d0d0d",
            corner_radius=0
        )

        self.clipboard_items = []
        self.last_clipboard = ""

        self.build_ui()

        # Start monitoring clipboard
        self.monitor_clipboard()

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

        self.refresh_list()

    # =========================================================
    # Clipboard monitoring
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
    # Add clipboard item
    # =========================================================

    def add_clipboard_item(self, text):

        # Remove existing copy of the same text
        if text in self.clipboard_items:
            self.clipboard_items.remove(text)

        # Newest item at the top
        self.clipboard_items.insert(0, text)

        # Keep only last 10
        self.clipboard_items = self.clipboard_items[
            :self.MAX_ITEMS
        ]

        self.refresh_list()

    # =========================================================
    # Refresh UI
    # =========================================================

    def refresh_list(self):

        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not self.clipboard_items:

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

        for index, text in enumerate(self.clipboard_items):

            self.create_clipboard_item(
                index,
                text
            )

    # =========================================================
    # Clipboard item
    # =========================================================

    def create_clipboard_item(self, index, text):

        item = ctk.CTkFrame(
            self.list_frame,
            fg_color="#1d1d1d",
            corner_radius=8
        )

        item.pack(
            fill="x",
            padx=5,
            pady=5
        )

        # Number
        number = ctk.CTkLabel(
            item,
            text=f"{index + 1:02}",
            width=35,
            font=("Consolas", 13, "bold"),
            text_color="#ff5500"
        )
        number.pack(
            side="left",
            padx=(10, 5),
            pady=10
        )

        # Preview
        preview = text.replace(
            "\n",
            " ↵ "
        )

        if len(preview) > 90:
            preview = preview[:90] + "..."

        text_label = ctk.CTkLabel(
            item,
            text=preview,
            font=("Consolas", 13),
            anchor="w",
            justify="left"
        )

        text_label.pack(
            side="left",
            fill="x",
            expand=True,
            padx=10,
            pady=12
        )

        # Copy button
        copy_button = ctk.CTkButton(
            item,
            text="Copy",
            width=70,
            height=30,
            font=("Consolas", 11),
            fg_color="#ff5500",
            hover_color="#cc4400",
            command=lambda value=text:
                self.copy_to_clipboard(value)
        )

        copy_button.pack(
            side="right",
            padx=10
        )

    # =========================================================
    # Copy item back to clipboard
    # =========================================================

    def copy_to_clipboard(self, text):

        self.clipboard_clear()
        self.clipboard_append(text)

        # Prevent the monitor from treating this as a new copy
        self.last_clipboard = text

    # =========================================================
    # Clear
    # =========================================================

    def clear_history(self):

        self.clipboard_items.clear()
        self.last_clipboard = ""

        self.refresh_list()