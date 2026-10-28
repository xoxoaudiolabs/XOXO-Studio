"""The box's Library screens: the recordings and the sample editor's files, pickers, a hold-to-confirm step and a
recording playing. Mixed into bridge.App, which provides the fonts, fit(), say(), draw_box() and the screen
machinery.
"""
from datetime import datetime
from pathlib import Path

import library
from meters import Player, clock, wav_seconds

def short_date(path_name):
    """"2026-10-21_171819_..." -> "10-21 17:18" """
    try:
        return datetime.strptime(path_name[:17], "%Y-%m-%d_%H%M%S").strftime("%m-%d %H:%M")
    except ValueError:
        return path_name[:11]


LIBRARY_KEYS = ("recording", "editor", "sd")


class LibraryScreens:
    """The Settings rows that reach the library (LIBRARY_KEYS: Recordings, the sample editor, Import SD card),
    and their screens: "pick" (a list), "confirm" (hold press 2 s) and "player". Back goes to Settings."""

    def library_init(self):
        self.pick = None                      # {"title", "items": [(label, value, payload)], "cursor", "on", "back"}
        self.confirm = None                   # {"title", "lines", "action", "back"}
        self.player, self.player_name = Player(), None    # a recording playing on the speaker

    # ---- the menu
    def library_choose(self, key):
        """one of LIBRARY_KEYS, chosen in Settings"""
        listing = library.listing()
        if key == "editor":
            self.open_pick("Sample editor", [("From a recording ›", "", "recordings"),
                                             ("From a sample ›", "", "samples")], self.pick_editor_source, "")
        elif key == "recording":
            items = [(short_date(r["name"]), clock(r.get("seconds", 0)), r["name"]) for r in listing["recordings"]]
            self.open_pick("Recordings", items, self.pick_recording, "No recordings yet")
        elif key == "sd":
            try:
                copied = library.import_sd()
                self.say(f"{len(copied)} new file{'s' if len(copied) != 1 else ''} from SD")
            except OSError as e:
                self.say(f"SD card: {e}"[:40])

    # ---- pickers
    def open_pick(self, title, items, on, empty, back="settings"):
        if not items:
            self.say(empty)
            return
        self.pick = {"title": title, "items": items, "cursor": 0, "on": on, "back": back}
        self.screen = "pick"

    def ask(self, title, lines, action, back="pick"):
        self.confirm = {"title": title, "lines": lines, "action": action, "back": back}
        self.screen = "confirm"

    def pick_editor_source(self, folder):
        listing = library.listing()[folder]
        if folder == "recordings":
            items = [(short_date(r["name"]), clock(r.get("seconds", 0)), r["name"]) for r in listing]
        else:
            items = [(Path(s["name"]).stem, "wav", s["name"]) for s in listing]
        self.open_pick("Edit which", items, lambda name: self.open_editor(name, folder),
                       "No recordings yet" if folder == "recordings" else "No samples yet", back="pick")

    def pick_recording(self, name):
        """what to do with a recording: play it on the speaker, make a sample of it, open one of its parts (each
        source on its own, with Record parts on), or delete it"""
        parts = library.recording_parts(name)
        actions = ([("Play", "", "play"), ("Edit as sample ›", "", "edit")]
                   + ([("Parts ›", str(len(parts)), "parts")] if parts else []) + [("Delete", "", "delete")])
        self.open_pick(short_date(name), actions, lambda action: self.recording_action(name, action), "")

    def pick_part(self, name):
        """a part: play it or make a sample of it (it goes with its take when that's deleted)"""
        label = library.part_label(library.PART.match(name).group(2))
        self.open_pick(label, [("Play", "", "play"), ("Edit as sample ›", "", "edit")],
                       lambda action: self.recording_action(name, action), "", back="pick")

    def recording_action(self, name, action):
        path = library.folder("recordings") / name
        if action == "play":
            if not self.cue_target():
                self.say("No speaker connected")
            elif self.player.start(self.cue_target(), path):
                self.player_name, self.screen = name, "player"
            else:
                self.say("Can't play (pw-play?)")
        elif action == "edit":
            self.open_editor(name)
        elif action == "parts":
            items = [(library.part_label(library.PART.match(n).group(2)), clock(wav_seconds(library.folder(
                "recordings") / n)), n) for n in library.recording_parts(name)]
            self.open_pick("Parts", items, self.pick_part, "", back="pick")
        elif action == "delete":
            parts = library.recording_parts(name)

            def delete():
                library.delete_recording(name)
                self.screen = "settings"
                self.say("Deleted")
            seconds = wav_seconds(path) if path.exists() else 0
            self.ask("Delete?", [short_date(name), f"{clock(seconds)} recorded"]
                     + ([f"and its {len(parts)} parts"] if parts else []), delete)

    # ---- keys
    def library_key(self, key, held):
        """True if a Library screen took the key"""
        if self.screen == "pick":
            p = self.pick
            if key in ("up", "down"):
                p["cursor"] = (p["cursor"] + (1 if key == "down" else -1)) % len(p["items"])
            elif key in ("press", "right") and not held:
                p["on"](p["items"][p["cursor"]][2])
            elif key == "left":
                self.screen = "settings"
            return True
        if self.screen == "confirm":
            if key == "press" and held:
                self.confirm["action"]()
            elif key == "press":
                self.say("Hold to confirm", 1.5)
            elif key == "left":
                back = self.confirm["back"]
                self.screen = "settings" if back == "pick" and not self.pick else back
            return True
        if self.screen == "player":
            if key in ("press", "left", "right") and not held:
                self.player.stop()
                self.screen = "settings"
            return True
        return False

    def draw_player(self, d):
        d.text((0, 0), "Playing", font=self.f_title, fill=1)
        d.line((0, 14, 127, 14), fill=1)
        d.text((0, 16), short_date(self.player_name or ""), font=self.f_body, fill=1)
        now, length = self.player.seconds(), self.player.length
        text = f"{clock(now)} / {clock(length)}"
        d.text((127 - d.textlength(text, font=self.f_body), 29), text, font=self.f_body, fill=1)
        d.rectangle((0, 42, 127, 49), outline=1)
        if length:
            d.rectangle((2, 44, 2 + int(123 * min(1.0, now / length)), 47), fill=1)
        d.text((0, 53), "press = stop", font=self.f_small, fill=1)

    # ---- drawing
    def library_view(self, now):
        if self.screen == "pick":
            return ("pick", self.pick["title"], self.pick["cursor"], tuple(i[:2] for i in self.pick["items"]))
        if self.screen == "confirm":
            return ("confirm", self.confirm["title"], tuple(self.confirm["lines"]))
        if self.screen == "player":
            if not self.player.playing():     # played to the end: back to Settings
                self.player.stop()
                self.screen = "settings"
                self.say("Played to the end", 1.5)
                return ("settings",)
            return ("player", self.player_name, int(self.player.seconds(now) * 2))
        return None

    def draw_list(self, d, title, items, cursor, footer):
        d.text((0, 0), title, font=self.f_title, fill=1)
        where = f"{cursor + 1}/{len(items)}"
        d.text((127 - d.textlength(where, font=self.f_small), 2), where, font=self.f_small, fill=1)
        d.line((0, 14, 127, 14), fill=1)
        top = min(max(0, cursor - 1), max(0, len(items) - 3))
        for i, (label, value) in enumerate(items[top:top + 3]):
            y, selected = 16 + i * 12, top + i == cursor
            if selected:
                d.rectangle((0, y, 127, y + 11), fill=1)
            value = self.fit(d, value or "", self.f_small, 44)
            w = d.textlength(value, font=self.f_small)
            d.text((2, y), self.fit(d, label, self.f_body, 120 - w), font=self.f_body, fill=0 if selected else 1)
            d.text((125 - w, y + 2), value, font=self.f_small, fill=0 if selected else 1)
        d.text((0, 53), footer, font=self.f_small, fill=1)

    def draw_pick(self, d):
        p = self.pick
        self.draw_list(d, p["title"], [i[:2] for i in p["items"]], p["cursor"], "press = choose   < back")

    def draw_confirm(self, d):
        c = self.confirm
        d.text((0, 0), c["title"], font=self.f_title, fill=1)
        d.line((0, 14, 127, 14), fill=1)
        for i, line in enumerate(c["lines"][:3]):
            d.text((0, 16 + i * 12), self.fit(d, line, self.f_body, 127), font=self.f_body, fill=1)
        d.rectangle((0, 52, 127, 63), fill=1)
        d.text((4, 53), "HOLD press 2 s · < back", font=self.f_small, fill=0)
