"""Network MIDI (RTP-MIDI): packets both ways, a session started from a 'computer' on this machine over UDP, and
the Mackie Control state a DAW sends. No network beyond localhost needed."""

import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fm1-bt-bridge"))

import netmidi  # noqa: E402


def test_packets():
    msgs = [b"\x90\x3c\x64", b"\xb0\x07\x50", b"\xf8", b"\xf0\x7d\x01\x02\xf7"]
    packet = netmidi.encode(msgs, 7, 0x1234)
    assert packet[:2] == b"\x80\x61" and struct.unpack(">H", packet[2:4])[0] == 7
    assert netmidi.decode(packet) == msgs
    long = [bytes([0x90, n, 100]) for n in range(10)]               # over 15 bytes: the long header
    assert netmidi.decode(netmidi.encode(long, 1, 1)) == long
    assert netmidi.encode([], 1, 1) is None
    # what a Mac sends: running status, a delta time before the first (Z), the journal flag (J) after
    body = bytes([0x90, 0x3c, 0x64, 0x00, 0x3e, 0x64, 0x00, 0xc0, 0x05])
    head = struct.pack(">BBHII", 0x80, 0x61, 1, 0, 9)
    assert netmidi.decode(head + bytes([0x60 | len(body) + 1, 0x00]) + body + b"\x20\x00") == [
        b"\x90\x3c\x64", b"\x90\x3e\x64", b"\xc0\x05"]
    assert netmidi.decode(b"\xff\xffIN") == []                      # a session command: not MIDI


def test_session(capsys):
    got = []
    session = netmidi.Session("FM-1 Companion", 15004, got.append)
    assert session.start()
    mac = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    mac_data = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    mac.settimeout(2)
    mac_data.settimeout(2)
    invite = b"\xff\xffIN" + struct.pack(">III", 2, 0xABCD, 0x5151) + b"Pat's Mac\0"
    mac.sendto(invite, ("127.0.0.1", 15004))
    reply, _ = mac.recvfrom(256)
    assert reply[:4] == b"\xff\xffOK" and struct.unpack(">I", reply[8:12])[0] == 0xABCD
    assert reply[16:].split(b"\0")[0] == b"FM-1 Companion"
    mac_data.sendto(invite, ("127.0.0.1", 15005))
    assert mac_data.recvfrom(256)[0][:4] == b"\xff\xffOK"
    time.sleep(0.05)
    assert session.names() == ["Pat's Mac"]
    mac_data.sendto(b"\xff\xffCK" + struct.pack(">IB3xQQQ", 0x5151, 0, 1000, 0, 0), ("127.0.0.1", 15005))
    ck, _ = mac_data.recvfrom(256)
    count, t1, t2 = struct.unpack(">B3xQQ", ck[8:28])
    assert ck[:4] == b"\xff\xffCK" and count == 1 and t1 == 1000 and t2 > 0
    mac_data.sendto(netmidi.encode([b"\x90\x40\x70"], 1, 0x5151), ("127.0.0.1", 15005))
    time.sleep(0.1)
    assert got == [b"\x90\x40\x70"]                                 # the DAW's note, through to the box
    session.send([b"\x80\x40\x00"])
    assert netmidi.decode(mac_data.recvfrom(256)[0]) == [b"\x80\x40\x00"]   # and the box's back
    mac.sendto(b"\xff\xffBY" + struct.pack(">III", 2, 0xABCD, 0x5151), ("127.0.0.1", 15004))
    time.sleep(0.1)
    assert session.names() == []
    log = capsys.readouterr().err                                    # the journal: linked once, then left
    assert "Pat's Mac linked from 127.0.0.1" in log and "Pat's Mac left (BY)" in log and "linked again" not in log



def test_a_pocket_forgotten_sooner(capsys):
    """a peer gone without BY: a computer forgotten after 90 s, a Pocket (syncing every 10 s) after 25 s, and the
    journal told"""
    import time
    s = netmidi.Session("XOXO Studio", 0, lambda m: None)
    now = time.monotonic()
    s.peers = {1: {"name": "Mac", "data": ("a", 1), "seen": now - 30},
               2: {"name": "FM-1 Companion Pocket", "data": ("b", 1), "seen": now - 30}}
    s.expire()
    assert s.names() == ["Mac"]
    assert "FM-1 Companion Pocket forgotten: no sync for 30 s" in capsys.readouterr().err


def test_follow_studio_names():
    """Follow Studio: the leader takes a following Studio as it takes a Pocket; a Studio finds the others, not
    itself nor one that's following a Studio itself"""
    assert netmidi.linked_box("FM-1 Companion Pocket") and netmidi.linked_box("XOXO Studio Link on studio2")
    assert not netmidi.linked_box("Pat's Mac") and not netmidi.linked_box("XOXO Studio")
    assert netmidi.follow_name("studio2") == "XOXO Studio Link on studio2"
    assert not netmidi.is_studio("XOXO Studio Link on studio2._apple-midi._udp.local")
    found = lambda: [("XOXO Studio on Studio1", "10.0.0.1", 5004), ("XOXO Studio on studio2", "10.0.0.2", 5004),  # noqa
                     ("XOXO Studio on studio3", "10.0.0.3", 5004)]
    find = netmidi.other_studios(found, host="studio2", following=lambda address: address == "10.0.0.3")
    assert find() == [("XOXO Studio on Studio1", "10.0.0.1", 5004)]



