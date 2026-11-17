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
Added for the default plug-ins (2026-11-17: the DJ decks, the sample editor, the decks; anyone's may use them):
  add_tab(name, tab)                             a tab of its own in the Studio's tab bar (before MORE), full
                                                 screen: tab(ui, studio) with draw(img, d, now) (the whole 480x320,
                                                 its own "< HOME"), and optional view(now), opened() (False: not
                                                 opened), stop() (switched off), what (its name in the Pi
                                                 Bluetooth warning: a tab that plays sound)
  add_app_sound(key, node_name, label, shown)    a program of its own playing to the Studio's output (the
                                                 default): a channel in the mixer under label, its level, MUTE,
                                                 SOLO and CUE set on that node; key its level's name in the
                                                 settings; shown() while it's on HOME and the MIXER
  add_setting(menu, label, value, change)        a row in MORE > PLAYING / AUDIO / MIDI SETTINGS (menu "play",
                                                 "audio", "midi"): value() its text, change() when it's pressed
  clock()                                        the Studio's beat grid now ([beat time, beat length, playing]),
                                                 or None
  redraw()                                       the screen drawn again (something its tab shows changed)
  add_editor_screen(screen)                      the sample editor's screen: drawn while a take or sample is open
                                                 to edit (the editor plug-in's), screen(ui, studio) with draw(img,
                                                 d, now); a pad's TRIM and "Edit as sample" are there while one is
  plugin.json "restart": true                    switching it starts the Studio app again
  plugin.json "process": "module"                a process of its own started with the Studio app, before the MIDI
                                                 process, while it's on (plugins.start_processes: module.start_process
                                                 (state, box), a module of its folder): the routes' SMP notes go to
                                                 its midi_conn (the sampler's pads); with "restart" too
  process()                                      that process (what start_process gave), or None
  plugin.json "controllers": [pattern, ...]      MIDI controllers it reads itself (regular expressions on the
                                                 port's name), kept off the MIDI routes while it's on;
             "controller_maps": "path"           and a JSON file (in ~/fm1-library) whose keys are the names of
                                                 more of them (learnt maps)

The sample editor, the DJ decks and the decks are plug-ins like any other: their folders are in the Studio's
repository (plugins/) and install-app.sh puts them in ~/xoxo-plugins, off until someone switches them on.
"""
import importlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

API = 1                                        # the host API this Studio gives plug-ins
LETTERS = "ABCDEFGH"

def switched_on(state, pid):
    """a plug-in switched on in the settings (state["plugins"][id]["on"]): off until someone switches it on"""
    entry = ((state or {}).get("plugins") or {}).get(pid)
    return isinstance(entry, dict) and entry.get("on") is True


CARDS = Path("/proc/asound/cards")
OWN_FOLDERS = ("samples", "recordings", "music")   # the Studio's library folders: not a plug-in's


def taken_controllers(state, dirs=None):
    """[[patterns, maps file]] of the MIDI controllers the plug-ins switched on read themselves (their manifests'
    "controllers" and "controller_maps"), for the MIDI process: read before any plug-in runs"""
    return [[list(m.get("controllers") or []), m.get("controller_maps")] for pid, (_, m) in find(dirs).items()
            if switched_on(state, pid) and (m.get("controllers") or m.get("controller_maps"))]


def start_processes(state, box, dirs=None):
    """{plug-in id: what its module.start_process(state, box) gave} of the plug-ins switched on whose manifest has
    "process" (the sampler's pads): started as the Studio app starts, before the MIDI process"""
    out = {}
    for pid, (folder, m) in sorted(find(dirs).items(), key=lambda kv: (kv[1][1]["order"], kv[0])):
        if m.get("process") and switched_on(state, pid):
            try:
                out[pid] = plugin_module(pid, m["process"], dirs).start_process(state, box)
            except Exception:
                continue
    return out


def plugin_module(pid, name, dirs=None):
    """a module of a plug-in's folder (web.py's: the decks' djlib), imported, or None if it isn't there"""
    found = find(dirs).get(pid)
    if not found or not (found[0] / f"{name}.py").is_file():
        return None
    if str(found[0]) not in sys.path:
        sys.path.append(str(found[0]))
    return importlib.import_module(name)


def plugin_dirs():
    dirs = [Path.home() / "xoxo-plugins"]
    if os.environ.get("XOXO_PLUGINS"):
        dirs.insert(0, Path(os.environ["XOXO_PLUGINS"]))
    return dirs


def find(dirs=None):
    """{id: (folder, manifest)} of the plug-ins in the folders (and one level further down: a repository of them)"""
    out = {}
    for base in plugin_dirs() if dirs is None else dirs:
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
            "library": library_folders(m.get("library")),
            "controllers": [str(x)[:64] for x in (m.get("controllers") or [])[:8] if isinstance(x, str) and valid_re(x)],
            "controller_maps": controller_maps(m.get("controller_maps")),
            "order": m.get("order") if isinstance(m.get("order"), int) else 99, "restart": m.get("restart") is True,
            "process": m["process"] if isinstance(m.get("process"), str) and re.fullmatch(r"[a-z][a-z0-9_]{0,31}",
                                                                                       m["process"]) else None}


def valid_re(pattern):
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def controller_maps(path):
    """a manifest's "controller_maps": a file inside ~/fm1-library (relative, no ..), or None"""
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        return None
    return path[:120]


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
        self.tabs, self.app_sounds, self.settings_rows = [], [], []
        self.editor_screens = []

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

    def add_tab(self, name, tab):
        self.tabs.append((re.sub(r"[^A-Z0-9-]", "", str(name).upper())[:8] or self.id.upper()[:8], tab))

    def add_app_sound(self, key, node_name, label, shown=None):
        key = re.sub(r"[^a-z0-9]", "", str(key).lower())[:16]
        self.app_sounds.append((key, str(node_name), str(label)[:10], shown))

    def add_setting(self, menu, label, value, change):
        if menu in ("play", "audio", "midi"):
            self.settings_rows.append((menu, str(label)[:20], value, change))

    def add_editor_screen(self, screen):
        self.editor_screens.append(screen)

    def process(self):
        return self._host.processes.get(self.id)

    def clock(self):
        midi = getattr(self._host.app, "midi", None)
        return (getattr(midi, "clock", None) or {}).get("grid")

    def redraw(self):
        if hasattr(self._host.app, "post"):
            self._host.app.post("plugin")


class Host:
    """the plug-ins found and those switched on; app: the Studio's App (its state, say, save_settings)"""

    def __init__(self, app, dirs=None):
        self.app, self.dirs = app, dirs
        self.found, self.loaded, self.errors = {}, {}, {}
        self.processes = {}                     # plug-in id -> its own process (start_processes), from main()
        self.started = False                    # start() run: a plug-in not found is off

    # ---- the Studio's side

    def save(self):
        self.app.save_settings()

    def say(self, text, seconds=2):
        self.app.say(text, seconds)

    def entry(self, pid):
        """state["plugins"][pid]: {"on": bool, "settings": {...}}"""
        plugins = self.app.state.setdefault("plugins", {})
        entry = plugins.setdefault(pid, {"on": False, "settings": {}})
        entry.setdefault("on", False)
        entry.setdefault("settings", {})
        return entry

    def start(self):
        """find the plug-ins, and run those switched on"""
        self.started = True
        self.found = dict(sorted(find(self.dirs).items(), key=lambda kv: (kv[1][1]["order"], kv[0])))
        for pid in self.found:
            if self.entry(pid)["on"]:
                self.load(pid)

    def load(self, pid):
        folder, m = self.found[pid]
        if m["api"] != API:
            self.errors[pid] = f"needs a Studio with plug-in API {m['api']}"
            return False
        studio = Studio(self, pid, self.entry(pid)["settings"])
        if str(folder) not in sys.path:        # (its other modules: imported by their names)
            sys.path.append(str(folder))
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
        m = self.found[pid][1]
        if m.get("restart") and bool(on) != (pid in self.loaded):   # (its process starts with the Studio app)
            self.entry(pid)["on"] = bool(on)
            self.save()
            (self.loaded.__setitem__(pid, Studio(self, pid, self.entry(pid)["settings"])) if on
             else self.loaded.pop(pid, None))
            self.app.plugins_changed()
            if hasattr(self.app, "restart_app"):
                self.app.restart_app()
            return f"{m['name']} {'on' if on else 'off'}: the Studio starts again"
        self.entry(pid)["on"] = bool(on)
        self.save()
        name = self.found[pid][1]["name"]
        if on and pid not in self.loaded:
            if not self.load(pid):
                self.entry(pid)["on"] = False
                self.save()
                return f"{name}: {self.errors.get(pid)}"
        if not on:
            self.stop_tabs(self.loaded.pop(pid, None))
        self.app.plugins_changed()
        return f"{name} {'on' if on else 'off'}"

    def stop_tabs(self, studio):
        """a plug-in switched off: its tabs' stop() (the decks' program stopped)"""
        for tab in (getattr(studio, "made_tabs", None) or {}).values():
            stop = getattr(tab, "stop", None)
            if stop:
                try:
                    stop()
                except Exception:
                    pass

    def fail(self, pid, error):
        """a plug-in raised an error while running: switched off, said"""
        studio = self.loaded.pop(pid, None)
        self.stop_tabs(studio)
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

    def tabs(self):
        """[(pid, name, tab class)] of the plug-ins switched on, in their order"""
        return [(pid, name, tab) for pid, studio in self.loaded.items() for name, tab in studio.tabs]

    def tab(self, pid, name, ui):
        """the tab's object (made once a run, with ui), or None if its plug-in is off or it failed"""
        studio = self.loaded.get(pid)
        if studio is None:
            return None
        made = studio.__dict__.setdefault("made_tabs", {})
        if name not in made:
            cls = next((t for n, t in studio.tabs if n == name), None)
            obj = self.call(pid, cls, ui, studio) if cls else None
            if obj is None:
                return None
            made[name] = obj
        return made[name]

    def editor_screen(self, ui):
        """(pid, the sample editor's screen, made once a run) of the first plug-in on with one, or None"""
        return self.first_made(ui, "editor_screens")

    def first_made(self, ui, kind):
        for pid, studio in list(self.loaded.items()):
            if getattr(studio, kind):
                made = studio.__dict__.setdefault("made_" + kind, [])
                if not made:
                    page = self.call(pid, getattr(studio, kind)[0], ui, studio)
                    if page is None:
                        continue
                    made.append(page)
                return pid, made[0]
        return None

    def app_sounds(self):
        """[(pid, key, node name, label, shown)] of the plug-ins switched on"""
        return [(pid,) + sound for pid, studio in self.loaded.items() for sound in studio.app_sounds]

    def setting_rows(self, menu):
        """[(row key, label, value text)] the plug-ins add to a settings menu"""
        out = []
        for pid, studio in list(self.loaded.items()):
            for i, (m, label, value, _change) in enumerate(studio.settings_rows):
                if m == menu:
                    out.append((f"plugin:{pid}:{i}", label, str(self.call(pid, value, default="?"))[:12]))
        return out

    def change_setting(self, key):
        """a plug-in's settings row pressed (its key from setting_rows); False if it isn't one"""
        m = re.fullmatch(r"plugin:([a-z0-9-]+):(\d+)", str(key))
        studio = m and self.loaded.get(m.group(1))
        if not studio or int(m.group(2)) >= len(studio.settings_rows):
            return False
        self.call(m.group(1), studio.settings_rows[int(m.group(2))][3])
        return True

    def taken_controllers(self):
        """[[patterns, maps file]] for the MIDI process, of the plug-ins switched on"""
        return [[list(m.get("controllers") or []), m.get("controller_maps")] for pid, (_, m) in self.found.items()
                if pid in self.loaded and (m.get("controllers") or m.get("controller_maps"))]

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
