# Running a XOXO Studio over SSH (no screen)

**A proposal. Nothing here is built yet.** Pat picks the commands he wants, then they get made and tested on a
Studio. Everything below about what the Studio does today comes from reading the code at 19cd78b, not from
trying it on a Studio over SSH.

For a Studio with no screen to look at: inside a case, on a show stand, or with the screen unplugged.

```bash
ssh xoxo@xoxostudio.local
```

## What already works without the screen

### The web API (`fm1-web`, port 80)

`web.py` serves the page and a small JSON API. The box (`fm1-bridge`) and the page are two processes that talk
through two files in `$XDG_RUNTIME_DIR` (`/run/user/<uid>`):

- `fm1-status.json`: the box writes its live status about once a second (`weblink.web_publish`). The page treats
  a status more than 5 s old as "the box isn't running".
- `fm1-commands.jsonl`: the page adds commands, one JSON object per line (`library.queue_command`). The box's main
  loop takes them (`weblink.web_commands`) and runs them through the same code the touchscreen uses.

| Endpoint | What it does |
|---|---|
| `GET /api/status` | The whole live status (below), or `{"offline": true}` |
| `POST /api/command` | Queues a command after `web.check_command` validates it. Returns 503 if the box isn't answering |
| `GET /api/library` | Samples and recordings (with their parts), newest first |
| `GET /files/<folder>/<name>` | Downloads a sample, recording or DJ track (Range requests work) |
| `POST /api/delete` | Deletes a library file |
| `POST /api/upload?folder=&name=` | Uploads a sample (checked), or a track to the music folder |
| `GET /api/update[?fresh=1]` | Installed version, newest on GitHub, whether an update can run |
| `GET /api/music` | The DJ decks' music folder |

`/api/status` already reports: the sources and the mixer (levels, mute, solo, inputs), the Bluetooth speaker, its
volume and battery, the master level, MIDI (peer, controllers, network MIDI, pads, XO-4), the MIDI route matrix and
its presets, the clock and tempo, recording seconds (or `null`), the latency step, the link settings (Pocket link,
Follow Studio, link audio, link return, link REC), USB out, Wi-Fi, the version, the theme, XO-4, kits, decks and
plug-ins.

It does **not** report whether a computer is plugged into the USB-C port. The box tracks that
(`bridge.computer_node`, `self.computer`) but `web_status` leaves it out.

The commands `/api/command` accepts (`web.check_command`; `weblink.web_command` runs them):

- `set` with a key: `metronome`, `bpm` (30–300), `clock_mode` (follow/box), `click`, `audio_rate` (44100/48000),
  `arp_on`, `chord_on`, `volume` (0–100, the BT speaker), `master` (0–100, DAC or USB out), `latency`
  (SAFE/LOW/LOWER/LOWEST), `usb_out`, `follow_studio`, `link_audio`, `link_return`, `link_rec`, `desk_theme`,
  `mix_<src>`, `mute_<src>`, `solo_<src>`, `input_<src>`
- `transport` start/stop; `record` start/stop
- `routes` (the whole MIDI route list); `preset` load/save/clear for slots 1–4
- `xo4` pattern / midi_in / sound / play; `kit`; `plugin` on/off or a plug-in's own command
- `update`. **This one doesn't work headless:** the box answers it with "Update?" on its screen and waits for a
  hold-press (`weblink.update_checked`).

So most "play" settings can already be driven over SSH today, with nothing new, e.g.:

```bash
curl -s localhost/api/status | python3 -m json.tool
curl -s -X POST localhost/api/command -d '{"cmd":"set","key":"bpm","value":120}'
curl -s -X POST localhost/api/command -d '{"cmd":"record","value":"start"}'
```

