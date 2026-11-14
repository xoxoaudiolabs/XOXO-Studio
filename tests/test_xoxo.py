"""Tests for xoxo, the Studio's command over SSH (xoxo.py, docs/SSH.md): each command queues what the web page
would (checked the same way), shows the status, refuses what it should, and installs. No Studio, no systemd, no
network: the app's status file is written here and systemctl / journalctl / the updater are stood in for.

  python tests/test_xoxo.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))
TMP = Path(tempfile.mkdtemp(prefix="xoxo-cli-"))
os.environ.update(FM1_LIBRARY=str(TMP / "library"), XDG_RUNTIME_DIR=str(TMP / "run"), FM1_SD_LIBRARY=str(TMP / "sd"))
(TMP / "run").mkdir()

import library  # noqa: E402
import update  # noqa: E402
import xoxo  # noqa: E402

RAN = []
xoxo.run = lambda command, timeout=30: (RAN.append(command), (0, "active"))[1]

ROUTES = {"BT>USB": {"on": True}, "USB>BT": {"on": True}, "XO4>BT": {"on": False}}
STATUS = {"box": "xoxo-studio", "version": "0.2.2", "sources": ["FM-1", "POCKET"], "live": True,
          "speaker": "JBL", "volume": 40, "speaker_battery": 80, "master": 70, "usb_out": "auto", "usb_outs": [],
          "usb_out_now": None, "latency": "SAFE", "follow_studio": False, "follows": None, "link_audio": "mix",
          "link_return": 46010, "link_rec": True, "pocket": None, "wifi": "home",
          "midi": {"peer": "FM-1", "enabled": True, "error": None, "controllers": ["Launchkey"], "net": [],
                   "pads": True, "xo4": True},
          "matrix": {"sources": ["BT", "USB", "XO4"], "dests": ["BT", "USB"]},
          "clock_text": "120 BPM", "recording": None,
          "settings": {"metronome": False, "bpm": 120, "clock_mode": "box", "click": "mid", "audio_rate": 48000},
          "routes": ROUTES, "presets": {"1": {"name": "live"}},
          "theme": {"value": "XOXO", "choices": ["XOXO", "MONO"]},
          "xo4": {"pattern": "A", "queued": None, "used": ["A"], "playing": False, "midi_in": False,
                  "sounds": ["KEYS", "BASS"], "choices": ["KEYS", "BASS"]},
          "kits": {"current": "808", "list": ["808"]},
          "plugins": {"list": [{"id": "fm1-companion", "name": "FM-1 Companion", "on": True}], "status": {}}}


def box(**changes):
    """the app running, with this status"""
    library.COMMANDS.unlink(missing_ok=True)
    library.write_status(dict(json.loads(json.dumps(STATUS)), **changes))


def xo(*argv):
    """xoxo argv -> (exit code, stdout, stderr)"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = xoxo.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def queued():
    try:
        lines = [json.loads(line) for line in library.COMMANDS.read_text().splitlines() if line.strip()]
    except OSError:
        return []
    return [{k: v for k, v in c.items() if k != "time"} for c in lines]   # (queue_command stamps the time)


def test_settings_go_to_the_box_as_the_page_sends_them():
    cases = [
        (("tempo", "128"), {"cmd": "set", "key": "bpm", "value": 128}),
        (("volume", "55"), {"cmd": "set", "key": "volume", "value": 55}),
        (("master", "0"), {"cmd": "set", "key": "master", "value": 0}),
        (("clock", "follow"), {"cmd": "set", "key": "clock_mode", "value": "follow"}),
        (("metronome", "on"), {"cmd": "set", "key": "metronome", "value": True}),
        (("latency", "lower"), {"cmd": "set", "key": "latency", "value": "LOWER"}),
        (("usb-out", "off"), {"cmd": "set", "key": "usb_out", "value": "off"}),
        (("link", "follow", "on"), {"cmd": "set", "key": "follow_studio", "value": True}),
        (("link", "rec", "off"), {"cmd": "set", "key": "link_rec", "value": False}),
        (("link", "audio", "fm1s"), {"cmd": "set", "key": "link_audio", "value": "fm1s"}),
        (("screen", "theme", "MONO"), {"cmd": "set", "key": "desk_theme", "value": "MONO"}),
        (("play",), {"cmd": "transport", "value": "start"}),
        (("stop",), {"cmd": "transport", "value": "stop"}),
        (("rec", "start"), {"cmd": "record", "value": "start"}),
        (("xo4", "pattern", "c"), {"cmd": "xo4", "action": "pattern", "value": "C", "track": None}),
        (("xo4", "play"), {"cmd": "xo4", "action": "play", "value": None, "track": None}),
        (("xo4", "midi-in", "on"), {"cmd": "xo4", "action": "midi_in", "value": True, "track": None}),
        (("xo4", "sound", "2", "bass"), {"cmd": "xo4", "action": "sound", "value": "BASS", "track": 2}),
        (("kit", "808"), {"cmd": "kit", "name": "808"}),
        (("plugin", "fm1-companion", "off"), {"cmd": "plugin", "id": "fm1-companion", "on": False}),
        (("midi", "preset", "2", "save", "my", "set"), {"cmd": "preset", "slot": "2", "action": "save",
                                                         "name": "my set"}),
        (("midi", "preset", "1", "load"), {"cmd": "preset", "slot": "1", "action": "load", "name": None}),
    ]
    for argv, sent in cases:
        box()
        code, out, err = xo(*argv)
        assert code == 0 and out.startswith("sent"), (argv, out, err)
        assert queued() == [sent], (argv, queued())


