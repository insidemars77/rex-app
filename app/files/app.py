"""
app.py
------
Entry point of the application. Run this file to start the chatbot:

    python app.py

Responsibilities of this file:
    - Configure CustomTkinter's global appearance (dark mode, blue theme).
    - Create the LauncherWindow (the small floating robot icon).
    - Create/show/hide the ChatWindow when needed.
    - Wire the two windows together: clicking the launcher opens the
      chat, minimizing the chat shows the launcher again, and closing
      the chat exits the whole application.
"""

import customtkinter as ctk

from launcher import LauncherWindow
from chat_window import ChatWindow


class ChatbotApp:
    """Top-level controller that owns and coordinates both windows."""

    def __init__(self):
        # Dark theme for the whole application; all actual colors
        # (black/orange) come from THEME in ui.py, not this call.
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # The launcher is created first because it acts as the Tk root
        # window; the chat window is created as a *child* of it later,
        # the first time the user clicks the launcher.
        self.launcher = LauncherWindow(on_open=self.open_chat)
        self.chat_window = None  # created lazily, the first time it's needed

    # ------------------------------------------------------------------ #
    # Callbacks passed down into the child windows
    # ------------------------------------------------------------------ #
    def open_chat(self):
        """Hide the launcher and show the chat window (creating it once)."""
        self.launcher.hide()
        if self.chat_window is None:
            self.chat_window = ChatWindow(
                master=self.launcher,
                on_minimize=self.minimize_chat,
                on_close=self.quit_app,
            )
        else:
            # Re-show the existing window - its chat history is still there.
            self.chat_window.show()

    def minimize_chat(self):
        """Called by the chat window's minimize button."""
        self.launcher.show()

    def quit_app(self):
        """Called by the chat window's close button. Ends the whole app."""
        self.launcher.destroy()

    # ------------------------------------------------------------------ #
    # Startup
    # ------------------------------------------------------------------ #
    def run(self):
        """Start the Tkinter event loop. Blocks until the app is closed."""
        self.launcher.mainloop()


if __name__ == "__main__":
    app = ChatbotApp()
    app.run()
