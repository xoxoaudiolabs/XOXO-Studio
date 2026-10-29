"""Tests for the web page's server (web.py) against a temporary library. No hardware needed.

  python tests/test_web.py [--serve]      (--serve keeps it running on http://localhost:8765 to look at)
"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
TMP = Path(tempfile.mkdtemp(prefix="fm1-web-"))
os.environ.update(FM1_LIBRARY=str(TMP / "library"), XDG_RUNTIME_DIR=str(TMP / "run"), FM1_SD_LIBRARY=str(TMP / "sd"))

import library  # noqa: E402
import web  # noqa: E402
from test_library import write_wav  # noqa: E402

PORT = 8765 if "--serve" in sys.argv else 0     # 0: any free port (a fixed one clashes with a preview server)
BASE = ""                                   # set by setup(); 127.0.0.1, not "localhost": Windows tries IPv6 first


def call(path, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(BASE + path, data=data, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            return reply.status, reply.read(), reply.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def jcall(path, body=None, raw=None):
    status, data, _ = call(path, body, raw)
    return status, json.loads(data)


def setup():
    global BASE
    server = web.ThreadingHTTPServer(("127.0.0.1", PORT), web.Handler)
    BASE = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_page_and_listing():
    status, page, headers = call("/")
    assert status == 200 and b"<title>" in page and headers["Content-Type"].startswith("text/html")
    status, lib = jcall("/api/library")
    assert status == 200 and set(lib) == {"samples", "recordings"}, lib


def test_installable():
    status, page, _ = call("/")
    assert b'rel="manifest" href="/manifest.webmanifest"' in page and b"apple-touch-icon" in page
    status, body, headers = call("/manifest.webmanifest")
    manifest = json.loads(body)
    assert status == 200 and headers["Content-Type"].startswith("application/manifest+json")
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    for icon in manifest["icons"] + [{"src": "/icons/apple-touch-icon.png"}]:
        status, png, headers = call(icon["src"])
        assert status == 200 and png.startswith(b"\x89PNG") and headers["Content-Type"] == "image/png", icon
    for bad in ("/icons/nope.png", "/icons/../web.py", "/icons/..%2Fweb.py", "/icons/icon-192.txt"):
        assert call(bad)[0] == 404, bad


def test_uploads():
    wav = write_wav(TMP / "bass_C2.wav", 0.1).read_bytes()
    assert jcall("/api/upload?folder=samples&name=bass_C2.wav", raw=wav)[1]["ok"]
    status, reply = jcall("/api/upload?folder=samples&name=noise.wav", raw=b"RIFF....not audio")
    assert status == 400 and not reply["ok"]
    assert not (library.folder("samples") / "noise.wav").exists()
    assert not list(library.folder("samples").glob(".*.part"))        # no leftovers
    # names and folders that would escape the library or mix kinds up
    for folder, name in (("samples", "../evil.wav"), ("samples", "x.sh"), ("etc", "passwd.json"),
                         ("firmware", "a.wav"), ("samples", ".hidden.wav")):
        status, reply = jcall(f"/api/upload?folder={folder}&name={name}", raw=wav)
        assert status == 400, (folder, name)


def test_downloads():
    wav = write_wav(library.folder("samples") / "kick_C2.wav", 0.1).read_bytes()
    status, data, headers = call("/files/samples/kick_C2.wav")
    assert status == 200 and data == wav and "attachment" in headers["Content-Disposition"]
    assert call("/files/samples/..%2F..%2Fx.wav")[0] == 404
    assert call("/files/backups/x.json")[0] == 404                      # no FM-1 backups here
    assert call("/api/project?backup=x.json&source=A")[0] == 404


def test_recordings():
    data = b"RIFF" + bytes(40) + bytes(192000 * 3)                 # a 3-second "recording"
    (library.folder("recordings") / "2026-10-22_101500_fm1.wav").write_bytes(data)
    status, lib = jcall("/api/library")
    rec = lib["recordings"][0]
    assert rec["name"] == "2026-10-22_101500_fm1.wav" and rec["seconds"] == 3
    status, body, headers = call("/files/recordings/2026-10-22_101500_fm1.wav")
    assert status == 200 and body == data and headers["Content-Type"] == "audio/wav"
    assert int(headers["Content-Length"]) == len(data)
    status, reply = jcall("/api/upload?folder=recordings&name=x.wav", raw=data)
    assert status == 400                                          # made on the box only
    # the sample editor: a real take, opened, edited and saved into the samples (no box confirmation)
    from test_library import write_recording
    take = write_recording(library.folder("recordings") / "2026-10-22_101600_fm1.wav", sound=2.0)
    status, info = jcall("/api/edit-info?folder=recordings&file=" + take.name)
    assert status == 200 and info["note"] == "A2" and info["name"] == "rec-101600" and 0 < info["level"] < 1, info
    edit = {"folder": "recordings", "file": take.name, "start": 1.0, "end": 2.0, "fade_in": 0.01,
            "fade_out": 0.05, "normalize": True, "reverse": True, "note": "A2", "name": "my bass"}
    status, reply = jcall("/api/save-sample", edit)
    assert status == 200 and reply["name"] == "my-bass_A2.wav", reply
    assert (library.folder("samples") / "my-bass_A2.wav").is_file()
    status, info = jcall("/api/edit-info?folder=samples&file=my-bass_A2.wav")
    assert status == 200 and info["start"] == 0.0 and info["name"] == "my-bass", info
    for bad in ({"start": 2.0, "end": 1.0}, {"note": "H2"}, {"file": "../x.wav"}, {"folder": "backups"},
                {"start": "soon"}):
        assert jcall("/api/save-sample", dict(edit, **bad))[0] == 400, bad
    assert jcall("/api/edit-info?folder=backups&file=x.json")[0] == 404
    assert jcall("/api/ask", {"cmd": "load-sample", "files": [rec["name"]], "slot": 3})[0] == 404   # no FM-1 slots
    assert jcall("/api/delete", {"folder": "recordings", "name": rec["name"]})[1]["ok"]


def test_status_and_commands():
    library.STATUS.unlink(missing_ok=True)
    assert jcall("/api/status")[1] == {"offline": True}                 # no box running
    assert jcall("/api/command", {"cmd": "set", "key": "metronome", "value": True})[0] == 503
    library.write_status({"live": True, "settings": {"bpm": 120}})
    status, st = jcall("/api/status")
    assert st["live"] is True and st["settings"]["bpm"] == 120
    for good in ({"cmd": "set", "key": "metronome", "value": True}, {"cmd": "set", "key": "bpm", "value": 96},
                 {"cmd": "set", "key": "clock_mode", "value": "box"}, {"cmd": "set", "key": "audio_rate", "value": 44100},
                 {"cmd": "set", "key": "volume", "value": 55}, {"cmd": "transport", "value": "start"},
                 {"cmd": "record", "value": "stop"}, {"cmd": "preset", "slot": "2", "action": "save", "name": "Keys"},
                 {"cmd": "routes", "routes": {"BT>SMP": {"transpose": 12, "channels": 9}}}):
        library.write_status({"live": True})      # as the box does every 2 s (a request here can take 2 s)
        reply = jcall("/api/command", good)
        assert reply[1]["ok"], (good, reply)
    for bad in ({"cmd": "set", "key": "bpm", "value": 999}, {"cmd": "set", "key": "metronome", "value": "yes"},
                {"cmd": "set", "key": "shutdown", "value": True}, {"cmd": "transport", "value": "rewind"},
                {"cmd": "routes", "routes": {"BT>SMP": {"transpose": 99}}},
                {"cmd": "routes", "routes": {"BT>BT": {"on": True}}},
                {"cmd": "routes", "routes": {"BT>SMP": {"channels": [0] * 15}}},
                {"cmd": "preset", "slot": "9", "action": "save"}, {"cmd": "reboot"}, ["not", "a", "dict"]):
        library.write_status({"live": True})
        assert jcall("/api/command", bad)[0] == 400, bad
    queued = library.take_commands()
    assert [c["cmd"] for c in queued] == ["set"] * 5 + ["transport", "record", "preset", "routes"]
    assert queued[-1]["routes"]["BT>SMP"]["transpose"] == 12 and queued[-1]["routes"]["Box>BT"]["on"] is True
    assert library.take_commands() == []                               # taken once



def test_studio_commands():
    """the Studio tab's commands: XO-4 (pattern, play, MIDI IN, a synth's sound), a kit, the decks' level"""
    for good in ({"cmd": "xo4", "action": "pattern", "value": "C"}, {"cmd": "xo4", "action": "play"},
                 {"cmd": "xo4", "action": "midi_in", "value": True},
                 {"cmd": "xo4", "action": "sound", "track": 2, "value": "BASS"},
                 {"cmd": "kit", "name": "808-KIT"}, {"cmd": "set", "key": "mix_decks", "value": 120}):
        library.write_status({"live": True})
        reply = jcall("/api/command", good)
        assert reply[1]["ok"], (good, reply)
    for bad in ({"cmd": "xo4", "action": "pattern", "value": "Z"}, {"cmd": "xo4", "action": "midi_in", "value": 1},
                {"cmd": "xo4", "action": "sound", "track": 3, "value": "BASS"},
                {"cmd": "xo4", "action": "sound", "track": True, "value": "BASS"},
                {"cmd": "xo4", "action": "sound", "track": 1, "value": "TUBA"}, {"cmd": "xo4", "action": "erase"},
                {"cmd": "kit", "name": ""}, {"cmd": "set", "key": "mix_a", "value": 100}):
        library.write_status({"live": True})
        assert jcall("/api/command", bad)[0] == 400, bad
    queued = library.take_commands()
    assert [c["cmd"] for c in queued] == ["xo4"] * 4 + ["kit", "set"]


