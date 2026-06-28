import json

#
# Handle Json STring encoded to fit in 20 byte BLE packets
# Includes headers + payload
#
class ble20Packets:
    def __init__(self, message_id=1, max_payload=190):
        self.message_id = message_id
        self.max_payload = max_payload

    # Take a dict, encode it and build a list of 20 byte packets
    # including message id and number of packets
    # 
    def build_packets(self, data):

        encoded = data

        chunk_size = self.max_payload
        chunks = [encoded[i : i + chunk_size] for i in range(0, len(encoded), chunk_size)]
        total_packets = len(chunks)
        msg_id = self.message_id

        packets = []
        for seq, chunk in enumerate(chunks):
            header = bytes([seq, total_packets, msg_id])
            chunk += b"\x00" * (self.max_payload - len(chunk))
            packet = header + chunk  # pad to full size
            packets.append(packet)

        return packets


    # Take a list of 20 byte BLE packets, decode them, strip headers and rebuild 
    # into Json String. Return the results as a dict
 
    def decode_packets(self, received_packets):
        buffer = {}
        for packet in received_packets:
            seq, total_packets, msg_id = packet[0], packet[1], packet[2]
            payload = packet[3:].rstrip(b"\x00")
            buffer[seq] = payload

        if len(buffer) != total_packets:
            print("Still missing packets after retry.")
        else:
            full_data = b"".join(buffer[i] for i in range(total_packets))
            reconstructed = json.loads(full_data.decode("utf-8"))

            return msg_id, seq, reconstructed
