import threading
import time
import subprocess

class LocalNetThread(threading.Thread):

    def __init__(self):

        self.traffic={'speed': {'rx': 0, 'tx': 0},
                        'total': {'recv': 0, 'sent': 0},
                        'average': { 'rx': 0, 'tx': 0}
                        }
        self.average_speed={'speed': {'rx': 0, 'tx': 0},
                'total': {'recv': 0, 'sent': 0},
                'average': { 'rx': 0, 'tx': 0}
                }
        self.iface = self.get_default_interface_ip_route()

        threading.Thread.__init__(self, daemon=True)

    def get_default_interface_ip_route(self) -> str | None:
        """
        Returns the default network interface by parsing `ip route`.
        Example output lines:
        'default via 192.168.1.1 dev wlp3s0 proto dhcp metric 600'
        """
        try:
            out = subprocess.check_output(["ip", "route"], text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

        for line in out.splitlines():
            if line.startswith("default "):
                parts = line.split()
                # Find 'dev' and grab the token after it
                if "dev" in parts:
                    idx = parts.index("dev")
                    if idx + 1 < len(parts):
                        return parts[idx + 1]
        return None
    
    def get_rx_bytes(self, interface):
        cmd = f"ip -s link show {interface} | head -4 | tail -1 | awk '{{print $1}}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return int(result.stdout.strip())
        return 0

    
    def run(self):
        print("Started LocalNetThread Thread")

        interval = 0.2

        # Get Speed Loop
        while(1==1):


            rx1 = self.get_rx_bytes(self.iface)
            time.sleep(interval)
            rx2 = self.get_rx_bytes(self.iface)

            rx_bps = min(100, (rx2 - rx1) / interval / 10000)
            #print(f"{rx_bps:.0f} {'-' * int(rx_bps)}")


            self.average_speed["speed"]["rx"] = rx_bps
            self.average_speed["speed"]["tx"] = 0
           
            time.sleep(0.1)

    def get_latest(self):

        data = {
            'v1': {
                'label': 'RX', 
                'value': self.average_speed["speed"]["rx"],
                'max_value': 100
            }
        }

        return data

