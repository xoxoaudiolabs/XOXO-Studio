"""Tests for the MIDI process's own logic (blemidi.py): BLE MIDI packets, clock tempo, the box as clock master.
No Bluetooth or USB gear needed (needs mido).

  python tests/test_midi.py
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fm1-bt-bridge"))

import blemidi  # noqa: E402

TICK_120 = 60 / (120 * 24)


class FakeControllers:
    """the USB MIDI devices (the routes' USB): what's sent to them"""
    def __init__(self):
        self.sent = []

    def send_messages(self, messages):
        self.sent.extend(messages)

    def send_to(self, name, messages):
        self.sent.extend(messages)

    def names(self):
        return ["SMK-37+VA"]

    def poll(self):
        pass


class FakePads:
    """the Studio's sampler (the routes' SMP): the notes it's sent, as bytes"""
    def __init__(self):
        self.sent = []

    def send(self, msg):
        if msg[0] == "midi":
            self.sent.extend(bytes(m) for m in msg[1])


def make_bridge():
    bridge = blemidi.MidiBridge(pads=FakePads())
    bridge.xo4_in = True                       # XO-4's MIDI IN on: the routes' SMP column reaches the pads
    bridge.controllers = FakeControllers()
    bridge.to_ble_sent = []
    bridge.to_ble = bridge.to_ble_sent.append
    bridge.bluez = {"idle_add": lambda f: f(), "connected_peers": lambda: []}
    return bridge


def test_midi_recording():
    """while a take records, what's played in is logged a track a source (every channel; not clock, not SysEx)
    and written as a .mid whose time 0 is the take's first frame"""
    import tempfile
    import mido
    bridge = make_bridge()
    bridge.split = True
    bridge.start_midi_log()
    t0 = time.monotonic()
    bridge.from_ble(ble_packet([0x90, 60, 100]), "/dev/keys")
    bridge.from_ble(ble_packet([0xBF, 102, 127]), "/dev/keys")         # channel 16: logged like any other
    bridge.from_ble(ble_packet([0xF8]), "/dev/keys")                   # clock: left out (the file has the tempo)
    bridge.from_controllers([0x90, 64, 90], name="SMK-37+VA")
    log = bridge.stop_midi_log()
    bridge.from_ble(ble_packet([0x80, 60, 0]), "/dev/keys")            # after the take: not logged
    assert [(s, list(m)) for _, s, m in log] == [("BT", [0x90, 60, 100]), ("BT", [0xBF, 102, 127]),
                                                 ("U:SMK-37+VA", [0x90, 64, 90])]
    shifted = [(t0 + 0.5, "BT", bytes([0x90, 60, 100])), (t0 + 1.0, "BT", bytes([0x80, 60, 0])),
               (t0 + 1.25, log[-1][1], bytes([0x90, 64, 90]))]      # (its note never let go)
    path = Path(tempfile.mkdtemp()) / "take.mid"
    assert blemidi.write_midi(shifted, path, t0, 120.0, bridge.source_label)
    mid = mido.MidiFile(str(path))
    assert mid.type == 1 and mid.ticks_per_beat == 480 and len(mid.tracks) == 3
    names = [next((m.name for m in tr if m.type == "track_name"), None) for tr in mid.tracks[1:]]
    assert names[0] == "Bluetooth MIDI" and names[1].startswith("SMK-37")
    ticks = []
    for tr in mid.tracks[1:]:
        at = 0
        for m in tr:
            at += m.time
            if not m.is_meta:
                ticks.append((m.type, m.note, at))
    assert ("note_on", 60, 480) in ticks and ("note_off", 60, 960) in ticks     # 0.5 s, 1 s at 120 BPM
    assert ("note_on", 64, 1200) in ticks and ("note_off", 64, 1200) in ticks   # let go at its end
    assert not blemidi.write_midi([], Path(tempfile.mkdtemp()) / "none.mid", t0, 120.0)   # nothing: no file


def test_peer_name_after_address():
    """BlueZ often has only the address when a keyboard connects; the name shows up once it has it."""
    bridge = make_bridge()
    names, timers = ["28-9E-F6-E8-D8-53", "28-9E-F6-E8-D8-53", "SMK-37+VA_BLE"], []
    bridge.bluez.update(connected_peers=lambda: [("/org/bluez/hci0/dev_28", names.pop(0), "28:9E:F6:E8:D8:53")],
                        timeout_add_seconds=lambda s, f: timers.append(f))
    bridge.find_names()
    assert bridge.peer == "28-9E-F6-E8-D8-53" and len(timers) == 1
    bridge.find_names()                                  # a second look doesn't start a second timer
    assert len(timers) == 1
    assert timers[0]() is False and bridge.peer == "SMK-37+VA_BLE"


