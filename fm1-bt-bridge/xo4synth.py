#!/usr/bin/env python3
"""XO-4's synth voice: two-operator FM, up to four notes at once (a chord on a step), rendered a block at a time
with numpy, as the pads are (pads.py): float32 stereo, -1..1.

A voice: a sine carrier at the note's pitch, its phase moved by a sine modulator at RATIO times that pitch. How far
it's moved is the modulation INDEX (radians), and the index has its own envelope: it starts at INDEX x the note's
velocity and falls to MOD_SUSTAIN of that over MOD_DECAY seconds (exponentially), so a note starts bright and
mellows: plucks, keys, bells (a ratio that isn't a whole number), basses (ratio 1 or 0.5). The voice's level is
an ADSR: ATTACK, DECAY to SUSTAIN, RELEASE after the note is let go, all straight ramps, as the pads' are.

Every sum runs over a whole block (no Python loop a sample): what a Pi 3 can afford for eight voices, two
tracks of four. No feedback (an operator modulating itself needs the sample before it: a loop a sample).

  xo4synth.py --bench [VOICES] [SECONDS]    render VOICES held notes (8: two tracks' chords) for SECONDS of
                                            sound, and say how much of a core it takes
  xo4synth.py --wav FILE                    a short demo (a chord, a bass line) into a WAV, to listen to
"""
import math
import sys
import time

VOICES = 4                                  # notes at once, a track: a chord on a step
BLOCK = 512                                 # frames a block (the pads' BLOCK: 10.7 ms at 48 kHz)
PATCH = {"ratio": 2.0, "index": 3.0, "mod_decay": 0.4, "mod_sustain": 0.2,
         "attack": 0.005, "decay": 0.3, "sustain": 0.6, "release": 0.25, "level": 0.22}
LIMITS = {"ratio": (0.25, 16.0), "index": (0.0, 12.0), "mod_decay": (0.005, 10.0), "mod_sustain": (0.0, 1.0),
          "attack": (0.0, 10.0), "decay": (0.005, 10.0), "sustain": (0.0, 1.0), "release": (0.005, 10.0),
          "level": (0.0, 1.0)}
TWO_PI = 2.0 * math.pi
CUT = 0.005                                 # s: a voice let go for another (the same note again, a fifth note)
                                            # fades this fast; gone at once it was a click mid-wave (112 a minute
                                            # in "Pocket Groove", 2026-11-03)


def np():
    import numpy
    return numpy


def clean_patch(patch):
    """a patch from anywhere (a saved file, the screen) -> every value there, a number, in its range"""
    out = dict(PATCH)
    for key, (lo, hi) in LIMITS.items():
        try:
            out[key] = float(max(lo, min(hi, float((patch or {}).get(key, out[key])))))
        except (TypeError, ValueError):
            pass
    return out


def note_freq(note):
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


class Voice:
    def __init__(self, note, velocity, rate):
        self.note, self.velocity = note, velocity
        self.inc = TWO_PI * note_freq(note) / rate      # the carrier's phase a frame
        self.carrier = self.mod = 0.0                   # phases (radians), carried from block to block
        self.age = 0                                    # frames since the note began
        self.level = 0.0                                # the ADSR's level now
        self.stage = "attack"                           # attack, decay, sustain, release, done
        self.from_level = 0.0                           # where the release ramp starts
        self.cut = False                                # let go for another note: released in CUT, not RELEASE


