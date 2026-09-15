#NOTE: try not to touch the main.py
#especially you digi
#29 aug 2026
import customtkinter as ctk
#ui folder imports
from ui.git_master import GitMaster
from ui.clipboard_manager import ClipboardManager
from ui.notification_centre import NotificationCentre
from ui.quick_app_group_2 import QuickAppGroup2
from ui.watch_dog import WatchDog   

#on top window
class Launcher(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry("80x80+1285+640")
        self.configure(fg_color="#111111")

        self.button = ctk.CTkButton(
            self,
            text="🦖",
            font=("Consolas", 50, "bold"),
            command=self.open_main,
            fg_color="#ff5500",
            hover_color="#cc4400",
            corner_radius=15
        )
        self.button.pack(fill="both", expand=True, padx=3, pady=3)

        self.main_window = None

    def open_main(self):
        self.withdraw()

        if self.main_window is None or not self.main_window.winfo_exists():
            self.main_window = MainWindow(self)
        else:
            self.main_window.deiconify()
            self.main_window.lift()

    def show_launcher(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)


#main window
class MainWindow(ctk.CTkToplevel):
    def __init__(self, launcher):
        super().__init__()

        self.launcher = launcher
        self.title("Rex")
        self.geometry("1120x720")
        self.minsize(960, 620)
        self.attributes("-topmost", False)
        self.configure(fg_color="#0d0d0d")

        # === Side Panel ===
        self.side_panel = SidePanel(self)
        self.side_panel.pack(side="left", fill="y")

        # === Main Content Area ===
        self.content = ctk.CTkFrame(self, fg_color="#0d0d0d", corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        # Dictionary to store pages
        self.pages = {}
        self.current_page = None

        # Create all pages
        self.create_pages()

        # Show default page
        self.show_page("Dashboard")

        self.protocol("WM_DELETE_WINDOW", self.hide_window)

    def create_pages(self):
        
        #git master
        git_master = GitMaster(self.content)
        self.pages["Git Master"] = git_master
        
        #clipboard manager
        clipboard_manager = ClipboardManager(self.content)
        self.pages["Clipboard Manager"] = clipboard_manager
        
        #notification centre
        notification_centre = NotificationCentre(self.content)
        self.pages["Notification Centre"] = notification_centre
        
        #quick app group 2
        quick_app_group_2 = QuickAppGroup2(self.content)
        self.pages["Quick App Groups"] = quick_app_group_2
    
        # Dashboard Page
        dashboard = ctk.CTkFrame(self.content, fg_color="#0d0d0d")
        self.build_page_header(
            dashboard,
            "Dashboard",
            "Your workspace at a glance"
        )

        #watch dog                      
        watch_dog = WatchDog(self.content)
        self.pages["Watch Dog"] = watch_dog
        

        welcome = ctk.CTkFrame(
            dashboard,
            fg_color="#1a1a1a",
            corner_radius=16,
            border_width=1,
            border_color="#292929"
        )
        welcome.pack(fill="x", padx=32, pady=(4, 18))

        welcome_copy = ctk.CTkFrame(welcome, fg_color="transparent")
        welcome_copy.pack(side="left", fill="both", expand=True, padx=24, pady=22)
        ctk.CTkLabel(
            welcome_copy,
            text="Welcome back to Rex",
            font=("Consolas", 22, "bold"),
            text_color="#ffffff",
            anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            welcome_copy,
            text="Launch tools, manage repositories, and keep your workflow moving.",
            font=("Consolas", 13),
            text_color="#999999",
            anchor="w"
        ).pack(anchor="w", pady=(7, 0))

        ctk.CTkLabel(
            welcome,
            text="🦖",
            font=("Segoe UI Emoji", 46)
        ).pack(side="right", padx=28, pady=18)

        quick_title = ctk.CTkLabel(
            dashboard,
            text="Quick access",
            font=("Consolas", 15, "bold"),
            text_color="#dddddd",
            anchor="w"
        )
        quick_title.pack(fill="x", padx=32, pady=(0, 10))

        quick_access = ctk.CTkFrame(dashboard, fg_color="transparent")
        quick_access.pack(fill="x", padx=26)
        shortcuts = [
            ("Git Master", "Manage repositories and branches", "Git"),
            ("Clipboard Manager", "Find your recent copied items", "Clipboard"),
            ("Quick App Groups", "Launch your everyday apps", "Apps"),
        ]
        for title, description, page_name in shortcuts:
            card = ctk.CTkFrame(
                quick_access,
                fg_color="#161616",
                corner_radius=12,
                border_width=1,
                border_color="#252525"
            )
            card.pack(side="left", fill="both", expand=True, padx=6)
            ctk.CTkLabel(
                card,
                text=title,
                font=("Consolas", 14, "bold"),
                text_color="#ff6a1a",
                anchor="w"
            ).pack(fill="x", padx=16, pady=(16, 4))
            ctk.CTkLabel(
                card,
                text=description,
                font=("Consolas", 11),
                text_color="#888888",
                anchor="w",
                justify="left",
                wraplength=190
            ).pack(fill="x", padx=16, pady=(0, 14))
            ctk.CTkButton(
                card,
                text=f"Open {page_name}",
                height=30,
                font=("Consolas", 11, "bold"),
                fg_color="#252525",
                hover_color="#333333",
                command=lambda name=title: self.show_page(name)
            ).pack(fill="x", padx=14, pady=(0, 14))
        self.pages["Dashboard"] = dashboard

        # Workflows Page
        workflows = ctk.CTkFrame(self.content, fg_color="#0d0d0d")
        self.build_placeholder_page(
            workflows,
            "Workflows",
            "Automate repeatable tasks from one focused workspace.",
            "No workflows created yet"
        )
        self.pages["Workflows"] = workflows

        # Agents Page
        agents = ctk.CTkFrame(self.content, fg_color="#0d0d0d")
        self.build_placeholder_page(
            agents,
            "Agents",
            "Keep your specialized assistants organized and ready.",
            "No agents configured yet"
        )
        self.pages["Agents"] = agents

        # Settings Page
        settings = ctk.CTkFrame(self.content, fg_color="#0d0d0d")
        self.build_placeholder_page(
            settings,
            "Settings",
            "Tune Rex to fit the way you work.",
            "Settings are coming soon"
        )
        self.pages["Settings"] = settings

    def build_page_header(self, parent, title, subtitle):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(28, 22))
        ctk.CTkLabel(
            header,
            text=title,
            font=("Consolas", 28, "bold"),
            text_color="#ffffff",
            anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text=subtitle,
            font=("Consolas", 12),
            text_color="#777777",
            anchor="w"
        ).pack(anchor="w", pady=(5, 0))

    def build_placeholder_page(self, page, title, subtitle, empty_title):
        self.build_page_header(page, title, subtitle)
        empty_card = ctk.CTkFrame(
            page,
            fg_color="#161616",
            corner_radius=16,
            border_width=1,
            border_color="#252525"
        )
        empty_card.pack(fill="x", padx=32, pady=(8, 0))
        ctk.CTkLabel(
            empty_card,
            text="✦",
            font=("Consolas", 28, "bold"),
            text_color="#ff5500"
        ).pack(pady=(28, 6))
        ctk.CTkLabel(
            empty_card,
            text=empty_title,
            font=("Consolas", 17, "bold"),
            text_color="#dddddd"
        ).pack()
        ctk.CTkLabel(
            empty_card,
            text="This space is ready when you are.",
            font=("Consolas", 12),
            text_color="#777777"
        ).pack(pady=(7, 28))

    def show_page(self, page_name):
        # Hide current page
        if self.current_page is not None:
            self.current_page.pack_forget()

        # Show new page
        page = self.pages[page_name]
        page.pack(fill="both", expand=True)
        self.current_page = page
        if hasattr(self, "side_panel"):
            self.side_panel.set_active(page_name)

    def hide_window(self):
        self.withdraw()
        self.launcher.show_launcher()


#side panel
class SidePanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(
            master,
            width=224,
            corner_radius=0,
            fg_color="#151515"
        )
        self.pack_propagate(False)
        self.master = master   # so we can call show_page

        # Logo
        logo = ctk.CTkLabel(
            self,
            text="🦖 REX",
            font=("Consolas", 20, "bold"),
            text_color="#ff5500"
        )
        logo.pack(pady=(27, 3))

        ctk.CTkLabel(
            self,
            text="WORKFLOW ASSISTANT",
            font=("Consolas", 9, "bold"),
            text_color="#666666"
        ).pack(pady=(0, 22))

        ctk.CTkFrame(self, height=1, fg_color="#292929").pack(fill="x", padx=18, pady=(0, 16))

        # Navigation buttons
        buttons = ["Git Master","Clipboard Manager","Quick App Groups","Notification Centre","Dashboard", "Watch Dog", "Workflows", "Agents", "Settings"]
        self.nav_buttons = {}

        for item in buttons:
            btn = ctk.CTkButton(
                self,
                text=item,
                font=("Consolas", 13),
                fg_color="transparent",
                hover_color="#2a2a2a",
                anchor="w",
                height=40,
                command=lambda name=item: self.master.show_page(name)
            )
            btn.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[item] = btn

        ctk.CTkFrame(self, height=1, fg_color="#292929").pack(fill="x", padx=18, pady=(18, 12))
        ctk.CTkLabel(
            self,
            text="REX  •  READY",
            font=("Consolas", 9, "bold"),
            text_color="#555555"
        ).pack(anchor="w", padx=20)

    def set_active(self, page_name):
        for name, button in self.nav_buttons.items():
            if name == page_name:
                button.configure(
                    fg_color="#ff5500",
                    hover_color="#cc4400",
                    text_color="#ffffff"
                )
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color="#2a2a2a",
                    text_color="#dddddd"
                )


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")

    app = Launcher()
    app.mainloop()