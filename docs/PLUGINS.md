# Plug-ins and devices: the design

**Being built for the launch** (Maker Faire Orlando; the user, 2026-10-31: "Yes, at launch"). Built so far: the
plug-in host (`fm1-bt-bridge/plugins.py`, API 1), MORE › PLUG-INS (`deskplugins.py`), the web app's status and
commands, and FM-1 Companion 0.1 (sound and MIDI). The device registry (section 1) and moving the built-ins
(section 3) come after the launch. Plug-ins are open to anyone from the start, so the API
below is versioned and kept stable. The first plug-in from outside the core is **FM-1 Companion**: the FM-1 as sound and
MIDI, and its library.

## Why

Today every feature is built into the core:

- The Studio's screens are one class with every feature mixed in (`deskui.DeskUI` takes `DeskPads`, `DeskDecks`,
  `DeskXO4`), and the tabs are one fixed list (`deskui.TABS`).
- The app (`bridge.App`) still mixes in the Pocket's OLED screens (`LibraryScreens`, `MeterScreens`, `MidiScreens`,
  `SampleEditor`).
- Devices are found in half a dozen places, each its own way: USB sound and the Studio's own sources in
  `bridge.pick_nodes`, the jack, the DAC and the computer in `jack_node`, `dac_node` and `computer_node`, the I/O
  card in `iocard.py`, MIDI devices, DJ controllers and the computer's MIDI in `blemidi.UsbControllers.wanted`,
  the Pocket in `pocket_linked`, and their PipeWire tuning in a WirePlumber file.

