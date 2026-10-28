"""XO-4, the Studio's own groovebox: four tracks on the box's beat grid, patterns A-H.

  DRUMS    the pads' kit (pads.py): a step holds pads 1-16, each hit with its level (NORM, GHOST, SOFT, HARD, as the
           pads' own sequencer) and ratchet (x1-x4: that many hits in the step); its hits go to the pad process,
           each with the time it's to be heard, sent LOOKAHEAD early so the pads never get one late
  SYNTH 1  an FM synth (xo4synth.py), rendered here: up to four notes a step (a chord)
  SYNTH 2  another, with its own patch (both through XO-4's own punch-in FX, padfx.py: the pads have theirs)
  MIDI     notes out through the MIDI routes (their source "XO4"), sent by the MIDI process when they're due

Each track has its own length (1-64 steps of a 16th), so tracks of different lengths drift and meet again; a
step: its notes, a velocity, a length in steps, and a nudge (in 64ths of a step, early or late of the grid).
Live REC: with REC on and playing, pads played (a tap, a note into the pads) go onto the drums' nearest step, at
the level they were hit; QUANT off keeps the nudge they were played with. The pattern playing changes on the next bar (16 steps) after
another is picked, for every track at once. SWING delays every second 16th, as the pads' sequencer does.

The process (XO4Process) renders BLOCK frames at a time into a virtual speaker whose other side is the source
"fm1-xo4" (XO-4 in the mixer, the meters, recordings), as the pads do. The app sends it the song and the patches;
the MIDI process sends it the grid; it sends the app the step playing, and the pads and MIDI their notes.
"""
import math
import os
import subprocess
import time

import xo4synth

TRACKS = ("DRUMS", "SYNTH 1", "SYNTH 2", "MIDI")
DRUMS, SYNTH1, SYNTH2, MIDI = range(4)
PATTERNS = tuple("ABCDEFGH")
NSTEP = 64
BAR = 16                                    # steps a bar: where a pattern change waits for
NOTES = 4                                   # notes a step at most (a chord)
GATE = 0.9                                  # a step's note ends at this share of its length (the next one clean)
LOOKAHEAD = 0.12                            # s: the drums' and MIDI's notes sent this far ahead of when they sound
BLOCK = 512
SOURCE, SINK = "fm1-xo4", "fm1-xo4-in"
SCALES = {"MAJOR": (0, 2, 4, 5, 7, 9, 11), "MINOR": (0, 2, 3, 5, 7, 8, 10), "DORIAN": (0, 2, 3, 5, 7, 9, 10),
          "MIXOLYD": (0, 2, 4, 5, 7, 9, 10), "PENTA": (0, 2, 4, 7, 9), "MIN PENTA": (0, 3, 5, 7, 10),
          "CHROMATIC": tuple(range(12))}         # the note keys on XO-4's screen offer these, from the root up
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
AUDITION = 0.4                              # s: a note tapped on the screen sounds this long
LEVELS = ("NORM", "GHOST", "SOFT", "HARD")  # a drum hit's level, as the pads' sequencer has it (pads.LEVELS)
LEVEL_VEL = (100, 42, 72, 127)              # ... its velocity
DRUM_GATE = 0.5                             # a drum hit's note-off at half its share of the step (the pads' GATE)
SYNTH_PATCHES = ({"ratio": 1.0, "index": 2.0, "mod_decay": 0.6, "attack": 0.005, "release": 0.3},   # keys
                 {"ratio": 0.5, "index": 4.0, "mod_decay": 0.15, "mod_sustain": 0.1, "sustain": 0.4,
                  "release": 0.08, "level": 0.3})                                                     # bass

SOUNDS = {                                  # the SOUND page's starting points: a whole patch each
    "KEYS": SYNTH_PATCHES[0],
    "BASS": SYNTH_PATCHES[1],
    "BELL": {"ratio": 3.5, "index": 3.0, "mod_decay": 1.5, "mod_sustain": 0.1, "attack": 0.002, "decay": 1.5,
             "sustain": 0.0, "release": 1.0, "level": 0.2},
    "PLUCK": {"ratio": 2.0, "index": 5.0, "mod_decay": 0.08, "mod_sustain": 0.0, "attack": 0.002, "decay": 0.3,
              "sustain": 0.0, "release": 0.15, "level": 0.25},
    "PAD": {"ratio": 1.0, "index": 1.0, "mod_decay": 3.0, "mod_sustain": 0.5, "attack": 0.5, "decay": 1.0,
            "sustain": 0.8, "release": 1.5, "level": 0.18},
    "LEAD": {"ratio": 1.0, "index": 3.5, "mod_decay": 0.6, "mod_sustain": 0.6, "attack": 0.01, "decay": 0.2,
             "sustain": 0.8, "release": 0.2, "level": 0.22},
}
# the SOUND page's settings: (patch key, its name there, the values - / + step through); RANGES: those that move
# by a step instead, (step, low, high)
RANGES = {"index": (0.25, 0.0, 12.0), "mod_sustain": (0.05, 0.0, 1.0), "sustain": (0.05, 0.0, 1.0),
          "level": (0.02, 0.0, 1.0)}