def test_several_bluetooth_devices():
    """Phones connect to the box and the box connects to keyboards, several at once: each sender keeps its own
    running status, and what goes out to BT reaches every one of them."""
    bridge = blemidi.MidiBridge(pads=FakePads())
    bridge.xo4_in = True
    notified, written = [], []
    connected = [("/hci0/dev_AA", "iPad", "AA:00:00:00:00:01"), ("/hci0/dev_BB", "microKEY", "BB:00:00:00:00:02")]
    bridge.bluez = {"idle_add": lambda f: f(), "connected_peers": lambda: connected,
                    "notify": notified.append, "write": lambda path, p: written.append((path, p))}
    bridge.ble_saved = [["BB:00:00:00:00:02", "microKEY"]]
    bridge.find_names()
    assert bridge.peers == {"/hci0/dev_AA": "iPad"}      # a saved keyboard isn't a central, even before it's linked
    bridge.keyboard_linked("/hci0/dev_BB", "BB:00:00:00:00:02", "microKEY")
    assert bridge.peer == "microKEY + iPad" and bridge.ble_note[1] == "microKEY connected"
    assert bridge.keyboard_list() == [["BB:00:00:00:00:02", "microKEY", True]]
    # two senders, each in running status: their bytes mustn't mix
    bridge.from_ble(bytes([0x80, 0x80, 0x90, 0x3C, 0x40]), "/hci0/dev_AA")
    bridge.from_ble(bytes([0x80, 0x80, 0x91, 0x30, 0x40]), "/hci0/dev_BB")
    bridge.from_ble(bytes([0x80, 0x80, 0x3E, 0x40]), "/hci0/dev_AA")
    assert bridge.pads.sent == [bytes([0x90, 0x3C, 0x40]), bytes([0x91, 0x30, 0x40]), bytes([0x90, 0x3E, 0x40])]
    bridge.to_ble(bytes([0xF8]))
    assert len(notified) == 1 and written == [("/hci0/dev_BB", notified[0])]
    bridge.keyboard_gone("/hci0/dev_BB")
    assert bridge.peer == "iPad" and bridge.keyboard_list() == [["BB:00:00:00:00:02", "microKEY", False]]
    bridge.to_ble(bytes([0xF8]))
    assert len(notified) == 2 and len(written) == 1      # gone: nothing written to it


def test_saved_keyboards_newest_first():
    bridge = make_bridge()
    for i in range(blemidi.MAX_KEYBOARDS + 1):
        bridge.keyboard_linked(f"/hci0/dev_{i}", f"00:00:00:00:00:0{i}", f"Keys {i}")
    names = [n for _, n in bridge.ble_saved]
    assert names[0] == f"Keys {blemidi.MAX_KEYBOARDS}" and len(names) == blemidi.MAX_KEYBOARDS
    bridge.keyboard_linked("/hci0/dev_2", "00:00:00:00:00:02", "Keys 2")      # again: moved up, not doubled
    assert [n for _, n in bridge.ble_saved].count("Keys 2") == 1 and bridge.ble_saved[0][1] == "Keys 2"


def ble_packet(*messages):
    return blemidi.encode([bytes(m) for m in messages], 1000)[0]


def test_packets():
    msgs = [b"\x90\x3c\x64", b"\xf0\x7d\x01\x02\xf7", b"\xf8"]
    packets = blemidi.encode(msgs, 1234)
    stream = blemidi.MidiStream()
    out = []
    for p in packets:
        out += stream.feed(blemidi.strip_timestamps(p))
    assert out == msgs


def test_clock_watch():
    watch = blemidi.ClockWatch()
    t = 100.0
    for i in range(30):
        watch.message(blemidi.CLOCK, t + i * TICK_120)
    now = t + 29 * TICK_120
    assert abs(watch.bpm(now) - 120) < 0.01
    assert watch.bpm(now + 0.6) is None                 # clock stopped
    watch.message(blemidi.START, now)
    assert watch.playing
    watch.message(blemidi.STOP, now)
    assert not watch.playing


