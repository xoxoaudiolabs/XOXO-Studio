#!/usr/bin/env python3
"""xoxo: run a XOXO Studio over SSH, with no screen (docs/SSH.md).

Commands go to the app the way the web page sends them: checked by web.check_command, then queued with
library.queue_command, which the app takes on its main loop as if they came from the touchscreen. So they work
before the web app is up (it waits 45 s after boot). The status comes from the app's status file
(library.read_status). Run it as the Studio's user, the one whose services run the app.

  xoxo status                         services, version, sources, MIDI, clock, recording, links
  xoxo restart [app|web|pocket|all]   restart a service (app: refused while recording, unless --force)
  xoxo volume [0-100]                 the Bluetooth speaker's volume
  xoxo master [0-100]                 the DAC's or USB out's level
  xoxo tempo [30-300]                 the tempo
  xoxo clock [follow|box]             the clock: follow MIDI or the box's own
  xoxo metronome [on|off]
  xoxo latency [SAFE|LOW|LOWER|LOWEST]
  xoxo play | stop                    MIDI start / stop
  xoxo rec [start|stop]               recording
  xoxo midi                           MIDI devices and the routes that are on
  xoxo midi route SRC DEST on|off     one route of the matrix
  xoxo midi preset [1-4 load|save|clear [NAME]]
  xoxo recordings                     the recordings, newest first
  xoxo pull NAME                      where a recording is, and the scp line to copy it to a computer
  xoxo update [--check|--back]        install the newest release (asks yes), see what's there, or go back
  xoxo logs [app|web|pocket|update] [-f] [-n N]
  xoxo link [follow|rec|return on|off | audio mix|fm1s|midi]
  xoxo screen [theme NAME]
  xoxo usb-out [auto|off|NODE]
  xoxo plugin [ID on|off]
  xoxo kit [NAME]
  xoxo xo4 [pattern A-H | play | midi-in on|off | sound 1|2 NAME]

Shutting down, rebooting, backups and switching the screen off aren't here yet (docs/SSH.md: they need new code).
Add --json to status, midi, recordings or update --check for JSON. Python's standard library only.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# an SSH login has XDG_RUNTIME_DIR; a bare `ssh host xoxo ...` may not: the app's files are in /run/user/<uid>
if not os.environ.get("XDG_RUNTIME_DIR") and hasattr(os, "getuid") and Path(f"/run/user/{os.getuid()}").is_dir():
    os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library  # noqa: E402

SERVICES = {"app": "fm1-bridge", "web": "fm1-web", "pocket": "fm1-pocket-in"}
LATENCY = ("SAFE", "LOW", "LOWER", "LOWEST")
LINK_AUDIO = ("mix", "fm1s", "midi")
ONOFF = {"on": True, "off": False}


class Fail(Exception):
    """what went wrong, said to the user; exit code 1"""


def run(command, timeout=30):
    """a command -> (exit code, its output); tests stand in for it"""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return done.returncode, (done.stdout + done.stderr).strip()


def status():
    """the app's live status, or Fail: it isn't running"""
    s = library.read_status()
    if not s:
        raise Fail("the Studio's app isn't answering (xoxo status, xoxo logs app)")
    return s


def send(command):
    """a command for the app, checked as the web page's are -> what was sent"""
    import web
    try:
        checked = web.check_command(command)
    except (ValueError, TypeError, AttributeError) as e:
        raise Fail(str(e)[:120] or "bad command")
    status()                                  # (the web page's 503: nobody would take it)
    library.queue_command(checked)
    return checked


def on_off(word):
    if word not in ONOFF:
        raise Fail(f"on or off, not {word!r}")
    return ONOFF[word]


def number(word, lo, hi):
    try:
        value = int(word)
    except ValueError:
        raise Fail(f"a number {lo}-{hi}, not {word!r}")
    if not lo <= value <= hi:
        raise Fail(f"a number {lo}-{hi}, not {value}")
    return value


def setting(key, value, text):
    send({"cmd": "set", "key": key, "value": value})
    return f"sent: {text}"


