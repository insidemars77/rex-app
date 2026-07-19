"""
launcher.py
-----------
Defines LauncherWindow: the small, round, always-on-top robot icon that
sits in the bottom-right corner of the screen (like the little chat
bubbles you see on websites). Clicking it opens the full chat window.

This is the very FIRST window created by the app, so it also acts as
the Tk "root" window - every other window (the chat window) is created
as a child of this one. That's why it subclasses `ctk.CTk` instead of
`ctk.CTkToplevel`.
"""

import customtkinter as ctk

from ui import THEME, make_circular_image, get_asset_path

# Size of the floating launcher window, in pixels (per spec: ~90x110).
LAUNCHER_WIDTH = 90
LAUNCHER_HEIGHT = 110

# How far (in pixels) the launcher sits from the screen edges.
SCREEN_MARGIN_X = 25
SCREEN_MARGIN_Y = 55  # a bit bigger so it clears the taskbar on Windows


class LauncherWindow(ctk.CTk):
    """
    The small floating launcher icon.

    Parameters
    ----------
    on_open : Callable
        Function called when the user clicks the launcher. app.py uses
        this to open the chat window.
    """

    def __init__(self, on_open):
        super().__init__()
        self.on_open = on_open

        # --- Basic window setup ---------------------------------------
        self.overrideredirect(True)         # no OS title bar / borders
        self.attributes("-topmost", True)    # always stay on top of other windows
        self.resizable(False, False)

        self._apply_rounded_window_style()
        self._position_bottom_right()
        self._build_ui()

    # ------------------------------------------------------------------ #
    # Window styling
    # ------------------------------------------------------------------ #
    def _apply_rounded_window_style(self):
        """
        Try to make the window background fully transparent so that only
        the rounded frame we draw inside it (see _build_ui) is visible -
        this is what gives the launcher its round, modern look.

        NOTE: `-transparentcolor` is a Windows-only Tk feature. On macOS
        and Linux it isn't available, so we fall back to a solid
        background that matches the button colour - the launcher will
        just have square corners there instead of round ones.
        """
        transparent_key = "#000001"  # an "unlikely to be used" colour
        try:
            self.attributes("-transparentcolor", transparent_key)
            self.configure(fg_color=transparent_key)
        except Exception:
            # Not supported on this OS - use a normal solid background.
            self.configure(fg_color=THEME["launcher_bg"])

    def _position_bottom_right(self):
        """Move the window to the bottom-right corner of the screen."""
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = screen_w - LAUNCHER_WIDTH - SCREEN_MARGIN_X
        y = screen_h - LAUNCHER_HEIGHT - SCREEN_MARGIN_Y
        self.geometry(f"{LAUNCHER_WIDTH}x{LAUNCHER_HEIGHT}+{x}+{y}")

    def _build_ui(self):
        """Create the round button + robot avatar shown inside the launcher."""
        # This frame is the part that's actually visible - the real
        # window behind it is transparent (see _apply_rounded_window_style).
        self.button_frame = ctk.CTkFrame(
            self,
            width=LAUNCHER_WIDTH,
            height=LAUNCHER_HEIGHT,
            corner_radius=28,
            fg_color=THEME["launcher_bg"],
            border_width=2,
            border_color=THEME["launcher_border"],
            cursor="hand2",
        )
        self.button_frame.place(x=0, y=0)

        # Load the avatar image and mask it into a circle.
        avatar_image = make_circular_image(get_asset_path("bot_avatar.png"), size=56)
        self.avatar_label = ctk.CTkLabel(
            self.button_frame, image=avatar_image, text="", cursor="hand2"
        )
        self.avatar_label.place(relx=0.5, rely=0.5, anchor="center")

        # Clicking anywhere on the launcher (frame or avatar) opens the chat.
        self.button_frame.bind("<Button-1>", self._handle_click)
        self.avatar_label.bind("<Button-1>", self._handle_click)

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #
    def _handle_click(self, event=None):
        """Called when the user clicks the launcher icon."""
        self.on_open()

    # ------------------------------------------------------------------ #
    # Public show/hide helpers (used by app.py)
    # ------------------------------------------------------------------ #
    def show(self):
        """Show the launcher again (e.g. after the chat window is minimised)."""
        self._position_bottom_right()
        self.deiconify()
        self.attributes("-topmost", True)

    def hide(self):
        """Hide the launcher (e.g. while the chat window is open)."""
        self.withdraw()