def test_a_pocket_turned_away(capsys):
    """a Studio following another turns a Pocket's invitation down (NO), so the Pocket links to the one leading"""
    session = netmidi.Session("XOXO Studio", 15008, lambda m, p=None: None, by_peer=True)
    session.refuse = lambda name: "Pocket" in name
    assert session.start()
    pocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    pocket.settimeout(2)
    invite = b"\xff\xffIN" + struct.pack(">III", 2, 0x1234, 0x77) + b"FM-1 Companion Pocket\0"
    pocket.sendto(invite, ("127.0.0.1", 15009))
    reply = pocket.recvfrom(256)[0]
    assert reply[:4] == b"\xff\xffNO" and struct.unpack(">I", reply[8:12])[0] == 0x1234
    assert session.names() == [] and "FM-1 Companion Pocket turned away" in capsys.readouterr().err


def test_following_sends_no_clock_back():
    """a Studio following another sends it notes (NET), never clock or start / stop: the other leads"""
    import blemidi

    class Link:
        def __init__(self):
            self.sent = []

        def send(self, messages):
            self.sent.append(messages)

        def names(self):
            return ["XOXO Studio"]

    bridge = blemidi.MidiBridge.__new__(blemidi.MidiBridge)
    bridge.net, bridge.follow = None, Link()
    bridge.pocket_fm1s = lambda: {}
    bridge.deliver("BT>NET", [b"\xf8", b"\x90\x3c\x64", b"\xfa"])
    assert bridge.follow.sent == [[b"\x90\x3c\x64"]] and bridge.leader() == "XOXO Studio"
    bridge.deliver("Box>NET", [b"\xf8", b"\xfc"])
    assert len(bridge.follow.sent) == 1


def test_the_leaders_clock_out_the_box_routes():
    """a Studio following another: the leader's clock and Start / Stop go out its Box routes (its FM-1 on Box>
    follows the leader), never back to NET, and not twice where NET's own route to it is on"""
    import blemidi
    bridge = blemidi.MidiBridge.__new__(blemidi.MidiBridge)
    bridge.routes, bridge.saved = {}, {"Box>U:FM-1": {"on": True}, "Box>U:EP-136": {"on": True},
                                       "NET>U:EP-136": {"on": True}}
    bridge.dests = lambda: ["BT", "U:FM-1", "U:EP-136", "U:Off", "NET", "SMP"]
    sent = []
    bridge.deliver = lambda key, messages: messages and sent.append((key, messages))
    bridge.leader_clock(b"\xf8")
    assert [k for k, _ in sent] == ["Box>BT", "Box>U:FM-1"] and sent[1][1] == [b"\xf8"]   # (Box>BT: on at first)

def test_mackie():
    m = netmidi.Mackie()
    m.feed(bytes([0xE2, 0x7F, 0x3F]))                               # strip 3's fader
    m.feed(bytes([0x90, 0x5E, 0x7F]))                               # Play lit
    m.feed(bytes([0xF0, 0x00, 0x00, 0x66, 0x14, 0x12, 0x00]) + b"BASS   LEAD" + b"\xf7")
    m.feed(bytes([0xF0, 0x00, 0x00, 0x66, 0x14, 0x12, 56]) + b"-6.0" + b"\xf7")
    s = m.state()
    assert s["faders"][2] == 0x7F | 0x3F << 7 and s["leds"] == [0x5E]
    assert s["lcd"][0].startswith("BASS   LEAD") and s["lcd"][1].startswith("-6.0") and len(s["lcd"][0]) == 56
    assert netmidi.Mackie.fader(8, 20000) == bytes([0xE8, 0x7F, 0x7F])
    # what Ableton Live adds: the handshake, the pan knobs' rings, the level meters
    query = m.feed(bytes([0xF0, 0x00, 0x00, 0x66, 0x14, 0x00, 0xF7]))
    assert query == [bytes([0xF0, 0, 0, 0x66, 0x14, 0x01]) + b"FM1CMP1" + bytes(4) + b"\xf7"]
    assert m.feed(bytes([0xF0, 0, 0, 0x66, 0x14, 0x02]) + b"FM1CMP1" + bytes(4) + b"\xf7") == [
        bytes([0xF0, 0, 0, 0x66, 0x14, 0x03]) + b"FM1CMP1\xf7"]
    m.feed(bytes([0xB0, 0x31, 0x16]))                               # strip 2's ring at 6 (the middle)
    m.feed(bytes([0xD0, 0x2B]), now=100.0)                          # strip 3's meter at 11
    assert m.state()["rings"][1] == 6
    assert m.meter_levels(100.0)[2] == 11 and m.meter_levels(101.0)[2] == 11 - 3   # falls 1 step a 0.3 s
    assert netmidi.Mackie.pan(4, -3) == bytes([0xB0, 0x14, 67]) and netmidi.Mackie.pan(0, 2) == bytes([0xB0, 0x10, 2])
    assert netmidi.Mackie.press(0x5E, False) == bytes([0x90, 0x5E, 0])


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
