#!/usr/bin/env python3
# test_sender.py
import asyncio
from bleak import BleakScanner, BleakClient

TARGET_NAME  = "ESP32S3-UART"  # must match the name you passed to BLESimplePeripheral

UART_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # <-- match ESP
UART_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UART_SVC_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"


async def find_device_by_name(name: str):
    devs = await BleakScanner.discover(timeout=8.0)
    for d in devs:
        if d.name == name:
            return d
    return None

async def main():
    device = await find_device_by_name(TARGET_NAME)
    if not device:
        raise SystemExit(f"Device {TARGET_NAME!r} not found. Is it advertising?")

    async with BleakClient(device) as client:
        # Ensure services are resolved
        await client.get_services()
        ch = client.services.get_characteristic(UART_RX_UUID)
        if ch is None:
            raise SystemExit("RX characteristic not found (UUID mismatch?)")

        # Negotiated, safe per-write payload for Write-Without-Response
        max_wwr = ch.max_write_without_response_size or 20
        print(f"Negotiated write-without-response size: {max_wwr} bytes")

        # Build exactly 200 bytes
        msg200 = bytes((i % 256 for i in range(200)))

        # Send once per second (Ctrl+C to stop)
        i = 0
        while True:
            # Chunk to the negotiated size
            for off in range(0, len(msg200), max_wwr):
                await client.write_gatt_char(ch, msg200[off:off+max_wwr], response=False)
            print(f"Sent 200 bytes (iter={i})")
            i += 1
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())