(Not tried over SSH. `fm1-web` waits 45 s after boot before it starts, `ExecStartPre=/bin/sleep 45`, so right
after a boot the API isn't there yet.)

### Shutdown

- On the screen: SETTINGS asks "Shut down?" (`deskui.py`), and KEY3 held does it on the OLED box. Both call
  `App.shutdown()` (`bridge.py`). That finishes the recording's WAV file, stops the player, loop and mixer, draws the
  "wait for SAFE TO UNPLUG" picture, then runs `sudo -n systemctl poweroff`.
- On battery, the box shuts itself down when the PiSugar runs empty (`battery_check`).
- **There is no web/API command for it.**
- `install.sh` writes `/etc/sudoers.d/fm1-bridge` so the Studio's user may run, without a password:
  `systemctl poweroff`, `nmcli radio wifi on|off` and `/usr/local/sbin/fm1-update`. So over SSH,
  `sudo systemctl poweroff` works without Pat's password today. But it skips `App.shutdown()`: a recording running
  at that moment is cut off rather than finished.
- **Reboot is not in sudoers.** Over SSH it needs Pat's password.

### Updates

- `update.py check` prints the installed and newest versions as JSON. It has no hold-press and is safe to run.
- `update.py run` runs the update: `fm1-update` (root, from sudoers) installs the newest `vX.Y` tag from GitHub with
  that release's `install.sh`, restarts the app, and puts the old code back (`fm1-update --back`) if the app's
  status doesn't come back within 120 s. `update.start()` refuses while a recording runs or another update is
  running. The log is `~/.cache/fm1-bridge/update.log`.
- `fm1-update` takes no tag. It always installs the **newest** release; on purpose, "what runs as root comes only
  from the project's GitHub". `--back` puts back the code from before the last update.
- An update never touches `~/.config/fm1-bridge` (settings, pairings), `~/fm1-library`, `~/xoxo-plugins` or the
  boot config.

### Services (systemd user services of `xoxo`; linger is on, so they run with nobody logged in)

| Service | What | Restart |
|---|---|---|
| `fm1-bridge` | The app (`bridge.py`) | `always`, 3 s |
| `fm1-web` | The web page (`web.py`), port 80 | `always`, 5 s; waits 45 s at start |
| `fm1-pocket-in` | PipeWire RTP receiver for a linked Pocket (UDP 46000) | `always`, 5 s |

`systemctl --user status|restart fm1-bridge` works over SSH with no sudo. (For the box's own user, in an SSH login.
Not tried here.) Logs: `journalctl --user -u fm1-bridge`. Untested whether the user journal is kept on the Studio's
Pi OS install.

### The library CLI

`python3 ~/.local/share/fm1-bridge/library.py list` prints the samples and recordings as JSON.
`library.py import-sd` copies new files from the SD card's `fm1-library`.

## The proposal: one `xoxo` command

A small Python script (standard library only), installed by `install-app.sh` as `~/.local/bin/xoxo`, run as the
Studio's user over SSH. To queue commands it imports `web.check_command` and `library.queue_command` directly. That
is the same door and the same checks as the page, and it works before `fm1-web` is up. It reads the status from
`fm1-status.json`. Every subcommand prints plain text, and `--json` prints JSON for scripts.

Columns:

- **Covered**: the existing code already does it (the CLI only wraps it).
- **New**: needs new code in the app.
- **Sudo**: needs root.

| # | Command | What it does | Covered / New | Sudo | Risk |
|---|---|---|---|---|---|
| 1 | `xoxo status` | One screen of text: services up, version, sources, speaker, MIDI devices, clock, recording, latency, links, USB out, Wi-Fi | Covered (status file + `systemctl --user is-active`). The USB-C computer needs **New**: one field in `web_status` | No | None: read-only |
| 2 | `xoxo shutdown` | Asks the app to shut down the way the screen does (finishes the recording, SAFE TO UNPLUG picture, poweroff). Falls back to `sudo -n systemctl poweroff` if the app isn't answering | **New**: a `shutdown` web command (in `check_command`, then `web_command` → `self.shutdown()`) | Uses the existing NOPASSWD line; no new sudo | **Needs Pat's explicit go each time.** The Studio goes off; nobody can switch it back on over SSH. Asks "type yes" unless `--yes` |
| 3 | `xoxo reboot` | As shutdown, then the Pi starts again | **New**: a `reboot` command, **and** `systemctl reboot` added to sudoers (or Pat types his password) | Yes: a new sudoers line, i.e. a system change | **Needs Pat's explicit go each time**, and a separate go to change sudoers. The same "type yes" |
| 4 | `xoxo restart` | Restarts the app (`systemctl --user restart fm1-bridge`); `restart web` / `restart all` for the others | Covered (systemd) | No | Stops the sound for a few seconds. A recording running then is cut off: refuse while `recording` isn't null, unless `--force` |
| 5 | `xoxo volume [N]` / `master [N]` | The BT speaker's volume, or the DAC/USB master, 0–100; without N it shows it | Covered (`set volume` / `set master`) | No | Loud: no cap beyond 100 |
| 6 | `xoxo tempo [BPM]`, `xoxo clock follow\|box`, `xoxo metronome on\|off` | Tempo 30–300, clock source, click | Covered | No | None |
| 7 | `xoxo latency [SAFE\|LOW\|LOWER\|LOWEST]` | PipeWire's block size and the link buffer | Covered (`set latency`) | No | LOWER/LOWEST can crackle on a Pi 4 1 GB |
| 8 | `xoxo play` / `stop` | Transport start/stop to MIDI | Covered (`transport`) | No | None |
| 9 | `xoxo midi` | Lists MIDI devices and routes; `midi preset 1-4`; `midi route add/remove SRC DEST` | Listing and presets: Covered. Adding/removing one route: the CLI edits the list and sends the whole of it (`routes`), so no app change | No | A wrong route list can leave a keyboard silent; presets can put it back |
| 10 | `xoxo rec start\|stop` | Starts or stops recording | Covered (`record`) | No | None |
| 11 | `xoxo recordings` / `xoxo pull NAME` | Lists recordings (`library.listing`); `pull` prints the path, for copying with `scp xoxo@xoxostudio.local:fm1-library/recordings/NAME .` from the computer | Covered (`library.py list`; the files are in `~/fm1-library/recordings`) | No | None (read-only). `xoxo rm` is left out on purpose: deleting stays on the page |
| 12 | `xoxo backup [FILE]` | A `.tar.gz` of `~/.config/fm1-bridge` (settings, pairings, presets), and with `--all` also `~/fm1-library` and `~/xoxo-plugins` | **New** (CLI only) | No | `--all` can be big; the SD card can fill. It checks free space first. Bluetooth pairing keys live in BlueZ (`/var/lib/bluetooth`, root), not here, so a backup doesn't carry the pairings themselves |
| 13 | `xoxo restore FILE` | Stops `fm1-bridge`, puts the settings back, starts it | **New** (CLI only) | No | Overwrites the settings. Saves a copy of the current ones first. Must stop the app first, or its next `save_settings` writes over the restore |
| 14 | `xoxo update [--check]` | `--check`: installed vs newest. Without it: runs the update with no hold-press (the SSH login is the confirmation) | `--check`: Covered (`update.py check`). Running it: Covered by `update.start()`, which the CLI calls straight, skipping the box's screen prompt | Uses the existing NOPASSWD `fm1-update` | Restarts the app; refuses while recording. Rolls back if the app doesn't come back. Asks "type yes" |
| 14b | `xoxo update --back` | Puts back the code from before the last update | Covered (`fm1-update --back`) | Existing NOPASSWD | Then restart the app |
| 14c | `xoxo update --tag vX.Y` | A chosen release, not just the newest | **New**, in `fm1-update`, which runs as root | Changes the root helper | **Not recommended**: `fm1-update` takes no input by design. Use `--back` for "the one before" |
| 15 | `xoxo logs [app\|web\|pocket\|update] [-f]` | `journalctl --user -u …`, or `update.log` | Covered (journal) | No | Whether the user journal survives a reboot on the Studio is untested |
| 16 | `xoxo link` | The Pocket link and Follow Studio: shows them; `link follow on\|off`, `link audio mix\|fm1s\|midi`, `link return on\|off`, `link rec on\|off` | Covered (`set …`) | No | Follow Studio changes the latency to the leader's |
| 17 | `xoxo screen` | Shows the theme; `screen theme NAME` | Covered (`set desk_theme`) | No | None |
| 17b | `xoxo screen off\|on` | Blanks the touchscreen to save power in a case | **New**: a web command. The app owns the screen (`TftDisplay.power` in desk.py writes `/sys/class/graphics/fbN/blank`), and the Studio's LCD never sleeps today | No (the app already writes `blank`) | A screen left off looks like a dead Studio: any touch wakes it |
| 18 | `xoxo usb-out [auto\|off\|NODE]` | USB out's choice (no DAC HAT) | Covered | No | None |
| 19 | `xoxo plugin [ID on\|off]` | Lists plug-ins; switches one | Covered | No | None |
| 20 | `xoxo xo4 …`, `xoxo kit NAME` | Pattern, play, MIDI IN, synth sounds; the pads' kit | Covered | No | None |

### Left out on purpose

- **Wi-Fi and Bluetooth on/off.** The NOPASSWD line for `nmcli radio wifi` exists, but switching Wi-Fi off over SSH
  on Wi-Fi cuts your own connection, and the rules say nothing touches Wi-Fi/Bluetooth without Pat's go. Not
  proposed.
- **Boot config** (`config.txt`, the screen overlay, the DAC, the USB gadget). `install.sh` by hand only.
- **Deleting files.** It stays on the web page, where you see what you delete.

## Untested

All of it. The proposal is from reading the code. Nothing above has been run over SSH on a Studio. In particular:

- that `$XDG_RUNTIME_DIR` in an SSH login is the same `/run/user/<uid>` the services use (the CLI needs that to find
  the status and commands files);
- the user journal over SSH;
- `sudo -n systemctl poweroff` from an SSH login.

## Next

Pat picks the rows he wants. Then the `xoxo` script gets built, plus the few app changes those rows need (shutdown,
reboot, screen off, the computer in the status), with tests, and is tried on a Studio once the Studio session hands
it over.