def test_follow_passes_clock_box_keeps_it():
    bridge = make_bridge()
    note, clock, start = b"\x90\x3c\x64", b"\xf8", b"\xfa"
    bridge.from_ble(ble_packet(note, clock, start), "/dev/keys")
    assert bridge.pads.sent == [note, clock, start]     # follow: everything through
    assert bridge.watch["BT"].playing
    bridge.pads.sent.clear()
    bridge.clock_mode = "box"
    bridge.from_ble(ble_packet(note, clock, b"\xfc"), "/dev/keys")
    assert bridge.pads.sent == [note]                    # box: its own clock only
    routes = blemidi.default_routes()
    routes["USB>BT"]["on"] = True
    bridge.set_routes(routes)
    bridge.from_controllers(clock)
    bridge.from_controllers(note)
    assert bridge.to_ble_sent == [note]


def test_running_status_across_packets():
    bridge = make_bridge()
    first = bytes([0x80, 0x80, 0x90, 0x3C, 0x64])        # header, timestamp, note on
    second = bytes([0x80, 0x81, 0x40, 0x64])            # header, timestamp, running-status data
    bridge.from_ble(first, "/dev/keys")
    bridge.from_ble(second, "/dev/keys")
    assert bridge.pads.sent == [b"\x90\x3c\x64", b"\x90\x40\x64"]


def test_box_clock_timing():
    bridge = make_bridge()
    times = []
    bridge.send_all = lambda m: times.append((time.monotonic(), m))
    bridge.clock_mode, bridge.bpm = "box", 300.0
    threading.Thread(target=bridge.clock_loop, daemon=True).start()
    time.sleep(1.0)
    bridge.clock_mode = "follow"
    ticks = [t for t, m in times if m == b"\xf8"]
    assert 110 <= len(ticks) <= 125, len(ticks)          # 300 BPM: 120 ticks a second
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert abs(sum(gaps) / len(gaps) - 60 / (300 * 24)) < 0.0005
    status = bridge.clock_status(time.monotonic())
    assert status is None or status["source"] != "box"   # back to following
    bridge.clock_mode = "box"
    status = bridge.clock_status(time.monotonic())
    assert {k: status[k] for k in ("bpm", "source", "playing")} == {"bpm": 300, "source": "box", "playing": False}
    assert status["bar"] and time.monotonic() - status["bar"] < 1.0       # a bar began in the last second
    bridge.clock_mode = "follow"


def test_transport():
    bridge = make_bridge()
    bridge.transport("start")
    assert bridge.to_ble_sent == [b"\xfa"] and bridge.playing
    assert bridge.controllers.sent == [] and bridge.pads.sent == []    # Box > USB, Box > SMP off at first
    bridge.transport("stop")
    assert bridge.to_ble_sent[-1] == b"\xfc" and not bridge.playing


def test_route_passes_everything_by_default():
    route = blemidi.Route()
    for m in (b"\x90\x3c\x64", b"\x80\x3c\x00", b"\xb3\x07\x64", b"\xe0\x00\x40", b"\xf8", b"\xf0\x01\xf7",
              b"\xd0\x30"):
        assert route.apply(m) == m, m


def test_route_channels_transpose_velocity():
    route = blemidi.Route({"channels": 4, "transpose": 12, "velocity": "fixed", "fixed": 90})
    assert route.apply(b"\x91\x3c\x20") == bytes([0x94, 0x48, 90])       # ch 2 -> 5, +12, fixed 90
    assert route.apply(b"\x81\x3c\x00") == bytes([0x84, 0x48, 0x00])
    assert route.apply(b"\xb1\x07\x64") == b"\xb4\x07\x64"               # CC follows the channel
    assert route.apply(b"\x90\x7a\x40") is None                         # 122 + 12: off the keyboard
    table = list(range(16))
    table[0], table[1] = 9, None
    route = blemidi.Route({"channels": table})
    assert route.apply(b"\x90\x3c\x40")[0] == 0x99 and route.apply(b"\x91\x3c\x40") is None
    soft, hard = blemidi.Route({"velocity": "soft"}), blemidi.Route({"velocity": "hard"})
    assert soft.apply(b"\x90\x3c\x20")[2] > 0x20 > hard.apply(b"\x90\x3c\x20")[2] >= 1
    assert soft.apply(b"\x90\x3d\x7f")[2] == 127


