#!/usr/bin/env python3
"""The Studio's library: samples and recordings in ~/fm1-library, and the files the web page and the box pass
each other (the box's status, the page's commands).

  library.py import-sd                copy new samples from the SD card's fm1-library folder
  library.py list                     the library as JSON
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

LIBRARY = Path(os.environ.get("FM1_LIBRARY", Path.home() / "fm1-library"))
FOLDERS = ("samples", "recordings")
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
SD = Path(os.environ.get("FM1_SD_LIBRARY", "/boot/firmware/fm1-library"))
SUFFIXES = {"samples": (".wav",), "recordings": (".wav",)}


def folder(name):
    path = LIBRARY / name
    path.mkdir(parents=True, exist_ok=True)
    return path


STATUS = RUNTIME / "fm1-status.json"    # the box's live status, for the web page
COMMANDS = RUNTIME / "fm1-commands.jsonl"  # the web page's settings commands, one JSON object a line


def write_status(status):
    """the box: its status for the web page (RAM: $XDG_RUNTIME_DIR), written in place like ask_box"""
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(dict(status, time=time.time())))


def read_status():
    """the web page: the box's status, or None if there's none or it's over 5 s old (the box isn't running)"""
    try:
        status = json.loads(STATUS.read_text())
    except (OSError, ValueError):
        return None
    return status if time.time() - status.get("time", 0) < 5 else None


def queue_command(command):
    """the web page: a command for the box (settings, routes, transport, recording); appended, so several
    clicks in a row all arrive"""
    COMMANDS.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMANDS, "a") as f:
        f.write(json.dumps(dict(command, time=time.time())) + "\n")


def take_commands():
    """the box: the queued commands (taken once), each under 30 s old"""
    taking = COMMANDS.with_suffix(".taking")
    try:
        COMMANDS.rename(taking)
        lines = taking.read_text().splitlines()
        taking.unlink()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            command = json.loads(line)
        except ValueError:
            continue
        if isinstance(command, dict) and time.time() - command.get("time", 0) < 30:
            out.append(command)
    return out


# ---------------------------------------------------------------- the SD card's folder

def import_sd():
    """new samples from the SD card's fm1-library folder into the library; -> names copied"""
    copied = []
    for name in FOLDERS:
        if name == "recordings":              # made on the box, not brought in
            continue
        source = SD / name
        if not source.is_dir():
            continue
        for path in sorted(source.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES[name] or path.name.startswith("."):
                continue
            target = folder(name) / path.name
            if target.exists() and target.stat().st_size == path.stat().st_size:
                continue
            shutil.copyfile(path, target)
            copied.append(f"{name}/{path.name}")
    return copied


PART = re.compile(r"^(.+_fm1)-(a|b|usb\d+|u-[a-z0-9]+)\.wav$")   # a take's part: "..._fm1-b.wav", "..._fm1-u-ep136.wav"


def part_label(key):
    """"u-ep136" -> "EP136" (a USB device, by its name), "usb0" -> "USB keys" (older takes)"""
    if key.startswith("u-"):
        return key[2:].upper()
    if key.startswith("usb"):
        n = int(key[3:] or 0)
        return "USB keys" + (f" {n + 1}" if n else "")
    return key.upper()


def recording_parts(name):
    """a take's parts (recorded with Record parts on, next to it), as file names in recording order"""
    stem = Path(name).stem
    found = [p.name for p in folder("recordings").glob(f"{stem}-*.wav") if PART.match(p.name)]
    order = {"a": 0, "b": 1}
    return sorted(found, key=lambda n: (order.get(PART.match(n).group(2), 2), n))


def delete_recording(name):
    """a take, its parts and their clip counts"""
    for n in [name] + recording_parts(name):
        path = folder("recordings") / n
        path.unlink(missing_ok=True)
        Path(str(path) + ".clips").unlink(missing_ok=True)


def recording_entry(path):
    """{name, bytes, date, seconds, clips?} for a take or a part"""
    entry = {"name": path.name, "bytes": path.stat().st_size, "date": path.stat().st_mtime}
    with open(path, "rb") as f:               # 16-bit stereo, 44.1 or 48 kHz: the byte rate is in the header
        head = f.read(44)
    rate = int.from_bytes(head[28:32], "little") if head[:4] == b"RIFF" else 0
    entry["seconds"] = max(0, entry["bytes"] - 44) // (rate or 192000)
    try:                                      # flat tops counted when it was saved (meters.clip_count)
        entry["clips"] = int(Path(str(path) + ".clips").read_text())
    except (OSError, ValueError):
        pass
    return entry


def listing():
    """{folder: [{name, bytes, date, ...}]} newest first, recordings with their parts (each {name, part, label,
    seconds, ...}) instead of beside them"""
    out = {}
    for name in FOLDERS:
        entries = []
        for path in sorted(folder(name).iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES[name]:
                continue
            if name == "recordings" and PART.match(path.name):
                continue                      # under its take, below
            entry = {"name": path.name, "bytes": path.stat().st_size, "date": path.stat().st_mtime}
            if name == "recordings":
                entry = recording_entry(path)
                parts = [dict(recording_entry(folder(name) / n), part=PART.match(n).group(2),
                              label=part_label(PART.match(n).group(2))) for n in recording_parts(path.name)]
                if parts:
                    entry["parts"] = parts
            entries.append(entry)
        out[name] = entries
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    command = argv[0]
    try:
        if command == "import-sd":
            print(json.dumps(import_sd()))
        elif command == "list":
            print(json.dumps(listing(), indent=1))
        else:
            print(__doc__)
            return 2
        return 0
    except (OSError, ValueError) as e:
        print("error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
