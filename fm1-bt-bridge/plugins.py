"""XOXO Studio's plug-ins: the host (docs/PLUGINS.md). A plug-in is a folder with plugin.json and a Python file:

  plugin.json   {"id": "fm1-companion", "name": "FM-1 Companion", "version": "1.0.0", "api": 1,
                 "author": "XOXO Audio Labs", "license": "GPL-3.0", "entry": "plugin.py"}
  plugin.py     API = 1
                def setup(studio): ...      # studio: a Studio, its only door into the Studio

Where plug-ins are found: ~/xoxo-plugins/<id>/ (anyone's; a clone of xoxoaudiolabs/XOXO-Studio-Plugins puts its
plug-ins one level down, ~/xoxo-plugins/XOXO-Studio-Plugins/<id>/, and those are found too), and $XOXO_PLUGINS (a
folder, for tests). A plug-in only runs once someone has switched it on (MORE > PLUG-INS, or the web page), and
one that raises an error is switched off with a message, instead of stopping the Studio.

What API 1 gives a plug-in (Studio):
  settings, save(), say(text)                    its own settings, kept in the Studio's (state["plugins"][id])
  sources()                                      the sound sources' names now ("FM-1 A", "XO-4", "EP-136" ...)
  add_audio_source(match, label)                 a sound source in the mixer: match a regular expression on the
                                                 PipeWire node's name, description and card name; label a name, or
                                                 a function of the source's number among this rule's (0, 1, ...)
  add_midi_device(pattern, name)                 a MIDI device's name in the routes: pattern a regular expression on
                                                 its ALSA client name; name, with {n} for its letter (A, B, ...)
  add_screen(label, screen)                      a screen of its own, opened from MORE > PLUG-INS: screen(ui, studio)
                                                 with draw(img, d, now), drawn with ui's widgets (480x320)
  add_web(status=None, commands=None)            fields in the web page's status (plugins.<id>) and its commands
  on(event, fn)                                  "tick" (about once a second, with the app), "devices" (the sound
                                                 sources changed: fn(labels))
Added to API 1 later (a plug-in checks with hasattr, so it runs on an older Studio too):
  add_card_names(fn)                             USB devices named by their ALSA sound card, for the mixer and the
                                                 MIDI routes alike: fn(the text of /proc/asound/cards, "" without
                                                 it) -> {card number: name}, asked on each device scan. Its names
                                                 come before add_audio_source's and add_midi_device's rules
  confirm(title, lines, fn)                      the Studio's hold-to-confirm screen (a 2 s hold), then fn()
  set_detail(source, text)                       a few words beside a sound source's name, on HOME and the web
                                                 page's mixer, in place of "USB" (an FM-1's firmware: "SLOOP
                                                 2.8"); source its name ("FM-1 A"), text None to take it away.
                                                 Gone when the plug-in is switched off
  add_sound_source(node_name, label)             its own sound process as a mixer source: the PipeWire Audio/Source
                                                 node of exactly that name (a pw-loopback's, as XO-4's), under label
                                                 ("SYNTH A"), its mixer level kept by the node's name; there while
                                                 the node is
  pocket()                                       a linked Pocket's IP address (its network MIDI session's), or
                                                 None. Its FM-1s A-C come as sound sources fm1-pocket-a/b/c and
                                                 MIDI devices "FM-1 Companion Pocket FM-1 A/B/C": name them with
                                                 add_audio_source(r"fm1-pocket-a", ...) and add_midi_device(r"Pocket
                                                 FM-1 A$", ...); unnamed they're POCKET FM-1 A-C
  midi_devices()                                 the MIDI devices with a column in the routes now ("FM-1 A",
                                                 "POCKET FM-1 A" ...), and NET (network MIDI: a linked Pocket's
                                                 whole session, a computer) while it's there
  send_midi(device, messages)                    MIDI to one of them, as a route to it would: messages a list of
                                                 messages, each a list of bytes ([0x90, 60, 100])
  source_nodes()                                 the sound sources now, {name: PipeWire node name}: to record one
                                                 (pw-record --target <node>)
  latency()                                      the Studio's latency step: {"name": "SAFE", "block": 1024 samples,
                                                 "buffer_ms": 40 (the Pocket link's receive buffer), "rate": 48000}
  plugin.json "library": {folder: [".suffix"]}   folders of its own in ~/fm1-library the web page can list files
                                                 of, upload to, download from and delete from (not the Studio's
                                                 own: samples, recordings)
"""
import importlib.util
import json
import os
import re
from pathlib import Path