def test_dj_music():
    """the DJ decks' music folder: listed, a track added (streamed to disk), deleted; only audio, only plain names"""
    import djlib
    status, body, _ = call("/api/upload?folder=music&name=Night%20Drive.mp3", raw=b"ID3" + b"\0" * 4096)
    assert status == 200, body
    assert (djlib.MUSIC / "Night Drive.mp3").stat().st_size == 4099
    (djlib.MUSIC / "Crate").mkdir(exist_ok=True)
    (djlib.MUSIC / "Crate" / "Deep.flac").write_bytes(b"fLaC")
    tracks = {m["name"]: m for m in jcall("/api/music")[1]}
    assert tracks["Night Drive.mp3"]["top"] and tracks["Night Drive.mp3"]["title"] == "Night Drive"
    assert not tracks["Crate/Deep.flac"]["top"]                       # in a subfolder: listed, not deleted here
    assert call("/api/upload?folder=music&name=notes.txt", raw=b"hi")[0] == 400
    assert call("/api/upload?folder=music&name=..%2Fx.mp3", raw=b"ID3")[0] == 400
    assert jcall("/api/delete", {"folder": "music", "name": "Crate/Deep.flac"})[0] == 404
    assert jcall("/api/delete", {"folder": "music", "name": "Night Drive.mp3"})[1]["ok"]
    assert not (djlib.MUSIC / "Night Drive.mp3").exists()

