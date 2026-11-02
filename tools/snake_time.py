"""Time the link between two Studios (Follow Studio): the sound's round trip over the cable, to the sample.

Run on the leading Studio, with its playback stopped (a click has to stand out) and Mix to Pocket on. A click goes
into the leader's XO-4, out in its mix back to the following Studio, and, looped there for the test, straight
back into the follower's link, to the leader's STUDIO. The leader's output has both, the click and its copy, in
one recording, so the gap between them is the round trip. Half of it is one way.

First, on the following Studio, the loop (it can't feed back: the mix back leaves STUDIO out); stop it after:

  pw-loopback --capture-props "target.object=xoxo-leader-mix node.dont-reconnect=true" \\
              --playback-props "target.object=xoxo-studio-link node.dont-reconnect=true node.name=snake-test-loop"

Then on the leader:

  python3 snake_time.py [OUTPUT_NODE]

OUTPUT_NODE: the leader's master out (default: the DAC HAT's, alsa_output.platform-soc_sound.stereo-fallback).
Give the link a minute after a Latency change or after linking: it starts high (85-104 ms at LOWER, 2026-11-01)
and settles as the receivers match the two Pis' clocks.
"""
import array
import math
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

RATE, CLICKS, EVERY = 48000, 5, 0.8     # five clicks, 0.8 s apart
OUTPUT = "alsa_output.platform-soc_sound.stereo-fallback"
INPUT = "fm1-xo4-in"                    # XO-4's sound: in the leader's mix and its mix back, not in STUDIO


def onsets(samples, threshold, hold):
    """where the sound first goes over threshold, each, at least hold samples apart"""
    found, i = [], 0
    while i < len(samples):
        if abs(samples[i]) > threshold:
            found.append(i)
            i += hold
        else:
            i += 1
    return found


def round_trips(samples, rate=RATE):
    """the gaps (ms) between each click and its copy back"""
    noise = max((abs(x) for x in samples[:int(rate * 0.4)]), default=0)
    found = onsets(samples, max(1500, noise * 4), int(rate * 0.006))
    gaps = [(b - a) * 1000 / rate for a, b in zip(found, found[1:])]
    return [round(g, 1) for g in gaps[::2] if 5 < g < 400], noise


def main(output=OUTPUT):
    path = Path(tempfile.gettempdir()) / "snake_time.wav"
    rec = subprocess.Popen(["pw-record", "--target", output, "-P", "stream.capture.sink=true", "--rate", str(RATE),
                            "--channels", "1", "--format", "s16", str(path)], stderr=subprocess.DEVNULL)
    time.sleep(2.0)                     # (pw-record a moment to start)
    burst = [int(12000 * math.sin(2 * math.pi * 2000 * i / RATE)) for i in range(int(RATE * 0.004))]
    one = array.array("h", [v for s in burst + [0] * (int(RATE * EVERY) - len(burst)) for v in (s, s)])
    play = subprocess.Popen(["pw-cat", "--playback", "--raw", "--target", INPUT, "--rate", str(RATE),
                             "--channels", "2", "--format", "s16", "-"], stdin=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    play.stdin.write(one.tobytes() * CLICKS)
    play.stdin.close()
    play.wait()
    time.sleep(1.5)
    rec.terminate()
    rec.wait()
    with wave.open(str(path)) as w:
        samples = array.array("h", w.readframes(w.getnframes()))
    path.unlink(missing_ok=True)
    gaps, noise = round_trips(samples)
    if not gaps:
        print(f"no click and copy found (noise {noise}: playback stopped? the loop on the follower running?)")
        return 1
    print(f"round trips (ms): {gaps}  one way about {min(gaps) / 2:.1f}-{max(gaps) / 2:.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
