import customtkinter as ctk
from datetime import datetime
import json
import os
import uuid


class NotificationCentre(ctk.CTkFrame):

    instance = None

    def __init__(self, master):
        super().__init__(master, fg_color="#0d0d0d", corner_radius=0)

        NotificationCentre.instance = self

        self.notifications = []
        self.filter_type = "All"

        self.load_notifications()
        self.build_ui()
        self.refresh_list()

    def build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(22, 8))

        title = ctk.CTkLabel(
            header,
            text="Notification Centre",
            font=("Consolas", 26, "bold")
        )
        title.pack(side="left")

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")

        self.mark_all_btn = ctk.CTkButton(
            btn_frame,
            text="Mark all read",
            width=120,
            height=32,
            font=("Consolas", 12),
            fg_color="#222222",
            hover_color="#333333",
            command=self.mark_all_read
        )
        self.mark_all_btn.pack(side="left", padx=(0, 8))

        clear_btn = ctk.CTkButton(
            btn_frame,
            text="Clear All",
            width=90,
            height=32,
            font=("Consolas", 12),
            fg_color="#222222",
            hover_color="#333333",
            command=self.clear_all
        )
        clear_btn.pack(side="left")

        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=28, pady=(0, 12))

        self.stats_label = ctk.CTkLabel(
            stats_frame,
            text="",
            font=("Consolas", 13),
            text_color="#888888",
            anchor="w"
        )
        self.stats_label.pack(side="left")

        filter_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
        filter_frame.pack(side="right")

        self.filter_buttons = {}
        filters = ["All", "System", "Git", "Workspace", "Browser", "Calendar", "Alert"]

        for f in filters:
            btn = ctk.CTkButton(
                filter_frame,
                text=f,
                width=70,
                height=28,
                font=("Consolas", 11),
                fg_color="#1a1a1a",
                hover_color="#2a2a2a",
                command=lambda t=f: self.set_filter(t)
            )
            btn.pack(side="left", padx=3)
            self.filter_buttons[f] = btn

        self.update_filter_buttons()

        self.list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#141414",
            corner_radius=12
        )
        self.list_frame.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        demo_frame = ctk.CTkFrame(self, fg_color="transparent")
        demo_frame.pack(fill="x", padx=28, pady=(0, 18))

        demo_btn = ctk.CTkButton(
            demo_frame,
            text="＋  Add Demo Notification",
            height=36,
            font=("Consolas", 13),
            fg_color="#ff5500",
            hover_color="#cc4400",
            command=self.add_demo_notification
        )
        demo_btn.pack(side="left")

        tip = ctk.CTkLabel(
            demo_frame,
            text="Other Rex modules can also push notifications here",
            font=("Consolas", 12),
            text_color="#666666"
        )
        tip.pack(side="left", padx=15)

    def load_notifications(self):
        try:
            os.makedirs("data", exist_ok=True)
            if os.path.exists("data/notifications.json"):
                with open("data/notifications.json", "r", encoding="utf-8") as f:
                    self.notifications = json.load(f)
            else:
                self.notifications = [
                    self._create_notif(
                        "Welcome to Rex",
                        "Your central notification hub is ready.",
                        "System"
                    ),
                    self._create_notif(
                        "Git Master Connected",
                        "You can now receive Git related alerts here.",
                        "Git"
                    ),
                ]
                self.save_notifications()
        except Exception:
            self.notifications = []

    def save_notifications(self):
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/notifications.json", "w", encoding="utf-8") as f:
                json.dump(self.notifications, f, indent=4)
        except Exception:
            pass

    def _create_notif(self, title, message, type_="System"):
        return {
            "id": str(uuid.uuid4()),
            "title": title,
            "message": message,
            "type": type_,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "read": False,
            "timestamp": datetime.now().timestamp()
        }

    @classmethod
    def push(cls, title: str, message: str, type_: str = "System"):
        if cls.instance is None:
            return
        notif = cls.instance._create_notif(title, message, type_)
        cls.instance.notifications.insert(0, notif)
        cls.instance.save_notifications()
        cls.instance.refresh_list()

    def set_filter(self, filter_type):
        self.filter_type = filter_type
        self.update_filter_buttons()
        self.refresh_list()

    def update_filter_buttons(self):
        for name, btn in self.filter_buttons.items():
            if name == self.filter_type:
                btn.configure(fg_color="#ff5500", hover_color="#cc4400")
            else:
                btn.configure(fg_color="#1a1a1a", hover_color="#2a2a2a")

    def get_filtered(self):
        if self.filter_type == "All":
            return self.notifications
        return [n for n in self.notifications if n.get("type") == self.filter_type]

    def refresh_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        filtered = self.get_filtered()
        total = len(self.notifications)
        unread = sum(1 for n in self.notifications if not n.get("read", False))

        self.stats_label.configure(
            text=f"{total} total  •  {unread} unread  •  showing {len(filtered)}"
        )

        if not filtered:
            empty = ctk.CTkLabel(
                self.list_frame,
                text="No notifications in this category.",
                font=("Consolas", 15),
                text_color="#555555"
            )
            empty.pack(pady=60)
            return

        for notif in filtered:
            self.create_notification_card(notif)

    def create_notification_card(self, notif):
        is_read = notif.get("read", False)
        bg = "#1c1c1c" if is_read else "#252525"

        colors = {
            "System": "#ff5500",
            "Git": "#a855f7",
            "Workspace": "#22c55e",
            "Browser": "#3b82f6",
            "Calendar": "#eab308",
            "Alert": "#ef4444"
        }
        accent = colors.get(notif.get("type", "System"), "#ff5500")

        card = ctk.CTkFrame(
            self.list_frame,
            fg_color=bg,
            corner_radius=10,
            border_width=1,
            border_color="#2a2a2a"
        )
        card.pack(fill="x", padx=6, pady=5)

        accent_bar = ctk.CTkFrame(card, width=6, fg_color=accent, corner_radius=0)
        accent_bar.pack(side="left", fill="y")

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=14, pady=12)

        top = ctk.CTkFrame(content, fg_color="transparent")
        top.pack(fill="x")

        title_text = notif["title"]
        if not is_read:
            title_text = "●  " + title_text

        title = ctk.CTkLabel(
            top,
            text=title_text,
            font=("Consolas", 14, "bold"),
            anchor="w",
            text_color="#ffffff" if not is_read else "#cccccc"
        )
        title.pack(side="left")

        time_lbl = ctk.CTkLabel(
            top,
            text=notif.get("time", ""),
            font=("Consolas", 11),
            text_color="#777777"
        )
        time_lbl.pack(side="right")

        msg = ctk.CTkLabel(
            content,
            text=notif["message"],
            font=("Consolas", 12),
            text_color="#aaaaaa",
            anchor="w",
            justify="left",
            wraplength=520
        )
        msg.pack(fill="x", pady=(5, 6))

        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(fill="x")

        type_lbl = ctk.CTkLabel(
            bottom,
            text=notif.get("type", "System"),
            font=("Consolas", 11, "bold"),
            text_color=accent
        )
        type_lbl.pack(side="left")

        if not is_read:
            mark_btn = ctk.CTkButton(
                bottom,
                text="Mark read",
                width=80,
                height=24,
                font=("Consolas", 11),
                fg_color="#333333",
                hover_color="#444444",
                command=lambda n=notif: self.mark_as_read(n)
            )
            mark_btn.pack(side="right", padx=(8, 0))

        del_btn = ctk.CTkButton(
            bottom,
            text="✕",
            width=28,
            height=24,
            font=("Consolas", 12),
            fg_color="#333333",
            hover_color="#ef4444",
            command=lambda n=notif: self.delete_notification(n)
        )
        del_btn.pack(side="right")

        def on_click(e, n=notif):
            if not n.get("read", False):
                self.mark_as_read(n)

        card.bind("<Button-1>", on_click)
        content.bind("<Button-1>", on_click)

    def mark_as_read(self, notif):
        notif["read"] = True
        self.save_notifications()
        self.refresh_list()

    def mark_all_read(self):
        for n in self.notifications:
            n["read"] = True
        self.save_notifications()
        self.refresh_list()

    def delete_notification(self, notif):
        self.notifications = [n for n in self.notifications if n["id"] != notif["id"]]
        self.save_notifications()
        self.refresh_list()

    def clear_all(self):
        self.notifications.clear()
        self.save_notifications()
        self.refresh_list()

    def add_demo_notification(self):
        import random
        samples = [
            ("New commit pushed", "main branch received a new commit", "Git"),
            ("Chrome notification", "You have 3 new emails", "Browser"),
            ("Meeting reminder", "Team standup starts in 15 minutes", "Calendar"),
            ("Workspace updated", "Project files were synchronized", "Workspace"),
            ("System alert", "Rex is running low on memory", "Alert"),
            ("Clipboard saved", "Important code snippet was stored", "System"),
        ]
        title, message, type_ = random.choice(samples)
        NotificationCentre.push(title, message, type_)