"""The Studio's sequencer (the SEQ tab): eight MIDI tracks on the box's beat grid, patterns A-H, up to 64 steps.

Each track plays a MIDI channel (song["tracks"][i]: {"channel": 0-15, "level"}), out through the MIDI routes (their
source "SEQ"), sent by the MIDI process when its notes are due; tracks 1-8 on channels 1-8 to start with. A step:
up to four notes (a chord), a velocity, a length in steps, and a nudge (in 64ths of a step, early or late of the
grid). The pads (the sampler plug-in) play from it like any MIDI gear: the route SEQ > SMP, notes 36-51.

Each track has its own length (1-64 steps of a 16th), so tracks of different lengths drift and meet again. The
pattern playing changes on the next bar (16 steps) after another is picked, for every track at once. SWING delays
every second 16th.

The process (SeqProcess) keeps time on the monotonic clock, a BLOCK's worth of time a turn, on the beat grid the
MIDI process sends it; it sends the app the step playing and the MIDI process its notes, LOOKAHEAD early. It makes
no sound of its own.

A song saved before (XO-4's four tracks, or this sequencer's when a track could be the pads) is kept: a drums or
pads track becomes a MIDI track on channel 10 with each pad as its note (36 + pad, the hit's level as velocity),
XO-4's MIDI track keeps its channel, and SYN 1 / SYN 2's notes go on the next channels.
"""
import math
import os
import time

NTRACK = 8
PAD_NOTE, PAD_CHANNEL = 36, 9               # a pads hit from an older song: note 36 + pad, on channel 10
PATTERNS = tuple("ABCDEFGH")
NSTEP = 64
BAR = 16                                    # steps a bar: where a pattern change waits for
NOTES = 4                                   # notes a step at most (a chord)
GATE = 0.9                                  # a step's note ends at this share of its length (the next one clean)
LOOKAHEAD = 0.12                            # s: the notes sent this far ahead of when they sound
BLOCK = 512
SCALES = {"MAJOR": (0, 2, 4, 5, 7, 9, 11), "MINOR": (0, 2, 3, 5, 7, 8, 10), "DORIAN": (0, 2, 3, 5, 7, 9, 10),
          "MIXOLYD": (0, 2, 4, 5, 7, 9, 10), "PENTA": (0, 2, 4, 7, 9), "MIN PENTA": (0, 3, 5, 7, 10),
          "CHROMATIC": tuple(range(12))}         # the note keys on the screen offer these, from the root up
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
LEVEL_VEL = (100, 42, 72, 127)              # an older song's pads hit level (NORM, GHOST, SOFT, HARD): its velocity


def empty_track():
    return {"len": 16, "steps": [None] * NSTEP}


def default_tracks():
    """tracks 1-8 on MIDI channels 1-8"""
    return [{"channel": i, "level": 1.0} for i in range(NTRACK)]


def empty_song():
    """the song: patterns A-H (eight tracks each), which plays, each track's channel and level, swing, and the
    key and scale the screen's note keys offer"""
    return {"patterns": {p: [empty_track() for _ in range(NTRACK)] for p in PATTERNS}, "pattern": "A",
            "tracks": default_tracks(), "swing": 0, "root": 0, "scale": "MAJOR"}


def scale_notes(song, low, count):
    """count notes of the song's scale from MIDI note low up (low itself if it's in the scale)"""
    steps, out, n = SCALES[song["scale"]], [], low
    while len(out) < count and n <= 127:
        if (n - song["root"]) % 12 in steps:
            out.append(n)
        n += 1
    return out


def note_name(note):
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


def clean_step(step):
    """a step from anywhere -> {"notes", "vel", "len", "nudge"} or None (empty): notes 0-127, at most NOTES, no
    repeats"""
    if not isinstance(step, dict):
        return None
    notes = []
    for n in step.get("notes") or []:
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if 0 <= n <= 127 and n not in notes:
            notes.append(n)
    if not notes:
        return None
    try:
        vel = max(1, min(127, int(step.get("vel", 100))))
    except (TypeError, ValueError):
        vel = 100
    try:
        length = max(0.25, min(16.0, float(step.get("len", 1.0))))
    except (TypeError, ValueError):
        length = 1.0
    return {"notes": sorted(notes[:NOTES]), "vel": vel, "len": length,
            "nudge": clamp_int(step.get("nudge", 0), -32, 31, 0)}


