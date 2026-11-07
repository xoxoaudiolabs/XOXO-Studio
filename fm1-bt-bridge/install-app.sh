#!/usr/bin/env bash
# The Studio's own files (its code, fonts, icons, kits, its PipeWire and WirePlumber settings, its user services):
# the part of install.sh that needs no root. install.sh runs it (sourced, DIR and BUILD set); the web app's update
# runs it alone, as the Studio's user, when the root update (fm1-update) can't run here (update.py): then it
# installs what it can without a password, and the system's files wait for install.sh or fm1-update.
#   bash install-app.sh
set -euo pipefail
DIR="${DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ -z "${BUILD:-}" ]; then
    case "$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)" in
        *Zero*) BUILD=pocket ;;
        *)      BUILD=desk ;;
    esac
fi
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
install -D -m 644 "$DIR/deskabout.py"                           ~/.local/share/fm1-bridge/deskabout.py
install -D -m 644 "$DIR/netmidi.py"                             ~/.local/share/fm1-bridge/netmidi.py
install -D -m 644 "$DIR/xoxostyle.py"                           ~/.local/share/fm1-bridge/xoxostyle.py
install -D -m 644 "$DIR/weblink.py"                             ~/.local/share/fm1-bridge/weblink.py
install -D -m 644 "$DIR/sampler.py"                             ~/.local/share/fm1-bridge/sampler.py
install -D -m 644 "$DIR/sampleui.py"                            ~/.local/share/fm1-bridge/sampleui.py
install -D -m 755 "$DIR/library.py"                             ~/.local/share/fm1-bridge/library.py
install -D -m 644 "$DIR/decks.py"                               ~/.local/share/fm1-bridge/decks.py
install -D -m 644 "$DIR/djlib.py"                               ~/.local/share/fm1-bridge/djlib.py
install -D -m 755 "$DIR/web.py"                                 ~/.local/share/fm1-bridge/web.py
install -D -m 755 "$DIR/update.py"                              ~/.local/share/fm1-bridge/update.py
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