def test_route_drops():
    route = blemidi.Route({"drop_clock": True, "drop_aftertouch": True, "drop_bend": True})
    for m in (b"\xf8", b"\xfa", b"\xfc", b"\xd0\x30", b"\xa0\x3c\x30", b"\xe0\x00\x40"):
        assert route.apply(m) is None, m
    assert route.apply(b"\x90\x3c\x40") and route.apply(b"\xf0\x01\xf7")


def test_no_stuck_notes():
    route = blemidi.Route({"transpose": 5})
    assert route.apply(b"\x90\x3c\x40") == b"\x90\x41\x40"
    route.update({"transpose": -7, "channels": 3})                      # changed while the key is held
    assert route.apply(b"\x80\x3c\x00") == b"\x80\x41\x00"             # still stops the note it started
    route.apply(b"\x90\x3c\x40")                                       # now: ch 4, 60 - 7 = 53
    route.update({"on": False})                                         # route switched off mid-note
    assert route.apply(b"\x90\x3c\x00") == b"\x93\x35\x00"             # the note-off still gets out
    assert route.apply(b"\x90\x3e\x40") is None                         # new notes don't


def test_bridge_uses_the_matrix():
    bridge = make_bridge()
    routes = blemidi.default_routes()
    routes["BT>SMP"]["transpose"] = 2
    routes["BT>USB"]["on"] = True
    routes["Box>BT"]["on"] = False
    routes["Box>USB"]["on"] = True
    bridge.set_routes(routes)
    bridge.from_ble(ble_packet(b"\x90\x3c\x40"), "/dev/keys")
    assert bridge.pads.sent == [b"\x90\x3e\x40"] and bridge.controllers.sent == [b"\x90\x3c\x40"]
    bridge.from_controllers(b"\x90\x3c\x40")
    assert bridge.to_ble_sent == []                                     # USB > BT off
    bridge.transport("start")
    assert bridge.controllers.sent[-1] == b"\xfa" and bridge.to_ble_sent == []  # Box > USB on, Box > BT off


def test_bars_follow_start():
    watch = blemidi.ClockWatch()
    t = 100.0
    watch.message(blemidi.START, t)
    for i in range(200):                                # two bars and a bit
        watch.message(blemidi.CLOCK, t + i * TICK_120)
    now = t + 199 * TICK_120
    assert abs(watch.bar(now) - (t + 192 * TICK_120)) < 1e-6   # bar 3 began at tick 192
    watch.message(blemidi.START, t + 5)
    for i in range(20):
        watch.message(blemidi.CLOCK, t + 5 + i * TICK_120)
    assert abs(watch.bar(t + 5.4) - (t + 5)) < 1e-6     # Start: tick 0 is beat 1 again


