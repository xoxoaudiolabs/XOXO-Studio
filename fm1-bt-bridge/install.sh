#!/usr/bin/env bash
# XOXO Studio installer for Raspberry Pi OS Lite: the Studio (Pi 3/4 + 3.5" SPI touchscreen), or the pocket
# build (Pi Zero W + OLED HAT) it shares its code with, told apart by the board.
# Run as your normal user (not with sudo):  bash install.sh
# Options (the Studio; docs/BUILD.md):
#   --dac          the InnoMaker HiFi DAC HAT (PCM5122) under the screen
#   --screen a     the 3.5" touchscreen: the Hosyond / Waveshare (A) (the default)
#   --screen c     the Waveshare 3.5" (C), 125 MHz SPI
#   --screen hdmi  the 3.5" HDMI touchscreen (UCTRONICS): the picture on HDMI, touch on the GPIO pins
# e.g.  bash install.sh --dac --screen c
set -euo pipefail
DAC=0
SCREEN_KIND=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dac) DAC=1 ;;
        --screen)
            shift
            case "${1:-}" in
                a|c|hdmi) SCREEN_KIND="$1" ;;
                *) echo "--screen takes a (the Hosyond / Waveshare A), c (the Waveshare C) or hdmi (the 3.5\" HDMI)" >&2
                   exit 1 ;;
            esac ;;
        *) echo "Unknown option: $1 (there are: --dac, --screen a, --screen c)" >&2; exit 1 ;;
    esac
    shift
done

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not root: bash install.sh" >&2
    exit 1
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)"
case "$MODEL" in
    *Zero*) BUILD=pocket ;;
    *)      BUILD=desk ;;
esac
echo "== $MODEL: the $([ "$BUILD" = desk ] && echo Studio || echo Pocket)"

echo "== Your password is needed once, for sudo"
sudo -v
while kill -0 "$$" 2>/dev/null; do sudo -n true; sleep 50; done 2>/dev/null &   # keep sudo for the whole install

echo "== Installing packages (this takes a while: several minutes, longest on a Pi Zero)"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    pipewire wireplumber libspa-0.2-bluetooth dbus-user-session rtkit bluez \
    python3-pil python3-spidev python3-libgpiod fonts-dejavu-core \
    python3-dbus python3-gi python3-mido python3-rtmidi python3-numpy python3-smbus2 i2c-tools \
    device-tree-compiler
if [ "$BUILD" = desk ]; then              # USB drives for the DJ decks: mounted, FAT / exFAT / NTFS
    sudo apt-get install -y --no-install-recommends udisks2 exfatprogs ntfs-3g
fi

echo "== Enabling SPI for the screen, Bluetooth, and permissions"
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0       # a PiSugar 3 battery, if there's one, answers on I2C
sudo rfkill unblock bluetooth || true
sudo systemctl enable --now bluetooth
sudo usermod -aG bluetooth,gpio,spi,i2c,audio "$USER"
# USB at full speed, Pocket only: the Zero's USB can't drive a USB 2 hub at high speed (devices behind it
# time out), and the FM-1 and USB keyboards are full-speed devices anyway. (A Pi 3/4's built-in ports need
# none of it.) Takes effect at the next boot.
CMDLINE=/boot/firmware/cmdline.txt
[ -f "$CMDLINE" ] || CMDLINE=/boot/cmdline.txt
if [ "$BUILD" = pocket ] && ! grep -q "dwc_otg.speed=1" "$CMDLINE"; then
    sudo cp "$CMDLINE" "$CMDLINE.bak"
    sudo sed -i '1 s/$/ dwc_otg.speed=1/' "$CMDLINE"
fi
# The Studio: no console text on its screens (its boot screen shows from early in boot instead, and HDMI
# mirrors the screen), no blinking cursor, no logo
for opt in vt.global_cursor_default=0 fbcon=map:9 logo.nologo; do
    if [ "$BUILD" = desk ] && ! grep -q "$opt" "$CMDLINE"; then
        sudo cp "$CMDLINE" "$CMDLINE.bak"
        sudo sed -i "1 s/\$/ $opt/" "$CMDLINE"
    fi
