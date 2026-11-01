"""Tests for the plug-in host (plugins.py) with made-up plug-ins in a temporary folder. No hardware needed.

  python tests/test_plugins.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fm1-bt-bridge"))

import plugins  # noqa: E402


def make(base, pid, code, api=1, entry="plugin.py"):
    folder = base / pid
    folder.mkdir(parents=True)
    (folder / "plugin.json").write_text(json.dumps({"id": pid, "name": pid.upper(), "version": "0.1", "api": api,
                                                    "author": "Test", "entry": entry}))
    (folder / entry).write_text(code)
    return folder


class App:
    def __init__(self):
        self.state, self.said, self.changed = {}, [], 0

    def save_settings(self):
        pass

    def say(self, text, seconds=2):
        self.said.append(text)

    def plugins_changed(self):
        self.changed += 1


GOOD = '''
API = 1
ticks = []
def setup(studio):
    studio.add_audio_source(r"felucca|sloop", lambda n: "FM-1 " + "AB"[n])
    studio.add_midi_device(r"^(felucca|sloop)", "FM-1 {n}")
    studio.add_web(status=lambda: {"count": len(ticks)}, commands={"hello": lambda args: "hi " + args["who"]})
    studio.on("tick", lambda: ticks.append(1))
'''


def test_found_off_until_switched_on():
    base = Path(tempfile.mkdtemp(prefix="xoxo-plugins-"))
    make(base, "fm1", GOOD)
    make(base / "XOXO-Studio-Plugins", "other", GOOD)            # a repository of them: one level down
    (base / "not-a-plugin").mkdir()
    host = plugins.Host(App(), [base])
    host.start()
    assert sorted(host.found) == ["fm1", "other"] and host.loaded == {}       # found, nothing running
    assert host.source_label({"node.name": "alsa_input.usb-Felucca"}, {}) is None
    assert host.set_on("fm1", True) == "FM1 on" and "fm1" in host.loaded
    assert host.app.state["plugins"]["fm1"]["on"] is True and host.app.changed == 1
    counts = {}
    assert host.source_label({"node.name": "alsa_input.usb-Felucca_FM-1-00"}, counts) == "FM-1 A"
    assert host.source_label({"node.description": "SLOOP"}, counts) == "FM-1 B"
    assert host.source_label({"node.name": "alsa_input.usb-Casio"}, counts) is None
    assert host.midi_names() == [["^(felucca|sloop)", "FM-1 {n}"]]
    host.emit("tick")
    assert host.web_status() == {"fm1": {"count": 1}}
    assert host.web_command("fm1", "hello", {"who": "you"}) == "hi you"
    assert host.set_on("fm1", False) == "FM1 off" and host.loaded == {} and host.midi_names() == []
    again = plugins.Host(App(), [base])                           # switched on: runs at the next start
    again.app.state = {"plugins": {"other": {"on": True, "settings": {}}}}
    again.start()
    assert list(again.loaded) == ["other"]


def test_a_failing_plugin_is_switched_off():
    base = Path(tempfile.mkdtemp(prefix="xoxo-plugins-"))
    make(base, "broken", "API = 1\ndef setup(studio):\n    raise RuntimeError('oops')\n")
    make(base, "later", "API = 1\ndef setup(studio):\n    studio.on('tick', lambda: 1 / 0)\n")
    make(base, "future", "API = 2\ndef setup(studio):\n    pass\n", api=2)
    host = plugins.Host(App(), [base])
    host.start()
    assert "BROKEN: RuntimeError" in host.set_on("broken", True) and "RuntimeError" in host.errors["broken"]
    assert host.app.state["plugins"]["broken"]["on"] is False      # it doesn't run, and stays off
    assert "plug-in API 2" in host.set_on("future", True)
    host.set_on("later", True)
    host.emit("tick")                                              # its error: off, said, the Studio carries on
    assert "later" not in host.loaded and "ZeroDivisionError" in host.errors["later"]
    assert host.app.state["plugins"]["later"]["on"] is False and "LATER stopped" in host.app.said[-1]


def test_manifest_checks():
    base = Path(tempfile.mkdtemp(prefix="xoxo-plugins-"))
    make(base, "Bad Name", GOOD)
    make(base, "escape", GOOD, entry="plugin.py")
    (base / "escape" / "plugin.json").write_text(json.dumps({"id": "escape", "api": 1, "entry": "../x.py"}))
    assert plugins.find([base]) == {}


def test_midi_device_names():
    rules = [["^(felucca|sloop)", "FM-1 {n}"], ["^nanokey", "KEYS"]]
    taken = set()
    for client, want in (("Felucca", "FM-1 A"), ("SLOOP", "FM-1 B"), ("nanoKEY2", "KEYS"), ("EP-136", None)):
        got = plugins.name_device(client, rules, taken)
        assert got == want, (client, got)
        if got:
            taken.add(got)


CARDS = '''
API = 1
def setup(studio):
    studio.add_card_names(lambda text: {int(n): "FM-1 " + "ABCD"[i] for i, n in enumerate(text.split())})
    studio.add_card_names(lambda text: {3: "NOT ME", "x": "BAD", 9: "  "})
    studio.add_audio_source(r"felucca", "RULE")
'''


def test_card_names():
    """devices named by their sound card come before the rules, in the mixer and in the MIDI routes alike"""
    base = Path(tempfile.mkdtemp(prefix="xoxo-plugins-"))
    make(base, "cards", CARDS)
    host = plugins.Host(App(), [base])
    host.start()
    assert host.card_names("3 2") == {}                            # (off: nothing)
    host.set_on("cards", True)
    assert host.card_names("3 2") == {3: "FM-1 A", 2: "FM-1 B"}    # the first plug-in's name wins; bad ones dropped
    counts = {"cards": host.card_names("3 2")}
    assert host.source_label({"node.name": "alsa_input.usb-Felucca", "api.alsa.path": "front:2"}, counts) == "FM-1 B"
    assert host.source_label({"node.name": "alsa_input.usb-Felucca", "alsa.card": "7"}, counts) == "RULE"
    cards = {3: "FM-1 A", 2: "FM-1 B"}
    assert plugins.port_card("Felucca:Felucca MIDI 1 28:0") == 3 and plugins.port_card("Through:Port 14:0") is None
    assert plugins.name_device("Felucca", [], set(), "Felucca:Felucca MIDI 1 24:0", cards) == "FM-1 B"
    assert plugins.name_device("Felucca", [], set(), "Felucca:Felucca MIDI 1 36:0", cards) is None


def test_confirm_and_library_folders():
    base = Path(tempfile.mkdtemp(prefix="xoxo-plugins-"))
    make(base, "lib", "API = 1\ndef setup(studio):\n    studio.on('tick', lambda: 1)\n")
    manifest = json.loads((base / "lib" / "plugin.json").read_text())
    manifest["library"] = {"backups": [".json"], "firmware": ".fwsc", "samples": [".wav"], "../up": [".x"],
                           "patches": ["syx"]}
    (base / "lib" / "plugin.json").write_text(json.dumps(manifest))
    found = plugins.find([base])
    assert found["lib"][1]["library"] == {"backups": [".json"], "firmware": [".fwsc"]}   # not the Studio's own
    app = App()
    asked = []
    app.ask = lambda title, lines, action, back="pick": asked.append((title, lines, action))
    host = plugins.Host(app, [base])
    host.start()
    host.set_on("lib", True)
    done = []
    host.loaded["lib"].confirm("Restore?", ["a backup", "replaces"], lambda: done.append(1))
    assert asked[0][:2] == ("Restore?", ["a backup", "replaces"]) and not done
    asked[0][2]()                                                  # held 2 s
    assert done == [1]


SYNTHS = '''
API = 1
def setup(studio):
    studio.add_sound_source("synths-a", "SYNTH A")
    studio.add_sound_source("synths-b", "SYNTH B")
'''


def test_sound_source_of_its_own():
    """add_sound_source: a plug-in's own sound process (a pw-loopback's Audio/Source) is a mixer source under its
    label, internal, its key from the node's name (so its level stays, whatever it's called); only while the
    plug-in is on and the node is there"""
    import bridge
    base = Path(tempfile.mkdtemp(prefix="xoxo-plugins-"))
    make(base, "synths", SYNTHS)
    host = plugins.Host(App(), [base])
    host.start()

    def node(i, name, cls="Audio/Source"):
        return {"id": i, "type": "PipeWire:Interface:Node", "info": {"props": {"media.class": cls, "node.name": name}}}
    port = {"type": "PipeWire:Interface:Port", "info": {"props": {"port.direction": "out", "port.name": "capture_FL",
                                                                   "node.id": 7, "port.id": 0}}}
    objects = [node(7, "synths-a"), node(8, "synths-a-in", "Audio/Sink"), port]
    assert bridge.pick_nodes(objects, host)[1] == []                 # off: not a source
    host.set_on("synths", True)
    _, sources = bridge.pick_nodes(objects, host)
    assert [(n["label"], n["internal"], n["ports"]) for n in sources] == [("SYNTH A", True, ["capture_FL"])]
    assert bridge.device_keys(sources) == ["u-synthsa"]
    assert bridge.device_keys([dict(sources[0], label="RENAMED")]) == ["u-synthsa"]   # (by the node's name)
    assert host.sound_source("synths-b") == "SYNTH B" and host.sound_source("fm1-xo4") is None
    host.set_on("synths", False)
    assert bridge.pick_nodes(objects, host)[1] == []


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
