#!/bin/sh
# XOXO Studio as a USB audio + MIDI interface for a computer, on a Pi 4's USB-C port (its USB controller in device
# mode: dtoverlay=dwc2,dr_mode=peripheral, install.sh). Linux's USB gadget, set up in configfs at boot
# (xoxo-usb-gadget.service): one device, "XOXO Studio", with
#   - USB Audio Class 2: stereo, 48 kHz, 16-bit, each way (the computer plays into the Studio, the Studio plays
#     into the computer). No driver on a Mac or Linux; Windows 10 and 11 have a class driver for it
#   - USB MIDI: one port each way
# The Studio's ALSA card is "UAC2Gadget"; its MIDI port's client is "f_midi" (blemidi.py names it COMPUTER).
# Run as root. Nothing to do if it's set up already, or if this Pi has no USB device controller (a Pi 3).
set -e

G=/sys/kernel/config/usb_gadget/xoxo
[ -d "$G" ] && exit 0
UDC="$(ls /sys/class/udc 2>/dev/null | head -n 1)"
if [ -z "$UDC" ]; then
    echo "xoxo-usb-gadget: no USB device controller (needs a Pi 4's USB-C and dtoverlay=dwc2,dr_mode=peripheral)"
    exit 0
fi
modprobe libcomposite
mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config

mkdir -p "$G"
cd "$G"
echo 0x1d6b > idVendor                         # the Linux Foundation's
echo 0x0104 > idProduct                        # Multifunction Composite Gadget
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB
echo 0xEF > bDeviceClass                       # composite with interface associations (Windows wants them)
echo 0x02 > bDeviceSubClass
echo 0x01 > bDeviceProtocol
mkdir -p strings/0x409
echo "XOXO Audio Labs" > strings/0x409/manufacturer
echo "XOXO Studio" > strings/0x409/product
SERIAL="$(tr -d '\0' < /sys/firmware/devicetree/base/serial-number 2>/dev/null || echo 0000000000000000)"
echo "$SERIAL" > strings/0x409/serialnumber

mkdir -p configs/c.1/strings/0x409
echo "Audio + MIDI" > configs/c.1/strings/0x409/configuration
echo 0xC0 > configs/c.1/bmAttributes           # self-powered: the Studio takes nothing from the computer
echo 2 > configs/c.1/MaxPower

mkdir -p functions/uac2.usb0
for side in c p; do                            # c: from the computer; p: to the computer
    echo 3 > functions/uac2.usb0/${side}_chmask
    echo 48000 > functions/uac2.usb0/${side}_srate
    echo 2 > functions/uac2.usb0/${side}_ssize
done
[ -e functions/uac2.usb0/function_name ] && echo "XOXO Studio" > functions/uac2.usb0/function_name

mkdir -p functions/midi.usb0
echo XOXOStudio > functions/midi.usb0/id
echo 1 > functions/midi.usb0/in_ports
echo 1 > functions/midi.usb0/out_ports

ln -s functions/uac2.usb0 configs/c.1/
ln -s functions/midi.usb0 configs/c.1/
echo "$UDC" > UDC
echo "xoxo-usb-gadget: XOXO Studio on $UDC (USB audio + MIDI)"