done
# The Studio's 3.5" touchscreen (ILI9486 display, XPT2046 touch: the common "3.5 inch RPi LCD"): the kernel's
# own driver, a framebuffer at /dev/fb1 and a touch input device; landscape. Not the seller's LCD-show script,
# which replaces system files. Takes effect at the next boot.
CONFIG=/boot/firmware/config.txt
[ -f "$CONFIG" ] || CONFIG=/boot/config.txt
# Raspberry Pi OS from 2026 no longer ships waveshare35a: piscreen is the same chips on the same pins (display on
# CE0, DC GPIO24, reset GPIO25; touch on CE1, its interrupt GPIO17). Its fbtft driver, not its DRM one (drm):
# on the Hosyond 3.5" the DRM driver's start-up leaves the panel white (tested 2026-10-24). 24 MHz SPI: clean on
# that panel and half again the frames of 16 MHz (the meters smoother; tested 2026-10-24).
# The Waveshare (C) (--screen c) is the same chips run faster (its "125 MHz" design): Waveshare's own overlay
# (waveshare35c) when it's in the overlays folder (Raspberry Pi OS doesn't ship it), else piscreen at 48 MHz.
# Not yet tried on a (C): if its picture is wrong, put Waveshare's waveshare35c.dtbo in the overlays folder and run
# this again with --screen c.
# The Hosyond / Waveshare (A) (the default): xoxo35, piscreen with the screen maker's panel start-up (config/xoxo35.sh:
# piscreen's left the backlight showing through and the blacks washed out, tested 2026-11-02); piscreen if it can't
# be made.
OVERLAYS="$(dirname "$CONFIG")/overlays"
if [ "$BUILD" = desk ] && [ -z "$SCREEN_KIND" -o "$SCREEN_KIND" = a ] && [ -f "$OVERLAYS/piscreen.dtbo" ]; then
    if bash "$DIR/config/xoxo35.sh" "$OVERLAYS/piscreen.dtbo" /tmp/xoxo35.dtbo; then
        sudo cp /tmp/xoxo35.dtbo "$OVERLAYS/xoxo35.dtbo"
    fi
fi
if [ "$SCREEN_KIND" = c ] && [ -f "$OVERLAYS/waveshare35c.dtbo" ]; then
    SCREEN="dtoverlay=waveshare35c,rotate=90"
elif [ "$SCREEN_KIND" = c ]; then
    SCREEN="dtoverlay=piscreen,speed=48000000,rotate=90"
elif [ -f "$OVERLAYS/xoxo35.dtbo" ]; then
    SCREEN="dtoverlay=xoxo35,speed=24000000,rotate=90"
elif [ -f "$OVERLAYS/waveshare35a.dtbo" ]; then
    SCREEN="dtoverlay=waveshare35a,rotate=90"
else
    SCREEN="dtoverlay=piscreen,speed=24000000,rotate=90"
fi
SCREEN_LINE="^dtoverlay=\(waveshare35a\|waveshare35c\|piscreen\|xoxo35\|mipi-dbi-spi\)"
# The 3.5" HDMI touchscreen (--screen hdmi; UCTRONICS 3.5" HDMI): a 480x320 panel on HDMI, sent 720x480 (at
# 480x320 it shows "no signal"), which it scales back to its panel; the Studio draws its 480x320 larger and turned
# round (desk.ScaledFb: the panel is upside down on the Pi). Its XPT2046 touch on SPI CE0, its interrupt on GPIO25,
# as the pins under it are marked: so no SPI screen's overlay (piscreen holds CE0 and GPIO25, and touch was dead
# with both: 2026-11-01). As FM-1 Companion's Studio sets it up (tested there 2026-10-29).
HDMI_TOUCH="dtoverlay=ads7846,cs=0,penirq=25,penirq_pull=2,speed=50000,keep_vref_on=0,swapxy=0,pmax=255,xohms=150"
VIDEO="video=HDMI-A-1:720x480M@60"
if [ "$BUILD" = desk ] && [ "$SCREEN_KIND" = hdmi ]; then
    if grep -q "$SCREEN_LINE" "$CONFIG"; then             # an SPI screen's overlay from before: switched off
        sudo cp "$CONFIG" "$CONFIG.bak"
        sudo sed -i "s/$SCREEN_LINE/# (off: XOXO Studio, the HDMI touchscreen) &/" "$CONFIG"
    fi
    if ! grep -q "^dtoverlay=ads7846" "$CONFIG"; then
        sudo cp "$CONFIG" "$CONFIG.bak"
        printf '
