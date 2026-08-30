import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess
import os


class GitMaster(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(
            master,
            fg_color="#0d0d0d",
            corner_radius=0
        )

        self.repositories = []
        self.current_repo = None
        self.commits = []
        self.commit_widgets = {}

        self.build_ui()

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):

        # -------------------------
        # Header
        # -------------------------

        header = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        header.pack(
            fill="x",
            padx=25,
            pady=(20, 10)
        )

        title = ctk.CTkLabel(
            header,
            text="Git Master",
            font=("Consolas", 28, "bold"),
            text_color="#ffffff"
        )
        title.pack(side="left")

        refresh_button = ctk.CTkButton(
            header,
            text="⟳ Refresh",
            width=100,
            font=("Consolas", 13),
            fg_color="#222222",
            hover_color="#333333",
            command=self.refresh
        )
        refresh_button.pack(side="right", padx=(10, 0))

        add_button = ctk.CTkButton(
            header,
            text="+ Add Repository",
            width=150,
            font=("Consolas", 13, "bold"),
            fg_color="#ff5500",
            hover_color="#cc4400",
            command=self.add_repository
        )
        add_button.pack(side="right")

        # -------------------------
        # Repository bar
        # -------------------------

        repo_bar = ctk.CTkFrame(
            self,
            fg_color="#161616",
            corner_radius=10
        )
        repo_bar.pack(
            fill="x",
            padx=25,
            pady=10
        )

        self.repo_label = ctk.CTkLabel(
            repo_bar,
            text="No repository selected",
            font=("Consolas", 14),
            anchor="w"
        )
        self.repo_label.pack(
            side="left",
            padx=15,
            pady=12
        )

        self.branch_label = ctk.CTkLabel(
            repo_bar,
            text="",
            font=("Consolas", 14),
            text_color="#ff5500"
        )
        self.branch_label.pack(
            side="right",
            padx=15
        )

        # -------------------------
        # Main area
        # -------------------------

        main_area = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        main_area.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=(5, 20)
        )

        # Graph
        self.graph = GitGraph(
            main_area,
            select_commit=self.select_commit
        )
        self.graph.pack(
            side="left",
            fill="both",
            expand=True
        )

        # Details
        self.details = CommitDetails(main_area)
        self.details.pack(
            side="right",
            fill="y",
            padx=(15, 0)
        )

    # =========================================================
    # Repository
    # =========================================================

    def add_repository(self):

        folder = filedialog.askdirectory(
            title="Select Git Repository"
        )

        if not folder:
            return

        if not self.is_git_repository(folder):
            messagebox.showerror(
                "Git Master",
                "That folder is not a Git repository."
            )
            return

        if folder not in self.repositories:
            self.repositories.append(folder)

        self.select_repository(folder)

    def is_git_repository(self, folder):

        try:

            result = subprocess.run(
                [
                    "git",
                    "-C",
                    folder,
                    "rev-parse",
                    "--is-inside-work-tree"
                ],
                capture_output=True,
                text=True
            )

            return result.returncode == 0

        except FileNotFoundError:

            messagebox.showerror(
                "Git Master",
                "Git was not found on this computer."
            )

            return False

    def select_repository(self, folder):

        self.current_repo = folder

        name = os.path.basename(folder)

        self.repo_label.configure(
            text=f"Repository: {name}"
        )

        self.load_git_data()

    # =========================================================
    # Git data
    # =========================================================

    def load_git_data(self):

        if not self.current_repo:
            return

        self.load_branch_name()
        self.load_commits()

    def load_branch_name(self):

        result = self.run_git(
            ["branch", "--show-current"]
        )

        if result is None:
            return

        branch = result.strip()

        if not branch:
            branch = "detached HEAD"

        self.branch_label.configure(
            text=f"● {branch}"
        )

    def load_commits(self):

        result = self.run_git(
            [
                "log",
                "--all",
                "--date=iso",
                "--pretty=format:%H|%P|%an|%ad|%s"
            ]
        )

        if result is None:
            return

        commits = []

        for line in result.splitlines():

            parts = line.split("|", 4)

            if len(parts) != 5:
                continue

            commit_hash, parents, author, date, message = parts

            commits.append({
                "hash": commit_hash,
                "short": commit_hash[:7],
                "parents": parents.split() if parents else [],
                "author": author,
                "date": date,
                "message": message
            })

        self.commits = commits

        self.graph.draw_graph(commits)

    # =========================================================
    # Git command
    # =========================================================

    def run_git(self, command):

        if not self.current_repo:
            return None

        try:

            result = subprocess.run(
                ["git", "-C", self.current_repo] + command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if result.returncode != 0:

                messagebox.showerror(
                    "Git Master",
                    result.stderr.strip()
                )

                return None

            return result.stdout

        except FileNotFoundError:

            messagebox.showerror(
                "Git Master",
                "Git is not installed or is not in PATH."
            )

            return None

    # =========================================================
    # Commit selection
    # =========================================================

    def select_commit(self, commit):

        self.details.show_commit(
            commit,
            self.current_repo
        )

    def refresh(self):

        if self.current_repo:
            self.load_git_data()


# =============================================================
# Git Graph
# =============================================================

class GitGraph(ctk.CTkFrame):

    def __init__(self, master, select_commit=None):

        super().__init__(
            master,
            fg_color="#101010",
            corner_radius=10
        )

        self.select_commit = select_commit

        self.canvas = ctk.CTkCanvas(
            self,
            background="#101010",
            highlightthickness=0
        )

        self.scrollbar = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self.canvas.yview
        )

        self.canvas.configure(
            yscrollcommand=self.scrollbar.set
        )

        self.canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.scrollbar.pack(
            side="right",
            fill="y"
        )

        self.canvas.bind(
            "<MouseWheel>",
            self.on_scroll
        )

    # =========================================================
    # Draw graph
    # =========================================================

    def draw_graph(self, commits):

        self.canvas.delete("all")

        if not commits:

            self.canvas.create_text(
                300,
                200,
                text="No Git history found.",
                fill="#777777",
                font=("Consolas", 14)
            )

            return

        # ---------------------------------------
        # Configuration
        # ---------------------------------------

        x_start = 100
        lane_width = 150

        box_width = 300
        box_height = 85

        y_start = 40
        y_gap = 120

        # ---------------------------------------
        # Find lanes
        # ---------------------------------------

        lanes = []

        positions = {}

        for index, commit in enumerate(commits):

            commit_hash = commit["hash"]

            # Try to keep commit on its existing lane
            lane = None

            for i, lane_hash in enumerate(lanes):

                if lane_hash == commit_hash:
                    lane = i
                    break

            # If not found, assign a new lane
            if lane is None:

                if commit["parents"]:

                    parent = commit["parents"][0]

                    for i, lane_hash in enumerate(lanes):

                        if lane_hash == parent:
                            lane = i
                            break

                if lane is None:
                    lane = len(lanes)
                    lanes.append(commit_hash)

            positions[commit_hash] = (
                x_start + lane * lane_width,
                y_start + index * y_gap
            )

            # Replace lane with first parent
            if commit["parents"]:

                if lane < len(lanes):
                    lanes[lane] = commit["parents"][0]

                else:
                    lanes.append(commit["parents"][0])

        # ---------------------------------------
        # Draw connections FIRST
        # ---------------------------------------

        for commit in commits:

            if commit["hash"] not in positions:
                continue

            x, y = positions[commit["hash"]]

            for parent in commit["parents"]:

                if parent not in positions:
                    continue

                px, py = positions[parent]

                # Commit center
                start_x = x
                start_y = y + box_height

                # Parent center
                end_x = px
                end_y = py

                if x == px:

                    self.canvas.create_line(
                        start_x,
                        start_y,
                        end_x,
                        end_y,
                        fill="#ff5500",
                        width=3
                    )

                else:

                    middle_y = (start_y + end_y) / 2

                    self.canvas.create_line(
                        start_x,
                        start_y,
                        start_x,
                        middle_y,
                        fill="#ff5500",
                        width=3
                    )

                    self.canvas.create_line(
                        start_x,
                        middle_y,
                        end_x,
                        middle_y,
                        fill="#ff5500",
                        width=3
                    )

                    self.canvas.create_line(
                        end_x,
                        middle_y,
                        end_x,
                        end_y,
                        fill="#ff5500",
                        width=3
                    )

        # ---------------------------------------
        # Draw commit boxes
        # ---------------------------------------

        for commit in commits:

            x, y = positions[commit["hash"]]

            self.draw_commit(
                commit,
                x,
                y,
                box_width,
                box_height
            )

        # ---------------------------------------
        # Scroll area
        # ---------------------------------------

        total_height = (
            y_start +
            len(commits) * y_gap +
            box_height +
            50
        )

        total_width = (
            x_start +
            max(len(lanes), 1) * lane_width +
            box_width +
            100
        )

        self.canvas.configure(
            scrollregion=(
                0,
                0,
                total_width,
                total_height
            )
        )

    # =========================================================
    # Commit box
    # =========================================================

    def draw_commit(
        self,
        commit,
        x,
        y,
        width,
        height
    ):

        # Box
        rect = self.canvas.create_rectangle(
            x,
            y,
            x + width,
            y + height,
            fill="#191919",
            outline="#333333",
            width=1
        )

        # Orange commit node
        node_x = x
        node_y = y + height / 2

        self.canvas.create_oval(
            node_x - 7,
            node_y - 7,
            node_x + 7,
            node_y + 7,
            fill="#ff5500",
            outline=""
        )

        # Hash
        self.canvas.create_text(
            x + 20,
            y + 18,
            text=commit["short"],
            anchor="w",
            fill="#ff5500",
            font=("Consolas", 12, "bold")
        )

        # Message
        self.canvas.create_text(
            x + 20,
            y + 42,
            text=commit["message"][:36],
            anchor="w",
            fill="#ffffff",
            font=("Consolas", 13, "bold")
        )

        # Author/date
        self.canvas.create_text(
            x + 20,
            y + 65,
            text=f'{commit["author"]} • {commit["date"][:16]}',
            anchor="w",
            fill="#777777",
            font=("Consolas", 10)
        )

        # Click tag
        tag = f"commit_{commit['hash']}"

        self.canvas.addtag_withtag(
            tag,
            rect
        )

        # Also tag text objects
        self.canvas.addtag_withtag(
            tag,
            self.canvas.create_text(
                x + 20,
                y + 18,
                text="",
                state="hidden"
            )
        )

        self.canvas.tag_bind(
            rect,
            "<Button-1>",
            lambda event, c=commit:
                self.select_commit(c)
        )

        self.canvas.tag_bind(
            rect,
            "<Enter>",
            lambda event, r=rect:
                self.canvas.itemconfigure(
                    r,
                    outline="#ff5500"
                )
        )

        self.canvas.tag_bind(
            rect,
            "<Leave>",
            lambda event, r=rect:
                self.canvas.itemconfigure(
                    r,
                    outline="#333333"
                )
        )

    def on_scroll(self, event):

        self.canvas.yview_scroll(
            int(-1 * (event.delta / 120)),
            "units"
        )


