#!/usr/bin/python3

import asyncio
from datetime import datetime
import math
import os
import sys
import signal
import argparse
import psutil

from MeterThingy import Transmitter
from MeterThingy import Dashboard
from Collectors.ASUSWrtThread import ASUSWrtThread
from Collectors.LocalNetThread import LocalNetThread



# Get running time as a string
def get_run_time(start_time):
    
    current_time = datetime.now()
    elapsed = current_time - start_time
    days = elapsed.days
    hours, remainder = divmod(elapsed.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    duration = f"{days} {hours:02}:{minutes:02}:{seconds:02}" 
    
    return duration

# Build Debug Output Line From lots of stuff
def info_line(status):
    
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UPTIME: {status['duration']} PT: {status['tx_time']:.3f} TTACK:{status['ack_time']:2d} Dropped: {status['failed_packets']}/{status['sent_packets']} "
    line += f"{status['metric_label']}: {status['metric_value']:3d} LOADAVG: {status['load_average']:.2f} {status['m1_smoothed']} "
    line += f"[{'-' * int(status['metric_value'] / 4 ):<12}] [{'*' * int((status['m1_smoothed']-32768) / 3000 ):<12}]"

    return line

# function that takes the desired value and increments it
# so that you can smooth out changes in value.
# Used by calling it with the last returned chaser value.
def chaser(desired, current_value, increment=100, decrement=100):

    if current_value != desired:
        
        # On the way up
        if current_value < desired:
            current_value += increment

        # On the way down
        if current_value > desired:
            current_value -= decrement
            if current_value < decrement:
                current_value = 0
        if current_value < 0:
            current_value = 0
    return current_value


# I want to be able to make the needle on meters move
# more aggresively at the bottom of the scale and
# slow down as it approaches full scale
# This is a reverse exponentiation 
# 
def reverse_exponential(input_value: float, full_scale: float = 15.0, curve_factor: float = 4.0) -> float:
    """
    Maps input_value (0.0 to 1.0) to a voltage with more movement at the bottom end.
    curve_factor > 1 makes the curve steeper at the bottom.
    """
    input_value = input_value/full_scale
    input_value = max(0.0, min(1.0, input_value))  # Clamp input
    shaped = 1 - math.exp(-curve_factor * input_value)
    normalized = shaped / (1 - math.exp(-curve_factor))
    return normalized * full_scale


# Main function. Async to handle threading bluetooth

async def main(location, debug, dry_run, display, start_time):

    if display:
        dashboard = Dashboard.Dashboard(refresh_per_second=1)
        dashboard.start()

    # Using Mac. Should figure out how to find mac based on name.
    ble_mac = {
        "home" : "2C:CF:67:F3:AF:3D",
        "work" : "2C:CF:67:F3:AF:3D",
        "test" : "2C:CF:67:E4:D5:10",
        "esp32-test" : "58:8C:81:ED:B3:52",
        "esp32-main" : "D0:CF:13:41:52:92"
    }

    ble_address = ble_mac[location]
    characteristic_uuid = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
     
    # Startup thread to retrieve router stats from a COllector
    if location == "work":
        CollectorThread = LocalNetThread()
    else:
        CollectorThread = ASUSWrtThread()

    CollectorThread.start()
     
    data = {
        "LCD": {
                "0": "This is a test",
                "1": "ddmmyy",
                "2": 0,
            },
        "meter": {
            "m1": {
                "v": 3,
                },
            "m2": {
                "v": 10000,
                },
            },
        "meta": {
            "cpu": 0,
            }
    }

    status={}

    # Create the bt transmitter object
    # Requedst a bt ack every ack_interval transmit loops
    transmitter =  Transmitter.Transmitter(ble_address, characteristic_uuid, dry_run, ack_interval=0, sleep_interval=0.05)

    # Start smoothing at 32768 (which is needle 0) Read later comments.
    status['m1_smoothed'] = 32768

    status['tx_time'] = 0
    status['max_packet_size'] = 0

    last_fail_count = -1
    loop = 0
    total_cpu = 0

    # Default Maximum Metric Value
    default_max_metric_value = 100

    while True:

        # An explanation of all the needle jiggery pokery
        #
        # The needle should be moved so that:
        #
        #   1. We dont hit the hard stop at the top because protect needle
        #   2. The moving iron part has inertia so stop it waving about
        #      by moving it's value up and down gradually
        #   3. Purely for looks, the needle should move down more slowly than up.
        #   4. The meter scale is non-linear in a non-linear fashion. Move it
        #      faster at the bottom in a kind of reverse exponential way.
        #   5. Sometimes it looks better to have a maximum metric value so that  
        #      the meter hangs around near the middle.
        #
        # IMPORTANT: The current Pico2 meter thingy is wired so that the output 
        #            driver sends 0v when the PWM duty cycle is set 32768. This is
        #            one way that the driver allows direction to be specified. The 
        #            moving iron meter always moves the same direction and is
        #            generally used as an AC meter. (I should probably set direction
        #            with the driver dir pin but atm it works)
        #            

        # Collect Data from collecter thread
        latest_data = CollectorThread.get_latest()
        status['metric_label'] = latest_data['v1']['label']
        status['metric_value'] = int(latest_data['v1']['value'])

        # Apply Collecter thread class specified maximum metric value
        max_metric_value = int(min(latest_data['v1']['max_value'], default_max_metric_value))
        status['metric_value'] = min(status['metric_value'],max_metric_value)

        # Boost the needle at lower values
        metric_value_exp = reverse_exponential(status['metric_value'], full_scale = max_metric_value, curve_factor = 5.0)

        # Needle 0 is duty 32768. The needle is 0 -> 100% at duty 32768 -> 65535
        # Calculate the duty as the ratio of (metric value / max value) * 32768
        needle_duty = (metric_value_exp/max_metric_value*32768)+32768
        
        # Final safewguard. Dont allow needle to swing all the way up to the stop
        max_needle_duty = 60000
        m1_duty = int(min(needle_duty, max_needle_duty))

        # Avoid waving due to iron inertia. and return to 0 slowly
        status['m1_smoothed'] = chaser(m1_duty, status['m1_smoothed'], increment=600, decrement=200)
        data["meter"]["m1"]["v"] = status['m1_smoothed']
        
        # How long since we started running
        status['duration'] = get_run_time(start_time)

        status['load_average'] = os.getloadavg()[0]
        
        loop += 1
        total_cpu += psutil.cpu_percent()
        if loop == 100:
            cpu = total_cpu/100
            data["meta"]["cpu"] = (f"{cpu:3.0f}%")
            loop = 0
            total_cpu = 0
        
        
        # Setup LCD Display Data
        data["LCD"]["0"] = f"{status['metric_label']}: {latest_data['v1']['value']:6.2f} L{status['load_average']:.2f}           "[:24]
        data["LCD"]["1"] = f"{status['duration']} T{status['tx_time']:3.2f} F{transmitter.failed_packets}"
        data["LCD"]["2"] = f"BTX: {transmitter.sent_packets:<7} V{status['metric_value']:03} "


        # Transmit data and return average packet time and packets until ack
        status['tx_time'], status['ack_time'], largest_packet  = await transmitter.transmit(data)


        status['raw_data_size'] = len(str(data))
        status['max_packet_size'] = max(status['max_packet_size'],largest_packet)

        status['failed_packets'] = transmitter.failed_packets
        status['sent_packets'] = transmitter.sent_packets

        ## Debugging output.
        debug_line = info_line(status)
        if last_fail_count != transmitter.failed_packets:
            status['status'] = "[red]failing"
            with open("/tmp/-testfailed.out", "a") as file:
                file.write(debug_line + "\n")
        else:
            status['status'] = "[green]OK"
            if debug:
                print("\r" + debug_line)

        with open("/tmp/test-mt.out", "w") as file:
            file.write("\r" + debug_line)

        last_fail_count = transmitter.failed_packets

        # Console Display
        if display:
            dashboard.update(status)


def handle_sigint(signum, frame):
    # Disable mouse reporting
    sys.stdout.write("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l")
    # Exit alternate screen if active
    sys.stdout.write("\x1b[?1049l")
    # Show cursor
    sys.stdout.write("\x1b[?25h")
    sys.stdout.flush()
    os.system('tput rmcup')
    os.system('tput cnorm')
    # progress.stop() / live.stop()
    print("\x1b[?25h", end="", flush=True)
    raise KeyboardInterrupt

## Main ##
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Run main with location context.")
    parser.add_argument("--location", choices=["home", "work",'test',"esp32-test","esp32-main"], default="home",
                        help="Specify the location: 'home' or 'work'")
    parser.add_argument("--debug", action='store_true',
                        help="Turn on debug")
    parser.add_argument("--dry-run", action='store_true',
                        help="Don't connect to remote")
    parser.add_argument("--display", action='store_true',
                        help="Turn on console display")

    args = parser.parse_args()
    start_time = datetime.now()


    
    signal.signal(signal.SIGINT, handle_sigint)
    
    asyncio.run(main(args.location,args.debug, args.dry_run, args.display, start_time))

    