[all]
# XOXO Studio: the 3.5" HDMI touchscreen'"'"'s touch
dtparam=spi=on
%s
' "$HDMI_TOUCH" | sudo tee -a "$CONFIG" >/dev/null
    fi
    if ! grep -q "video=HDMI-A-1:" "$CMDLINE"; then
        sudo cp "$CMDLINE" "$CMDLINE.bak"
        sudo sed -i "1 s/\$/ $VIDEO/" "$CMDLINE"
    fi
elif [ "$BUILD" = desk ] && ! grep -q "$SCREEN_LINE" "$CONFIG"; then
    sudo cp "$CONFIG" "$CONFIG.bak"
    printf '
[all]
# XOXO Studio: the 3.5" touchscreen
dtparam=spi=on
%s
' "$SCREEN" | sudo tee -a "$CONFIG" >/dev/null
elif [ "$BUILD" = desk ] && { [ -n "$SCREEN_KIND" ] \
        || { [ "${SCREEN%%,*}" = dtoverlay=xoxo35 ] && grep -q "^dtoverlay=piscreen,speed=24000000" "$CONFIG"; }; }; then
    # a screen named, or the (A) set up before xoxo35: its line in place of the one there
    sudo cp "$CONFIG" "$CONFIG.bak"
    sudo sed -i "s#$SCREEN_LINE.*#$SCREEN#" "$CONFIG"
fi
# A touch overlay of its own (dtoverlay=ads7846, left by an earlier setup) beside the screen's: a second touch chip
# on the display's SPI line (CE0) and its reset pin, and touch dead (seen on a box that ran FM-1 Companion Studio
# before, 2026-11-01). The screen's overlays bring their own touch: that one switched off.
if [ "$BUILD" = desk ] && [ "$SCREEN_KIND" != hdmi ] && grep -q "$SCREEN_LINE" "$CONFIG" \
        && grep -q "^dtoverlay=ads7846" "$CONFIG"; then
    sudo cp "$CONFIG" "$CONFIG.bak"
    sudo sed -i 's/^dtoverlay=ads7846/# (off: XOXO Studio, the screen has its own touch) &/' "$CONFIG"
fi
# The InnoMaker HiFi DAC HAT (bash install.sh --dac): its PCM5122 on I2S (GPIO 18, 19, 21; mute GPIO 6; the DAC
# on I2C), none of them the screen's pins. Its ID EEPROM isn't fitted, so the driver is named here: the Allo
# Boss's, as InnoMaker's manual says. The Studio then uses it as its headphone jack (bridge.dac_node). Takes effect
# at the next boot.
if [ "$BUILD" = desk ] && [ "$DAC" = 1 ] && ! grep -q "^dtoverlay=allo-boss-dac-pcm512x-audio" "$CONFIG"; then
    sudo cp "$CONFIG" "$CONFIG.bak"
    printf '
[all]
# XOXO Studio: the InnoMaker HiFi DAC HAT
dtoverlay=allo-boss-dac-pcm512x-audio
' | sudo tee -a "$CONFIG" >/dev/null
fi
# A Pi 4: the Studio as a USB audio + MIDI interface for a computer on its USB-C port (docs/BUILD.md). The port's
# USB controller in device mode (its USB-A ports stay hosts); the gadget set up at each boot
# (config/xoxo-usb-gadget.sh). A Pi 3 has no such port: nothing done there.
case "$MODEL" in
    *"Raspberry Pi 4"*) USB_IFACE=1 ;;
    *) USB_IFACE=0 ;;
