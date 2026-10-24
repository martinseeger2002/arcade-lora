"""Send one PRIVATE_APP packet as a direct message: sendraw.py PORT DEST TEXT"""
import sys, time
import meshtastic.serial_interface
from meshtastic.protobuf import portnums_pb2

iface = meshtastic.serial_interface.SerialInterface(sys.argv[1])
p = iface.sendData(sys.argv[3].encode(), destinationId=sys.argv[2],
                   portNum=portnums_pb2.PortNum.PRIVATE_APP, wantAck=True)
print("sent id", p.id, flush=True)
time.sleep(20)
iface.close()