def show_or_set(args, key, shown, parse, text):
    """a setting shown with no argument, set with one"""
    if not args:
        return shown(status())
    return setting(key, parse(args[0]), text(parse(args[0])))


# ---------------------------------------------------------------- status

def service_states():
    out = {}
    for name, unit in SERVICES.items():
        code, text = run(["systemctl", "--user", "is-active", unit])
        out[name] = text.splitlines()[-1] if text else ("active" if code == 0 else "unknown")
    return out


def status_text(s, services):
    """the status as a few lines of text"""
    lines = ["services   " + "  ".join(f"{n} {state}" for n, state in services.items())]
    if not s:
        return "\n".join(lines + ["app        not answering (xoxo logs app)"])
    midi, settings = s.get("midi") or {}, s.get("settings") or {}
    rec = s.get("recording")
    lines += [
        f"version    {s.get('version') or '?'}",
        f"sources    {', '.join(s.get('sources') or []) or 'none'}",
        f"speaker    {s.get('speaker') or 'none'}" + (f"  volume {s['volume']}" if s.get("speaker") else "")
        + (f"  battery {s['speaker_battery']}%" if s.get("speaker_battery") is not None else ""),
        f"master     {s['master']}" if s.get("master") is not None else "master     (no DAC or USB out)",
        f"usb out    {s.get('usb_out', 'auto')} -> {s.get('usb_out_now') or 'none'}",
        f"midi       {', '.join(midi.get('controllers') or []) or 'no controllers'}"
        + (f"; network {', '.join(midi['net'])}" if midi.get("net") else "")
        + (f"; error {midi['error']}" if midi.get("error") else ""),
        f"clock      {s.get('clock_text') or settings.get('bpm')}  ({settings.get('clock_mode')}, "
        f"metronome {'on' if settings.get('metronome') else 'off'})",
        f"recording  {'no' if rec is None else f'{rec // 60}:{rec % 60:02d}'}",
        f"latency    {s.get('latency')}",
        f"link       follow studio {'on' if s.get('follow_studio') else 'off'}"
        + (f" ({s['follows']})" if s.get("follows") else "")
        + f", pocket sends {s.get('link_audio')}, return {'on' if s.get('link_return') else 'off'}, "
        f"linked rec {'on' if s.get('link_rec') else 'off'}",
    ]
    if s.get("pocket"):
        lines.append(f"pocket     {s['pocket']}")
    if s.get("wifi") is not None:
        lines.append(f"wifi       {s['wifi']}")
    return "\n".join(lines)


def cmd_status(args, as_json):
    s, services = library.read_status(), service_states()
    if as_json:
        return json.dumps({"services": services, "status": s}, indent=1)
    return status_text(s, services)


# ---------------------------------------------------------------- services, logs

def cmd_restart(args, force):
    which = args[0] if args else "app"
    if which not in (*SERVICES, "all"):
        raise Fail("restart app, web, pocket or all")
    names = list(SERVICES) if which == "all" else [which]
    if "app" in names and not force:
        s = library.read_status()
        if s and s.get("recording") is not None:
            raise Fail("a recording is running: xoxo rec stop first (or --force to cut it off)")
    code, text = run(["systemctl", "--user", "restart", *(SERVICES[n] for n in names)], timeout=120)
    if code:
        raise Fail(text or "the restart failed")
    return "restarted " + ", ".join(SERVICES[n] for n in names)


def cmd_logs(args, follow, lines):
    which = args[0] if args else "app"
    if which == "update":
        import update
        command = ["tail", f"-n{lines}", *(["-f"] if follow else []), str(update.LOG)]
    elif which in SERVICES:
        command = ["journalctl", "--user", "-u", SERVICES[which], "-n", str(lines), "--no-pager",
                   *(["-f"] if follow else [])]
    else:
        raise Fail("logs app, web, pocket or update")
    return os.execvp(command[0], command)     # (its own output, and -f until Ctrl+C)


# ---------------------------------------------------------------- MIDI

def midi_info(s):
    routes = s.get("routes") or {}
    on = sorted(k for k, r in routes.items() if r.get("on"))
    return {"midi": s.get("midi"), "matrix": s.get("matrix"), "routes_on": on, "presets": s.get("presets") or {}}


