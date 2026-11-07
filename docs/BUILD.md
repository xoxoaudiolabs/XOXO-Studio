# Building an XOXO Studio

The parts, what they cost, and how they go together. This is the **Pi 4 build**, planned next, after this beta.
**Not one of these Pi 4 builds has been put together yet**, so nothing on this page has been tried on a Pi 4. The
Studio so far has run on a Pi 3 B+ (and a Pi 3 B). Prices are PiShop.us's, an authorized Raspberry Pi reseller, in October 2026, before
shipping and tax.

## Parts

| Part | Price | What it's for |
|---|---|---|
| Raspberry Pi 4 Model B, 1GB | $35.00 | The Studio. Its USB-C port is what lets the Studio be a USB audio + MIDI interface for a computer |
| Waveshare 3.5" Resistive Touch Display (C), 480×320, 125 MHz SPI | $29.95 | The touchscreen (sits on the pins) |
| InnoMaker RPi HiFi DAC HAT (PCM5122) | $26.95 | Headphones (its own amp) and RCA line out. Optional: without it, the Pi's own 3.5 mm jack (not yet heard on hardware) |
| EDATEC Pi4 Passive Cooling Open CNC Case, black | $8.95 | Aluminium heatsink case: cooling with no fan (no noise near the audio) |
| Adafruit 2x20 Socket Riser Header ×2 (×3 with a spare) | $5.90 | Lifts the DAC clear of the case's fins, and the screen above the DAC |
| USB-C power/data splitter (PiKVM's, or Waveshare's) | about $6–15 | One USB-C into the Pi: power from the supply, data from the computer |
| 5 V / 3 A USB-C power supply (the official Pi 4 one) | about $8 | Power |
| microSD card, 16–32 GB | about $8 | Raspberry Pi OS and the Studio |
| **Total** | **about $129–138** (about $141 with the spare riser) | |

Without the DAC: about $102–111. Prices at other shops differ a lot: the same Pi 4 1GB was $85 on Amazon.

Optional: a Bluetooth speaker (Bluetooth headphones not yet tried), USB MIDI keyboards and controllers, USB audio (a keyboard's own sound,
an audio interface), a Hercules DJControl Inpulse 200 MK2 for the DJ decks, a PiSugar 3 Plus battery (left off
this build for now).

**The screen:** the Studio was built and tested with a Hosyond 3.5" (the common "3.5 inch RPi LCD", the same
ILI9486 and XPT2046 chips as Waveshare's (A)). The (C) is the same design run faster; it's not yet tried. Either
sits on the pins; the installer sets up each (below).

## Putting it together

Bottom to top:

1. **The Pi 4 in the EDATEC case.** The thermal pads on the chips, the case's two halves round the board.
2. **A riser header** on the Pi's 40 pins.
3. **The DAC HAT** on the riser. Check for a clear gap between the DAC's underside and the case's fins all the way
   across: bare solder joints on aluminium can short. If it's tight, a strip of Kapton (polyimide) tape on the
   DAC's underside as well. Its pins must go fully into the riser.
4. **A riser header** on the DAC's pins (if the screen would touch the DAC's tall parts: the RCA jacks, the red
   capacitors).
5. **The screen** on top. Standoffs, so it isn't held by the pins alone.
6. **Power and the computer:** the splitter's output into the Pi's USB-C; the power supply into the splitter's
   power side; the computer, with a standard USB cable, into its data side. The splitter is meant to keep the
   computer's 5 V from the Pi (not yet tried).

The DAC uses GPIO 18, 19, 21 (sound), GPIO 6 (mute) and I2C; the screen uses SPI and GPIO 17, 24, 25. None of
them is used twice.

**The 3D-printed case:** leave vents by the EDATEC case's fins (it's cooled by air, with no fan), openings for the
DAC's RCA and headphone jacks, and the computer's USB-C (the splitter's data side) and the power.

## Installing

As in the [README](../README.md#set-up), with the options for this build:

```
bash fm1-bt-bridge/install.sh --dac --screen c
```

- `--dac`: the DAC HAT's driver. The DAC is then the master out (its headphone and RCA outs); the Pi's own jack
  gets a copy for headphones and CUE (tried on a Pi 3 B+: the DAC's outs; the Pi's jack beside it not yet)
- `--screen c`: the Waveshare (C). Without it, the Hosyond / Waveshare (A) settings: the Studio's `xoxo35` overlay
  (piscreen with the screen maker's panel start-up: blacker blacks), made on the Pi by `config/xoxo35.sh`
- On a Pi 4 the installer also makes the Studio a USB audio + MIDI interface on its USB-C port (below)

## The Studio as a USB interface

Plugged into a computer through the splitter's data side, a Pi 4 Studio shows up as **XOXO Studio**, a
standard USB audio + MIDI device (USB Audio Class 2; macOS, Linux and Windows 10 and 11 have class drivers for it;
tried on Windows 11 only):

- **Audio to the computer:** the Studio's mix in stereo, 48 kHz, as an input in the DAW. It's every source but
  the computer's own sound (so a DAW monitoring its input can't feed back)
- **Audio from the computer:** the DAW's output, a source in the Studio's mixer (COMPUTER), on the speaker, the
  headphones and in recordings
- **MIDI both ways:** COMPUTER in the MIDI routes, beside the network MIDI

**Tried** (2026-11-07, the first Pi 4 Studio on Windows 11, no driver installed): Windows listed *Speakers (XOXO
Studio)*, *Microphone (XOXO Studio)* and a *MIDI function*. A tone from the PC reached the Studio bit for bit (and
was heard on its speaker); a tone in the Studio's mix reached the PC's input (0.7 dB under, the mix's level); SysEx
went through both ways. The Pi was powered from the PC's port alone for this, and it reported under-voltage: use
the splitter (or a supply on the GPIO's 5 V). **Not yet tried:** the splitter, a DAW, a Mac or Linux, MIDI notes
into the Studio's routes, latency.