API = 1                                        # the host API this Studio gives plug-ins
LETTERS = "ABCDEFGH"
CARDS = Path("/proc/asound/cards")
OWN_FOLDERS = ("samples", "recordings", "music")   # the Studio's library folders: not a plug-in's


def plugin_dirs():
    dirs = [Path.home() / "xoxo-plugins"]
    if os.environ.get("XOXO_PLUGINS"):
        dirs.insert(0, Path(os.environ["XOXO_PLUGINS"]))
    return dirs


def find(dirs=None):
    """{id: (folder, manifest)} of the plug-ins in the folders (and one level further down: a repository of them)"""
    out = {}
    for base in dirs or plugin_dirs():
        if not base.is_dir():
            continue
        for folder in sorted([p for p in base.iterdir() if p.is_dir()] +
                             [q for p in base.iterdir() if p.is_dir() for q in p.iterdir() if q.is_dir()]):
            manifest = read_manifest(folder)
            if manifest and manifest["id"] not in out:
                out[manifest["id"]] = (folder, manifest)
    return out


def read_manifest(folder):
    """a folder's plugin.json, checked; None if it isn't a plug-in"""
    try:
        m = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(m, dict) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", str(m.get("id", ""))):
        return None
    entry = str(m.get("entry") or "plugin.py")
    if Path(entry).name != entry or not (folder / entry).is_file():
        return None
    return {"id": m["id"], "name": str(m.get("name") or m["id"])[:24], "version": str(m.get("version") or "?")[:16],
            "api": m.get("api"), "author": str(m.get("author") or "")[:40], "license": str(m.get("license") or "")[:24],
            "entry": entry, "description": str(m.get("description") or "")[:200],
            "library": library_folders(m.get("library"))}


def library_folders(declared):
    """a manifest's "library": {folder: [".suffix", ...]}, checked: plain folder names, not the Studio's own"""
    out = {}
    if not isinstance(declared, dict):
        return out
    for folder, suffixes in list(declared.items())[:8]:
        if isinstance(suffixes, str):
            suffixes = [suffixes]
        if (not isinstance(folder, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,23}", folder)
                or folder in OWN_FOLDERS or not isinstance(suffixes, list)):
            continue
        kinds = [x.lower() for x in suffixes[:4] if isinstance(x, str) and re.fullmatch(r"\.[A-Za-z0-9]{1,8}", x)]
        if kinds:
            out[folder] = kinds
    return out


class Studio:
    """what a plug-in is given: its one door into the Studio (API 1)"""

    def __init__(self, host, pid, settings):
        self._host, self.id, self.settings = host, pid, settings
        self.audio, self.midi, self.screens, self.events, self.cards = [], [], [], {}, []
        self.web_status, self.web_commands = None, {}
        self.details = {}                     # source name (upper case) -> its few words (set_detail)
        self.nodes = {}                       # its own sound processes' node names -> their labels

    def save(self):
        self._host.save()

    def say(self, text, seconds=2):
        self._host.say(str(text), seconds)

    def sources(self):
        return [str(n.get("label", "")) for n in (getattr(self._host.app, "others", None) or [])]

    def add_sound_source(self, node_name, label):
        self.nodes[str(node_name)] = str(label)[:16]

    def set_detail(self, source, text):
        key = str(source).strip().upper()
        if text is None or not str(text).strip():
            self.details.pop(key, None)
        else:
            self.details[key] = str(text).strip()[:16]

    def pocket(self):
        app = self._host.app
        return app.pocket_address() if hasattr(app, "pocket_address") else None

    def midi_devices(self):
        app = self._host.app
        dests = app.matrix_lists()[1] if getattr(app, "midi", None) and hasattr(app, "matrix_lists") else []
        return [d[2:] if d.startswith("U:") else d for d in dests if d.startswith("U:") or d == "NET"]

    def send_midi(self, device, messages):
        midi = getattr(self._host.app, "midi", None)
        if midi and hasattr(midi, "send_to"):
            midi.send_to(str(device), [[int(b) & 0xFF for b in m] for m in messages if m])

    def source_nodes(self):
        found = {}
        for _, node in self._host.app.mix_channels():   # (their full names, as the MIDI devices': the mixer's
            name = str(node.get("label") or "USB").upper()   # are cut to 10 letters)
            n = 2
            while name in found:
                name, n = f"{str(node.get('label') or 'USB').upper()} #{n}", n + 1
            found[name] = str(node.get("name"))
        return found

    def latency(self):
        app = self._host.app
        import bridge
        name, block, ms = bridge.latency_step(app.state.get("latency"))
        return {"name": name, "block": block, "buffer_ms": ms, "rate": app.state.get("audio_rate", 48000)}

    def add_audio_source(self, match, label):
        self.audio.append((re.compile(match, re.I) if isinstance(match, str) else match, label))

    def add_card_names(self, fn):
        self.cards.append(fn)

    def confirm(self, title, lines, fn):
        """the Studio's hold-to-confirm screen; fn() once it's held (a mistake in fn switches the plug-in off)"""
        host = self._host
        host.app.ask(str(title)[:20], [str(line)[:40] for line in lines][:3], lambda: host.call(self.id, fn),
                     back="status")

    def add_midi_device(self, pattern, name):
        re.compile(pattern)                    # (a bad pattern fails here, in setup, not in the MIDI process)
        self.midi.append([pattern, str(name)])

    def add_screen(self, label, screen):
        self.screens.append((str(label)[:16], screen))

    def add_web(self, status=None, commands=None):
        self.web_status, self.web_commands = status, dict(commands or {})

    def on(self, event, fn):
        self.events.setdefault(event, []).append(fn)