def test_audio_ranges():
    data = bytes(range(256)) * 40
    (library.folder("recordings") / "2026-10-22_120000_fm1.wav").write_bytes(data)
    status, body, headers = call("/files/recordings/2026-10-22_120000_fm1.wav?inline=1")
    assert status == 200 and body == data and headers["Accept-Ranges"] == "bytes" and "inline" in headers["Content-Disposition"]
    request = urllib.request.Request(BASE + "/files/recordings/2026-10-22_120000_fm1.wav", headers={"Range": "bytes=10-19"})
    with urllib.request.urlopen(request, timeout=10) as reply:
        assert reply.status == 206 and reply.read() == data[10:20]
        assert reply.headers["Content-Range"] == f"bytes 10-19/{len(data)}"
    assert web.byte_range("bytes=-5", 100) == (95, 99) and web.byte_range("bytes=90-", 100) == (90, 99)
    assert web.byte_range("bytes=200-300", 100) is None and web.byte_range("bytes=1-2,5-6", 100) is None


def test_run_and_delete():
    (TMP / "sd" / "samples").mkdir(parents=True, exist_ok=True)
    write_wav(TMP / "sd" / "samples" / "pad_C3.wav", 0.1)
    status, reply = jcall("/api/run", {"cmd": "import-sd"})
    assert reply["ok"] and "1 new" in reply["message"]
    assert jcall("/api/run", {"cmd": "reboot"})[0] == 400
    assert jcall("/api/delete", {"folder": "samples", "name": "pad_C3.wav"})[1]["ok"]
    assert not (library.folder("samples") / "pad_C3.wav").exists()
    assert jcall("/api/delete", {"folder": "samples", "name": "../../x.wav"})[0] == 404
    assert jcall("/api/run", {"cmd": "backup"})[0] == 400                # no FM-1 jobs here


if __name__ == "__main__":
    server = setup()
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
    if "--serve" in sys.argv:
        write_wav(library.folder("samples") / "lead_A4.wav", 0.2)
        print(f"serving {BASE} (Ctrl-C to stop)")
        threading.Event().wait()