esac
if [ "$BUILD" = desk ] && [ "$USB_IFACE" = 1 ]; then
    echo "== The Studio as a USB audio + MIDI interface (the Pi 4's USB-C)"
    if ! grep -q "^dtoverlay=dwc2,dr_mode=peripheral" "$CONFIG"; then
        sudo cp "$CONFIG" "$CONFIG.bak"
        printf '
[pi4]
# XOXO Studio: USB-C as a USB audio + MIDI device for a computer
dtoverlay=dwc2,dr_mode=peripheral
[all]
' | sudo tee -a "$CONFIG" >/dev/null
    fi
    sudo install -D -m 755 "$DIR/config/xoxo-usb-gadget.sh" /usr/local/sbin/xoxo-usb-gadget
    sudo install -D -m 644 "$DIR/config/xoxo-usb-gadget.service" /etc/systemd/system/xoxo-usb-gadget.service
    sudo systemctl daemon-reload
    sudo systemctl enable xoxo-usb-gadget.service
fi

if [ "$BUILD" = desk ]; then              # the boot screen as soon as the touchscreen appears (deskboot.py)
    echo "== The Studio's boot screen, early in boot"
    printf 'SUBSYSTEM=="graphics", KERNEL=="fb[0-9]", ATTR{name}=="fb_ili9486|ili9486drmfb", RUN+="/bin/sh -c '"'"'test -f %s && cat %s > /dev/%%k'"'"'"\n' \
        "$HOME/.local/share/fm1-bridge/splash.raw" "$HOME/.local/share/fm1-bridge/splash.raw" \
        | sudo tee /etc/udev/rules.d/90-fm1-splash.rules >/dev/null
fi

if [ "$BUILD" = desk ]; then              # network MIDI for a DAW (Kraken): listed for computers to find
    echo "== Announcing the Studio's network MIDI (XOXO Studio, XOXO Studio MCU)"
    sudo install -D -m 644 "$DIR/config/fm1-midi.service" /etc/avahi/services/fm1-midi.service
    sudo install -D -m 644 "$DIR/config/fm1-midi-mcu.service" /etc/avahi/services/fm1-midi-mcu.service
    echo "== Ethernet straight to another box (the Pocket): a link-local address when there's no router"
    sudo install -D -m 644 "$DIR/config/50-fm1-ethernet-link.conf" /etc/NetworkManager/conf.d/50-fm1-ethernet-link.conf
    sudo nmcli general reload conf || true
fi

echo "== Letting the bridge shut down and switch Wi-Fi without a password"
SUDOERS=/etc/sudoers.d/fm1-bridge
printf '%s ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff, /usr/bin/nmcli radio wifi on, /usr/bin/nmcli radio wifi off\n' \
    "$USER" | sudo tee "$SUDOERS" >/dev/null
sudo chmod 440 "$SUDOERS"
sudo visudo -cf "$SUDOERS"

echo "== Letting the web page use port 80 (http://$(hostname).local) without root"
echo "net.ipv4.ip_unprivileged_port_start=80" | sudo tee /etc/sysctl.d/50-fm1-bridge.conf >/dev/null
sudo sysctl -q -w net.ipv4.ip_unprivileged_port_start=80

echo "== Letting PipeWire run its audio threads in real time (no desktop session on a headless Pi)"
sed "s/FM1_USER/$USER/" "$DIR/config/50-fm1-bridge-rtkit.rules" | sudo tee /etc/polkit-1/rules.d/50-fm1-bridge-rtkit.rules >/dev/null
if [ "$BUILD" = desk ]; then
    echo "== Letting the DJ decks mount a USB drive of music when it's plugged in"
    sed "s/FM1_USER/$USER/" "$DIR/config/50-fm1-bridge-usb.rules" | sudo tee /etc/polkit-1/rules.d/50-fm1-bridge-usb.rules >/dev/null
