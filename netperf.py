#!/usr/bin/python3

import subprocess
import time


def get_default_interface_ip_route() -> str | None:
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




interval = 1  # seconds


def get_rx_bytes(interface):
    cmd = f"ip -s link show {interface} | head -4 | tail -1 | awk '{{print $1}}'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        return int(result.stdout.strip())
    return 0




iface = get_default_interface_ip_route()

print(f"Monitoring RX on {iface} using shell... (Ctrl+C to stop)")

while True:
    rx1 = get_rx_bytes(iface)
    time.sleep(interval)
    rx2 = get_rx_bytes(iface)

    rx_bps = min(50, (rx2 - rx1) / interval / 10000)
    print(f"{rx_bps:.0f} {'-' * int(rx_bps)}")