TIMES = (0.002, 0.005, 0.01, 0.02, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
SETTINGS = (("ratio", "RATIO", (0.25, 0.5, 0.75, 1.0, 1.41, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0,
                                11.0, 12.0, 14.0, 16.0)),
            ("index", "BRIGHT", None),
            ("mod_decay", "BR DECAY", TIMES),
            ("mod_sustain", "BR HOLD", None),
            ("attack", "ATTACK", (0.0,) + TIMES),
            ("decay", "DECAY", TIMES),
            ("sustain", "SUSTAIN", None),
            ("release", "RELEASE", TIMES),
            ("level", "LEVEL", None))


def step_setting(key, value, steps):
    """a SOUND setting moved steps along: through its list of values (from the nearest one), or by its step"""
    if key in RANGES:
        step, lo, hi = RANGES[key]
        return round(max(lo, min(hi, value + steps * step)), 3)
    values = next(v for k, _, v in SETTINGS if k == key)
    near = min(range(len(values)), key=lambda i: abs(values[i] - value))
    return values[max(0, min(len(values) - 1, near + steps))]


def setting_text(key, value):
    """how the SOUND page shows a value"""
    if key in ("mod_sustain", "sustain", "level"):
        return f"{round(value * 100)}%"
    if key in ("mod_decay", "attack", "decay", "release"):
        return f"{round(value * 1000)}MS" if value < 1 else f"{value:g}S"
    return f"{value:g}"


def np():
    import numpy
    return numpy


def empty_track():
    return {"len": 16, "steps": [None] * NSTEP}


def empty_song():
    """the song: patterns A-H (four tracks each), which plays, the synths' patches, the MIDI track's channel,
    swing, each track's level, and the key and scale the screen's note keys offer"""
    return {"patterns": {p: [empty_track() for _ in TRACKS] for p in PATTERNS}, "pattern": "A",
            "patches": [xo4synth.clean_patch(p) for p in SYNTH_PATCHES], "midi_channel": 0, "swing": 0,
            "levels": [1.0, 1.0, 1.0, 1.0], "root": 0, "scale": "MAJOR", "quant": True}


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


def vel_level(vel):
    """a velocity -> the level a drum hit records as (the pads' vel_level)"""
    return 1 if vel < 56 else 2 if vel < 88 else 0 if vel < 116 else 3


def clean_step(step, track):
    """a step from anywhere -> {"notes", "vel", "len", "nudge"} (drums also "levels" and "ratchets", one each
    note) or None (empty). Drums: pads 0-15; the rest: notes 0-127, at most NOTES; no repeats"""
    if not isinstance(step, dict):
        return None
    hi = 15 if track == DRUMS else 127
    notes, levels, ratchets = [], [], []
    given_levels = step.get("levels") if isinstance(step.get("levels"), list) else []
    given_ratchets = step.get("ratchets") if isinstance(step.get("ratchets"), list) else []
    for k, n in enumerate(step.get("notes") or []):
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if 0 <= n <= hi and n not in notes:
            notes.append(n)
            levels.append(clamp_int(given_levels[k] if k < len(given_levels) else 0, 0, 3, 0))
            ratchets.append(clamp_int(given_ratchets[k] if k < len(given_ratchets) else 1, 1, 4, 1))
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
    out = {"vel": vel, "len": length, "nudge": clamp_int(step.get("nudge", 0), -32, 31, 0)}
    if track != DRUMS:
        return dict(out, notes=sorted(notes[:NOTES]))
    order = sorted(range(len(notes)), key=lambda k: notes[k])
    return dict(out, notes=[notes[k] for k in order], levels=[levels[k] for k in order],
                ratchets=[ratchets[k] for k in order])


def clamp_int(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def clean_song(song):
    song = song if isinstance(song, dict) else {}
    out = empty_song()
    patterns = song.get("patterns") if isinstance(song.get("patterns"), dict) else {}
    for p in PATTERNS:
        tracks = patterns.get(p) if isinstance(patterns.get(p), list) else []
        for i, track in enumerate(tracks[:len(TRACKS)]):
            if not isinstance(track, dict):
                continue
            try:
                out["patterns"][p][i]["len"] = max(1, min(NSTEP, int(track.get("len", 16))))
            except (TypeError, ValueError):
                pass
            steps = track.get("steps") if isinstance(track.get("steps"), list) else []
            out["patterns"][p][i]["steps"] = [clean_step(s, i) for s in (steps + [None] * NSTEP)[:NSTEP]]
    if song.get("pattern") in PATTERNS:
        out["pattern"] = song["pattern"]
    patches = song.get("patches") if isinstance(song.get("patches"), list) else []
    for k, patch in enumerate(patches[:2]):
        if isinstance(patch, dict):
            out["patches"][k] = xo4synth.clean_patch(dict(SYNTH_PATCHES[k], **patch))
    out["patches"] = [xo4synth.clean_patch(p) for p in out["patches"]]
    if song.get("scale") in SCALES:
        out["scale"] = song["scale"]
    out["quant"] = bool(song.get("quant", True))
    for key, lo, hi in (("midi_channel", 0, 15), ("swing", 0, 100), ("root", 0, 11)):
        try:
            out[key] = max(lo, min(hi, int(song.get(key, out[key]))))
        except (TypeError, ValueError):
            pass
    for i, level in enumerate((song.get("levels") or [])[:4]):
        try:
            out["levels"][i] = max(0.0, min(2.0, float(level)))
        except (TypeError, ValueError):
            pass
    return out


# ---------------------------------------------------------------- the sequencer

class Lane:
    """a run through the steps for some of the tracks: the synths on the time they're rendered, the drums and
    MIDI LOOKAHEAD ahead of it. Each keeps its own place, so the two never wait for each other"""

    def __init__(self, tracks):
        self.tracks = tracks
        self.next = None                        # the absolute step (since tick 0) to fire next
        self.pending = []                       # (time, track, "on" / "off", note, velocity) not yet due
        self.held = set()                       # (track, note) sounding: let go when it stops
        self.skip = set()                       # (absolute step, pad): recorded live, already heard: not again


class Sequencer:
    """the four tracks on the beat grid (seconds a tick, tick 0's time, playing). due() hands out a lane's
    notes in a stretch of (heard) time, in order"""

    def __init__(self):
        self.grid = None
        self.now = Lane((SYNTH1, SYNTH2))
        self.ahead = Lane((DRUMS, MIDI))
        self.switches = {}                      # absolute step -> the pattern from there on
        self.queued = None                      # a pattern picked, waiting for the next bar
        self.step = None                        # the absolute step heard last (the playhead)
        self.rec = False                        # live REC: pads played go onto the drums' steps

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
            if i == DRUMS:                      # each hit its level, and its ratchets: its share of the step
                n = len(step["notes"])
                for pad, level, rat in zip(step["notes"], step.get("levels") or [0] * n, step.get("ratchets") or [1] * n):
                    if (a, pad) in lane.skip:
                        continue
                    for h in range(rat):
                        at = t + h * u / rat
                        lane.pending += [(at, i, "on", pad, LEVEL_VEL[level]),
                                         (at + max(0.01, u * DRUM_GATE / rat), i, "off", pad, 0)]
                continue
            off = t + max(0.01, step["len"] * u * GATE)
            for note in step["notes"]:
                lane.pending += [(t, i, "on", note, step["vel"]), (off, i, "off", note, 0)]
        lane.skip = {k for k in lane.skip if k[0] > a}

    def record(self, song, pad, vel, t):
        """live REC: a pad played at time t onto the drums' nearest step, at the level it was hit (QUANT off:
        with the nudge it was played at) -> True if the song changed"""
        if not (self.rec and self.playing()) or not 0 <= pad < 16:
            return False
        u = self.unit()
        a0 = round((t - self.grid[1]) / u)
        a = min((x for x in (a0 - 1, a0, a0 + 1) if x >= 0), key=lambda x: abs(t - self.time(song, x)), default=None)
        if a is None:
            return False
        track = song["patterns"][self.pattern_at(song, a)][DRUMS]
        idx = a % track["len"]
        step = track["steps"][idx] or {"notes": [], "vel": 100, "len": 1.0, "nudge": 0, "levels": [], "ratchets": []}
        n = len(step["notes"])
        hits = {p: (lv, r) for p, lv, r in zip(step["notes"], step.get("levels") or [0] * n,
                                               step.get("ratchets") or [1] * n) if p != pad}
        hits[pad] = (vel_level(vel), 1)
        step = dict(step, notes=sorted(hits), levels=[hits[n][0] for n in sorted(hits)],
                    ratchets=[hits[n][1] for n in sorted(hits)])
        if not song["quant"]:                   # QUANT off: where it was played, kept as the step's nudge
            step["nudge"] = max(-32, min(31, round((t - self.time(song, a)) / u * 64)))
        track["steps"][idx] = step
        if self.ahead.next is None or a >= self.ahead.next:
            self.ahead.skip.add((a, pad))       # heard as it was played: not again when its step comes
        return True


# ---------------------------------------------------------------- the engine

class Engine:
    """renders XO-4's synths and hands out the drums' and the MIDI track's notes; all on the process's thread"""

    def __init__(self, rate=48000):
        self.rate = rate
        self.song = empty_song()
        self.seq = Sequencer()
        self.synths = [xo4synth.Synth(rate, p) for p in self.song["patches"]]
        self.master = 1.0
        import padfx
        self.fx = padfx.PunchFX(rate)           # XO-4's own punch-in FX, on the synths (the pads have theirs)

    def set_song(self, song):
        """a new song (from the app): what plays and where it is carry on"""
        playing = self.song["pattern"]
        self.song = clean_song(song)
        if self.seq.switches:                   # (a change already waiting: the song's own pattern stays)
            self.song["pattern"] = playing
        for synth, patch in zip(self.synths, self.song["patches"]):
            synth.set_patch(patch)

    def render(self, n, t0=None):
        """the next n frames -> (float32 (n, 2), [the drums' and MIDI's notes LOOKAHEAD ahead]). t0: when the
        first frame is heard"""
        num = np()
        if t0 is None:
            events, ahead = [], []
        else:
            t1 = t0 + n / self.rate
            events = self.seq.due(self.song, self.seq.now, t0, t1)
            ahead = self.seq.due(self.song, self.seq.ahead, t0 + LOOKAHEAD, t1 + LOOKAHEAD)
        out, done = num.zeros((n, 2), dtype=num.float32), 0
        for at, track, kind, note, vel in events:
            frame = max(done, min(n, int(round((at - t0) * self.rate))))
            if frame > done:
                out[done:frame] = self.mix(frame - done)
                done = frame
            synth = self.synths[track - SYNTH1]
            synth.note_on(note, vel) if kind == "on" else synth.note_off(note)
        if done < n:
            out[done:] = self.mix(n - done)
        return self.fx.process(out, self.seq.grid, t0), ahead

    def mix(self, n):
        levels = self.song["levels"]
        return (self.synths[0].render(n) * levels[SYNTH1] + self.synths[1].render(n) * levels[SYNTH2]) * self.master

    def sounding(self):
        return [s.sounding() for s in self.synths]

    def played(self, pad, vel, t):
        """a pad played live (from the pad process) -> True if live REC put it on a step"""
        return self.seq.record(self.song, pad, vel, t)


def to_pcm(block):
    num = np()
    return (num.clip(block, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def drum_hits(notes, levels):
    """the drums' notes -> the pads' ("hits", [(time, "on" / "off", pad, velocity)])"""
    level = levels[DRUMS]
    return [(t, kind, note, max(1, min(127, round(vel * level))) if kind == "on" else 0)
            for t, track, kind, note, vel in notes if track == DRUMS]


def midi_notes(notes, channel, level):
    """the MIDI track's notes -> [(time, MIDI bytes)] for the MIDI process to send when they're due"""
    out = []
    for t, track, kind, note, vel in notes:
        if track != MIDI:
            continue
        if kind == "on":
            out.append((t, [0x90 | channel, note, max(1, min(127, round(vel * level)))]))
        else:
            out.append((t, [0x80 | channel, note, 0]))
    return out


# ---------------------------------------------------------------- the process

def run(app_conn, midi_conn, pads_conn, notes_conn, rate):
    """the XO-4 process: render into the virtual speaker SINK (its other side the SOURCE the box hears), take the
    app's and the MIDI process's messages between blocks, send the pads and the MIDI process their notes, tell
    the app the step playing"""
    import fcntl
    subprocess.run(["pkill", "-f", f"^pw-(loopback|cat) .*{SINK}"], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    loop = subprocess.Popen(
        ["pw-loopback", "--capture-props", f"media.class=Audio/Sink node.name={SINK} audio.position=[FL,FR] "
                                           "node.description=XO-4 priority.session=1",
         "--playback-props", f"media.class=Audio/Source node.name={SOURCE} audio.position=[FL,FR] "
                             "node.description=XO-4"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    cat = subprocess.Popen(
        ["pw-cat", "--playback", "--raw", "--target", SINK, "--rate", str(rate), "--channels", "2",
         "--format", "s16", "--latency", "10ms", "-P", "{ node.name = fm1-xo4-out node.dont-reconnect = true }",
         "-"],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:                                        # a small pipe: a block written is heard ~20 ms later
        fcntl.fcntl(cat.stdin.fileno(), 1031, 4096)                 # F_SETPIPE_SZ
    except OSError:
        pass
    engine, step_shown, pattern_shown = Engine(rate), None, None
    auditions = []                              # (when it ends, synth, note): notes tapped on the screen
    ahead = 1024 / rate + 0.010                 # as the pads: a block written now is heard after the pipe and pw-cat
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
                    elif msg[0] == "master":
                        engine.master = float(msg[1])
                    elif msg[0] == "fx":                  # ("fx", a punch-in FX 0-15, or None: let go)
                        engine.fx.press(msg[1])
                    elif msg[0] == "rec":                 # ("rec", on): live REC
                        engine.seq.rec = bool(msg[1])
                    elif msg[0] == "played":              # ("played", pad, velocity, time): a pad played live
                        if engine.played(int(msg[1]), int(msg[2]), float(msg[3])):
                            app_conn.send(("song", engine.song))
                    elif msg[0] == "audition":          # ("audition", track, [notes], velocity): heard now
                        if msg[1] in (SYNTH1, SYNTH2):
                            synth = engine.synths[msg[1] - SYNTH1]
                            for note in msg[2]:
                                synth.note_on(note, msg[3])
                                auditions.append((time.monotonic() + AUDITION, synth, note))
            now = time.monotonic()
            for end in [a for a in auditions if a[0] <= now]:
                auditions.remove(end)
                end[1].note_off(end[2])
            heard = time.monotonic() + ahead
            if base is None or abs(base + frames / rate - heard) > 0.015:
                base, frames = heard, 0
            block, notes = engine.render(BLOCK, base + frames / rate)
            if notes:
                hits = drum_hits(notes, engine.song["levels"])
                if hits and pads_conn is not None:
                    pads_conn.send(("hits", hits))
                out = midi_notes(notes, engine.song["midi_channel"], engine.song["levels"][MIDI])
                if out and notes_conn is not None:
                    notes_conn.send(("xo4", out))
            cat.stdin.write(to_pcm(block))     # blocks while PipeWire is full
            frames += BLOCK
            shown = (engine.seq.step, engine.song["pattern"], engine.seq.queued)
            if shown != step_shown:
                step_shown = shown
                app_conn.send(("step",) + shown)
            if engine.song["pattern"] != pattern_shown:
                pattern_shown = engine.song["pattern"]
                app_conn.send(("pattern", pattern_shown))
    except (BrokenPipeError, OSError):
        pass
    finally:
        for proc in (cat, loop):
            proc.terminate()


class XO4Process:
    """XO-4 in a process of its own; the app's side. midi_conn: the end the MIDI process sends the grid to;
    notes_in: the end the MIDI process reads the MIDI track's notes from; pads_conn: the pads' xo4_conn (the
    drums' hits)"""

    def __init__(self, rate=48000, pads_conn=None):
        import multiprocessing
        ctx = multiprocessing.get_context("fork")
        self.conn, child = ctx.Pipe()
        self.grid_in, self.midi_conn = ctx.Pipe(duplex=False)        # the MIDI process writes midi_conn
        self.notes_in, notes_w = ctx.Pipe(duplex=False)              # XO-4 writes, the MIDI process reads
        self.proc = ctx.Process(target=run, args=(child, self.grid_in, pads_conn, notes_w, rate), daemon=True,
                                name="fm1-xo4")
        self.step = self.pattern = self.queued = None
        self.on_step = None
        self.on_song = None                         # called with the song live REC changed (from this thread)

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
            elif msg[0] == "song" and self.on_song:   # live REC changed the song
                self.on_song(msg[1])

    def send(self, *msg):
        try:
            self.conn.send(msg)
        except (BrokenPipeError, OSError):
            pass