fi

echo "== Installing the bridge"
install -D -m 755 "$DIR/bridge.py"                              ~/.local/share/fm1-bridge/bridge.py
install -D -m 644 "$DIR/blemidi.py"                             ~/.local/share/fm1-bridge/blemidi.py
install -D -m 644 "$DIR/libui.py"                               ~/.local/share/fm1-bridge/libui.py
install -D -m 644 "$DIR/meters.py"                              ~/.local/share/fm1-bridge/meters.py
install -D -m 644 "$DIR/midiui.py"                              ~/.local/share/fm1-bridge/midiui.py
install -D -m 644 "$DIR/metronome.py"                           ~/.local/share/fm1-bridge/metronome.py
install -D -m 644 "$DIR/battery.py"                             ~/.local/share/fm1-bridge/battery.py
install -D -m 644 "$DIR/device.py"                              ~/.local/share/fm1-bridge/device.py
install -D -m 644 "$DIR/iocard.py"                              ~/.local/share/fm1-bridge/iocard.py
install -D -m 644 "$DIR/desk.py"                                ~/.local/share/fm1-bridge/desk.py
install -D -m 644 "$DIR/deskui.py"                              ~/.local/share/fm1-bridge/deskui.py
install -D -m 644 "$DIR/deskmeters.py"                          ~/.local/share/fm1-bridge/deskmeters.py
install -D -m 644 "$DIR/deskpages.py"                           ~/.local/share/fm1-bridge/deskpages.py
install -D -m 644 "$DIR/pads.py"                                ~/.local/share/fm1-bridge/pads.py
install -D -m 644 "$DIR/xo4.py"                                 ~/.local/share/fm1-bridge/xo4.py
install -D -m 644 "$DIR/xo4synth.py"                            ~/.local/share/fm1-bridge/xo4synth.py
install -D -m 644 "$DIR/deskpads.py"                            ~/.local/share/fm1-bridge/deskpads.py
install -D -m 644 "$DIR/deskxo4.py"                             ~/.local/share/fm1-bridge/deskxo4.py
install -D -m 644 "$DIR/deskplugins.py"                             ~/.local/share/fm1-bridge/deskplugins.py
install -D -m 644 "$DIR/plugins.py"                             ~/.local/share/fm1-bridge/plugins.py
install -D -m 644 "$DIR/deskdecks.py"                           ~/.local/share/fm1-bridge/deskdecks.py
install -D -m 644 "$DIR/padfx.py"                               ~/.local/share/fm1-bridge/padfx.py
install -D -m 644 "$DIR/deskboot.py"                            ~/.local/share/fm1-bridge/deskboot.py
install -D -m 644 "$DIR/netmidi.py"                             ~/.local/share/fm1-bridge/netmidi.py
install -D -m 644 "$DIR/xoxostyle.py"                           ~/.local/share/fm1-bridge/xoxostyle.py
install -D -m 644 "$DIR/weblink.py"                             ~/.local/share/fm1-bridge/weblink.py
install -D -m 644 "$DIR/sampler.py"                             ~/.local/share/fm1-bridge/sampler.py
install -D -m 644 "$DIR/sampleui.py"                            ~/.local/share/fm1-bridge/sampleui.py
install -D -m 755 "$DIR/library.py"                             ~/.local/share/fm1-bridge/library.py
install -D -m 644 "$DIR/decks.py"                               ~/.local/share/fm1-bridge/decks.py
install -D -m 644 "$DIR/djlib.py"                               ~/.local/share/fm1-bridge/djlib.py
install -D -m 755 "$DIR/web.py"                                 ~/.local/share/fm1-bridge/web.py
mkdir -p ~/fm1-library/samples ~/fm1-library/recordings ~/xoxo-plugins   # (plug-ins: plugins.py)
mkdir -p ~/.local/share/fm1-bridge/vendor/fonts
install -m 644 "$DIR"/vendor/fonts/*                            ~/.local/share/fm1-bridge/vendor/fonts/
mkdir -p ~/.local/share/fm1-bridge/icons
install -m 644 "$DIR"/icons/*.png                              ~/.local/share/fm1-bridge/icons/
mkdir -p ~/.local/share/fm1-bridge/kits/808       # the sampler's ready-made 808 KIT (pads.factory_kits copies it in)
install -m 644 "$DIR"/kits/808/*                               ~/.local/share/fm1-bridge/kits/808/
install -D -m 644 "$DIR/config/pipewire-10-fm1-bridge.conf"     ~/.config/pipewire/pipewire.conf.d/10-fm1-bridge.conf
install -D -m 644 "$DIR/config/wireplumber-51-fm1-bridge.conf"  ~/.config/wireplumber/wireplumber.conf.d/51-fm1-bridge.conf
if wireplumber --version 2>/dev/null | grep -q "Linked with libwireplumber 0\.4"; then   # Bookworm: Lua config
    install -D -m 644 "$DIR/config/wireplumber-51-fm1-bridge.lua" ~/.config/wireplumber/bluetooth.lua.d/51-fm1-bridge.lua
else                                                                                # 0.5+ warns about Lua files
    rm -f ~/.config/wireplumber/bluetooth.lua.d/51-fm1-bridge.lua
fi
install -D -m 644 "$DIR/config/fm1-bridge.service"              ~/.config/systemd/user/fm1-bridge.service
install -D -m 644 "$DIR/config/fm1-web.service"                 ~/.config/systemd/user/fm1-web.service
if [ "$BUILD" = desk ]; then              # the Pocket's sound over the link (RTP on UDP 46000): POCKET
    install -D -m 644 "$DIR/config/pipewire-fm1-pocket-in.conf" ~/.local/share/fm1-bridge/pipewire-fm1-pocket-in.conf
    install -D -m 644 "$DIR/config/fm1-pocket-in.service"       ~/.config/systemd/user/fm1-pocket-in.service
fi

if [ "$BUILD" = desk ] && [ ! -f ~/.local/share/fm1-bridge/splash.raw ]; then   # the first boot's picture
    (cd ~/.local/share/fm1-bridge && python3 -c "import deskboot, xoxostyle; deskboot.save(xoxostyle.Theme())")         || echo "   (the boot screen's picture comes with the first start instead)"
fi

echo "== Booting faster (on Trixie a Zero W otherwise takes ~3 minutes before the app starts)"
# cloud-init only applies Raspberry Pi Imager's settings on the first boot, but costs ~40 s on every boot
sudo touch /etc/cloud/cloud-init.disabled
# start the user services (PipeWire, the bridge) without waiting for NetworkManager
sudo install -m 644 "$DIR/config/systemd-user-sessions.service" /etc/systemd/system/systemd-user-sessions.service
# swap in RAM only: the default file-backed swap is rebuilt on every boot (~20 s)
sudo install -D -m 644 "$DIR/config/rpi-swap-50-fm1-bridge.conf" /etc/rpi/swap.conf.d/50-fm1-bridge.conf
sudo systemctl daemon-reload

echo "== Starting at boot without a login"
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable pipewire.socket wireplumber.service fm1-bridge.service fm1-web.service
if [ "$BUILD" = desk ]; then
    systemctl --user enable fm1-pocket-in.service
fi
sync                                    # on the card before anyone pulls the power

echo
echo "Done. Reboot now:  sudo reboot"
if [ "$BUILD" = desk ]; then
    echo "After the reboot: the boot screen, then HOME (on the first install, the touch setup first: four targets)."
else
    echo "After the reboot the OLED shows the bridge. If it is upside down, see README.md."
    echo "Once everything works, turn Wi-Fi off on the device: joystick right > Wi-Fi."
fi
