#!/usr/bin/env python3
# pc_sender.py — Ubuntu + Bleak
# pip install bleak
import asyncio
import datetime as dt
from bleak import BleakScanner, BleakClient

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DC4179"
UART_RX_UUID      = "6E400002-B5A3-F393-E0A9-E50E24DC4179"
TARGET_NAME       = "ESP32S3-UART"   # must match the name in main.py

async def find_device(name: str):
    devs = await BleakScanner.discover(timeout=8.0)
    for d in devs:
        if d.name == name:
            return d
    return None

async def send_loop():
    device = await find_device(TARGET_NAME)
    if not device:
        raise SystemExit(f"Device named {TARGET_NAME!r} not found. Is it advertising?")

    async with BleakClient(device) as client:
        # Resolve services so we can get the characteristic
        ch = client.services.get_characteristic(UART_RX_UUID)

        # On Linux, you generally can't force MTU from Bleak;
        # instead use the OS-determined safe max for Write Without Response.  # [3](https://bleak.readthedocs.io/en/latest/api/client.html)[4](https://github.com/hbldh/bleak/discussions/1166)
        max_wwr = ch.max_write_without_response_size or 20
        max_wwr = 30
        print(f"Using chunk size = {max_wwr} bytes")

        counter = 0
        while True:
            max_wwr = ch.max_write_without_response_size or 20
            print(f"max -------> {max_wwr}")
            # Build a message once per second
            msg = f"{'-1234567890' * 22}".encode()

            # Chunk to safe size
            for i in range(0, len(msg), max_wwr):
                print(f"{i}")
                print(f"[{msg[i:i+max_wwr]}]")
                await client.write_gatt_char(ch, msg[i:i+max_wwr], response=False)

            counter += 1
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(send_loop())
