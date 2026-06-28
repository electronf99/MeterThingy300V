
import asyncio
from bleak import BleakClient, BleakError, BleakScanner
import json
from time import sleep

# === Make sure these UUIDs MATCH your ESP ===
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_UUID      = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # write here
UART_TX_UUID   = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # notify from ESP

class Transmitter:
    def __init__(self, address_or_name: str, char_uuid: str = UART_RX_UUID,
                 dry_run: bool = False, ack_interval: int = 5):
        self.address_or_name = address_or_name
        self.char_uuid = char_uuid
        self.client: BleakClient | None = None
        self._char = None
        self._max_wwr = 190  # negotiated later
        self.failed_packets = 0
        self.sent_packets = 0
        self.ack_interval = ack_interval
        self.ack_loop_count = 0
        self.dry_run = dry_run

    async def _resolve_device(self):
        """Return a Bleak BLEDevice or MAC string."""
        # If a MAC/UUID-like string was given, use it directly
        if isinstance(self.address_or_name, str) and self.address_or_name.count(":") == 5:
            return self.address_or_name
        # Otherwise scan by name
        devs = await BleakScanner.discover(timeout=8.0)
        for d in devs:
            if d.name == self.address_or_name:
                return d
        raise RuntimeError(f"Device {self.address_or_name!r} not found (not advertising?)")

    async def connect(self):
        dev = await self._resolve_device()
        self.client = BleakClient(dev)
        # Small settle delay helps some BlueZ adapters
        await asyncio.sleep(0.2)
        try:
            await self.client.connect()
            print(f"Connected to {dev}")

            # Resolve services and fetch the RX characteristic
            await self.client.get_services()
            self._char = self.client.services.get_characteristic(self.char_uuid)
            if self._char is None:
                raise RuntimeError(f"RX characteristic {self.char_uuid} not found")

            # --- Print negotiated sizes (what matters on PC) ---
            # 1) Bleak's mtu_size (may be None or not accurate depending on backend)
            mtu_str = getattr(self.client, "mtu_size", None)
            print(f"Client reported MTU (if available): {mtu_str}")

            # 2) The reliable send size for Write Without Response:
            sleep(1)
            self._max_wwr = self._char.max_write_without_response_size or 190
            self._max_wwr = 190
            print(f"Negotiated max Write-Without-Response size: {self._max_wwr} bytes")

        except BleakError as e:
            print(f"Connection failed: {e}")
            raise

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            print("Disconnected")

    # async def _write_chunked(self, data: bytes, require_ack: bool):
    #     """Write data in chunks sized to negotiated capability."""
    #     step = self._max_wwr
    #     for i in range(0, len(data), step):
    #         chunk = data[i:i+step]
    #         await self.client.write_gatt_char(self._char, chunk, response=require_ack)


    async def _write_chunked(self, data: bytes, require_ack: bool):
        """
        Write data in chunks. We re-read the negotiated capacity from
        self._char.max_write_without_response_size before *each* slice.
        """
        if not self._char:
            raise RuntimeError("Characteristic not resolved; call connect() first")

        offset = 0
        self._max_wwr = self._char.max_write_without_response_size or 200
        print(f"Negotiated max Write-Without-Response size: {self._max_wwr} bytes")
        while offset < len(data):
            # Re-check the backend-advertised capacity each time
            max_wwr = self._char.max_write_without_response_size or 200
            if max_wwr <= 0:
                max_wwr = 200  # paranoid fallback

            end = offset + max_wwr
            chunk = data[offset:end]

            # Use response=True only if you actually want an ACK for this write
            #require_ack = False
            await self.client.write_gatt_char(self._char, chunk, response=require_ack) # and end >= len(data))
            offset = end


    async def send_data(self, data: bytes, ack: bool):
        if not self.client or not self.client.is_connected:
            await self.connect()
        # NOTE: if ack=True we use response=True for the LAST chunk only
        await self._write_chunked(data, require_ack=ack)

    async def transmit(self, data_dict: dict, packetizer=None):
        """
        If you have a packetizer, pass it in (must expose .build_packets()).
        Otherwise, we msgpack the dict and send as one stream in negotiated chunks.
        """
        import msgpack

        if not self.client or not self.client.is_connected:
            await self.connect()

        payload = msgpack.packb(data_dict)
        payload = ("1"+json.dumps(data_dict)).encode()
        #payload = '12345678910'.encode('utf-8')

        # Decide if this call gets an ack on the last packet
        self.ack_loop_count += 1
        ack_now = (self.ack_interval > 0 and self.ack_loop_count >= self.ack_interval)
        if ack_now:
            self.ack_loop_count = 0

        if self.dry_run:
            await asyncio.sleep(0.3)
            return 0.0, (self.ack_interval - self.ack_loop_count)

        try:
            start = asyncio.get_running_loop().time()

            if packetizer is None:
                await self._write_chunked(payload, require_ack=ack_now)
            else:
                packets = packetizer.build_packets(payload)
                for idx, p in enumerate(packets, 1):
                    last = (idx == len(packets))
                    await self._write_chunked(p, require_ack=(ack_now and last))

            end = asyncio.get_running_loop().time()
            self.sent_packets += 1
            per_packet = (end - start) / max(1, 1)  # simple metric
            return per_packet, (self.ack_interval - self.ack_loop_count)

        except Exception as e:
            print(f"Error: {e}; disconnecting")
            self.failed_packets += 1
            await self.disconnect()
            raise

# --- Quick sanity runner: sends exactly 200 bytes once each second ---
async def _demo():
    tx = Transmitter(address_or_name="ESP32S3-UART", char_uuid=UART_RX_UUID, ack_interval=5)
    await tx.connect()

    # Build exactly 200 bytes
    msg200 = bytes((i % 256 for i in range(200)))

    n = 0
    while True:
        await tx.send_data(msg200, ack=False)
        print(f"Sent 200 bytes (iter={n})")
        n += 1
        await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(_demo())