def test_bunched_bluetooth_ticks():
    """ticks delivered in radio packets every 7.5 ms (bunched, late by up to a packet): the fitted grid
    stays within a millisecond or two, where single arrival times are off by up to 7.5 ms"""
    import random
    rng = random.Random(1)
    watch = blemidi.ClockWatch()
    period, t0 = 60 / (96.4 * 24), 50.0
    for i in range(300):
        sent = t0 + i * period
        arrived = (int(sent / 0.0075) + 1) * 0.0075 + rng.uniform(0, 0.002)   # the next connection event
        watch.message(blemidi.CLOCK, arrived)
    now = t0 + 299 * period + 0.01
    assert abs(watch.bpm(now) - 96.4) < 0.3, watch.bpm(now)
    true_bar = t0 + period * 96 * (299 // 96) + 0.0075 / 2 + 0.001   # plus the average delivery delay
    assert abs(watch.bar(now) - true_bar) < 0.003, watch.bar(now) - true_bar


def test_chord_memory():
    route = blemidi.Route({"chord_on": True, "chord": "maj"})
    assert route.apply_all(b"\x90\x3c\x50") == [b"\x90\x3c\x50", b"\x90\x40\x50", b"\x90\x43\x50"]
    route.update({"chord_on": True, "chord": "m7"})                     # changed while the key is held
    assert route.apply_all(b"\x80\x3c\x00") == [b"\x80\x3c\x00", b"\x80\x40\x00", b"\x80\x43\x00"]
    assert len(blemidi.Route({"chord_on": True, "chord": "oct", "transpose": 120}).apply_all(b"\x90\x02\x50")) == 1
    assert blemidi.Route({"chord": "maj"}).apply_all(b"\x90\x3c\x50") == [b"\x90\x3c\x50"]   # chord off: one note
    legacy = blemidi.Route({"chord": "off", "arp": "off"})                # saved before the on/off switches
    assert legacy.s["chord"] == "maj" and legacy.s["arp"] == "up" and not legacy.arp_active()


def play(route, ticks):
    """the notes the arp starts over `ticks` clock ticks, and every message"""
    messages = [m for _ in range(ticks) for m in route.tick()]
    return [m[1] for m in messages if m[0] & 0xF0 == 0x90], messages


def test_arpeggiator():
    route = blemidi.Route({"arp_on": True, "arp": "up", "arp_rate": "1/16"})
    for note in (0x43, 0x3C, 0x40):                                     # G, C, E: played out of order
        assert route.apply_all(bytes([0x90, note, 0x64])) == []        # held, not played: the arp plays them
    notes, messages = play(route, 36)                                   # 36 ticks of 1/16: 6 steps
    assert notes == [0x3C, 0x40, 0x43, 0x3C, 0x40, 0x43]
    ons = [i for i, m in enumerate(messages) if m[0] == 0x90]
    assert all(messages[i + 1][0] == 0x80 for i in ons[:-1])            # each note ends before the next
    for pattern, expected in (("down", [0x43, 0x40, 0x3C]), ("updown", [0x3C, 0x40, 0x43, 0x40]),
                              ("played", [0x43, 0x3C, 0x40])):
        route.update({"arp_on": True, "arp": pattern, "arp_rate": "1/16"})
        for note in (0x43, 0x3C, 0x40):
            route.apply_all(bytes([0x90, note, 0x64]))
        route.restart()
        assert play(route, 6 * len(expected))[0] == expected, pattern
    route.update({"arp_on": False})                                     # lets go of everything
    route.update({"arp_on": True, "arp": "up", "arp_rate": "1/4", "arp_octaves": 2, "chord_on": True, "chord": "5th"})
    route.apply_all(b"\x90\x30\x64")                                   # one key, a fifth, two octaves
    route.restart()
    assert play(route, 24 * 4)[0] == [0x30, 0x37, 0x3C, 0x43]
    # letting go stops the note; switching the arp off mid-note stops it too
    route.restart()
    route.tick()
    assert route.apply_all(b"\x80\x30\x00") == [bytes([0x80, 0x30, 0])]
    route.apply_all(b"\x90\x30\x64")
    route.restart()
    route.tick()
    assert route.update({"arp_on": False, "chord_on": True, "chord": "5th"}) == [bytes([0x80, 0x30, 0])]


def test_arp_keeps_time_without_a_clock():
    bridge = make_bridge()
    routes = blemidi.default_routes()
    routes["BT>SMP"].update(arp_on=True, arp="up", arp_rate="1/16")
    bridge.set_routes(routes)
    bridge.bpm = 120.0                                                  # 1/16 at 120 BPM: every 125 ms
    bridge.from_ble(ble_packet(b"\x90\x3c\x64", b"\x90\x40\x64"), "/dev/keys")
    assert bridge.pads.sent == []
    threading.Thread(target=bridge.clock_loop, daemon=True).start()
    time.sleep(0.6)
    ons = [m for m in bridge.pads.sent if m[0] == 0x90]
    assert 4 <= len(ons) <= 6 and [m[1] for m in ons[:3]] == [0x3C, 0x40, 0x3C], ons
    assert b"\xf8" not in bridge.pads.sent                              # its own ticks: no clock sent
    bridge.set_routes(blemidi.default_routes())                          # arp off: the loop goes quiet


def test_notes_for_the_midi_meter():
    bridge = make_bridge()
    bridge.from_ble(ble_packet(b"\x90\x3c\x40", b"\x90\x40\x40", b"\x99\x24\x7f"), "/dev/keys")
    bridge.from_controllers(b"\x92\x43\x50")                          # a USB keyboard: any source counts
    notes, chans = bridge.notes_status(time.monotonic())
    assert notes == [0x24, 0x3C, 0x40, 0x43] and chans == (1 << 0) | (1 << 9) | (1 << 2)
    bridge.from_ble(ble_packet(b"\x80\x3c\x00", b"\x90\x40\x00"), "/dev/keys")
    notes, _ = bridge.notes_status(time.monotonic())
    assert notes == [0x24, 0x43]
    notes, chans = bridge.notes_status(time.monotonic() + 31)          # no note-off for 30 s: forgotten
    assert notes == [] and chans == 0


PORTS = ["Midi Through:Midi Through Port-0 14:0", "EP-136:EP-136 MIDI 1 16:0", "SMK-37+VA:SMK-37+VA MIDI 1 20:0",
         "RtMidiIn Client:RtMidiIn Client 129:0", "AA:BB:CC:DD:EE:FF:Bluetooth 128:0"]


def test_usb_midi_devices():
    """every USB MIDI device is taken (a client's first port), the system's own ports and Bluetooth links aren't"""
    controllers = blemidi.UsbControllers(lambda message, name=None: None)
    assert controllers.wanted(PORTS) == {"EP-136": "EP-136:EP-136 MIDI 1 16:0",
                                         "SMK-37+VA": "SMK-37+VA:SMK-37+VA MIDI 1 20:0"}


def test_usb_keys_play_the_pads():
    bridge = make_bridge()
    bridge.from_controllers(b"\x90\x3c\x40")
    assert bridge.pads.sent == [b"\x90\x3c\x40"]                       # USB > SMP on at first
    assert bridge.to_ble_sent == []                                    # USB > BT off at first
    bridge.from_ble(ble_packet(b"\x90\x31\x40"), "/dev/keys")
    assert bridge.controllers.sent == []                               # nothing to the keyboard at first
    routes = blemidi.default_routes()
    routes["USB>SMP"]["transpose"] = 12
    routes["BT>USB"]["on"] = True
    bridge.set_routes(routes)
    bridge.from_controllers(b"\x90\x3c\x40")
    assert bridge.pads.sent[-1] == b"\x90\x48\x40"
    bridge.from_ble(ble_packet(b"\x90\x30\x40"), "/dev/keys")
    assert bridge.controllers.sent == [b"\x90\x30\x40"]
    bridge.enabled = False                                             # BLE MIDI off: USB keys still play
    bridge.from_controllers(b"\x90\x41\x40")
    assert bridge.pads.sent[-1] == b"\x90\x4d\x40"
    assert {k for k, r in blemidi.default_routes().items() if not r["on"]} == set(blemidi.OFF_AT_FIRST)


def test_xo4_midi_in_off():
    """XO-4's MIDI IN off (as it starts): a synth's notes on the routes don't play the pads; real-time still does"""
    assert blemidi.MidiBridge(pads=FakePads()).xo4_in is False
    bridge = make_bridge()
    bridge.xo4_in = False
    bridge.from_controllers(b"\x90\x3c\x40")
    bridge.deliver("USB>SMP", [b"\xf8", b"\x80\x3c\x00"])
    assert bridge.pads.sent == [b"\xf8"]
    bridge.xo4_in = True
    bridge.from_controllers(b"\x90\x3c\x40")
    assert bridge.pads.sent == [b"\xf8", b"\x90\x3c\x40"]


def test_a_computer_on_usb_c():
    """a Pi 4 Studio as a computer's USB MIDI device (the f_midi gadget): one more device, named COMPUTER"""
    controllers = blemidi.UsbControllers(lambda message, name=None: None)
    assert controllers.wanted(["f_midi:f_midi 24:0", "EP-136:EP-136 MIDI 1 16:0"]) == {
        "COMPUTER": "f_midi:f_midi 24:0", "EP-136": "EP-136:EP-136 MIDI 1 16:0"}


def test_plugin_names_midi_devices():
    """a plug-in's names (the FM-1 Companion's): two FM-1s are FM-1 A and FM-1 B, the same in and out"""
    controllers = blemidi.UsbControllers(lambda message, name=None: None)
    controllers.rules = [["^(felucca|sloop)", "FM-1 {n}"]]
    assert controllers.names() == []                   # (the rules beside it: the devices' list still works)
    ports = ["Felucca:Felucca MIDI 1 24:0", "Felucca:Felucca MIDI 1 28:0", "EP-136:EP-136 MIDI 1 16:0"]
    want = {"FM-1 A": ports[0], "FM-1 B": ports[1], "EP-136": ports[2]}
    assert controllers.wanted(ports) == want and controllers.wanted(list(reversed(ports))) == want


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
