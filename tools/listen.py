"""Print every packet on the arcade test port that this radio hears."""
import sys, time
import meshtastic.serial_interface
from pubsub import pub

def on_rx(packet, interface):
    d = packet.get("decoded", {})
    if d.get("portnum") in ("PRIVATE_APP", 256):
        print(f"RX from={packet.get('fromId')} hops={packet.get('hopStart',0)-packet.get('hopLimit',0)} "
              f"snr={packet.get('rxSnr')} rssi={packet.get('rxRssi')} pki={packet.get('pkiEncrypted')} "
              f"payload={d.get('payload')!r}", flush=True)

pub.subscribe(on_rx, "meshtastic.receive")
iface = meshtastic.serial_interface.SerialInterface(sys.argv[1])
print("listening", flush=True)
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 120)
iface.close()