class Host:
    """the plug-ins found and those switched on; app: the Studio's App (its state, say, save_settings)"""

    def __init__(self, app, dirs=None):
        self.app, self.dirs = app, dirs
        self.found, self.loaded, self.errors = {}, {}, {}

    # ---- the Studio's side

    def save(self):
        self.app.save_settings()

    def say(self, text, seconds=2):
        self.app.say(text, seconds)

    def entry(self, pid):
        """state["plugins"][pid]: {"on": bool, "settings": {...}}"""
        plugins = self.app.state.setdefault("plugins", {})
        return plugins.setdefault(pid, {"on": False, "settings": {}})

    def start(self):
        """find the plug-ins, and run those switched on"""
        self.found = find(self.dirs)
        for pid in self.found:
            if self.entry(pid)["on"]:
                self.load(pid)

    def load(self, pid):
        folder, m = self.found[pid]
        if m["api"] != API:
            self.errors[pid] = f"needs a Studio with plug-in API {m['api']}"
            return False
        studio = Studio(self, pid, self.entry(pid)["settings"])
        try:
            spec = importlib.util.spec_from_file_location(f"xoxo_plugin_{pid.replace('-', '_')}", folder / m["entry"])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.setup(studio)
        except Exception as e:                 # a plug-in's mistake isn't the Studio's: it's off, and said so
            self.errors[pid] = f"{type(e).__name__}: {e}"[:80]
            return False
        self.loaded[pid] = studio
        self.errors.pop(pid, None)
        return True

    def set_on(self, pid, on):
        """switch a plug-in on or off (kept); -> a message for the screen"""
        if pid not in self.found:
            return "No such plug-in"
        self.entry(pid)["on"] = bool(on)
        self.save()
        name = self.found[pid][1]["name"]
        if on and pid not in self.loaded:
            if not self.load(pid):
                self.entry(pid)["on"] = False
                self.save()
                return f"{name}: {self.errors.get(pid)}"
        if not on:
            self.loaded.pop(pid, None)
        self.app.plugins_changed()
        return f"{name} {'on' if on else 'off'}"

    def fail(self, pid, error):
        """a plug-in raised an error while running: switched off, said"""
        studio = self.loaded.pop(pid, None)
        self.errors[pid] = f"{type(error).__name__}: {error}"[:80]
        self.entry(pid)["on"] = False
        self.save()
        name = self.found.get(pid, (None, {"name": pid}))[1]["name"]
        self.say(f"{name} stopped: {self.errors[pid]}"[:60], 4)
        if studio is not None:
            self.app.plugins_changed()

    def call(self, pid, fn, *args, default=None):
        try:
            return fn(*args)
        except Exception as e:
            self.fail(pid, e)
            return default

    # ---- what the plug-ins add

    def listing(self):
        """[{id, name, version, author, license, description, on, error}] of every plug-in found"""
        return [dict(m, on=pid in self.loaded, error=self.errors.get(pid)) for pid, (_, m) in self.found.items()]

    def card_names(self, text=None):
        """{sound card number: name} from the plug-ins' add_card_names (text: /proc/asound/cards, read here)"""
        if not any(studio.cards for studio in self.loaded.values()):
            return {}
        if text is None:
            try:
                text = CARDS.read_text(errors="replace")
            except OSError:
                text = ""
        out = {}
        for pid, studio in list(self.loaded.items()):
            for fn in studio.cards:
                names = self.call(pid, fn, text, default=None) or {}
                for card, name in (names.items() if isinstance(names, dict) else []):
                    if isinstance(card, int) and not isinstance(card, bool) and str(name).strip():
                        out.setdefault(card, str(name)[:16])
        return out

    def source_label(self, props, counts):
        """a sound source's name from a plug-in's card names or rules, or None; counts: {rule: sources named by it
        so far, "cards": the card names, asked once a scan}"""
        if "cards" not in counts:
            counts["cards"] = self.card_names()
        if counts["cards"]:
            card = node_card(props)
            if card in counts["cards"]:
                return counts["cards"][card]
        text = " ".join(str(props.get(k, "")) for k in ("node.name", "node.description", "alsa.card_name",
                                                         "alsa.long_card_name", "api.alsa.card.name"))
        for pid, studio in list(self.loaded.items()):
            for i, (match, label) in enumerate(studio.audio):
                hit = self.call(pid, (match.search if hasattr(match, "search") else match), text, default=None)
                if hit:
                    n = counts.get((pid, i), 0)
                    counts[(pid, i)] = n + 1
                    return str(self.call(pid, label, n, default=pid) if callable(label) else label)[:16]
        return None

    def sound_source(self, node_name):
        """the label a plug-in gives its own sound process's node (add_sound_source), or None"""
        return next((s.nodes[node_name] for s in list(self.loaded.values()) if node_name in s.nodes), None)

    def source_detail(self, name):
        """a plug-in's few words for a sound source (set_detail), or None"""
        key = str(name).strip().upper()
        return next((s.details[key] for s in list(self.loaded.values()) if key in s.details), None)

    def midi_names(self):
        """[[pattern, name]] for the MIDI process: a device whose client name matches is called name ({n}: A, B..)"""
        return [rule for studio in self.loaded.values() for rule in studio.midi]

    def screens(self):
        """[(pid, label, screen class)] for MORE > PLUG-INS"""
        return [(pid, label, screen) for pid, studio in self.loaded.items() for label, screen in studio.screens]

    def web_status(self):
        out = {}
        for pid, studio in list(self.loaded.items()):
            if studio.web_status:
                out[pid] = self.call(pid, studio.web_status, default=None)
        return out

    def web_command(self, pid, name, args):
        studio = self.loaded.get(pid)
        if not studio or name not in studio.web_commands:
            raise ValueError("no such plug-in command")
        return self.call(pid, studio.web_commands[name], args)

    def emit(self, event, *args):
        for pid, studio in list(self.loaded.items()):
            for fn in studio.events.get(event, []):
                self.call(pid, fn, *args)


