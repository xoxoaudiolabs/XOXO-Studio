"""Tests for XO-4's FM synth voice (xo4synth.py): pitch, envelopes, chords, voice stealing, blocks that join.

  python tests/test_xo4synth.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))

import xo4synth  # noqa: E402

RATE = 48000


def render(synth, seconds):
    n = int(seconds * RATE)
    return np.concatenate([synth.render(xo4synth.BLOCK) for _ in range(-(-n // xo4synth.BLOCK))])[:n]


def peak_hz(x):
    """the loudest frequency in x (mono), to a few Hz"""
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(spectrum) * RATE / len(x)


def test_pitch():
    """with no modulation it's a sine at the note's pitch: A4 is 440 Hz, A2 110"""
    for note, hz in ((69, 440.0), (45, 110.0)):
        s = xo4synth.Synth(RATE, {"index": 0.0, "attack": 0.0, "sustain": 1.0})
        s.note_on(note)
        x = render(s, 1.0)[:, 0]
        assert abs(peak_hz(x) - hz) < 2, (note, peak_hz(x))
        y = render(s, 0.01)
        assert np.array_equal(y[:, 0], y[:, 1])                 # mono, the same in both channels


def test_blocks_join():
    """a note rendered in odd-sized blocks is the same sound as in whole ones: phases and envelopes carry over"""
    a, b = xo4synth.Synth(RATE), xo4synth.Synth(RATE)
    a.note_on(60)
    b.note_on(60)
    whole = np.concatenate([a.render(512) for _ in range(8)])
    parts = np.concatenate([b.render(n) for n in (100, 412, 7, 505, 1024, 300, 212, 1536)])
    assert np.allclose(whole, parts, atol=1e-4), np.abs(whole - parts).max()


def test_envelope():
    """the attack starts from silence; the sustain holds; the release ends the note and frees the voice"""
    s = xo4synth.Synth(RATE, {"index": 0.0, "attack": 0.01, "decay": 0.05, "sustain": 0.5, "release": 0.1,
                              "level": 1.0})
    s.note_on(69, 127)
    x = render(s, 0.5)[:, 0]
    assert abs(x[0]) < 0.01                                     # from silence
    held = np.abs(x[int(0.3 * RATE):]).max()
    assert 0.45 < held < 0.55, held                             # the sustain level
    s.note_off(69)
    y = render(s, 0.2)[:, 0]
    assert np.abs(y[-RATE // 50:]).max() == 0 and s.sounding() == []   # released and gone after 0.1 s


def test_modulation_brightens():
    """modulation adds overtones, and the index envelope lets them fall away"""
    def bright(x):
        spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        cut = int(1000 * len(x) / RATE)                         # above 1 kHz, for a 220 Hz note
        return spectrum[cut:].sum() / spectrum.sum()
    plain = xo4synth.Synth(RATE, {"index": 0.0})
    fm = xo4synth.Synth(RATE, {"index": 5.0, "mod_decay": 0.1, "mod_sustain": 0.0})
    for s in (plain, fm):
        s.note_on(57)
    p, f = render(plain, 1.0)[:, 0], render(fm, 1.0)[:, 0]
    early, late = f[:RATE // 10], f[-RATE // 10:]
    assert bright(p[:RATE // 10]) < 0.02 < bright(early)
    assert bright(late) < bright(early) / 4                     # it mellows as the index falls


def test_chords_and_stealing():
    """four notes at once; a fifth takes the oldest's place; the same note again restarts it"""
    s = xo4synth.Synth(RATE)
    for note in (60, 64, 67, 71):
        s.note_on(note)
    assert s.sounding() == [60, 64, 67, 71]
    s.note_on(74)
    assert s.sounding() == [64, 67, 71, 74]
    s.note_on(67)
    assert s.sounding() == [64, 67, 71, 74] and len(s.voices) == 4
    x = render(s, 0.5)
    assert np.abs(x).max() <= 1.0                               # four at full velocity stay under full scale


def test_patch_cleaned():
    """a patch from anywhere is made safe: numbers in range, the rest the defaults"""
    p = xo4synth.clean_patch({"ratio": 99, "index": -3, "level": "loud", "attack": "0.5", "nonsense": 1})
    assert p["ratio"] == 16.0 and p["index"] == 0.0 and p["level"] == xo4synth.PATCH["level"] and p["attack"] == 0.5
    assert set(p) == set(xo4synth.PATCH)
    s = xo4synth.Synth(RATE)
    s.set_patch({"ratio": 3.5})
    assert s.patch["ratio"] == 3.5 and s.patch["index"] == xo4synth.PATCH["index"]


def test_bench_and_demo():
    """the measuring and listening tools run (a short bench; the demo into a WAV)"""
    import tempfile
    import wave
    took, budget, share = xo4synth.bench(8, 0.5)
    assert took > 0 and abs(budget - 512 / 48 / 1000 * 1000) < 0.01 and share > 0
    path = Path(tempfile.mkdtemp()) / "demo.wav"
    xo4synth.demo_wav(path)
    with wave.open(str(path)) as w:
        assert w.getnchannels() == 2 and w.getframerate() == RATE and w.getnframes() >= 5 * RATE


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
