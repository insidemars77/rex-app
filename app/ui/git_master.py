import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
import subprocess
import os
import threading
import textwrap


class GitMaster(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="#0d0d0d", corner_radius=0)

        self.repositories = []
        self.current_repo = None
        self.commits = []
        self.branches = []
        self.current_branch = ""

        self.build_ui()

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):
        # ------------------------- Header -------------------------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        title = ctk.CTkLabel(
            header, text="Git Master",
            font=("Consolas", 28, "bold"), text_color="#ffffff"
        )
        title.pack(side="left")

        ctk.CTkLabel(
            header,
            text="A focused control room for your repositories",
            font=("Consolas", 12),
            text_color="#777777"
        ).pack(side="left", padx=(16, 0), pady=(8, 0))

        refresh_button = ctk.CTkButton(
            header, text="⟳ Refresh", width=100,
            font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333",
            command=self.refresh
        )
        refresh_button.pack(side="right", padx=(10, 0))

        add_button = ctk.CTkButton(
            header, text="+ Add Repository", width=150,
            font=("Consolas", 13, "bold"),
            fg_color="#ff5500", hover_color="#cc4400",
            command=self.add_repository
        )
        add_button.pack(side="right")

        # ------------------------- Repo bar -------------------------
        repo_bar = ctk.CTkFrame(
            self,
            fg_color="#161616",
            corner_radius=12,
            border_width=1,
            border_color="#292929"
        )
        repo_bar.pack(fill="x", padx=25, pady=10)

        self.repo_label = ctk.CTkLabel(
            repo_bar, text="No repository selected",
            font=("Consolas", 14), anchor="w"
        )
        self.repo_label.pack(side="left", padx=15, pady=12)

        self.branch_label = ctk.CTkLabel(
            repo_bar, text="",
            font=("Consolas", 14), text_color="#ff5500"
        )
        self.branch_label.pack(side="right", padx=15)

        # ------------------------- Actions bar -------------------------
        actions = ctk.CTkFrame(
            self,
            fg_color="#161616",
            corner_radius=12,
            border_width=1,
            border_color="#292929"
        )
        actions.pack(fill="x", padx=25, pady=(0, 10))

        # Branch selector
        ctk.CTkLabel(actions, text="Branch:", font=("Consolas", 13)).pack(side="left", padx=(15, 5), pady=10)

        self.branch_menu = ctk.CTkOptionMenu(
            actions,
            values=["(no branches)"],
            width=180,
            font=("Consolas", 13),
            fg_color="#222222",
            button_color="#333333",
            button_hover_color="#444444",
            dropdown_fg_color="#222222",
            command=self.on_branch_selected
        )
        self.branch_menu.pack(side="left", padx=5)

        self.switch_btn = ctk.CTkButton(
            actions, text="Switch", width=80, font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333",
            command=self.switch_branch
        )
        self.switch_btn.pack(side="left", padx=5)

        # --- Staging & Commit ---
        self.add_btn = ctk.CTkButton(
            actions, text="＋ Stage All", width=100, font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333",
            command=self.stage_all
        )
        self.add_btn.pack(side="left", padx=(15, 5))

        self.commit_btn = ctk.CTkButton(
            actions, text="✔ Commit", width=90, font=("Consolas", 13, "bold"),
            fg_color="#ff5500", hover_color="#cc4400",
            command=self.commit_with_message
        )
        self.commit_btn.pack(side="left", padx=5)

        # Push / Pull / Status
        self.push_btn = ctk.CTkButton(
            actions, text="⬆ Push", width=90, font=("Consolas", 13, "bold"),
            fg_color="#222222", hover_color="#333333",
            command=self.push_current
        )
        self.push_btn.pack(side="left", padx=5)

        self.pull_btn = ctk.CTkButton(
            actions, text="⬇ Pull", width=90, font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333",
            command=self.pull_current
        )
        self.pull_btn.pack(side="left", padx=5)

        self.status_btn = ctk.CTkButton(
            actions, text="Status", width=80, font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333",
            command=self.show_status
        )
        self.status_btn.pack(side="left", padx=5)

        # ------------------------- Main area -------------------------
        main_area = ctk.CTkFrame(self, fg_color="transparent")
        main_area.pack(fill="both", expand=True, padx=25, pady=(5, 5))

        self.graph = GitGraph(main_area, select_commit=self.select_commit)
        self.graph.pack(side="left", fill="both", expand=True)

        self.details = CommitDetails(main_area)
        self.details.pack(side="right", fill="y", padx=(15, 0))

        # ------------------------- Output + Command section -------------------------
        output_frame = ctk.CTkFrame(
            self,
            fg_color="#161616",
            corner_radius=12,
            border_width=1,
            border_color="#292929"
        )
        output_frame.pack(fill="x", padx=25, pady=(5, 20))

        ctk.CTkLabel(
            output_frame, text="Command Output",
            font=("Consolas", 14, "bold"), text_color="#ff5500"
        ).pack(anchor="w", padx=15, pady=(12, 5))

        self.output_box = ctk.CTkTextbox(
            output_frame, height=170, font=("Consolas", 12),
            fg_color="#0d0d0d", text_color="#dddddd", wrap="word"
        )
        self.output_box.pack(fill="x", padx=15, pady=(0, 10))
        self.output_box.insert("1.0", "Select a repository and run commands…\n")
        self.output_box.configure(state="disabled")

        cmd_row = ctk.CTkFrame(output_frame, fg_color="transparent")
        cmd_row.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkLabel(cmd_row, text="git", font=("Consolas", 13, "bold"), text_color="#ff5500").pack(side="left", padx=(0, 6))

        self.cmd_entry = ctk.CTkEntry(
            cmd_row,
            placeholder_text="status  |  log --oneline -5  |  branch -a  |  any other command…",
            font=("Consolas", 13), height=44
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.cmd_entry.bind("<Return>", lambda e: self.run_custom_command())

        self.run_btn = ctk.CTkButton(
            cmd_row, text="Run", width=80, font=("Consolas", 13, "bold"),
            fg_color="#ff5500", hover_color="#cc4400",
            command=self.run_custom_command
        )
        self.run_btn.pack(side="left")

        clear_btn = ctk.CTkButton(
            cmd_row, text="Clear", width=70, font=("Consolas", 13),
            fg_color="#222222", hover_color="#333333",
            command=self.clear_output
        )
        clear_btn.pack(side="left", padx=(8, 0))

    # =========================================================
    # Repository
    # =========================================================

    def add_repository(self):
        folder = filedialog.askdirectory(title="Select Git Repository")
        if not folder:
            return
        if not self.is_git_repository(folder):
            messagebox.showerror("Git Master", "That folder is not a Git repository.")
            return
        if folder not in self.repositories:
            self.repositories.append(folder)
        self.select_repository(folder)

    def is_git_repository(self, folder):
        try:
            result = subprocess.run(
                ["git", "-C", folder, "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            messagebox.showerror("Git Master", "Git was not found on this computer.")
            return False

    def select_repository(self, folder):
        self.current_repo = folder
        name = os.path.basename(folder)
        self.repo_label.configure(text=f"Repository: {name}")
        self.load_git_data()
        self.append_output(f"── Switched to repository: {folder}\n")

    # =========================================================
    # Git data loading
    # =========================================================

    def load_git_data(self):
        if not self.current_repo:
            return
        self.load_branch_name()
        self.load_branches()
        self.load_commits()

    def load_branch_name(self):
        result = self.run_git(["branch", "--show-current"], show_output=False)
        if result is None:
            return
        branch = result.strip() or "detached HEAD"
        self.current_branch = branch
        self.branch_label.configure(text=f"● {branch}")

    def load_branches(self):
        result = self.run_git(["branch", "--format=%(refname:short)"], show_output=False)
        if result is None:
            self.branches = []
            self.branch_menu.configure(values=["(no branches)"])
            return

        self.branches = [b.strip() for b in result.splitlines() if b.strip()]
        if not self.branches:
            self.branch_menu.configure(values=["(no branches)"])
            return

        display = []
        for b in self.branches:
            if b == self.current_branch:
                display.insert(0, f"● {b}")
            else:
                display.append(b)

        self.branch_menu.configure(values=display)
        self.branch_menu.set(display[0] if display else "(no branches)")

    def load_commits(self):
        result = self.run_git(
            ["log", "--all", "--date=iso", "--pretty=format:%H|%P|%an|%ad|%s"],
            show_output=False
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
    # Git command runner
    # =========================================================

    def run_git(self, command, show_output=True, show_errors=True):
        if not self.current_repo:
            if show_errors:
                self.append_output("⚠ No repository selected.\n")
            return None

        full_cmd = ["git", "-C", self.current_repo] + command

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += result.stderr

            if show_output and output.strip():
                self.append_output(f"$ git {' '.join(command)}\n{output}\n")

            if result.returncode != 0:
                if show_errors and not show_output:
                    self.append_output(f"$ git {' '.join(command)}\n{output}\n")
                return None

            return result.stdout

        except FileNotFoundError:
            msg = "Git is not installed or is not in PATH."
            if show_errors:
                self.append_output(f"⚠ {msg}\n")
                messagebox.showerror("Git Master", msg)
            return None

    def run_git_async(self, command, callback=None):
        def worker():
            result = self.run_git(command, show_output=True)
            if callback:
                self.after(0, lambda: callback(result))
        threading.Thread(target=worker, daemon=True).start()

    # =========================================================
    # Operations
    # =========================================================

    def on_branch_selected(self, choice):
        pass

    def switch_branch(self):
        if not self.current_repo:
            self.append_output("⚠ No repository selected.\n")
            return

        selected = self.branch_menu.get()
        if not selected or selected.startswith("(no"):
            return

        branch = selected.replace("● ", "").strip()
        if branch == self.current_branch:
            self.append_output(f"Already on branch '{branch}'\n")
            return

        self.append_output(f"Switching to branch '{branch}'…\n")
        result = self.run_git(["checkout", branch])
        if result is not None:
            self.load_git_data()
            self.append_output(f"✓ Now on branch '{branch}'\n")

    def stage_all(self):
        """git add ."""
        if not self.current_repo:
            self.append_output("⚠ No repository selected.\n")
            return

        self.append_output("Staging all changes (git add .)…\n")
        result = self.run_git(["add", "."])
        if result is not None:
            self.append_output("✓ All changes staged.\n")
            # Show status so user can see what was staged
            self.run_git(["status", "--short"])

    def commit_with_message(self):
        """Ask for commit message, then git commit -m "..." """
        if not self.current_repo:
            self.append_output("⚠ No repository selected.\n")
            return

        # Ask the user for the commit message
        message = simpledialog.askstring(
            "Commit Message",
            "Enter commit message:",
            parent=self
        )

        if message is None:          # User cancelled
            self.append_output("Commit cancelled.\n")
            return

        message = message.strip()
        if not message:
            messagebox.showwarning("Git Master", "Commit message cannot be empty.")
            return

        self.append_output(f"Committing with message: \"{message}\"\n")
        result = self.run_git(["commit", "-m", message])

        if result is not None:
            self.append_output("✓ Commit successful.\n")
            self.load_git_data()     # refresh graph + branch info

    def push_current(self):
        if not self.current_repo:
            self.append_output("⚠ No repository selected.\n")
            return
        self.append_output(f"Pushing '{self.current_branch}'…\n")
        self.run_git_async(["push", "-u", "origin", "HEAD"])

    def pull_current(self):
        if not self.current_repo:
            self.append_output("⚠ No repository selected.\n")
            return
        self.append_output(f"Pulling '{self.current_branch}'…\n")
        self.run_git_async(["pull"])

    def show_status(self):
        if not self.current_repo:
            self.append_output("⚠ No repository selected.\n")
            return
        self.run_git(["status"])

    def run_custom_command(self):
        if not self.current_repo:
            self.append_output("⚠ No repository selected.\n")
            return

        raw = self.cmd_entry.get().strip()
        if not raw:
            return

        parts = raw.split()
        if not parts:
            return

        self.append_output(f"$ git {raw}\n")
        self.run_git(parts, show_output=True)
        self.cmd_entry.delete(0, "end")

        mutating = {"commit", "checkout", "switch", "branch", "merge", "rebase", "reset", "pull", "push", "add"}
        if parts[0] in mutating:
            self.after(300, self.load_git_data)

    # =========================================================
    # Output helpers
    # =========================================================

    def append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text)
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def clear_output(self):
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")

    def select_commit(self, commit):
        self.details.show_commit(commit, self.current_repo)

    def refresh(self):
        if self.current_repo:
            self.load_git_data()
            self.append_output("── Refreshed\n")


# =============================================================
# Git Graph
# =============================================================

class GitGraph(ctk.CTkFrame):

    def __init__(self, master, select_commit=None):
        super().__init__(master, fg_color="#101010", corner_radius=10)
        self.select_commit = select_commit

        self.canvas = ctk.CTkCanvas(self, background="#101010", highlightthickness=0)
        self.vertical_scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        self.horizontal_scrollbar = ctk.CTkScrollbar(self, orientation="horizontal", command=self.canvas.xview)
        self.canvas.configure(
            yscrollcommand=self.vertical_scrollbar.set,
            xscrollcommand=self.horizontal_scrollbar.set
        )

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas.bind("<MouseWheel>", self.on_scroll)
        self.canvas.bind("<Shift-MouseWheel>", self.on_horizontal_scroll)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def draw_graph(self, commits):
        self.canvas.delete("all")
        if not commits:
            self.canvas.create_text(300, 200, text="No Git history found.",
                                    fill="#777777", font=("Consolas", 14))
            return

        x_start, lane_width = 80, 40
        box_width, box_height = 320, 78
        y_start, y_gap = 30, 105

        lanes, positions = [], {}

        for index, commit in enumerate(commits):
            commit_hash = commit["hash"]
            lane = None
            for i, lane_hash in enumerate(lanes):
                if lane_hash == commit_hash:
                    lane = i
                    break
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

            positions[commit_hash] = (x_start + lane * lane_width, y_start + index * y_gap)

            if commit["parents"]:
                if lane < len(lanes):
                    lanes[lane] = commit["parents"][0]
                else:
                    lanes.append(commit["parents"][0])

        for commit in commits:
            if commit["hash"] not in positions:
                continue
            x, y = positions[commit["hash"]]
            for parent in commit["parents"]:
                if parent not in positions:
                    continue
                px, py = positions[parent]
                start_x, start_y = x, y + box_height
                end_x, end_y = px, py
                if x == px:
                    self.canvas.create_line(start_x, start_y, end_x, end_y, fill="#ff5500", width=2)
                else:
                    mid_y = (start_y + end_y) / 2
                    self.canvas.create_line(start_x, start_y, start_x, mid_y, fill="#ff5500", width=2)
                    self.canvas.create_line(start_x, mid_y, end_x, mid_y, fill="#ff5500", width=2)
                    self.canvas.create_line(end_x, mid_y, end_x, end_y, fill="#ff5500", width=2)

        for commit in commits:
            x, y = positions[commit["hash"]]
            self.draw_commit(commit, x, y, box_width, box_height)

        total_height = y_start + len(commits) * y_gap + box_height + 40
        total_width = x_start + max(len(lanes), 1) * lane_width + box_width + 80
        self.canvas.configure(scrollregion=(0, 0, total_width, total_height))

    def draw_commit(self, commit, x, y, width, height):
        rect = self.canvas.create_rectangle(x, y, x + width, y + height,
                                            fill="#191919", outline="#333333", width=1)
        node_x, node_y = x, y + height / 2
        self.canvas.create_oval(node_x - 6, node_y - 6, node_x + 6, node_y + 6,
                                fill="#ff5500", outline="")

        text_x = x + 18
        message = self.fit_commit_text(commit["message"], 38)
        author = self.fit_commit_text(commit["author"], 22)

        self.canvas.create_text(text_x, y + 16, text=commit["short"],
                                anchor="w", fill="#ff5500", font=("Consolas", 11, "bold"))
        self.canvas.create_text(text_x, y + 38, text=message,
                                anchor="w", fill="#ffffff", font=("Consolas", 12, "bold"))
        self.canvas.create_text(text_x, y + 58,
                                text=f'{author} • {commit["date"][:16]}',
                                anchor="w", fill="#777777", font=("Consolas", 10))

        self.canvas.tag_bind(rect, "<Button-1>",
                             lambda e, c=commit: self.select_commit(c) if self.select_commit else None)
        self.canvas.tag_bind(rect, "<Enter>",
                             lambda e, r=rect: self.canvas.itemconfigure(r, outline="#ff5500"))
        self.canvas.tag_bind(rect, "<Leave>",
                             lambda e, r=rect: self.canvas.itemconfigure(r, outline="#333333"))

    @staticmethod
    def fit_commit_text(value, max_chars):
        lines = textwrap.wrap(
            str(value),
            width=max_chars,
            break_long_words=True,
            break_on_hyphens=False
        )
        if not lines:
            return ""
        if len(lines) > 1:
            return lines[0][:max_chars - 3].rstrip() + "..."
        return lines[0]

    def on_scroll(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_horizontal_scroll(self, event):
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")


# =============================================================
# Commit Details
# =============================================================

class CommitDetails(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, width=300, fg_color="#161616", corner_radius=10)
        self.pack_propagate(False)

        title = ctk.CTkLabel(self, text="Commit Details",
                             font=("Consolas", 18, "bold"), text_color="#ff5500")
        title.pack(anchor="w", padx=20, pady=(20, 15))

        self.hash_label = ctk.CTkLabel(self, text="Select a commit",
                                       font=("Consolas", 16, "bold"), anchor="w")
        self.hash_label.pack(fill="x", padx=20)

        self.message_label = ctk.CTkLabel(self, text="", font=("Consolas", 13),
                                          anchor="w", wraplength=250)
        self.message_label.pack(fill="x", padx=20, pady=(10, 20))

        self.info = ctk.CTkLabel(self, text="", font=("Consolas", 11),
                                 text_color="#888888", anchor="w", justify="left")
        self.info.pack(fill="x", padx=20)

    def show_commit(self, commit, repo):
        self.hash_label.configure(text=commit["short"])
        self.message_label.configure(text=commit["message"])
        self.info.configure(text=(
            f'Author: {commit["author"]}\n\n'
            f'Date:\n{commit["date"]}\n\n'
            f'Full hash:\n{commit["hash"]}\n\n'
            f'Parents:\n'
            + ("\n".join(p[:10] for p in commit["parents"]) if commit["parents"] else "None")
        ))


# =============================================================
# Main
# =============================================================

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    root = ctk.CTk()
    root.title("Git Master")
    root.geometry("1280x860")
    root.minsize(1000, 700)

    app = GitMaster(root)
    app.pack(fill="both", expand=True)

    root.mainloop()