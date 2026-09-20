import os
import platform
import time
from datetime import datetime

import customtkinter as ctk

try:
    import psutil
except ImportError:
    psutil = None


class PerformanceDashboard(ctk.CTkFrame):
    """Live view of the host system's most useful performance signals."""

    ACCENT = "#ff5500"
    CARD = "#161616"
    BORDER = "#292929"
    MUTED = "#888888"
    REFRESH_INTERVAL_MS = 2000

    def __init__(self, master):
        super().__init__(master, fg_color="#0d0d0d", corner_radius=0)

        self._last_network = None
        self._last_network_time = None
        self._after_id = None
        self.metric_values = {}

        self.build_ui()
        if psutil is None:
            self.show_dependency_warning()
        else:
            self.refresh_metrics()

    def build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(24, 8))

        title_group = ctk.CTkFrame(header, fg_color="transparent")
        title_group.pack(side="left")
        ctk.CTkLabel(
            title_group,
            text="Performance Dashboard",
            font=("Consolas", 28, "bold"),
            text_color="#ffffff",
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_group,
            text="A live pulse check for your machine",
            font=("Consolas", 12),
            text_color="#777777",
            anchor="w",
        ).pack(anchor="w", pady=(5, 0))

        self.refresh_button = ctk.CTkButton(
            header,
            text="⟳ Refresh",
            width=105,
            font=("Consolas", 13),
            fg_color="#222222",
            hover_color="#333333",
            command=self.refresh_now,
        )
        self.refresh_button.pack(side="right", pady=(8, 0))

        self.status_label = ctk.CTkLabel(
            self,
            text="● Live monitoring",
            font=("Consolas", 12),
            text_color=self.ACCENT,
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=30, pady=(0, 14))

        self.metrics_grid = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics_grid.pack(fill="x", padx=24)
        self.metrics_grid.grid_columnconfigure((0, 1), weight=1)

        self.create_metric_card(
            "cpu", "CPU", "Overall processor load", "⚡", "#ff7a33"
        )
        self.create_metric_card(
            "memory", "RAM", "Memory currently in use", "◉", "#d990ff"
        )
        self.create_metric_card(
            "disk", "Storage", "System drive space used", "▣", "#55c7ff"
        )
        self.create_metric_card(
            "battery", "Battery", "Power and charging status", "◇", "#65d68a"
        )

        details = ctk.CTkFrame(self, fg_color="transparent")
        details.pack(fill="both", expand=True, padx=24, pady=(16, 20))
        details.grid_columnconfigure(0, weight=1)
        details.grid_columnconfigure(1, weight=1)
        details.grid_rowconfigure(0, weight=1)

        self.create_system_card(details)
        self.create_process_card(details)

    def create_metric_card(self, key, title, subtitle, icon, color):
        card = ctk.CTkFrame(
            self.metrics_grid,
            fg_color=self.CARD,
            corner_radius=14,
            border_width=1,
            border_color=self.BORDER,
        )
        card.grid(
            row=len(self.metric_values) // 2,
            column=len(self.metric_values) % 2,
            sticky="nsew",
            padx=6,
            pady=6,
        )
        self.metric_values[key] = {}

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(15, 2))
        ctk.CTkLabel(
            top, text=icon, font=("Segoe UI Symbol", 22), text_color=color
        ).pack(side="left")
        ctk.CTkLabel(
            top, text=title, font=("Consolas", 16, "bold"), text_color="#ffffff"
        ).pack(side="left", padx=(10, 0))
        value_label = ctk.CTkLabel(
            top, text="--", font=("Consolas", 20, "bold"), text_color=color
        )
        value_label.pack(side="right")

        ctk.CTkLabel(
            card,
            text=subtitle,
            font=("Consolas", 11),
            text_color=self.MUTED,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 10))

        progress = ctk.CTkProgressBar(
            card,
            height=8,
            corner_radius=4,
            fg_color="#292929",
            progress_color=color,
        )
        progress.set(0)
        progress.pack(fill="x", padx=18, pady=(0, 16))

        self.metric_values[key].update(value=value_label, progress=progress)

    def create_system_card(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color=self.CARD,
            corner_radius=14,
            border_width=1,
            border_color=self.BORDER,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(6, 8))

        ctk.CTkLabel(
            card,
            text="System overview",
            font=("Consolas", 16, "bold"),
            text_color=self.ACCENT,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 12))

        self.system_details = {}
        for key, label in (
            ("os", "Operating system"),
            ("uptime", "Uptime"),
            ("cores", "Processor"),
            ("network", "Network"),
        ):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=6)
            ctk.CTkLabel(
                row, text=label, font=("Consolas", 12), text_color=self.MUTED
            ).pack(side="left")
            value = ctk.CTkLabel(
                row, text="--", font=("Consolas", 12, "bold"), text_color="#dddddd"
            )
            value.pack(side="right")
            self.system_details[key] = value

    def create_process_card(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color=self.CARD,
            corner_radius=14,
            border_width=1,
            border_color=self.BORDER,
        )
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 6))

        ctk.CTkLabel(
            card,
            text="Top memory consumers",
            font=("Consolas", 16, "bold"),
            text_color=self.ACCENT,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 8))
        self.process_list = ctk.CTkFrame(card, fg_color="transparent")
        self.process_list.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    def show_dependency_warning(self):
        self.status_label.configure(
            text="● Performance metrics unavailable",
            text_color="#ffcc66",
        )
        warning = ctk.CTkLabel(
            self.metrics_grid,
            text="Install psutil to enable live system metrics:\npython -m pip install psutil",
            font=("Consolas", 13),
            text_color="#ffcc66",
        )
        warning.grid(row=0, column=0, columnspan=2, pady=30)

    def refresh_now(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.refresh_metrics()

    def refresh_metrics(self):
        if psutil is None:
            return

        try:
            cpu = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            self.update_metric("cpu", cpu, f"{cpu:.0f}%", cpu / 100)
            self.update_metric(
                "memory",
                memory.percent,
                f"{memory.percent:.0f}%",
                memory.percent / 100,
            )
            self.update_metric(
                "disk",
                disk.percent,
                f"{disk.percent:.0f}%",
                disk.percent / 100,
            )

            battery = psutil.sensors_battery()
            if battery is None:
                self.update_metric("battery", 0, "AC power", 0)
            else:
                state = "charging" if battery.power_plugged else "on battery"
                self.update_metric(
                    "battery", battery.percent, f"{battery.percent:.0f}% {state}", battery.percent / 100
                )

            self.update_system_details(memory, disk)
            self.update_processes()
            self.status_label.configure(
                text=f"● Live monitoring  •  Updated {datetime.now().strftime('%H:%M:%S')}",
                text_color=self.ACCENT,
            )
        except (OSError, RuntimeError) as error:
            self.status_label.configure(
                text=f"● Metrics update failed: {error}",
                text_color="#ffcc66",
            )

        self._after_id = self.after(self.REFRESH_INTERVAL_MS, self.refresh_metrics)

    def update_metric(self, key, _value, text, progress):
        widgets = self.metric_values[key]
        widgets["value"].configure(text=text)
        widgets["progress"].set(max(0, min(progress, 1)))

    def update_system_details(self, memory, disk):
        boot_time = psutil.boot_time()
        uptime_seconds = max(0, time.time() - boot_time)
        days, remainder = divmod(int(uptime_seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60
        uptime = f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"

        net = psutil.net_io_counters()
        now = time.time()
        network = "No traffic"
        if self._last_network is not None and self._last_network_time is not None:
            elapsed = max(now - self._last_network_time, 0.001)
            received = max(0, net.bytes_recv - self._last_network.bytes_recv) / elapsed
            sent = max(0, net.bytes_sent - self._last_network.bytes_sent) / elapsed
            network = f"↓ {self.format_bytes(received)}/s  ↑ {self.format_bytes(sent)}/s"
        self._last_network = net
        self._last_network_time = now

        self.system_details["os"].configure(
            text=f"{platform.system()} {platform.release()} / "
            f"{platform.machine() or 'system'}"
        )
        self.system_details["uptime"].configure(text=uptime)
        self.system_details["cores"].configure(
            text=f"{psutil.cpu_count(logical=False) or 1} physical / {psutil.cpu_count() or 1} logical"
        )
        self.system_details["network"].configure(text=network)

    def update_processes(self):
        processes = []
        for process in psutil.process_iter(["name", "memory_percent"]):
            try:
                name = process.info["name"] or "Unknown"
                memory = process.info["memory_percent"] or 0
                processes.append((memory, name))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        for widget in self.process_list.winfo_children():
            widget.destroy()
        for memory, name in sorted(processes, reverse=True)[:5]:
            row = ctk.CTkFrame(self.process_list, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(
                row,
                text=name[:28],
                font=("Consolas", 11),
                text_color="#dddddd",
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                row,
                text=f"{memory:.1f}%",
                font=("Consolas", 11, "bold"),
                text_color="#d990ff",
            ).pack(side="right")

    @staticmethod
    def format_bytes(value):
        units = ("B", "KB", "MB", "GB", "TB")
        size = float(value)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