def test_bad_values_are_refused_and_nothing_is_queued():
    for argv in [("tempo", "500"), ("tempo", "fast"), ("volume", "101"), ("latency", "FASTEST"),
                 ("clock", "usb"), ("metronome", "maybe"), ("rec", "pause"), ("link", "audio", "loud"),
                 ("xo4", "pattern", "Z"), ("xo4", "sound", "3", "BASS"), ("midi", "preset", "5", "load"),
                 ("plugin", "Bad Id", "on"), ("play", "now"), ("nothing",)]:
        box()
        code, out, err = xo(*argv)
        assert code == 1 and err.startswith("xoxo: ") and not out, (argv, out, err)
        assert queued() == [], argv


def test_nothing_is_queued_while_the_app_isnt_answering():
    box()
    library.STATUS.write_text(json.dumps(dict(STATUS, time=0)))      # old: the app stopped
    code, _, err = xo("tempo", "100")
    assert code == 1 and "isn't answering" in err and queued() == []
    library.STATUS.unlink()
    code, out, _ = xo("status")                # the status still says what it can: the services
    assert code == 0 and "services" in out and "not answering" in out


def test_settings_shown_without_a_value():
    box()
    assert xo("tempo")[1].strip() == "120 BPM"
    assert xo("volume")[1].strip() == "volume 40 (JBL)"
    assert xo("latency")[1].strip() == "latency SAFE"
    assert xo("rec")[1].strip() == "not recording"
    box(recording=75)
    assert xo("rec")[1].strip() == "recording 1:15"
    assert queued() == []


def test_status():
    box(recording=61)
    RAN.clear()
    code, out, _ = xo("status")
    assert code == 0
    for text in ("app active", "web active", "pocket active", "version    0.2.2", "FM-1, POCKET", "JBL",
                 "Launchkey", "recording  1:01", "latency    SAFE", "wifi       home"):
        assert text in out, (text, out)
    assert ["systemctl", "--user", "is-active", "fm1-bridge"] in RAN
    code, out, _ = xo("status", "--json")
    data = json.loads(out)
    assert data["services"]["app"] == "active" and data["status"]["version"] == "0.2.2"


def test_midi_routes_one_at_a_time():
    box()
    code, out, _ = xo("midi")
    assert code == 0 and "BT->USB" in out and "USB->BT" in out and "XO4->BT" not in out and "1:live" in out
    code, out, _ = xo("midi", "route", "XO4", "BT", "on")
    assert code == 0, out
    sent = queued()[0]
    assert sent["cmd"] == "routes" and sent["routes"]["XO4>BT"]["on"] is True
    assert sent["routes"]["BT>USB"]["on"] is True and sent["routes"]["USB>BT"]["on"] is True   # the rest kept
    box()
    code, _, err = xo("midi", "route", "NOPE", "BT", "on")
    assert code == 1 and "no route" in err and queued() == []


def test_restart():
    box()
    RAN.clear()
    assert xo("restart")[0] == 0 and RAN[-1] == ["systemctl", "--user", "restart", "fm1-bridge"]
    assert xo("restart", "all")[0] == 0
    assert RAN[-1] == ["systemctl", "--user", "restart", "fm1-bridge", "fm1-web", "fm1-pocket-in"]
    box(recording=10)                          # a recording would be cut off: not without --force
    RAN.clear()
    code, _, err = xo("restart")
    assert code == 1 and "recording" in err and RAN == []
    assert xo("restart", "web")[0] == 0 and RAN[-1][-1] == "fm1-web"   # (the web app doesn't record)
    assert xo("restart", "--force")[0] == 0 and RAN[-1][-1] == "fm1-bridge"
    assert xo("restart", "everything")[0] == 1