def cmd_midi(args, as_json):
    if not args:
        s = status()
        info = midi_info(s)
        if as_json:
            return json.dumps(dict(info, routes=s.get("routes")), indent=1)
        m, matrix = info["midi"] or {}, info["matrix"] or {}
        presets = info["presets"]
        return "\n".join([
            f"bluetooth  {m.get('peer') or 'none'}",
            f"usb        {', '.join(m.get('controllers') or []) or 'none'}",
            f"network    {', '.join(m.get('net') or []) or 'none'}",
            f"sources    {' '.join(matrix.get('sources') or [])}",
            f"dests      {' '.join(matrix.get('dests') or [])}",
            "routes on  " + (" ".join(r.replace(">", "->") for r in info["routes_on"]) or "none"),
            "presets    " + (" ".join(f"{k}:{(v or {}).get('name') or 'saved'}" for k, v in sorted(presets.items()))
                             or "none"),
        ])
    if args[0] == "route" and len(args) == 4:
        key, value = f"{args[1]}>{args[2]}", on_off(args[3])
        routes = json.loads(json.dumps(status().get("routes") or {}))
        if key not in routes:
            raise Fail(f"no route {args[1]} -> {args[2]} now (xoxo midi lists sources and dests)")
        routes[key]["on"] = value
        send({"cmd": "routes", "routes": routes})
        return f"sent: route {args[1]} -> {args[2]} {args[3]}"
    if args[0] == "preset":
        if len(args) == 1:
            return cmd_midi([], as_json)
        if len(args) < 3 or args[2] not in ("load", "save", "clear"):
            raise Fail("midi preset 1-4 load|save|clear [NAME]")
        name = " ".join(args[3:]) or None
        send({"cmd": "preset", "slot": args[1], "action": args[2], "name": name if args[2] == "save" else None})
        return f"sent: preset {args[1]} {args[2]}"
    raise Fail("midi, midi route SRC DEST on|off, or midi preset 1-4 load|save|clear [NAME]")


# ---------------------------------------------------------------- recordings

def cmd_recordings(args, as_json):
    takes = library.listing()["recordings"]
    if as_json:
        return json.dumps(takes, indent=1)
    if not takes:
        return "no recordings"
    out = []
    for t in takes:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(t.get("date") or 0))
        secs = t.get("seconds")
        length = f"{int(secs) // 60}:{int(secs) % 60:02d}" if isinstance(secs, (int, float)) else "?"
        parts = f"  +{len(t['parts'])} part(s)" if t.get("parts") else ""
        out.append(f"{when}  {length:>6}  {t['bytes'] / 1e6:7.1f} MB  {t['name']}{parts}")
    return "\n".join(out)


def cmd_pull(args):
    if len(args) != 1:
        raise Fail("pull NAME (xoxo recordings lists them)")
    name = args[0]
    path = library.folder("recordings") / Path(name).name
    if Path(name).name != name or not path.is_file():
        raise Fail(f"no recording {name!r}")
    host = socket.gethostname() + ".local"
    user = os.environ.get("USER") or "xoxo"
    return f"{path}\non the computer:  scp {user}@{host}:{path.relative_to(Path.home()).as_posix()} ."


# ---------------------------------------------------------------- update

def confirm(question, yes):
    if yes:
        return True
    try:
        return input(f"{question} Type yes: ").strip().lower() == "yes"
    except EOFError:
        return False


