#NOTE: try not to touch the main.py
#especially you digi
#29 aug 2026
import customtkinter as ctk
#ui folder imports
from ui.git_master import GitMaster
from ui.clipboard_manager import ClipboardManager
from ui.notification_centre import NotificationCentre
from ui.quick_app_group_2 import QuickAppGroup2


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
        self.geometry("1000x650")
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
        ctk.CTkLabel(dashboard, text="Dashboard", font=("Consolas", 28, "bold")).pack(pady=40)
        ctk.CTkLabel(dashboard, text="Welcome to Rex Workflow Assistant", font=("Consolas", 16)).pack()
        self.pages["Dashboard"] = dashboard

        # Workflows Page
        workflows = ctk.CTkFrame(self.content, fg_color="#0d0d0d")
        ctk.CTkLabel(workflows, text="Workflows", font=("Consolas", 28, "bold")).pack(pady=40)
        ctk.CTkLabel(workflows, text="Your workflows will appear here", font=("Consolas", 16)).pack()
        self.pages["Workflows"] = workflows

        # Agents Page
        agents = ctk.CTkFrame(self.content, fg_color="#0d0d0d")
        ctk.CTkLabel(agents, text="Agents", font=("Consolas", 28, "bold")).pack(pady=40)
        ctk.CTkLabel(agents, text="Manage your AI agents here", font=("Consolas", 16)).pack()
        self.pages["Agents"] = agents

        # Settings Page
        settings = ctk.CTkFrame(self.content, fg_color="#0d0d0d")
        ctk.CTkLabel(settings, text="Settings", font=("Consolas", 28, "bold")).pack(pady=40)
        ctk.CTkLabel(settings, text="App settings go here", font=("Consolas", 16)).pack()
        self.pages["Settings"] = settings

    def show_page(self, page_name):
        # Hide current page
        if self.current_page is not None:
            self.current_page.pack_forget()

        # Show new page
        page = self.pages[page_name]
        page.pack(fill="both", expand=True)
        self.current_page = page

    def hide_window(self):
        self.withdraw()
        self.launcher.show_launcher()


#side panel
class SidePanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(
            master,
            width=200,
            corner_radius=0,
            fg_color="#161616"
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
        logo.pack(pady=(25, 20))

        # Navigation buttons
        buttons = ["Git Master","Clipboard Manager","Quick App Groups","Notification Centre","Dashboard", "Workflows", "Agents", "Settings"]

        for item in buttons:
            btn = ctk.CTkButton(
                self,
                text=item,
                font=("Consolas", 14),
                fg_color="transparent",
                hover_color="#2a2a2a",
                anchor="w",
                height=38,
                command=lambda name=item: self.master.show_page(name)
            )
            btn.pack(fill="x", padx=10, pady=3)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")

    app = Launcher()
    app.mainloop()