"""Tests for the library (library.py, sampler.py). No hardware needed.

  python tests/test_library.py        (needs numpy)
"""
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
TMP = Path(tempfile.mkdtemp(prefix="fm1-test-"))
os.environ.update(FM1_LIBRARY=str(TMP / "library"), XDG_RUNTIME_DIR=str(TMP / "run"), FM1_SD_LIBRARY=str(TMP / "sd"))
os.environ["FM1_SETTINGS"] = str(TMP / "settings.json")          # never this computer's own box settings

import library  # noqa: E402


def write_wav(path, seconds=0.3, hz=220):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / 44100)))
                               for i in range(int(44100 * seconds))))
    return path


def write_recording(path, before=1.0, sound=10.0, hz=110.0):
    """a 48 kHz stereo recording: silence, a sawtooth-like synth note, silence"""
    import numpy as np
    t = np.arange(int(48000 * sound)) / 48000
    note = sum(np.sin(2 * math.pi * hz * k * t) / k for k in range(1, 6)) * 8000
    x = np.concatenate([np.zeros(int(48000 * before)), note, np.zeros(48000)])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(np.repeat(x.astype("<i2"), 2).tobytes())
    return path


def test_sample_editor():
    """A recording, edited, saved to the samples; a sample edited again."""
    import numpy as np
    import sampler
    rec = write_recording(library.folder("recordings") / "2026-10-22_001217_fm1.wav")
    info = sampler.info(rec)                               # opens on the sound, its note found
    assert info["name"] == "rec-001217" and info["note"] == "A2" and info["rate"] == 48000, info  # 110 Hz: A2
    assert 0.98 < info["start"] < 1.0 < info["end"], info
    out = sampler.save(rec, info["name"], sampler.parse_note(info["note"]), 1.0, 3.0,
                       fade_in=0.1, fade_out=0.2, normalize=True, reverse=False)
    assert out.parent.name == "samples" and out.name == "rec-001217_A2.wav", out.name
    rate, y = sampler.load(out)
    assert rate == 48000 and abs(len(y) - 2 * 48000) <= 1                 # mono, the take's rate, 2 s
    assert abs(y[0]) < 50 and abs(y[-1]) < 50                            # faded in and out
    assert abs(np.abs(y).max() - sampler.PEAK) <= 1                      # normalized: -6 dBFS
    rate, x = sampler.load(rec)
    back = sampler.render(x, rate, 1.0, 3.0, fade_in=0, fade_out=0, normalize=False, reverse=True)
    assert np.array_equal(back[::-1], np.clip(np.round(x[48000:144000]), -32768, 32767).astype("<i2"))
    # a sample opens whole, with the note in its name; saving it again makes a new file
    info = sampler.info(out)
    assert info["name"] == "rec-001217" and info["note"] == "A2" and (info["start"], info["end"]) == (0.0, 2.0), info
    again = sampler.save(out, "rec-001217", 45, 0.0, 1.0)
    assert again.name == "rec-001217-2_A2.wav" and out.exists()
    assert sampler.file_name("pad A3 soft", 60) == "pad-soft_C4.wav"     # no second note to confuse a sampler
    for bad in ("H2", "C9"):
        try:
            sampler.parse_note(bad)
            raise AssertionError(f"{bad} was accepted")
        except ValueError:
            pass
    try:
        sampler.save(rec, "x", None, 2.0, 2.005)
        raise AssertionError("a selection that short was accepted")
    except ValueError:
        pass


def test_sd_import():
    sd = TMP / "sd" / "samples"
    sd.mkdir(parents=True)
    write_wav(sd / "pad_C3.wav", 0.1)
    (sd / "notes.txt").write_text("not a sample")
    assert library.import_sd() == ["samples/pad_C3.wav"]
    assert library.import_sd() == []                       # already there


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    tests.sort(key=lambda t: t[1].__code__.co_firstlineno)
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
