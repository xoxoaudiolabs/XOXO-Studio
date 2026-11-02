"""Test the Studio's mixer live: a quiet 997 Hz tone (-20 dBFS) into XO-4's input, measured at the master out and
the Bluetooth speaker while the web page's commands mute, solo and level the channels. Every mixer setting is put
back after. The tone plays out of the speakers for about a minute, so have them down; a mic in the mix hears them,
so its channel (a USB mic named ATR...) is muted for the test, and a hardware mute on the mic helps too.

Run on the Studio, with XO-4 stopped:

  python3 mixer_test.py [OUTPUT_NODE]

OUTPUT_NODE: the master out (default: the DAC HAT's, alsa_output.platform-soc_sound.stereo-fallback). A busy Pi 3
takes up to ~2 s to start each capture, so each reading takes about 4 s.
"""
import array
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave

DAC = sys.argv[1] if len(sys.argv) > 1 else "alsa_output.platform-soc_sound.stereo-fallback"
RATE, FREQ = 48000, 997.0


def status():
    return json.load(urllib.request.urlopen("http://localhost/api/status", timeout=5))


def command(key, value):
    body = json.dumps({"cmd": "set", "key": key, "value": value}).encode()
    req = urllib.request.Request("http://localhost/api/command", body, {"Content-Type": "application/json"})
    json.load(urllib.request.urlopen(req, timeout=5))
    ch, field = key.split("_", 1)[1], key.split("_", 1)[0]
    field = {"mix": "level"}.get(field, field)
    for _ in range(40):                       # until the box shows it, then a moment for PipeWire
        row = next(r for r in status()["mixer"] if r["key"] == ch)
        if row[field] == value:
            break
        time.sleep(0.25)
    else:
        print("  ! the box never showed", key, value)
    time.sleep(1.5)


def tone_level(target, seconds=1.0):
    """the 997 Hz tone's amplitude (0..1 of full scale) in what plays on target (Goertzel, left channel)"""
    for _ in range(3):                        # a capture that never got going comes back empty: try again
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            p = subprocess.Popen(["pw-record", "--target", target, "-P", "stream.capture.sink=true", "--format",
                                  "s16", "--rate", str(RATE), "--channels", "2", f.name])
            time.sleep(seconds + 3.0)         # a busy Pi 3 takes up to ~2 s to start capturing
            p.terminate(); p.wait()
            raw = open(f.name, "rb").read()   # (the header's length can be unwritten: read past "data" by hand)
        i = raw.find(b"data")
        a = array.array("h", raw[i + 8:len(raw) - (len(raw) - i - 8) % 2] if i >= 0 else b"")[::2]
        a = a[-int(RATE * seconds):]
        if len(a) >= RATE * seconds * 0.9:
            break
    else:
        print("  ! no capture from", target)
        return 0.0
    k = 2 * math.cos(2 * math.pi * FREQ / RATE)
    s1 = s2 = 0.0
    for x in a:
        s1, s2 = x / 32768 + k * s1 - s2, s1
    return 2 * math.sqrt(max(s1 * s1 + s2 * s2 - k * s1 * s2, 0)) / len(a)


def db(x):
    return 20 * math.log10(x) if x > 1e-6 else -120


results = []


def check(name, ok, detail):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ": " + detail)


st = status()
bt = next((o for o in subprocess.run(["pw-cli", "ls", "Node"], capture_output=True, text=True).stdout.split()
           if o.strip('"').startswith("bluez_output.")), None)
bt = bt and bt.strip('"').split("=")[-1].strip('"')
saved = {r["key"]: r for r in st["mixer"]}
print("channels:", ", ".join(f'{r["label"]} {r["level"]}' for r in st["mixer"]), "| speaker:", bt)

with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    tone = f.name
w = wave.open(tone, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
n = RATE * 180
w.writeframes(array.array("h", (v for i in range(n) for v in [int(3277 * math.sin(2 * math.pi * FREQ * i / RATE))] * 2)).tobytes())
w.close()

for key in saved:                             # a mic hears the speakers: muted for the test (put back after)
    if key.startswith("u-atr") and not saved[key]["mute"]:
        print("muting", saved[key]["label"], "for the test")
        command(f"mute_{key}", True)
floor = tone_level(DAC)
player = subprocess.Popen(["pw-cat", "-p", "--target", "fm1-xo4-in", tone])
time.sleep(1.5)
try:
    base = tone_level(DAC)
    check("XO-4 tone at the DAC master", base > 10 * max(floor, 1e-5), f"{db(base):.1f} dBFS (before the tone {db(floor):.1f})")
    if bt:
        b = tone_level(bt)
        check("same tone at the Bluetooth speaker", b > 10 * max(floor, 1e-5), f"{db(b):.1f} dBFS")
    command("mute_u-xo4", True); m = tone_level(DAC)
    check("mute XO-4 silences it", m < base / 30, f"{db(m):.1f} dBFS")
    command("mute_u-xo4", False); m = tone_level(DAC)
    check("unmute brings it back", abs(db(m) - db(base)) < 1.5, f"{db(m):.1f} dBFS")
    command("solo_u-sampler", True); m = tone_level(DAC)
    check("solo SAMPLER silences XO-4", m < base / 30, f"{db(m):.1f} dBFS")
    command("solo_u-sampler", False); m = tone_level(DAC)
    check("unsolo brings it back", abs(db(m) - db(base)) < 1.5, f"{db(m):.1f} dBFS")
    command("solo_u-xo4", True); m = tone_level(DAC)
    check("solo XO-4 keeps it", abs(db(m) - db(base)) < 1.5, f"{db(m):.1f} dBFS")
    command("solo_u-xo4", False)
    command("mix_u-xo4", 50); m = tone_level(DAC)
    check("XO-4 level 50 is quieter", m < base * 0.8, f"{db(m):.1f} dBFS ({db(m) - db(base):+.1f} dB)")
    command("mix_u-xo4", saved["u-xo4"]["level"]); m = tone_level(DAC)
    check("level back to " + str(saved["u-xo4"]["level"]), abs(db(m) - db(base)) < 1.5, f"{db(m):.1f} dBFS")
finally:
    player.terminate()
    os.unlink(tone)
    for key, row in saved.items():            # every setting as it was
        now = next(r for r in status()["mixer"] if r["key"] == key)
        for field, prefix in (("mute", "mute"), ("solo", "solo"), ("level", "mix")):
            if now[field] != row[field]:
                command(f"{prefix}_{key}", row[field])
    time.sleep(1)
    after = tone_level(DAC)
    check("tone gone after the test", after < base / 30 if results else True, f"{db(after):.1f} dBFS")
print(f"{sum(results)}/{len(results)} passed")