Adding or taking out a feature (the FM-1's, most of all) means editing the core in all those places.

## 1. One device registry

Every kind of device becomes a **profile**, in one list (`devices.py`), each saying how to recognise it, what it is
to the Studio, and what it's called:

```python
AudioProfile(id="dac-hat", role=HEADPHONES, label="DAC", priority=20,
             match=lambda props: any(k in text(props) for k in ("bossdac", "pcm512x")))
MidiProfile(id="computer", label="COMPUTER", match=lambda port: port.lower().startswith("f_midi"))
```

- **Roles** (audio): `SOURCE` (into the mixer), `SPEAKER` (the main output), `HEADPHONES` (the copy, CUE, PFL),
  `LINE_OUT` (a copy of the main mix), `COMPUTER` (the USB link: in as a source, out as the mix without itself).
  MIDI: `KEYS` (a route end), `CONTROLLER` (taken by a screen, e.g. the decks), `CLOCK`.
- **Priority** decides between profiles that both match (the DAC HAT before the Pi's jack).
- The core scan becomes one loop: every PipeWire node and MIDI port goes through the profiles once, and the
  Studio works from what that gives (`sources`, `speaker`, `headphones`, `line_outs`, `computer`, `midi`).
- A profile can carry its **WirePlumber tuning** (headroom, clock priority, never the default output), written
  into the WirePlumber file at install, instead of a separate hand-kept rule.

The built-in profiles: the Bluetooth speaker, the Pi's jack, the DAC HAT, the I/O card (line out, DIN), the
computer link (audio, MIDI), any USB sound source, any USB MIDI device, the Hercules, a learnt DJ controller,
the pads, XO-4, the decks, the Pocket link. Each one moves over with its tests, one at a time.

## 2. Plug-ins

A plug-in is a folder with a manifest and a Python file:

```
plugins/fm1-companion/
  plugin.json     {"id": "fm1-companion", "name": "FM-1 Companion", "version": "1.0.0", "api": 1,
                   "author": "XOXO Audio Labs", "license": "GPL-3.0", "entry": "plugin.py"}
  plugin.py
```

```python
API = 1

def setup(studio):                 # studio: the plug-in host, the only door into the Studio
    studio.add_audio_source(r"felucca|sloop", lambda n: "FM-1 " + "AB"[n])   # a mixer source, named
    studio.add_midi_device(r"^(felucca|sloop)", "FM-1 {n}")                  # a MIDI device, named
    studio.add_screen("FM-1", FM1Screen)          # opened from MORE > PLUG-INS
    studio.add_web(status=web_status, commands={"backup": backup})
    studio.on("tick", tick)
```

That is API 1 as built for the launch (`plugins.py` lists it in full: also `settings`, `save()`, `say()`,
`sources()`). The rest of this section (device profiles with roles, MIDI route ends of a plug-in's own, a sound
process, settings rows, the web page's plug-in rows) is the plan for later versions of the API.

**What a plug-in can add:**

- **Devices:** audio and MIDI profiles (above)
- **MIDI route ends:** sources and destinations in the MIDI routes, with a callback for what arrives
- **Screens:** full screens opened from MORE › PLUG-INS ("< PLUG-INS" top left), drawn with the Studio's widgets (`button`, `widget` kinds tap,
  hold, gate, slide, drag), its theme and font, at 480×320
- **Settings:** its own, under MORE › PLUG-INS › its name, kept in the Studio's settings under its id
- **A sound process:** like XO-4's or the pads', its sound a mixer source by its node name
- **The web app:** fields in `/api/status` (under `plugins.<id>`) and commands; the page shows them as a section
  of plain rows (a switch, a choice, a button, a value), described by the plug-in, drawn by the page. No plug-in
  JavaScript, so a plug-in can't change the page itself
- **Events:** a device in or out, play / stop, the tempo, a pattern change

**What the host gives a plug-in:** its settings, `say()` (a message on the screen), the mixer levels, sending MIDI
to a route end, the library folders, the clock. Nothing else of the core: a plug-in that reaches past `studio`
isn't supported and may break on any update.

**Versions:** `api` in the manifest is the host API it was written for. The host runs plug-ins of the API
versions it supports and says so for one it doesn't ("needs a newer Studio"). Additions keep the version; a
change that breaks plug-ins makes a new one, and the old one stays supported for a while.

**Installing:** a plug-in folder in `~/xoxo-plugins/` (from a download, or `git clone`), or from the web app
(upload a `.zip`). Each is switched on or off in MORE › PLUG-INS and on the web page; one that's off leaves no
trace: no tab, no device profiles, no process. First-party plug-ins live in their own repository,
**xoxoaudiolabs/XOXO-Studio-Plugins** (one folder per plug-in, the same layout as anyone's), apart from the Studio's code,
except the **default plug-ins** (XO-4, the decks, the Pocket link, the computer link: section 3), which stay in the
Studio's repository (`plugins/`), so a new Studio works without a second download.

**Trust:** a plug-in is Python running as the Studio does, with its access to the files and the network. The
Studio says so when one is switched on from outside the repository, and only runs plug-ins someone switched on.
A plug-in that raises an error is switched off with a message on the screen, instead of stopping the Studio.

## 3. The built-ins move onto it

The core keeps the HOME, MIXER, RECORD, MIDI, EDITOR and MORE screens, the device registry, the mixer, the
recorder and the plug-in host. These become first-party plug-ins, each its own step with its tests:

- **XO-4** (with the pads, its DRUMS)
- **DJ decks** (the Hercules and learnt controllers are its device profiles)
- **Pocket link** (its receiver, its network MIDI peer, POCKET in the mixer)
- **Computer link** (the USB interface: the gadget, COMPUTER)

The Pocket's OLED screens leave the Studio's app (they belong to the FM-1 Companion's Pocket).

## 4. The FM-1 Companion plug-in

In XOXO-Studio-Plugins, as `fm1-companion`. Ported from the FM-1 Companion app's code (`FM-1-Companion`, GPL-3.0, our own repository; that repository isn't
changed for it):

- **Sound and MIDI:** an FM-1 (Felucca, SLOOP, Clipper firmware: `sloop.fm1_cards`' rules) recognised as a
  device, FM-1 A / FM-1 B as mixer sources and MIDI route ends, its clock (the FM-1 keeping the clock when it's
  the driver), its WirePlumber tuning
- **Library:** its backups, projects, sample slots and firmware: the library screens and the web app's FM-1
  groups, with the hold-press on the box before anything is written to the FM-1

Not in it: the SLOOP and X0X apps, and FM-1 ON STUDIO (left out by choice).

**Where the FM-1 work goes (the user, 2026-10-31):** this plug-in makes the FM-1 Companion Studio obsolete. The
Pocket (in `FM-1-Companion`) stays the FM-1-focused box; the Studio has outgrown being an FM-1 companion, so for
the Studio this plug-in is what gets the FM-1 updates made on the Pocket. Its code follows the Pocket's FM-1 code
(the FM-1 detection, the library, the FM-1's MIDI and clock), brought over as each update lands there.

## Order, after the launch

1. The device registry: the built-in profiles, one at a time, tests unchanged
2. The plug-in host: manifests, switching on and off, settings, screens, MIDI route ends, events, errors
3. The web app's plug-in sections (with the Web app development session: the page is shared)
4. XO-4, the decks, the Pocket link and the computer link as plug-ins
5. The FM-1 Companion plug-in
6. The plug-in guide for others (this file, finished as a guide) and an example plug-in
