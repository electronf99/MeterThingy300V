from bleak import BleakClient, BleakError, BleakScanner
import msgpack
from MeterThingy.ble20Packets import ble20Packets
import time
from time import sleep
import asyncio


class Transmitter:
    def __init__(self, address: str, char_uuid: str, dry_run=False, ack_interval=30, sleep_interval=0.04):
        self.address = address
        self.char_uuid = char_uuid
        self.client = BleakClient(address)
        self.packer = ble20Packets(message_id=1, max_payload=190)
        self.failed_packets = 0
        self.sent_packets = 0
        self.ack_interval = ack_interval
        self.sleep_interval = sleep_interval
        self.ack_loop_count = 0
        self.dry_run = dry_run


    async def connect(self):
        sleep(1)
        self.client
        try:
            await self.client.connect()
            print(f"Connected to {self.address}")
        except BleakError as e:
            print(f"Connection failed: {e}")
            await BleakScanner.discover(timeout=5.0)
            raise

    async def disconnect(self):
        if self.client.is_connected:
            await self.client.disconnect()
            print("Disconnected")

    async def send_data(self, data: bytes, ack):
        if not self.client.is_connected:
            print("Not Connected")
            await self.connect()
        try:
            ############
            #ack=False
            ############
            await self.client.write_gatt_char(self.char_uuid, data, ack)
            await asyncio.sleep(self.sleep_interval)
            #print(f"Sent: {data}")
        except BleakError as e:
            print(f"Write failed: {e}")
            raise

    async def transmit(self, data: dict): 
        
        # Packet list handler
        mpack = msgpack.packb(data)
        packets = self.packer.build_packets(mpack)
        print(len(packets))
        duration = 0
        largest_packet  = 0

        # Should we ack this time?
        if self.ack_interval > 0:
            self.ack_loop_count += 1
        
        if self.ack_interval > 0 and self.ack_loop_count == self.ack_interval:
            ack = True
            self.ack_loop_count = 0
        else:
            ack = False

        if self.dry_run:
            sleep(0.1)
        else:
            try:

                start_time = time.perf_counter()
                count = 1
                for packet in packets:
                    count += 1
                                                 
                    if ack is True: #and count == len(packets):
                        print("Requesting ack.. ", end="")
                        await self.send_data(packet, True)
                        print("ack received")
                    else:
                        await self.send_data(packet, False)

                largest_packet = max(largest_packet, len(packet) )
                    
                end_time = time.perf_counter()
                duration = (end_time - start_time) / float(len(packets))
                self.sent_packets += 1
            except Exception as e:
                print(f"Error: {e}, disconnect")
                self.failed_packets += 1
                await self.disconnect()
        
        return duration, (self.ack_interval - self.ack_loop_count), largest_packet

