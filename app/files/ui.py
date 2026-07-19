"""
ui.py
-----
Shared, reusable pieces used by both launcher.py and chat_window.py:

    - THEME             : one dictionary with every colour used in the app.
    - get_asset_path()  : builds a safe path to a file inside assets/.
    - make_circular_image(): turns any image into a round CTkImage avatar.
    - MessageBubble     : one rounded chat bubble (user or AI).
    - TypingBubble      : an animated "Typing..." bubble used while the
                           AI "thinks" of a reply.

Keeping these in one file means launcher.py and chat_window.py don't
repeat code, and the whole app's look can be changed from one place
(the THEME dictionary below).
"""

import os
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageOps

# --------------------------------------------------------------------------
# Folder that contains images used by the app (e.g. the robot avatar).
# Built from this file's own location so it works no matter where the
# app is launched from (VS Code, double-click, terminal, etc).
# --------------------------------------------------------------------------
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def get_asset_path(filename: str) -> str:
    """Return the full path to a file that lives inside the assets/ folder."""
    return os.path.join(ASSETS_DIR, filename)


# --------------------------------------------------------------------------
# THEME - every colour the app uses, in one place.
# Change a value here and it updates everywhere THEME[...] is used.
# --------------------------------------------------------------------------
THEME = {
    "app_bg": "#0d0d0d",            # fallback background colour
    "header_bg": "#1a1a1a",         # header bar / launcher button
    "header_bg_hover": "#fc5400",   # orange on hover for header buttons
    "chat_bg": "#0d0d0d",           # background of the scrollable chat area
    "input_bg": "#141414",          # background of the bottom input bar
    "entry_bg": "#1f1f1f",          # background of the text entry box
    "user_bubble": "#fc5400",       # colour of the current user's bubbles
    "ai_bubble": "#1f1f1f",         # colour of the other side's bubbles
    "text_light": "#F5F5F5",        # main light text colour (on dark bubbles)
    "text_dark": "#0d0d0d",         # dark text colour (on orange bubbles)
    "text_muted": "#8a8a8a",        # secondary / greyed out text
    "accent": "#fc5400",            # primary orange accent colour
    "launcher_bg": "#0d0d0d",       # background of the round launcher button
    "launcher_border": "#fc5400",   # border ring around the launcher button
}


def make_circular_image(image_path: str, size: int = 60) -> "ctk.CTkImage":
    """
    Load an image from disk and mask it into a perfect circle, so it can
    be used as a circular avatar inside a CTkLabel.

    If `image_path` doesn't exist (e.g. you haven't added an assets/
    folder yet), this falls back to a plain drawn circle instead of
    crashing, so the UI still runs with zero external files.

    Args:
        image_path: path to the source image (png/jpg/etc).
        size: width and height (in pixels) of the final circular image.

    Returns:
        A CTkImage ready to be passed to `CTkLabel(..., image=...)`.
    """
    if not os.path.isfile(image_path):
        return make_placeholder_avatar(size)

    # Open the source image and make sure it has an alpha (transparency) channel.
    original = Image.open(image_path).convert("RGBA")

    # Crop + resize so the image completely (and evenly) fills a `size` x `size` square.
    square = ImageOps.fit(original, (size, size), method=Image.LANCZOS)

    # Build a black & white "mask": a white circle on a black background.
    # White areas of a mask stay visible; black areas become transparent.
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)

    # Paste the square image onto a blank canvas, using the mask as the
    # alpha channel - this is what actually "cuts out" the circle shape.
    circular = Image.new("RGBA", (size, size))
    circular.paste(square, (0, 0), mask=mask)

    # CustomTkinter needs its own CTkImage wrapper (not a raw PIL image)
    # to correctly display and scale images on both light & dark mode.
    return ctk.CTkImage(light_image=circular, dark_image=circular, size=(size, size))


def make_placeholder_avatar(size: int = 60, letter: str = "R") -> "ctk.CTkImage":
    """
    Draw a simple circular avatar with no source image needed: a solid
    orange circle with a single letter in the middle. Used automatically
    by `make_circular_image()` when no image file is found, and can also
    be called directly if you never want to bother with image assets.
    """
    from PIL import ImageFont

    circular = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(circular)
    draw.ellipse((0, 0, size, size), fill=THEME["accent"])

    try:
        font = ImageFont.truetype("consolab.ttf", int(size * 0.45))
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), letter, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - text_w) / 2 - bbox[0], (size - text_h) / 2 - bbox[1]),
        letter,
        font=font,
        fill=THEME["text_dark"],
    )

    return ctk.CTkImage(light_image=circular, dark_image=circular, size=(size, size))


class MessageBubble(ctk.CTkFrame):
    """
    A single chat message bubble.

    Internally this is just a small rounded CTkFrame (the "bubble")
    with a CTkLabel inside it holding the text. Depending on `sender`
    the bubble is coloured/aligned differently:

        sender="user" -> blue bubble,  aligned to the right of the chat.
        sender="ai"   -> grey bubble,  aligned to the left of the chat.
    """

    def __init__(self, master, text: str, sender: str = "ai", **kwargs):
        # `fg_color="transparent"` makes this outer frame invisible - it
        # only exists to control left/right alignment of the real bubble.
        super().__init__(master, fg_color="transparent", **kwargs)

        is_user = sender == "user"
        bubble_color = THEME["user_bubble"] if is_user else THEME["ai_bubble"]
        text_color = THEME["text_dark"] if is_user else THEME["text_light"]
        anchor_side = "e" if is_user else "w"          # e = east/right, w = west/left
        justify_side = "right" if is_user else "left"

        # The coloured, rounded "bubble" itself.
        self.bubble = ctk.CTkFrame(self, fg_color=bubble_color, corner_radius=16)
        self.bubble.pack(anchor=anchor_side, padx=10, pady=4)

        # The message text, word-wrapped so long messages break onto new lines.
        self.label = ctk.CTkLabel(
            self.bubble,
            text=text,
            text_color=text_color,
            wraplength=240,
            justify=justify_side,
            font=ctk.CTkFont(size=13),
        )
        self.label.pack(padx=12, pady=8)

        # Make this bubble row stretch the full chat width so the anchor
        # (left/right) actually has room to align within.
        self.pack(fill="x", pady=2)