# =============================================================
# Commit Details
# =============================================================

class CommitDetails(ctk.CTkFrame):

    def __init__(self, master):

        super().__init__(
            master,
            width=300,
            fg_color="#161616",
            corner_radius=10
        )

        self.pack_propagate(False)

        title = ctk.CTkLabel(
            self,
            text="Commit Details",
            font=("Consolas", 18, "bold"),
            text_color="#ff5500"
        )
        title.pack(
            anchor="w",
            padx=20,
            pady=(20, 15)
        )

        self.hash_label = ctk.CTkLabel(
            self,
            text="Select a commit",
            font=("Consolas", 16, "bold"),
            anchor="w"
        )
        self.hash_label.pack(
            fill="x",
            padx=20
        )

        self.message_label = ctk.CTkLabel(
            self,
            text="",
            font=("Consolas", 13),
            anchor="w",
            wraplength=250
        )
        self.message_label.pack(
            fill="x",
            padx=20,
            pady=(10, 20)
        )

        self.info = ctk.CTkLabel(
            self,
            text="",
            font=("Consolas", 11),
            text_color="#888888",
            anchor="w",
            justify="left"
        )
        self.info.pack(
            fill="x",
            padx=20
        )

    def show_commit(self, commit, repo):

        self.hash_label.configure(
            text=commit["short"]
        )

        self.message_label.configure(
            text=commit["message"]
        )

        self.info.configure(
            text=(
                f'Author: {commit["author"]}\n\n'
                f'Date:\n{commit["date"]}\n\n'
                f'Full hash:\n{commit["hash"]}\n\n'
                f'Parents:\n'
                + (
                    "\n".join(
                        p[:10]
                        for p in commit["parents"]
                    )
                    if commit["parents"]
                    else "None"
                )
            )
        )