def cmd_update(args, as_json, yes):
    import update
    if "--check" in args:
        info = update.check(fresh=True)
        if as_json:
            return json.dumps(info, indent=1)
        last = (info.get("last") or {}).get("message")
        return "\n".join([f"installed  {info['installed']}", f"newest     {info['newest'] or '?'}"
                          + (f"  ({info['error']})" if info.get("error") else ""),
                          f"update     {'yes' if info['newer'] else 'no'}"
                          + (f" (but {info['busy']})" if info.get("busy") else ""),
                          f"root       {'yes (fm1-update)' if info['root'] else "no: the Studio's own files only"}"]
                         + ([f"last       {last}"] if last else []))
    if "--back" in args:
        why = update.busy()
        if why:
            raise Fail(why)
        if not confirm("Put back the code from before the last update, and restart the app?", yes):
            return "nothing done"
        ok, last = update.helper("--back") if update.root_ready() else update.user_back()
        if not ok:
            raise Fail(last or "going back failed")
        update.restart()
        return f"{last}\nrestarted the app"
    if args:
        raise Fail("update, update --check or update --back")
    info = update.check(fresh=True)
    if info.get("busy"):
        raise Fail(info["busy"])
    if not info["newer"]:
        return f"up to date ({info['installed']})" if not info.get("error") else f"can't tell: {info['error']}"
    if not confirm(f"Update {info['installed']} -> {info['newest']}? The app restarts; your files are kept.", yes):
        return "nothing done"
    error = update.start()
    if error:
        raise Fail(error)
    return "updating: it restarts when done (xoxo logs update -f, then xoxo update --check)"


# ---------------------------------------------------------------- the rest of the settings

def cmd_link(args):
    if not args:
        s = status()
        return (f"follow studio {'on' if s.get('follow_studio') else 'off'}"
                + (f" ({s['follows']})" if s.get("follows") else "")
                + f"\npocket sends  {s.get('link_audio')}\nreturn        {'on' if s.get('link_return') else 'off'}"
                f"\nlinked rec    {'on' if s.get('link_rec') else 'off'}\npocket        {s.get('pocket') or 'none'}")
    keys = {"follow": "follow_studio", "rec": "link_rec", "return": "link_return"}
    if len(args) == 2 and args[0] in keys:
        return setting(keys[args[0]], on_off(args[1]), f"link {args[0]} {args[1]}")
    if len(args) == 2 and args[0] == "audio" and args[1] in LINK_AUDIO:
        return setting("link_audio", args[1], f"pocket sends {args[1]}")
    raise Fail("link follow|rec|return on|off, or link audio mix|fm1s|midi")


def cmd_screen(args):
    if not args:
        theme = status().get("theme") or {}
        return f"theme  {theme.get('value')}\nthemes {' '.join(theme.get('choices') or [])}"
    if len(args) == 2 and args[0] == "theme":
        return setting("desk_theme", args[1], f"theme {args[1]}")
    raise Fail("screen, or screen theme NAME")


def cmd_plugin(args):
    if not args:
        plugs = (status().get("plugins") or {}).get("list") or []
        return "\n".join(f"{p.get('id')}  {'on' if p.get('on') else 'off'}  {p.get('name') or ''}".rstrip()
                         for p in plugs) or "no plug-ins"
    if len(args) == 2:
        send({"cmd": "plugin", "id": args[0], "on": on_off(args[1])})
        return f"sent: plug-in {args[0]} {args[1]}"
    raise Fail("plugin, or plugin ID on|off")


def cmd_kit(args):
    if not args:
        kits = status().get("kits") or {}
        return f"kit   {kits.get('current')}\nkits  {', '.join(kits.get('list') or [])}"
    name = " ".join(args)
    send({"cmd": "kit", "name": name})
    return f"sent: kit {name}"


def cmd_xo4(args):
    if not args:
        x = status().get("xo4") or {}
        return (f"pattern  {x.get('pattern')}" + (f" (next {x['queued']})" if x.get("queued") else "")
                + f"\nplaying  {'yes' if x.get('playing') else 'no'}\nmidi in  {'on' if x.get('midi_in') else 'off'}"
                f"\nsounds   {', '.join(x.get('sounds') or [])}\nused     {' '.join(x.get('used') or []) or 'none'}")
    if args == ["play"]:
        send({"cmd": "xo4", "action": "play"})
        return "sent: XO-4 play"
    if len(args) == 2 and args[0] == "pattern":
        send({"cmd": "xo4", "action": "pattern", "value": args[1].upper()})
        return f"sent: XO-4 pattern {args[1].upper()}"
    if len(args) == 2 and args[0] == "midi-in":
        send({"cmd": "xo4", "action": "midi_in", "value": on_off(args[1])})
        return f"sent: XO-4 MIDI IN {args[1]}"
    if len(args) == 3 and args[0] == "sound" and args[1] in ("1", "2"):
        send({"cmd": "xo4", "action": "sound", "track": int(args[1]), "value": args[2].upper()})
        return f"sent: SYN {args[1]} {args[2].upper()}"
    raise Fail("xo4, xo4 play, xo4 pattern A-H, xo4 midi-in on|off, or xo4 sound 1|2 NAME")


# ---------------------------------------------------------------- the command line

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    flags = {f for f in argv if f in ("--json", "--force", "--yes", "-f", "--check", "--back")}
    lines = 100
    if "-n" in argv:
        i = argv.index("-n")
        word = argv[i + 1] if i + 1 < len(argv) else "100"
        del argv[i:i + 2]
        if not word.isdigit() or not 1 <= int(word) <= 100000:
            print(f"xoxo: -n takes a number of lines, not {word!r}", file=sys.stderr)
            return 1
        lines = int(word)
    words = [a for a in argv if a not in flags or a in ("--check", "--back")]
    if not words or words[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if words else 2
    name, args, as_json = words[0], words[1:], "--json" in flags
    s = lambda: status()                       # noqa: E731
    try:
        if name == "status":
            out = cmd_status(args, as_json)
        elif name == "restart":
            out = cmd_restart(args, "--force" in flags)
        elif name == "logs":
            out = cmd_logs(args, "-f" in flags, lines)
        elif name == "volume":
            out = show_or_set(args, "volume", lambda st: f"volume {st.get('volume')} ({st.get('speaker') or 'no speaker'})",
                              lambda w: number(w, 0, 100), lambda v: f"volume {v}")
        elif name == "master":
            out = show_or_set(args, "master", lambda st: f"master {st.get('master')}",
                              lambda w: number(w, 0, 100), lambda v: f"master {v}")
        elif name == "tempo":
            out = show_or_set(args, "bpm", lambda st: st.get("clock_text") or str((st.get("settings") or {}).get("bpm")),
                              lambda w: number(w, 30, 300), lambda v: f"tempo {v}")
        elif name == "clock":
            out = show_or_set(args, "clock_mode", lambda st: f"clock {(st.get('settings') or {}).get('clock_mode')}",
                              lambda w: w, lambda v: f"clock {v}")
        elif name == "metronome":
            out = show_or_set(args, "metronome",
                              lambda st: f"metronome {'on' if (st.get('settings') or {}).get('metronome') else 'off'}",
                              on_off, lambda v: f"metronome {'on' if v else 'off'}")
        elif name == "latency":
            out = show_or_set(args, "latency", lambda st: f"latency {st.get('latency')}",
                              lambda w: w.upper(), lambda v: f"latency {v}")
        elif name == "usb-out":
            out = show_or_set(args, "usb_out", lambda st: f"usb out {st.get('usb_out')} -> {st.get('usb_out_now') or 'none'}"
                              + "".join(f"\n  {o.get('name')}  {o.get('label') or ''}" for o in st.get("usb_outs") or []),
                              lambda w: w, lambda v: f"usb out {v}")
        elif name in ("play", "stop") and not args:
            send({"cmd": "transport", "value": "start" if name == "play" else "stop"})
            out = f"sent: {name}"
        elif name == "rec":
            if not args:
                rec = s().get("recording")
                out = "not recording" if rec is None else f"recording {rec // 60}:{rec % 60:02d}"
            else:
                send({"cmd": "record", "value": args[0]})
                out = f"sent: rec {args[0]}"
        elif name == "midi":
            out = cmd_midi(args, as_json)
        elif name == "recordings":
            out = cmd_recordings(args, as_json)
        elif name == "pull":
            out = cmd_pull(args)
        elif name == "update":
            out = cmd_update(args, as_json, "--yes" in flags)
        elif name == "link":
            out = cmd_link(args)
        elif name == "screen":
            out = cmd_screen(args)
        elif name == "plugin":
            out = cmd_plugin(args)
        elif name == "kit":
            out = cmd_kit(args)
        elif name == "xo4":
            out = cmd_xo4(args)
        else:
            raise Fail(f"no command {name!r} (xoxo help)")
    except Fail as e:
        print(f"xoxo: {e}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
