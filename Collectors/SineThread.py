#!/usr/bin/python3

import math
import time

# Configuration
step = 0.05          # radians per step
delay = 0.5         # seconds between samples
amplitude = 1.0      # scale the sine value

theta = 0.0
try:
    while True:
        y = amplitude * math.sin(theta)
        print(f"{y:.6f}")
        theta += step
        # keep theta bounded to avoid float drift
        if theta >= 2 * math.pi:
            theta -= 2 * math.pi
        time.sleep(delay)
except KeyboardInterrupt:
    pass