class Synth:
    """one XO-4 synth track: its patch and up to VOICES notes"""

    def __init__(self, rate=48000, patch=None, voices=None):
        self.rate, self.max = rate, voices or VOICES
        self.patch = clean_patch(patch)
        self.voices = []

    def set_patch(self, patch):
        self.patch = clean_patch(dict(self.patch, **(patch or {})))

    def note_on(self, note, velocity=100):
        """a note starts; the same note again restarts; past VOICES, the oldest stops for it (those let go fade
        out in CUT, beside the new one)"""
        for v in self.voices:
            if v.note == note and not v.cut:
                self.cut_voice(v)
        live = [v for v in self.voices if not v.cut]
        if len(live) >= self.max:
            self.cut_voice(live[0])
        self.voices.append(Voice(note, max(1, min(127, velocity)) / 127.0, self.rate))

    @staticmethod
    def cut_voice(v):
        if v.stage != "release":
            v.stage, v.from_level, v.age_off = "release", v.level, v.age
        else:                                   # (already releasing: from where it is now, faster)
            v.from_level, v.age_off = v.level, v.age
        v.cut = True

    def note_off(self, note):
        for v in self.voices:
            if v.note == note and v.stage not in ("release", "done") and not v.cut:
                v.stage, v.from_level, v.age_off = "release", v.level, v.age

    def all_off(self):
        for v in list(self.voices):
            self.note_off(v.note)

    def sounding(self):
        return sorted(v.note for v in self.voices if not v.cut)

    def envelope(self, v, n):
        """the voice's ADSR level for its next n frames (float32), its stage moved on as it goes"""
        num, p, r = np(), self.patch, self.rate
        out = num.empty(n, dtype=num.float32)
        done = 0
        while done < n:
            left = n - done
            if v.stage == "attack":
                frames = max(1, int(p["attack"] * r))
                k = min(left, max(0, frames - v.age))
                if k:
                    out[done:done + k] = (v.age + 1 + num.arange(k, dtype=num.float32)) / frames
                    v.age += k
                    done += k
                if v.age >= frames:
                    v.stage, v.decay_at = "decay", v.age
                continue
            if v.stage == "decay":
                frames = max(1, int(p["decay"] * r))
                into = v.age - v.decay_at
                k = min(left, frames - into)
                ramp = (into + 1 + num.arange(k, dtype=num.float32)) / frames
                out[done:done + k] = 1.0 + (p["sustain"] - 1.0) * ramp
                v.age += k
                done += k
                if into + k >= frames:
                    v.stage = "sustain"
                continue
            if v.stage == "sustain":
                out[done:] = p["sustain"]
                v.age += left
                done = n
                continue
            if v.stage == "release":
                frames = max(1, int((CUT if v.cut else p["release"]) * r))
                into = v.age - v.age_off
                k = min(left, max(0, frames - into))
                if k:
                    ramp = (into + 1 + num.arange(k, dtype=num.float32)) / frames
                    out[done:done + k] = v.from_level * (1.0 - ramp)
                    v.age += k
                    done += k
                if into + k >= frames:
                    v.stage = "done"
                continue
            out[done:] = 0.0                    # done: silent from here
            v.age += left
            done = n
        v.level = float(out[-1])
        return out

    def curves(self, n):
        """(0..n-1, the index's decay over n frames from 1) as float32, made once for each block size and decay"""
        num, key = np(), (n, self.patch["mod_decay"])
        if getattr(self, "_curves_key", None) != key:
            steps = num.arange(n, dtype=num.float32)
            self._curves = steps, num.exp(-steps / (self.patch["mod_decay"] * self.rate)).astype(num.float32)
            self._curves_key = key
        return self._curves

    def render(self, n=BLOCK):
        """the next n frames -> float32 (n, 2). In float32 (half the work of float64 on a Pi's NEON): the phases
        are wrapped every block, so they stay small enough to keep their precision"""
        num, p = np(), self.patch
        mono = num.zeros(n, dtype=num.float32)
        steps, fall = self.curves(n)
        sus = p["mod_sustain"]
        for v in self.voices:
            start = v.age
            env = self.envelope(v, n)
            depth = p["index"] * v.velocity * (1.0 - sus) * math.exp(-start / (p["mod_decay"] * self.rate))
            index = depth * fall + p["index"] * v.velocity * sus          # the index's envelope, this block
            mod_inc = v.inc * p["ratio"]
            phase = num.sin(num.float32(v.mod) + num.float32(mod_inc) * steps)
            phase *= index
            phase += num.float32(v.carrier) + num.float32(v.inc) * steps
            out = num.sin(phase)
            out *= env
            out *= num.float32(p["level"] * v.velocity)
            mono += out
            v.carrier = (v.carrier + v.inc * n) % TWO_PI
            v.mod = (v.mod + mod_inc * n) % TWO_PI
        self.voices = [v for v in self.voices if v.stage != "done"]
        return num.repeat(mono[:, None], 2, axis=1)


# ---------------------------------------------------------------- measuring and listening

def bench(voices=8, seconds=10.0, rate=48000):
    """voices held notes over two synths (two tracks' chords), seconds of sound rendered as fast as it goes ->
    (ms a block, the block's own length in ms, the share of one core)"""
    synths = [Synth(rate), Synth(rate, {"ratio": 1.0, "index": 1.5})]
    chord = [48, 52, 55, 59, 60, 64, 67, 71]
    for k in range(voices):
        synths[k % 2].note_on(chord[k % len(chord)], 100)
    blocks = int(seconds * rate / BLOCK)
    began = time.perf_counter()
    for _ in range(blocks):
        out = synths[0].render(BLOCK)
        out += synths[1].render(BLOCK)
    took = (time.perf_counter() - began) / blocks * 1000
    budget = BLOCK / rate * 1000
    return took, budget, took / budget


def demo_wav(path, rate=48000):
    """a held chord on a keys patch, then a bass line, written as 16-bit stereo"""
    import wave
    num = np()
    keys = Synth(rate, {"ratio": 1.0, "index": 2.0, "mod_decay": 0.8, "attack": 0.01, "release": 0.6})
    bass = Synth(rate, {"ratio": 0.5, "index": 4.0, "mod_decay": 0.15, "mod_sustain": 0.1, "sustain": 0.4,
                        "release": 0.08, "level": 0.3})
    out, frames = [], 0
    events = [(0.0, keys, "on", 60), (0.0, keys, "on", 64), (0.0, keys, "on", 67), (0.0, keys, "on", 71),
              (2.0, keys, "off", None)]
    for k, note in enumerate([36, 36, 43, 41, 36, 48, 46, 43]):
        events += [(2.5 + k * 0.25, bass, "on", note), (2.5 + k * 0.25 + 0.18, bass, "off", note)]
    events.sort(key=lambda e: e[0])
    total = int(5.0 * rate)
    while frames < total:
        now = frames / rate
        for e in [e for e in events if e[0] <= now]:
            events.remove(e)
            synth, kind, note = e[1], e[2], e[3]
            if kind == "on":
                synth.note_on(note, 100)
            elif note is None:
                synth.all_off()
            else:
                synth.note_off(note)
        out.append(keys.render(BLOCK) + bass.render(BLOCK))
        frames += BLOCK
    pcm = (num.clip(num.concatenate(out), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--bench":
        voices = int(sys.argv[2]) if len(sys.argv) > 2 else 8
        seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
        took, budget, share = bench(voices, seconds)
        print(f"{voices} voices: {took:.2f} ms a {budget:.1f} ms block = {share * 100:.0f}% of one core")
    elif len(sys.argv) > 2 and sys.argv[1] == "--wav":
        print("wrote", demo_wav(sys.argv[2]))
    else:
        print(__doc__)