def pads_step(step):
    """an older song's pads hits (pads 0-15, each with its level) -> a MIDI step on PAD_CHANNEL: 36 + pad, the
    loudest hit's velocity"""
    if not isinstance(step, dict):
        return None
    pads = [p for p in (step.get("notes") or []) if isinstance(p, int) and 0 <= p <= 15]
    levels = step.get("levels") if isinstance(step.get("levels"), list) else []
    vel = max([LEVEL_VEL[clamp_int(lv, 0, 3, 0)] for lv in levels[:len(pads)]] or [100])
    return clean_step({"notes": [PAD_NOTE + p for p in pads], "vel": vel, "len": 0.5, "nudge": step.get("nudge", 0)})


def clamp_int(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def old_song(song):
    """a song saved when this was XO-4's (four tracks: DRUMS, SYNTH 1, SYNTH 2, MIDI; "midi_channel") -> this
    sequencer's: track 1 its drums (pads hits, made notes on channel 10 by clean_song), 2 its MIDI track on its
    channel, 3 and 4 the synth tracks' notes on the next channels"""
    channel = clamp_int(song.get("midi_channel", 0), 0, 15, 0)
    levels = song.get("levels") if isinstance(song.get("levels"), list) else []
    tracks = default_tracks()
    tracks[0]["kind"] = "pads"
    tracks[1]["channel"] = channel
    tracks[2]["channel"], tracks[3]["channel"] = (channel + 1) % 16, (channel + 2) % 16
    for new, old in ((0, 0), (1, 3), (2, 1), (3, 2)):
        try:
            tracks[new]["level"] = float(levels[old])
        except (IndexError, TypeError, ValueError):
            pass
    patterns = {}
    for p, old in (song.get("patterns") or {}).items():
        if isinstance(old, list):
            old = (old + [None] * 4)[:4]
            patterns[p] = [old[0], old[3], old[1], old[2]]
    out = {k: v for k, v in song.items() if k not in ("patches", "midi_channel", "levels")}
    return dict(out, patterns=patterns, tracks=tracks)


def clean_song(song):
    song = song if isinstance(song, dict) else {}
    if "tracks" not in song and ("patches" in song or "midi_channel" in song):
        song = old_song(song)
    out = empty_song()
    given = song.get("tracks") if isinstance(song.get("tracks"), list) else []
    was_pads = set()                            # tracks that were the pads (an older song): notes on channel 10
    for i, t in enumerate(given[:NTRACK]):
        if isinstance(t, dict):
            mine = out["tracks"][i]
            if t.get("kind") == "pads":
                was_pads.add(i)
                mine["channel"] = PAD_CHANNEL
            elif t.get("kind") == "midi" and "channel" not in t:
                pass
            else:
                mine["channel"] = clamp_int(t.get("channel", mine["channel"]), 0, 15, mine["channel"])
            try:
                mine["level"] = max(0.0, min(2.0, float(t.get("level", 1.0))))
            except (TypeError, ValueError):
                pass
    patterns = song.get("patterns") if isinstance(song.get("patterns"), dict) else {}
    for p in PATTERNS:
        tracks = patterns.get(p) if isinstance(patterns.get(p), list) else []
        for i, track in enumerate(tracks[:NTRACK]):
            if not isinstance(track, dict):
                continue
            try:
                out["patterns"][p][i]["len"] = max(1, min(NSTEP, int(track.get("len", 16))))
            except (TypeError, ValueError):
                pass
            steps = track.get("steps") if isinstance(track.get("steps"), list) else []
            clean = pads_step if i in was_pads else clean_step
            out["patterns"][p][i]["steps"] = [clean(s) for s in (steps + [None] * NSTEP)[:NSTEP]]
    if song.get("pattern") in PATTERNS:
        out["pattern"] = song["pattern"]
    if song.get("scale") in SCALES:
        out["scale"] = song["scale"]
    for key, lo, hi in (("swing", 0, 100), ("root", 0, 11)):
        out[key] = clamp_int(song.get(key, out[key]), lo, hi, out[key])
    return out


# ---------------------------------------------------------------- the sequencer

class Lane:
    """a run through the steps for some of the tracks: the playhead on the time it's heard, the notes LOOKAHEAD
    ahead of it. Each keeps its own place, so the two never wait for each other"""

    def __init__(self, tracks):
        self.tracks = tracks
        self.next = None                        # the absolute step (since tick 0) to fire next
        self.pending = []                       # (time, track, "on" / "off", note, velocity) not yet due
        self.held = set()                       # (track, note) sounding: let go when it stops


class Sequencer:
    """the eight tracks on the beat grid (seconds a tick, tick 0's time, playing). due() hands out a lane's
    notes in a stretch of (heard) time, in order"""

    def __init__(self):
        self.grid = None
        self.now = Lane(())                     # (the playhead and the pattern, on the time it's heard)
        self.ahead = Lane(tuple(range(NTRACK)))
        self.switches = {}                      # absolute step -> the pattern from there on
        self.queued = None                      # a pattern picked, waiting for the next bar
        self.step = None                        # the absolute step heard last (the playhead)

    def playing(self):
        return bool(self.grid and self.grid[2] and self.grid[1] is not None)

    def unit(self):
        return self.grid[0] * 6                 # a 16th: six clock ticks

    def time(self, song, a):
        """when absolute step a sounds: every second 16th late by the swing"""
        u = self.unit()
        return self.grid[1] + a * u + (song["swing"] * u / 200 if a % 2 else 0.0)

    def pattern_at(self, song, a):
        names = [p for at, p in sorted(self.switches.items()) if at <= a]
        return names[-1] if names else song["pattern"]

    def pick(self, song, pattern, now_step=None):
        """a pattern to play from the next bar on (at once while stopped)"""
        if pattern not in PATTERNS:
            return
        if not self.playing():
            song["pattern"], self.switches = pattern, {}
            return
        a = max(x for x in (self.now.next, self.ahead.next, now_step, 0) if x is not None)
        at = (a // BAR + 1) * BAR
        self.switches = {k: v for k, v in self.switches.items() if k < at}
        self.switches[at] = pattern
        self.queued = pattern

    def due(self, song, lane, t0, t1):
        """lane's notes due in [t0, t1): (time, track, "on" / "off", note, velocity), in order"""
        if not self.playing():
            if lane.next is not None or lane.held:      # stopped: what's held ends
                offs = [(t0, track, "off", note, 0) for track, note in sorted(lane.held)]
                lane.next, lane.pending, lane.held = None, [], set()
                return offs
            return []
        u = self.unit()
        if lane.next is None or self.time(song, lane.next) < t0 - 2 * u:   # PLAY, or the grid jumped
            a = max(0, math.floor((t0 - self.grid[1]) / u))
            while self.time(song, a) < t0 - 0.002:
                a += 1
            lane.next = a
        while self.time(song, lane.next) < t1:
            self.fire(song, lane, lane.next)
            lane.next += 1
        due = sorted(p for p in lane.pending if p[0] < t1)
        lane.pending = [p for p in lane.pending if p[0] >= t1]
        for t, track, kind, note, _ in due:
            (lane.held.add if kind == "on" else lane.held.discard)((track, note))
        return due

    def fire(self, song, lane, a):
        name = self.pattern_at(song, a)
        if lane is self.now:
            self.step = a
            if name != song["pattern"]:         # the new pattern, heard from here
                song["pattern"], self.queued = name, None
                self.switches = {k: v for k, v in self.switches.items() if k > a}
        tracks = song["patterns"][name]
        u = self.unit()
        for i in lane.tracks:
            track = tracks[i]
            step = track["steps"][a % track["len"]]
            if not step:
                continue
            t = self.time(song, a) + step.get("nudge", 0) * u / 64
            off = t + max(0.01, step["len"] * u * GATE)
            for note in step["notes"]:
                lane.pending += [(t, i, "on", note, step["vel"]), (off, i, "off", note, 0)]


# ---------------------------------------------------------------- the engine

class Engine:
    """the song and the sequencer; hands out the tracks' notes, on the process's thread"""

    def __init__(self, rate=48000):
        self.rate = rate
        self.song = empty_song()
        self.seq = Sequencer()

    def set_song(self, song):
        """a new song (from the app): what plays and where it is carry on"""
        playing = self.song["pattern"]
        self.song = clean_song(song)
        if self.seq.switches:                   # (a change already waiting: the song's own pattern stays)
            self.song["pattern"] = playing

    def step(self, n, t0):
        """the next n frames' time stepped through -> the notes LOOKAHEAD ahead"""
        t1 = t0 + n / self.rate
        self.seq.due(self.song, self.seq.now, t0, t1)   # (the playhead, a pattern changing on the bar)
        return self.seq.due(self.song, self.seq.ahead, t0 + LOOKAHEAD, t1 + LOOKAHEAD)


def midi_notes(notes, song):
    """the tracks' notes -> [(time, MIDI bytes)], each on its track's channel, for the MIDI process to send when
    they're due"""
    out = []
    for t, i, kind, note, vel in notes:
        ch, level = song["tracks"][i]["channel"], song["tracks"][i]["level"]
        if kind == "on":
            out.append((t, [0x90 | ch, note, max(1, min(127, round(vel * level)))]))
        else:
            out.append((t, [0x80 | ch, note, 0]))
    return out


# ---------------------------------------------------------------- the process

def run(app_conn, midi_conn, notes_conn, rate):
    """the sequencer's process: the app's and the MIDI process's messages, the tracks' notes to the MIDI process,
    the step to the app; it keeps time on the monotonic clock, a BLOCK's worth of time a turn"""
    engine, step_shown, pattern_shown = Engine(rate), None, None
    ahead = 1024 / rate + 0.010
    base, frames = None, 0
    try:
        while True:
            for conn in (app_conn, midi_conn):
                while conn is not None and conn.poll():
                    try:
                        msg = conn.recv()
                    except (EOFError, OSError):
                        os._exit(0)
                    if msg[0] == "song":
                        engine.set_song(msg[1])
                    elif msg[0] == "pick":              # ("pick", pattern): from the next bar
                        engine.seq.pick(engine.song, msg[1])
                    elif msg[0] == "grid":              # ("grid", seconds a tick, tick 0's time or None, playing)
                        engine.seq.grid = tuple(msg[1:4])
            heard = time.monotonic() + ahead
            if base is None or abs(base + frames / rate - heard) > 0.015:
                base, frames = heard, 0
            notes = engine.step(BLOCK, base + frames / rate)
            if notes:
                out = midi_notes(notes, engine.song)
                if out and notes_conn is not None:
                    notes_conn.send(("seq", out))
            frames += BLOCK
            shown = (engine.seq.step, engine.song["pattern"], engine.seq.queued)
            if shown != step_shown:
                step_shown = shown
                app_conn.send(("step",) + shown)
            if engine.song["pattern"] != pattern_shown:
                pattern_shown = engine.song["pattern"]
                app_conn.send(("pattern", pattern_shown))
            wait = base + frames / rate - ahead - time.monotonic()
            if wait > 0:
                time.sleep(wait)
    except (BrokenPipeError, OSError):
        pass


class SeqProcess:
    """the sequencer in a process of its own; the app's side. midi_conn: the end the MIDI process sends the grid
    to; notes_in: the end the MIDI process reads the tracks' notes from"""

    def __init__(self, rate=48000):
        import multiprocessing
        ctx = multiprocessing.get_context("fork")
        self.conn, child = ctx.Pipe()
        self.grid_in, self.midi_conn = ctx.Pipe(duplex=False)        # the MIDI process writes midi_conn
        self.notes_in, notes_w = ctx.Pipe(duplex=False)              # the sequencer writes, the MIDI process reads
        self.proc = ctx.Process(target=run, args=(child, self.grid_in, notes_w, rate), daemon=True,
                                name="fm1-seq")
        self.step = self.pattern = self.queued = None
        self.on_step = None

    def start(self):
        import threading
        self.proc.start()
        threading.Thread(target=self.receive, daemon=True).start()

    def receive(self):
        while True:
            try:
                msg = self.conn.recv()
            except (EOFError, OSError):
                return
            if msg[0] == "step":
                self.step, self.pattern, self.queued = msg[1:4]
                if self.on_step:
                    self.on_step()
            elif msg[0] == "pattern":
                self.pattern = msg[1]

    def send(self, *msg):
        try:
            self.conn.send(msg)
        except (BrokenPipeError, OSError):
            pass