def test_recordings_and_pull():
    take = library.folder("recordings") / "take-001.wav"
    with wave.open(str(take), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(b"\0\0\0\0" * 48000 * 3)
    code, out, _ = xo("recordings")
    assert code == 0 and "take-001.wav" in out and "0:03" in out
    assert json.loads(xo("recordings", "--json")[1])[0]["name"] == "take-001.wav"
    code, out, _ = xo("pull", "take-001.wav")
    assert code == 0 and str(take) in out and "scp " in out
    for bad in ("nope.wav", "../take-001.wav"):
        assert xo("pull", bad)[0] == 1


def test_logs():
    calls = []
    real, xoxo.os.execvp = xoxo.os.execvp, lambda f, a: calls.append(a)
    try:
        xo("logs")
        xo("logs", "web", "-f", "-n", "20")
        xo("logs", "update")
        assert xo("logs", "-n", "lots")[0] == 1 and xo("logs", "kernel")[0] == 1
    finally:
        xoxo.os.execvp = real
    assert calls[0] == ["journalctl", "--user", "-u", "fm1-bridge", "-n", "100", "--no-pager"]
    assert calls[1] == ["journalctl", "--user", "-u", "fm1-web", "-n", "20", "--no-pager", "-f"]
    assert calls[2] == ["tail", "-n100", str(update.LOG)]


def test_update():
    info = {"build": "studio", "installed": "v0.2", "newest": "v0.3", "tag": "v0.3", "newer": True, "error": None,
            "notes": "", "helper": True, "root": True, "last": {}, "busy": None}
    started = []
    saved = update.check, update.start, update.busy, update.helper, update.restart, update.root_ready
    update.check = lambda fresh=False: dict(info)
    update.start = lambda: started.append(1)
    update.busy = lambda status=None: None
    update.root_ready = lambda: True
    update.helper = lambda *a: (started.append(a), (True, "Put back"))[1]
    update.restart = lambda: started.append("restart")
    real_input = xoxo.input if hasattr(xoxo, "input") else None
    try:
        code, out, _ = xo("update", "--check")
        assert code == 0 and "v0.2" in out and "v0.3" in out and "update     yes" in out
        assert json.loads(xo("update", "--check", "--json")[1])["newest"] == "v0.3"
        xoxo.input = lambda prompt: "no"       # asked, and not yes: nothing
        assert xo("update")[1].strip() == "nothing done" and started == []
        xoxo.input = lambda prompt: "yes"
        assert xo("update")[0] == 0 and started == [1]
        started.clear()
        del xoxo.input
        assert xo("update", "--yes")[0] == 0 and started == [1]
        started.clear()
        assert xo("update", "--back", "--yes")[0] == 0 and started == [("--back",), "restart"]
        update.check = lambda fresh=False: dict(info, newer=False)
        assert "up to date (v0.2)" in xo("update", "--yes")[1]
        update.check = lambda fresh=False: dict(info, busy="a recording is running: stop it first")
        started.clear()
        assert xo("update", "--yes")[0] == 1 and started == []
        update.busy = lambda status=None: "an update is already running"
        assert xo("update", "--back", "--yes")[0] == 1 and started == []
    finally:
        update.check, update.start, update.busy, update.helper, update.restart, update.root_ready = saved
        if real_input:
            xoxo.input = real_input
        elif hasattr(xoxo, "input"):
            del xoxo.input


def test_a_closed_input_is_not_a_yes():
    import builtins
    real = builtins.input

    def closed(prompt):
        raise EOFError
    builtins.input = closed
    try:
        assert xoxo.confirm("Update?", False) is False and xoxo.confirm("Update?", True) is True
    finally:
        builtins.input = real


def test_help_and_installed():
    code, out, _ = xo("help")
    assert code == 0 and "xoxo status" in out
    assert xo()[0] == 2
    import inspect
    source = inspect.getsource(xoxo.main)
    for line in xoxo.__doc__.splitlines():     # every command the help lists is one main() knows
        if line.startswith("  xoxo "):
            assert f'"{line.split()[1]}"' in source, line
    app = (ROOT / "fm1-bt-bridge" / "install-app.sh").read_text()
    assert '"$DIR/xoxo.py"' in app and "~/.local/bin/xoxo" in app


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
