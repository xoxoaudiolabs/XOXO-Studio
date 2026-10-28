"""Tests for the library (sloop.py, library.py) against a pretend FM-1. No hardware needed.

  python tests/test_library.py        (needs mido: pip install mido)
"""
import json
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

import fake_fm1  # noqa: E402
import library  # noqa: E402
import sloop  # noqa: E402


def device(**kw):
    fake = fake_fm1.FakeFM1(**kw)
    return fake, sloop.Sloop(sloop.Link(mido=fake, time_scale=0.02))


def use(fake):
    """library jobs connect through the fake"""
    library.connect = lambda: sloop.Sloop(sloop.Link(mido=fake, time_scale=0.02))


def write_wav(path, seconds=0.3, hz=220):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / 44100)))
                               for i in range(int(44100 * seconds))))
    return path


def test_encodings():
    for data in (b"", b"\x00", bytes(range(256)), bytes([0xFF] * 7), bytes([0x80] * 15)):
        assert sloop.unpack7(sloop.pack7(data)) == data
        assert all(b < 0x80 for b in sloop.pack7(data))
    assert sloop.u35(0x12345678) == [0x78, 0x2C, 0x51, 0x11, 0x01]
    assert sloop.project_format(fake_fm1.project(6)) == 6 and sloop.project_format(b"PER3") == 0
    assert sloop.firmware_at_least("SLOOP 2.6", (2, 5, 1)) and not sloop.firmware_at_least("SLOOP 2.5", (2, 5, 1))


def test_info():
    fake, dev = device()
    assert dev.version == "SLOOP 2.7.1" and dev.info["proto"] == 12 and dev.can_backup()
    assert dev.info["pcount"] == 71 and sloop.device_format(dev.info) == 6
    assert device(proto=5)[1].can_backup() is False


def test_backup_round_trip():
    fake, dev = device()
    original = dict(fake.objects)
    backup = dev.backup()
    assert backup["format"] == "sloop-backup" and backup["version"] == 1 and backup["firmware"] == "SLOOP 2.7.1"
    objects = sloop.objects_of(backup)
    assert objects == {i: original[i] for i in fake.listed()}
    json.dumps(backup)                                     # it serialises as SLOOP's editor expects
    # wipe the device, restore, and everything is back byte for byte
    for i in fake.objects:
        fake.objects[i] = b"" if i >= 2 else fake.objects[i]
    dev.restore(backup)
    assert all(fake.objects[i] == original[i] for i in original), "restore is not byte-identical"


def test_lost_frames_are_retried():
    fake, dev = device()
    fake.drop_every = 7                                    # every 7th request gets no answer
    backup = dev.backup()
    assert sloop.objects_of(backup)[0] == fake.objects[0]


def test_lost_replies_after_a_write():
    fake, dev = device()
    original = dict(fake.objects)
    backup = dev.backup()
    for i in (2, 5, 32):
        fake.objects[i] = b""
    fake.lose_reply_every = 3  # writes happen, but some replies never come back
    dev.restore(backup)
    fake.lose_reply_every = 0
    assert all(fake.objects[i] == original[i] for i in original), "restore with lost replies differs"


def test_refusals():
    fake, dev = device()
    backup = dev.backup()
    fake.playing = True
    try:
        dev.restore(backup)
        raise AssertionError("restore while playing")
    except sloop.SloopError as e:
        assert e.code == "stop"
    fake.playing = False
    newer = dict(backup, objects=[dict(o) for o in backup["objects"]])
    old_fake, old_dev = device(version="SLOOP 2.5", pcount=61, proto=10)
    try:
        old_dev.restore(newer)
        raise AssertionError("a 2.7 backup into 2.5")
    except sloop.SloopError as e:
        assert e.code == "newer"
    broken = json.loads(json.dumps(backup))
    broken["objects"][0]["crc"] ^= 1
    try:
        sloop.objects_of(broken)
        raise AssertionError("damaged backup accepted")
    except sloop.SloopError as e:
        assert e.code == "bad"


def test_projects():
    fake, dev = device()
    backup = dev.backup()
    assert set(sloop.projects_in(backup)) == {"working", "A", "D"}
    data = sloop.project_from(backup, "D")
    dev.put_project(data, "B")
    assert fake.objects[3] == fake.objects[5]
    shared = sloop.project_file(data, "My song", "SLOOP 2.7.1", "x:D")
    assert sloop.project_from(json.loads(json.dumps(shared))) == data
    try:
        sloop.project_from(backup, "C")
        raise AssertionError("empty project accepted")
    except sloop.SloopError:
        pass


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
