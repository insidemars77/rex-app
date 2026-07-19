"""
chat_window.py
--------------
Defines ChatWindow: the popup window that appears after the user clicks
the launcher icon. It has a header (avatar + title + window buttons), a
scrollable message area, and a text entry + send button at the bottom.

This is UI only - no message logic is wired in. `send_message()` below
adds the user's text as a bubble and then calls `handle_message()`,
which is left as a hook for you to fill in with your own logic.

This window has no OS title bar (overrideredirect), so it draws its own
header and lets the user drag the window around by clicking that header.
"""

import customtkinter as ctk

from ui import THEME, MessageBubble, make_circular_image, get_asset_path

# Size of the chat window, in pixels (per spec: ~380x550).
CHAT_WIDTH = 380
CHAT_HEIGHT = 550

# How far (in pixels) the window sits from the screen edges.
SCREEN_MARGIN_X = 25
SCREEN_MARGIN_Y = 55


class ChatWindow(ctk.CTkToplevel):
    """
    The main chat popup window (UI shell only).

    Parameters
    ----------
    master : ctk.CTk
        The root window (the LauncherWindow instance).
    on_minimize : Callable
        Called when the user clicks the minimize button.
    on_close : Callable
        Called when the user clicks the close button.
    """

    def __init__(self, master, on_minimize, on_close):
        super().__init__(master)
        self.on_minimize = on_minimize
        self.on_close = on_close

        # Full chat history, kept in memory for as long as the app runs.
        # Each entry looks like: {"sender": "user" | "ai", "text": "..."}
        self.history = []

        # Used by the header drag-to-move feature (see _start_move/_do_move).
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Tracks the currently-running fade animation, if any, so a new
        # animation (e.g. clicking close while it's still opening) can
        # cancel the old one instead of both running at once.
        self._anim_after_id = None

        self._setup_window()
        self._build_header()
        self._build_chat_area()
        self._build_input_area()

        self._animate_open()

    # ------------------------------------------------------------------ #
    # Window setup
    # ------------------------------------------------------------------ #
    def _setup_window(self):
        """Configure size, position and basic window attributes."""
        self.overrideredirect(True)         # no OS title bar
        self.attributes("-topmost", True)    # always stay on top
        self.resizable(False, False)
        self.configure(fg_color=THEME["chat_bg"])
        self._position_bottom_right()
        self._set_alpha(0.0)  # start invisible; _animate_open() fades it in

    def _position_bottom_right(self):
        """Place the window in the bottom-right corner of the screen."""
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = screen_w - CHAT_WIDTH - SCREEN_MARGIN_X
        y = screen_h - CHAT_HEIGHT - SCREEN_MARGIN_Y
        self.geometry(f"{CHAT_WIDTH}x{CHAT_HEIGHT}+{x}+{y}")

    def _set_alpha(self, value: float):
        """Set window opacity (0 = invisible, 1 = fully opaque), safely."""
        try:
            self.attributes("-alpha", value)
        except Exception:
            # Some Linux window managers don't support per-window alpha.
            # The window just stays fully opaque, which is fine.
            pass

    # ------------------------------------------------------------------ #
    # UI building blocks
    # ------------------------------------------------------------------ #
    def _build_header(self):
        """Build the header bar: avatar, title, minimize/close buttons."""
        self.header = ctk.CTkFrame(self, height=70, corner_radius=0, fg_color=THEME["header_bg"])
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)

        # Circular avatar on the left of the header.
        avatar_image = make_circular_image(get_asset_path("bot_avatar.png"), size=42)
        self.header_avatar = ctk.CTkLabel(self.header, image=avatar_image, text="")
        self.header_avatar.place(x=16, rely=0.5, anchor="w")

        # Title label - change this text to whatever fits your app.
        self.title_label = ctk.CTkLabel(
            self.header,
            text="Chat",
            text_color=THEME["accent"],
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        )
        self.title_label.place(x=68, rely=0.5, anchor="w")

        # Close button (rightmost).
        self.close_button = ctk.CTkButton(
            self.header,
            text="\u2715",  # ✕
            width=30,
            height=30,
            corner_radius=15,
            fg_color="transparent",
            hover_color=THEME["header_bg_hover"],
            text_color=THEME["text_light"],
            font=ctk.CTkFont(size=14),
            command=self.close,
        )
        self.close_button.place(relx=1.0, x=-14, rely=0.5, anchor="e")

        # Minimize button (just left of close).
        self.minimize_button = ctk.CTkButton(
            self.header,
            text="\u2014",  # —
            width=30,
            height=30,
            corner_radius=15,
            fg_color="transparent",
            hover_color=THEME["header_bg_hover"],
            text_color=THEME["text_light"],
            font=ctk.CTkFont(size=14),
            command=self.minimize,
        )
        self.minimize_button.place(relx=1.0, x=-50, rely=0.5, anchor="e")

        # Let the user drag the window by clicking anywhere on the header,
        # except on the minimize/close buttons themselves.
        self._make_draggable(self.header, exclude={self.close_button, self.minimize_button})

    def _build_chat_area(self):
        """Build the scrollable area where chat bubbles are stacked."""
        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color=THEME["chat_bg"], corner_radius=0)
        self.chat_frame.pack(side="top", fill="both", expand=True, padx=4, pady=4)

    def _build_input_area(self):
        """Build the bottom bar with the text entry and send button."""
        self.input_bar = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=THEME["input_bg"])
        self.input_bar.pack(side="bottom", fill="x")
        self.input_bar.pack_propagate(False)

        self.message_entry = ctk.CTkEntry(
            self.input_bar,
            placeholder_text="Type a message...",
            fg_color=THEME["entry_bg"],
            border_width=0,
            corner_radius=20,
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(14, 8), pady=12)
        # Pressing Enter inside the entry box also sends the message.
        self.message_entry.bind("<Return>", self.send_message)

        self.send_button = ctk.CTkButton(
            self.input_bar,
            text="\u27A4",  # ➤
            width=40,
            height=40,
            corner_radius=20,
            fg_color=THEME["accent"],
            hover_color=THEME["header_bg_hover"],
            text_color=THEME["text_dark"],
            font=ctk.CTkFont(size=16),
            command=self.send_message,
        )
        self.send_button.pack(side="right", padx=(0, 14), pady=12)

    # ------------------------------------------------------------------ #
    # Chat logic (UI only - wire your own behavior into handle_message)
    # ------------------------------------------------------------------ #
    def send_message(self, event=None):
        """
        Called when the user presses Enter or clicks the Send button.
        Shows the user's message, then hands the text off to
        `handle_message()` for you to act on.
        """
        text = self.message_entry.get().strip()
        if not text:
            return  # ignore empty messages

        self.message_entry.delete(0, "end")
        self._add_message(text, "user")

        self.handle_message(text)

    def handle_message(self, text: str):
        """
        Hook called with each message the user sends.

        This is intentionally empty - add your own logic here (or call
        `self._add_message(reply, "other")` once you have a response to
        show on the left side of the chat).
        """
        pass

    def _add_message(self, text: str, sender: str):
        """
        Add a message bubble to the chat and record it in history.

        sender: "user" for the right-aligned/orange bubble,
                anything else (e.g. "other") for the left-aligned bubble.
        """
        MessageBubble(self.chat_frame, text=text, sender=sender)
        self.history.append({"sender": sender, "text": text})
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """Scroll the chat area down so the newest message is visible."""
        # CTkScrollableFrame doesn't expose a public "scroll to end"
        # method, but we can reach its internal canvas and move the view
        # all the way down (1.0 = 100%) once Tk finishes laying things out.
        self.update_idletasks()
        try:
            self.chat_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Window dragging (there's no OS title bar to drag by, so we make
    # our own using the header)
    # ------------------------------------------------------------------ #
    def _make_draggable(self, widget, exclude=frozenset()):
        """
        Recursively bind mouse-drag events to `widget` and all of its
        children (skipping anything in `exclude`) so the user can move
        the window by clicking and dragging anywhere on the header.
        """
        if widget in exclude:
            return
        widget.bind("<ButtonPress-1>", self._start_move)
        widget.bind("<B1-Motion>", self._do_move)
        for child in widget.winfo_children():
            self._make_draggable(child, exclude=exclude)

    def _start_move(self, event):
        # Store the offset between the mouse pointer and the window's
        # top-left corner, using ABSOLUTE screen coordinates so it works
        # correctly no matter which header child widget was clicked.
        self._drag_start_x = event.x_root - self.winfo_x()
        self._drag_start_y = event.y_root - self.winfo_y()

    def _do_move(self, event):
        x = event.x_root - self._drag_start_x
        y = event.y_root - self._drag_start_y
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------ #
    # Opening / closing animation
    # ------------------------------------------------------------------ #
    def _cancel_pending_animation(self):
        """Stop whichever fade animation is currently running, if any."""
        if self._anim_after_id is not None:
            try:
                self.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None

    def _animate_open(self, step: float = 0.0):
        """Fade the window in smoothly from invisible to fully opaque."""
        self._set_alpha(step)
        if step < 1.0:
            self._anim_after_id = self.after(15, lambda: self._animate_open(min(step + 0.08, 1.0)))
        else:
            self._anim_after_id = None

    def _animate_close(self, on_done, step: float = 1.0):
        """Fade the window out, then call `on_done` once it's invisible."""
        self._set_alpha(step)
        if step > 0.0:
            self._anim_after_id = self.after(15, lambda: self._animate_close(on_done, max(step - 0.12, 0.0)))
        else:
            self._anim_after_id = None
            on_done()

    # ------------------------------------------------------------------ #
    # Public actions (minimize / close / re-show)
    # ------------------------------------------------------------------ #
    def minimize(self):
        """Fade out, hide the chat window, then show the launcher again."""
        self._cancel_pending_animation()
        self._animate_close(self._do_minimize)

    def _do_minimize(self):
        self.withdraw()
        self.on_minimize()

    def close(self):
        """Fade out, then fully close the application."""
        self._cancel_pending_animation()
        self._animate_close(self.on_close)

    def show(self):
        """
        Reset position/appearance and show the window again.
        Used by app.py when re-opening a chat window that was minimized
        earlier in the session (chat history is preserved automatically,
        since the window was only hidden, never destroyed).
        """
        self._position_bottom_right()
        self._set_alpha(0.0)
        self.deiconify()
        self.attributes("-topmost", True)
        self._animate_open()
