"""Log the T-Deck's serial console to a file, following it across reconnects."""
import glob, sys, time
import serial

out = open(sys.argv[1], "ab")
end = time.time() + float(sys.argv[2])
while time.time() < end:
    ports = sorted(glob.glob("/dev/ttyACM*"))
    if not ports:
        time.sleep(0.5)
        continue
    try:
        s = serial.Serial(ports[0], 115200, timeout=1)
        out.write(("\n=== open %s %s ===\n" % (ports[0], time.strftime("%H:%M:%S"))).encode()); out.flush()
        while time.time() < end:
            b = s.read(4096)
            if b:
                out.write(b); out.flush()
    except Exception as e:
        out.write(("\n=== lost %s: %s ===\n" % (time.strftime("%H:%M:%S"), e)).encode()); out.flush()
        time.sleep(0.5)
