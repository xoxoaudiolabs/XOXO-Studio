# XOXO Studio

A portable studio on a Raspberry Pi with a 3.5" touchscreen, by XOXO Audio Labs. It's the FM-1 Companion Studio with the FM-1 taken out, so it works as a universal tool with any USB or Bluetooth MIDI gear and any USB sound source.

**Status: installs and starts on a Pi; most of it not yet tried on hardware.** The FM-1 parts are out: the SLOOP and X0X apps, the FM-1 library (backups, projects, sample slots, firmware), and FM-1 A/B in the sound sources and MIDI routes. What's been tried and what hasn't is under [Tested](#tested).

## Hardware

- Raspberry Pi 3 B+ (what the FM-1 Companion Studio ran on), with a microSD card (8 GB or more)
- A 3.5" SPI touchscreen (ILI9486 display, XPT2046 touch: the common "3.5 inch RPi LCD")
- A Bluetooth speaker or headphones, or the Pi's 3.5 mm jack
- Optional: USB MIDI keyboards and controllers, USB audio (a keyboard's own sound, an audio interface), a Hercules DJControl Inpulse 200 MK2 for the DJ decks, a PiSugar battery

## Set up

1. **Flash the card** with Raspberry Pi Imager: *Raspberry Pi 3*, *Raspberry Pi OS Lite*. In its settings, set the hostname `XOXOStudio`, a user name and password, your Wi-Fi, and **enable SSH**.
2. **Boot the Pi** (give it a few minutes the first time).
3. **Get the app onto the Pi**, either way:
   - **From a download:** on GitHub, *Code › Download ZIP*, unzip it, and from the unzipped `XOXO-Studio-main` folder:
     ```
     scp -r fm1-bt-bridge YOUR_USER@xoxostudio.local:~
     ```
   - **With git** (updates later are a `git pull`): the repository is private, so give the Pi a deploy key, an SSH key that opens this repository only, read-only. On the Pi (`ssh YOUR_USER@xoxostudio.local`):
     ```
     sudo apt-get update && sudo apt-get install -y git
     ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C "xoxostudio"
     cat ~/.ssh/id_ed25519.pub
     ```
     On GitHub: the repository's **Settings › Deploy keys › Add deploy key**, paste that line, leave *Allow write access* off. Then `git clone git@github.com:xoxoaudiolabs/XOXO-Studio.git` (answer `yes` to GitHub's host key) and use `XOXO-Studio/fm1-bt-bridge` below.
4. **Install** over SSH, then reboot (it asks for your password once):
   ```
   ssh YOUR_USER@xoxostudio.local
   bash fm1-bt-bridge/install.sh
   sudo reboot
   ```
   On the first start the Studio asks for the touch setup (four targets) before HOME.

**Updating with git:** on the Pi, `cd XOXO-Studio && git pull && bash fm1-bt-bridge/install.sh`, then `sudo reboot`.

The web page is at `http://xoxostudio.local`. It's XOXO Studio's own web app, apart from the FM-1 Companion's, so a phone can keep both on its home screen.

## What's inside

- **HOME:** the tempo with − / +; every source (each USB device, the pads, XO-4, the decks while they run) and the speaker, each with a small bar and a % for its mixer level; REC, START, TAP
- **MIXER, RECORD:** every source a level, recorded as one mix (or a part each), with meters
- **EDITOR:** the sample editor (full screen): a recording or a sample trimmed, faded, its note found, saved as a new sample, or put straight on a pad (TO PAD)
- **XO-4:** the Studio's own groovebox, with the 16-pad sampler in its DRUMS (full screen; below); the 808 KIT is loaded on the first start
- **DECKS:** two DJ decks (full screen), from the Studio DJ Music folder or a USB drive, played by touch, a Hercules DJControl Inpulse 200 MK2, or any controller after MIDI LEARN; each deck its own FX (ECHO on the beat, REVERB, FLANGER, BRAKE: FX tapped on or off, held for the next one; echo and reverb ring out)
- **MIDI:** routes between Bluetooth MIDI, each USB MIDI device, network MIDI (a DAW) and the pads, with channels, transpose, velocity, chord memory and an arpeggiator per route
- **The Pocket by Ethernet:** an FM-1 Companion Pocket on a cable straight to the Studio (no router needed: both take a link-local address) joins the Studio's network MIDI as NET. MIDI goes both ways, and the Studio's clock leads: its clock to NET (Box>NET) is on from the start
- **MORE:** settings, themes, Wi-Fi, touch setup, shut down

EDITOR, XO-4, DECKS and RECORD are full screen: "< HOME", top left, leads back. MIXER, MIDI and MORE keep the tab bar and have "< HOME" too.

### XO-4

The Studio's own groovebox, being built (`fm1-bt-bridge/xo4.py`, `xo4synth.py`, `deskxo4.py`):

- **Four tracks on the box's beat grid:**
  - **DRUMS** is the 16-pad sampler (notes 36–51 play it from the MIDI routes, as SMP): each hit with its level (NORM, GHOST, SOFT, HARD) and ratchet (X1–X4).
  - **SYN 1** and **SYN 2** are two-operator FM synths, with chords of up to four notes.
  - **MIDI** goes out through the routes, as the source XO4.
- **Patterns:** A–H, changing on the next bar. Each track has its own length, up to 64 steps.
- **Sound:** a source of its own, XO-4, in the mixer, the meters and recordings.
- **The XO-4 tab:**
  - **Header:** < HOME, the patterns A–H, REC (live: pads played go onto DRUMS while it plays) and PLAY / STOP.
  - **Track row:** the track, its length LEN − / +, and HOLD CLR.
  - **Steps:** 16 a page.
  - **Step row:** the pages, then the selected step's VEL and LEN.
  - **DRUMS:**
    - **The pads:** played (they sound while held, playing or not) and picked for the steps: the steps put the picked pad on or off.
    - **The hit just put on:** its LEVEL, ratchet and the step's NUDGE − / +. QUANT: live REC on the grid, or where it was played.
    - **KIT:** the kits (load, save, new). **RPT:** note repeat. **FX:** the sixteen punch-in FX (on the pads' sound). **PADS:** the 16 pads big, 4×4 as on an MPC, full screen, with KIT, RPT, FX, REC and EDIT above them. **EDIT:** a tap opens the pad's page (its sample, level, pan, tune, mode, choke; sampling into it, trimming it).
  - **SYN 1, SYN 2, MIDI:**
    - **The note keys:** OCT, KEY, SCALE, and 14 keys, which offer only the scale's notes.
    - **FX:** XO-4's own sixteen punch-in FX on the two synths' sound (hold one, or LATCH it), apart from the pads' FX.
    - **Placing a step:** tap an empty step to place the last notes and select it. Keys add notes to it or take them off, four at most.
    - **Emptying a step:** tap the selected step again.
  - **SOUND** (SYN 1, SYN 2): the synth's page. Six starting sounds (KEYS, BASS, BELL, PLUCK, PAD, LEAD) and its
    settings, each − / + (held: four steps): RATIO, BRIGHT, BR DECAY, BR HOLD (how the brightness falls, and what
    stays), ATTACK, DECAY, SUSTAIN, RELEASE, LEVEL. HEAR plays the track's last notes; while stopped, a change does.
  - **Hearing it:** while stopped, what you tap sounds.

The SAMPLER tab and its own step sequencer are gone: a kit's pattern from it moves into the drums of XO-4's first pattern with empty drums, the first time that kit is used.

What XO-4 can't do yet is under [Known limitations](#known-limitations).

## Screens

Drawn on a PC by the Studio's own drawing code with a made-up studio (`python tools/studio_screens.py docs/images`), at twice the screen's 480×320: not photos of the device.

| | |
|---|---|
| ![HOME](docs/images/studio-home.png) **HOME** | ![MIXER](docs/images/studio-mixer.png) **MIXER** |
| ![XO-4 drums](docs/images/studio-xo4-drums.png) **XO-4: DRUMS** | ![XO-4 synth](docs/images/studio-xo4-synth.png) **XO-4: SYN 1** |
| ![XO-4 sound](docs/images/studio-xo4-sound.png) **XO-4: SOUND** | ![XO-4 pads](docs/images/studio-xo4-pads.png) **XO-4: PADS** |
| ![XO-4 FX](docs/images/studio-xo4-fx.png) **XO-4: synth FX** | ![DECKS](docs/images/studio-decks.png) **DECKS** |
| ![EDITOR](docs/images/studio-editor.png) **EDITOR** | ![MIDI](docs/images/studio-midi.png) **MIDI** |
| ![MORE](docs/images/studio-more.png) **MORE** | |

## Known limitations

- **Mostly untried on hardware.** Much of the Studio has only run on a PC so far: see [Tested](#tested) for what has and hasn't been tried on a Pi.
- **One hardware setup.** Made for a Raspberry Pi 3 B+ with a 3.5" 480×320 touchscreen (ILI9486 / XPT2046). Other Pis and other screens haven't been tried, and the screens are drawn for 480×320 only.
- **CPU.** Each part was measured on its own on a Pi 3 B+: XO-4 about 30% of one core while it plays, the pads about 20%, the decks 28% (up to 49% with REVERB on both decks). Everything running at once hasn't been measured.
- **XO-4:**
  - Patterns can't be copied yet.
  - The synths can't be played live from a keyboard yet: XO-4 isn't a MIDI destination in the routes.
  - Eight patterns (A–H), up to 64 steps a track, four notes a step; a pattern change waits for the next bar.
- **DJ decks:** one FX at a time a deck. The Hercules DJControl Inpulse 200 MK2 has its own mapping; other controllers go through MIDI LEARN, which hasn't been tried with real hardware.
- **Speaker battery:** shown only when the speaker reports its battery to the Pi's Bluetooth (BlueZ). Many speakers don't, and then nothing shows.
- **Web page:** plain HTTP on the local network (`http://xoxostudio.local`), no password.
- **Private repository:** installing with git needs a deploy key (see [Set up](#set-up)).
- **Old names inside:** some names in the code still say fm1 (the `fm1-bt-bridge` folder, `~/fm1-library`, the service names). They're internal, and they're left as they are for now.

## Tested

**On hardware** (2026-10-28: a Raspberry Pi 3 B+ on Raspberry Pi OS Lite, Trixie, 64-bit; a 3.5" ILI9486 / ADS7846 touchscreen; a PiSugar battery):
- installed from the GitHub ZIP as above: the installer ran to the end with no errors in its log
- after the reboot the app, its sampler and the web page start; the screen and the touch are found; the settings hold a touch calibration and a theme picked on the screen
- the battery's charge is read
- the web page loads from a PC at `xoxostudio.local`, as XOXO Studio, with its own manifest and icon
- the tab bar with DECKS on it looks right on the Studio's screen
- XO-4's FM synth: 8 voices (two tracks' 4-note chords) take 22% of one core, measured with the app running; it writes its demo WAV there (the demo not yet listened to)
- XO-4's engine, with a demo pattern put in by hand and the box clock started from the web page: the XO-4 source and the pads (the 808 KIT, played by XO-4's drum track) both carry sound, measured by recording each source on the Pi (peaks 0.66 and 0.81); XO-4 takes about 30% of one core while it plays, the pads about 20%
- the XO-4 tab, used by hand on the Studio's screen: works well (the user's report, 2026-10-28)
- "< HOME" at the top left of MIXER, SAMPLER, RECORD, MIDI and MORE looks right on the Studio's screen (the user's report)
- SAMPLER and RECORD full screen (no tab bar) look right on the Studio's screen (the user's report)
- HOME's tempo - / + beside the BPM work well on the Studio's screen (the user's report)
- HOME listing every source with its mixer level looks right on the Studio's screen (the user's report; the decks' row not yet seen with the decks playing there)
- the FX (the pads' punch-in FX, XO-4's synth FX, the decks' ECHO, REVERB, FLANGER, BRAKE) sound good on the Studio (the user's report, 2026-10-28)
- the Pocket link's Studio side, with a stand-in Pocket on a PC over Wi-Fi: it joins the Studio's network MIDI as "FM-1 Companion Pocket" and gets the Studio's clock (2026-10-29); the Studio's Ethernet setting is loaded by NetworkManager with no error
- the DJ decks played by touch alone (no controller), music from a USB drive, out of a JBL Go 3 over Bluetooth (the user's report, 2026-10-28, after the fix for their volume starting at 0)

**Not yet tried on hardware:** sound out heard (a Bluetooth speaker, the jack), XO-4 by ear (its timing against the pads, the MIDI track to real gear), USB sound sources, the mixer and CUE, recording, XO-4's DRUMS by hand (finger drumming, levels, ratchets, nudge, live REC, RPT, FX, the kit pages from XO-4), the EDITOR tab, the sample editor, MIDI (Bluetooth, USB, network, the routes, arp and chord), the DJ decks with a controller (MIDI learn, a Hercules), shutting down from the screen, the Pocket on a real Ethernet cable (link-local, finding each other by mDNS).

**On a PC:** the test suite passes (each `tests/test_*.py` with its own runner; `tests/test_desk.py` through pytest).

## License and credits

XOXO Studio is GPL-3.0 (see [LICENSE](LICENSE)), like SLOOP, which parts of it come from. It began as the FM-1 Companion Studio (xoxoaudiolabs/FM-1-Companion, GPL-3.0).

**From SLOOP** ([isod89/sloop-fm1](https://github.com/isod89/sloop-fm1), GPL-3.0), rewritten in Python here: the pads' step sequencer (its `seq.c`), the sixteen punch-in FX (`punch.c`), and the look: the palettes and track colours (`gfx.c`).

**Copied into this repository** (each with its licence beside it):

| What | From | Licence |
|---|---|---|
| `fm1-bt-bridge/vendor/fonts/` (Terminus) | Dimitar Toshkov Zhekov, as SLOOP ships it ([VENDORED.md](fm1-bt-bridge/vendor/fonts/VENDORED.md)) | SIL Open Font License 1.1 |
| `fm1-bt-bridge/kits/808/` (the 808 KIT's sixteen sounds) | Michael Fischer's recordings of a Roland TR-808 (1994), from [tidalcycles/sounds-tr808-fischer](https://github.com/tidalcycles/sounds-tr808-fischer) ([CREDITS.md](fm1-bt-bridge/kits/808/CREDITS.md)) | CC0 1.0 |

Not affiliated with Roland or Hercules. TR-808 is a trademark of Roland Corporation; DJControl Inpulse is Hercules's (Guillemot Corporation).

**Built on** (installed by `install.sh` from Raspberry Pi OS's own packages, or already part of it; not copied into this repository, and each under its own licence):

| Software | What XOXO Studio uses it for | Licence |
|---|---|---|
| Raspberry Pi OS (Debian) and the Linux kernel | the system; the screen's drivers (fbtft, SPI, I2C) | GPL-2.0 (the kernel); Debian's packages each their own |
| PipeWire (`pw-cat`, `pw-record`, `pw-loopback` …) and its Bluetooth plugin | all the sound: the mixer, Bluetooth audio, recording, the pads, the decks | MIT, with some parts LGPL-2.1-or-later |
| WirePlumber (`wpctl`) | PipeWire's session manager; levels | MIT |
| BlueZ | Bluetooth: speakers, Bluetooth MIDI | GPL-2.0-or-later (its libraries LGPL-2.1-or-later) |
| D-Bus | talking to BlueZ | GPL-2.0-or-later or AFL-2.1 (some parts MIT, BSD) |
| systemd | the app's services | LGPL-2.1-or-later (some parts GPL-2.0-or-later) |
| NetworkManager (`nmcli`) | Wi-Fi on / off | GPL-2.0-or-later (its libraries LGPL-2.1-or-later) |
| RealtimeKit (rtkit) | real-time priority for the sound | GPL-3.0-or-later (some parts MIT) |
| udisks2, exfatprogs, ntfs-3g | USB drives of music for the decks | GPL-2.0-or-later (udisks2's library LGPL-2.0-or-later) |
| Python 3 | the app itself | PSF License |
| Pillow | drawing every screen, the icons | the PIL Software License (MIT-CMU) |
| NumPy | meters, the sampler, the sample editor | BSD-3-Clause |
| mido and python-rtmidi (RtMidi) | MIDI | MIT |
| libsndfile, with mpg123 | the DJ decks reading MP3, FLAC, WAV, AIFF and Ogg | LGPL-2.1-or-later (some parts Apache-2.0); mpg123 LGPL-2.1 |
| dbus-python | BlueZ over D-Bus | MIT (some parts AFL-2.1 or GPL-2.0-or-later) |
| PyGObject | BlueZ's events (GLib) | LGPL-2.1-or-later |
| spidev, libgpiod's Python bindings, smbus2, i2c-tools | the pocket build's screen and keys; the PiSugar battery | MIT; LGPL-2.1-or-later; MIT; GPL-2.0-or-later |
| DejaVu fonts | the pocket build's text | Bitstream Vera / DejaVu licence (free) |

The licences are each project's own, as Debian lists them in each package's `/usr/share/doc/<package>/copyright` on the Pi: that file is the one to go by.