def node_card(props):
    """a PipeWire node's ALSA sound card number, or None ("api.alsa.path": "front:3", or "alsa.card": "3")"""
    m = re.search(r":(\d+)", str(props.get("api.alsa.path", "")))
    card = m.group(1) if m else str(props.get("alsa.card", ""))
    return int(card) if card.isdigit() else None


def port_card(port):
    """a MIDI port's name -> its ALSA sound card number, or None: "Felucca:Felucca MIDI 1 28:0" -> 3 (a sound
    card's MIDI is sequencer client 16 + 4 x its card number)"""
    m = re.search(r"\s(\d+):\d+$", str(port or ""))
    client = int(m.group(1)) if m else 0
    return (client - 16) // 4 if 16 <= client < 128 else None


def name_device(client, rules, taken, port=None, cards=None):
    """a MIDI device's name in the routes from the plug-ins' card names (port: its full port name, cards: {card:
    name}) or rules (midi_names), or None; taken: names given so far this scan (so a second matching device is B)"""
    card = port_card(port) if cards else None
    if card in (cards or {}):
        return cards[card]
    for pattern, name in rules or []:
        if re.search(pattern, client, re.I):
            if "{n}" not in name:
                return name
            for letter in LETTERS:
                candidate = name.replace("{n}", letter)
                if candidate not in taken:
                    return candidate
    return None
