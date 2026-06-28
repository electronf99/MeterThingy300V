import math

from typing import Dict, Any, Optional
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.bar import Bar

class Dashboard:
    def __init__(self, refresh_per_second: int = 10):
        self.console = Console()
        self.live: Optional[Live] = None
        self.refresh_per_second = refresh_per_second
        self.state: Dict[str, Any] = {"title": "MeterThingy", "status": "Idle", "metrics": [], "stats": []}

    def start(self):
        if self.live is None:
            self.live = Live(self._render(), console=self.console,
                             refresh_per_second=self.refresh_per_second, screen=True)
            self.live.start()

    def stop(self):
        if self.live is not None:
            self.live.stop()
            self.live = None

    def update(self, status):

        data={}
        data["status"] = status["status"]
        data["stats"] = [
            ("Duration", status["duration"]),
            ("Packet Time", f"{status['tx_time']:.3f}"),
            ("TTACK", f"{status['ack_time']:2d}"),
            ("Sent Packets", f"{status['sent_packets']}"),
            ("Raw Data Size / Max Packed Size", f"{status['raw_data_size']} / {status['max_packet_size']}"),
            ("[red]Failed Packets", f"[red]{status['failed_packets']}")
        ]
        
        data["metrics"] = [
            (status['metric_label'], f"{status['metric_value']}", Bar(20, 0, status['metric_value'] / 4, color="deep_sky_blue4")),
            (f"Meter  {status['metric_label']}", f"{status['m1_smoothed']-32768}", Bar(20,0,int((status['m1_smoothed']-32768) / 3000 ),color="sky_blue3")),
            ("Load Average", f"{status['load_average']:.2f}", f"{'-' * math.ceil(status['load_average']):<20}"),
        ]
        
        self.state.update(data)
        if self.live is not None:
            self.live.update(self._render(),refresh=True)  # updates once; no loop

    def _render(self):
        header = Panel(f"[bold blue]{self.state['title']}[blue]", border_style="blue")
        
        data_table = Table(show_header=False)
        data_table.add_column("Metric") #, style="bold")
        data_table.add_column("Value", justify="right", width=10)
        data_table.add_column("", justify="left",max_width=40)
        for name, value, bar in self.state["metrics"]:
            data_table.add_row(name, value, bar)

        stats_table = Table(show_header=False)
        stats_table.add_column("Name") #, style="bold")
        stats_table.add_column("Value", justify="right")
        for name, value in self.state["stats"]:
            stats_table.add_row(name, value)
        
        footer = Panel(f"[bold blue]Status:[/bold blue] {self.state['status']}", border_style="blue")
        return Group(header, data_table, stats_table, footer)  # <-- return Group, not list



