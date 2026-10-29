"""The box's side of the web page (mixed into bridge.App): its live status for the page, and the page's commands.

The page (web.py, a process of its own) reads library.STATUS and queues commands in library.COMMANDS; the box
writes the status about once a second when something changed (monitor thread) and takes the commands on its
main loop, so they go through the same code as the joystick. Writes to the FM-1's data (restore, loads,
firmware) aren't commands: they still wait for a hold-press on the box (library.ask_box).
"""
import re
import time

import blemidi
import library

SETTINGS = ("metronome", "bpm", "clock_mode", "click", "audio_rate")


class WebLink:
    def web_init(self):
        self.web_shown, self.web_written = None, 0.0     # the status last written for the page, and when

    def web_status(self):
        """everything the page shows, as plain JSON"""
        midi, clock = self.midi, getattr(self.midi, "clock", None) if self.midi else None
        keys = self.keys_route()
        return {
            "box": "xoxo-studio",             # which box (one web app for it and the FM-1 Companions: "pocket", "studio")
            "sources": [self.channel_name(k, n) for k, n in self.mix_channels()],
            "live": self.live(),
            "mixer": self.web_mixer(),
            "pocket": self.pocket_link(),
            "speaker": self.sink and self.sink["label"], "speaker_name": self.state["last_name"],
            "speaker_battery": getattr(self, "spk_battery", None),
            "connecting": self.connecting, "volume": self.volume, "battery": self.battery,
            "midi": {"peer": midi and midi.peer, "enabled": bool(midi and midi.enabled),
                     "error": midi and midi.error, "controllers": list(getattr(midi, "controllers", None) or []),
                     "net": list(getattr(midi, "net", None) or []),
                     "pads": bool(getattr(midi, "pads", False)), "xo4": bool(getattr(midi, "xo4", False))},
            "matrix": dict(zip(("sources", "dests"), self.matrix_lists())),
            "clock": clock, "clock_text": self.clock_text(),
            "recording": int(self.recorder.seconds()) if self.recorder.recording() else None,
            "settings": dict({k: self.state[k] for k in SETTINGS}, arp_on=keys["arp_on"], chord_on=keys["chord_on"],
                             arp=keys["arp"], arp_rate=keys["arp_rate"], chord=keys["chord"]),
            "routes": self.routes(), "presets": self.presets(), "wifi": self.wifi,
            "xo4": self.web_xo4(), "kits": self.web_kits(), "decks": self.web_decks(),
        }

    def web_mixer(self):
        """the mixer's levels: each source, and the DJ decks while they play; None with only one source"""
        rows = [{"key": k, "label": self.channel_name(k, n), "level": self.mix_level(k),
                 "input": self.input_label(k, n)} for k, n in self.mix_channels()]
        if "decks" in (getattr(self, "app_here", None) or ()):
            rows.append({"key": "decks", "label": "DECKS", "level": self.mix_level("decks"), "input": None})
        return rows if len(rows) > 1 else None

    def web_xo4(self):
        """XO-4: the pattern playing (or to play), the one waiting for the bar, those with steps, MIDI IN, the
        synths' starting sounds"""
        import xo4
        song = self.state.get("xo4") or self.song()
        x = getattr(self, "xo4", None)
        used = [p for p in xo4.PATTERNS if any(any(t["steps"]) for t in song["patterns"][p])]
        return {"pattern": (x and x.pattern) or song["pattern"], "queued": x and x.queued, "used": used,
                "playing": self.seq_playing(), "midi_in": bool(self.state.get("xo4_midi_in")),
                "sounds": [self.xo4_sound_name(p) for p in song["patches"]], "choices": list(xo4.SOUNDS)}

    def web_kits(self):
        import pads
        return {"current": self.kit()["name"], "list": pads.list_kits()}

    def web_decks(self):
        """the DJ decks while they run: each deck's track, tempo, key, playing, FX; None: not running"""
        proc = getattr(self, "desk", None) and self.desk.decks_proc
        if not proc or not proc.running():
            return None
        status = getattr(proc, "status", None) or {}
        keep = ("title", "artist", "bpm", "camelot", "playing", "fx", "fx_on")
        return [{k: (d or {}).get(k) for k in keep} for d in (status.get("decks") or [])]

    def web_publish(self):
        """called by the monitor thread every second: the status file, rewritten when it changed, and every 2 s
        anyway (the page takes a status over 5 s old to mean the box isn't running). A small file in RAM."""
        status, now = self.web_status(), time.monotonic()
        if status != self.web_shown or now - self.web_written >= 2:
            try:
                library.write_status(status)
                self.web_shown, self.web_written = status, now
            except OSError:
                pass

    def web_commands(self):
        """called by the main loop: apply what the page asked for"""
        for command in library.take_commands():
            try:
                text = self.web_command(command)
            except (KeyError, TypeError, ValueError) as e:
                text = f"Web: {str(e)[:30]}"
            if text:
                self.say(text, 1.5)

    def web_command(self, c):
        """one command from the page -> a short message for the screen. Values are checked here too: the page
        checks them, but the commands file is the only door and it gets the same care."""
        cmd = c.get("cmd")
        if cmd == "set":
            key, value = c["key"], c["value"]
            if key in ("metronome",) and isinstance(value, bool):
                self.state[key] = value
                self.save_settings()
                return f"Web: Metronome {'on' if value else 'off'}"
            if key == "bpm" and isinstance(value, (int, float)) and 30 <= value <= 300:
                self.set_clock(bpm=value)
                return f"Web: Tempo {self.state['bpm']}"
            if key == "clock_mode" and value in ("follow", "box"):
                self.set_clock(mode=value)
                return f"Web: Clock {value}"
            if key == "click" and value in ("low", "mid", "high"):
                self.state["click"] = value
                self.save_settings()
                return f"Web: Click {value}"
            if key == "audio_rate" and value in (44100, 48000):
                if value != self.state["audio_rate"]:
                    self.state["audio_rate"] = value
                    self.save_settings()
                    self.loop.reopen(value)
                    self.mixer.reopen(value)
                return f"Web: Audio {value / 1000:g} kHz"
            if key in ("arp_on", "chord_on") and isinstance(value, bool):
                if self.keys_route()[key] != value:
                    self.toggle_keys(key)
                return None                   # toggle_keys says it
            if re.fullmatch(r"mix_(decks|u-[a-z0-9]+)", key) and isinstance(value, int) and 0 <= value <= 200:
                self.set_mix_level(key[4:], value)
                return None
            if re.fullmatch(r"input_u-[a-z0-9]+", key):          # a multichannel source: its next pair
                pair = self.next_input_pair(key[6:])
                return pair and f"Web: inputs {pair}"
            if key == "volume" and isinstance(value, int) and 0 <= value <= 100 and self.sink:
                self.volume_to(value)
                return None
            raise ValueError(f"bad setting {key}")
        if cmd == "transport" and c.get("value") in ("start", "stop"):
            if self.midi:
                self.playing = c["value"] == "start"
                self.midi.transport(c["value"])
            return f"Web: {c['value'].title()}"
        if cmd == "record" and c.get("value") in ("start", "stop"):
            if (c["value"] == "start") != self.recorder.recording():
                self.toggle_recording()
            return None                       # toggle_recording says it
        if cmd == "routes":
            self.state["routes"] = self.keep_routes(blemidi.clean_routes(c.get("routes")))
            self.save_settings()
            if self.midi:
                self.midi.set_routes(self.routes())
            return "Web: MIDI routes"
        if cmd == "preset" and c.get("slot") in ("1", "2", "3", "4") and c.get("action") in ("load", "save", "clear"):
            name = c.get("name")
            self.preset_apply(c["slot"], c["action"], name if isinstance(name, str) else None)
            return None                       # preset_apply says it
        if cmd == "xo4":
            return self.web_xo4_command(c)
        if cmd == "kit":
            import pads
            if c.get("name") not in pads.list_kits():
                raise ValueError("no such kit")
            kit = pads.load_kit(pads.kits_folder() / f"{c['name']}.json")
            if kit:
                self.set_kit(kit)
            return kit and f"Web: Kit {kit['name']}"
        raise ValueError(f"bad command {cmd}")

    def web_xo4_command(self, c):
        import xo4
        action, value = c.get("action"), c.get("value")
        if action == "pattern" and value in xo4.PATTERNS:
            self.xo4_pick_pattern(value)
            return f"Web: XO-4 pattern {value}"
        if action == "midi_in" and isinstance(value, bool):
            self.set_xo4_midi_in(value)
            return f"Web: XO-4 MIDI IN {'on' if value else 'off'}"
        if action == "sound" and c.get("track") in (1, 2) and value in xo4.SOUNDS:
            self.xo4_sound(c["track"], value)
            return f"Web: SYN {c['track']} {value}"
        if action == "play":
            self.seq_play()
            return None
        raise ValueError(f"bad XO-4 command {action}")
