# XOXO Studio

A portable studio on a Raspberry Pi with a 3.5" touchscreen, by XOXO Audio Labs. It's the FM-1 Companion Studio with the FM-1 taken out, so it works as a universal tool with any USB or Bluetooth MIDI gear and any USB sound source.

**Status: not yet tested on hardware.** The FM-1 parts are out: the SLOOP and X0X apps, the FM-1 library (backups, projects, sample slots, firmware), and FM-1 A/B in the sound sources and MIDI routes. Recording and the meters now take whatever the Studio plays. The first fresh install on a Pi is next. Until it's done, read everything here as how it's meant to work.

## Hardware

- Raspberry Pi 3 B+ (what the FM-1 Companion Studio ran on), with a microSD card (8 GB or more)
- A 3.5" SPI touchscreen (ILI9486 display, XPT2046 touch: the common "3.5 inch RPi LCD")
- A Bluetooth speaker or headphones, or the Pi's 3.5 mm jack
- Optional: USB MIDI keyboards and controllers, USB audio (a keyboard's own sound, an audio interface), a Hercules DJControl Inpulse 200 MK2 for the DJ decks, a PiSugar battery

## Set up

1. **Flash the card** with Raspberry Pi Imager: *Raspberry Pi 3*, *Raspberry Pi OS Lite*. In its settings, set the hostname `XOXOStudio`, a user name and password, your Wi-Fi, and **enable SSH**.
2. **Boot the Pi** (give it a few minutes the first time). On your computer, from this repository's folder, copy the app over:
   ```
   scp -r fm1-bt-bridge YOUR_USER@xoxostudio.local:~
   ```
3. **Install** over SSH, then reboot:
   ```
   ssh YOUR_USER@xoxostudio.local
   bash fm1-bt-bridge/install.sh
   sudo reboot
   ```
   On the first start the Studio asks for the touch setup (four targets) before HOME.

The web page is at `http://xoxostudio.local`. It's XOXO Studio's own web app, apart from the FM-1 Companion's, so a phone can keep both on its home screen.

## What's inside

- **HOME, MIXER, RECORDER:** every USB sound source and the pads, a level each, recorded as one mix (or a part each), with meters
- **PADS:** the 16-pad sampler (notes 36–51), its step sequencer, note repeat, punch-in FX and sample editor; an 808 kit comes with it
- **MIDI:** routes between Bluetooth MIDI, each USB MIDI device, network MIDI (a DAW) and the pads, with channels, transpose, velocity, chord memory and an arpeggiator per route
- **MORE:** the DJ decks, themes, Wi-Fi, touch setup, shut down

Next: **XO-4**, the Studio's own groovebox (drums, two FM synth tracks, a MIDI track).

Some names inside the code still say fm1 (the `fm1-bt-bridge` folder, `~/fm1-library`, the service names). They're internal, and they're left as they are for now.

## License

GPL-3.0 (see LICENSE). The pad sequencer, the punch-in FX and the look come from SLOOP (isod89/sloop-fm1, GPL-3.0). The 808 kit is Michael Fischer's recordings of a TR-808 (CC0).
