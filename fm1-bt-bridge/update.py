#!/usr/bin/env python3
"""The web app's one-click update: the newest XOXO Studio release, from the project's GitHub
(xoxoaudiolabs/XOXO-Studio, release tags v0.1, v0.2 ...). From FM-1 Companion's update.py (the Pocket's), for the
Studio alone.

What's yours stays as it is: an update replaces the Studio's code (~/.local/share/fm1-bridge) and its system files,
never the settings and pairings (~/.config/fm1-bridge), the library (~/fm1-library: samples, kits, songs,
recordings) or the plug-ins (~/xoxo-plugins). Nor the boot settings (config.txt: the screen, the DAC): those change
only with install.sh run by hand. It won't start while a recording is running.

The web page asks for it (Library > Software); the Studio asks for a hold-press on its screen (weblink.py), then
start() runs `update.py run` as a systemd unit of its own (it outlives the app's restart). That asks
/usr/local/sbin/fm1-update (root, no password: install.sh's sudoers) to install the release with its own
install.sh, restarts the app and waits for it: if it doesn't come back, the code from before is put back
(fm1-update --back) and started again. Where fm1-update can't run (missing, FM-1 Companion's, or not allowed
without a password: root_ready), nothing is asked either: the release's install-app.sh installs the Studio's own
files as its user (user_install), and the system's files wait for install.sh or fm1-update.

  python3 update.py check     the installed version and the newest, as JSON
  python3 update.py run       update now (what the Studio starts)

Python's standard library only.
"""
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library  # noqa: E402

REPO = "xoxoaudiolabs/XOXO-Studio"
TAGS = f"https://api.github.com/repos/{REPO}/tags?per_page=100"
NOTES = f"https://github.com/{REPO}/releases"
TAG = re.compile(r"^v(\d+(?:\.\d+)+)$")
HELPER = "/usr/local/sbin/fm1-update"
STATE = library.RUNTIME / "fm1-update.json"     # where an update is up to, for the web page (and the screen)
CACHE = library.RUNTIME / "fm1-update-newest.json"
LOG = Path.home() / ".cache" / "fm1-bridge" / "update.log"
APP = Path.home() / ".local" / "share" / "fm1-bridge"     # the Studio's code
WORK = Path.home() / ".cache" / "fm1-bridge" / "update"   # user_install's download and the code before it
CACHE_FOR = 600                 # s: GitHub answers 60 unauthenticated asks an hour
BACK_WITHIN = 120               # s: the app's status has to come back within this after the restart


def version(text):
    """"v0.2", "0.1 BETA", "1.0.3" -> (0, 2) ...; None if there's no version in it"""
    m = re.search(r"(\d+(?:\.\d+)+)", text or "")
    return tuple(int(n) for n in m.group(1).split(".")) if m else None


def label(v):
    return "v" + ".".join(map(str, v)) if v else "?"


def installed():
    """the version installed here: deskboot.VERSION"""
    import deskboot
    return version(deskboot.VERSION)


def newest_of(tags):
    """the newest release tag among GitHub's tags -> (tag, version) or None"""
    found = [(version(t), t) for t in tags if TAG.match(t)]
    if not found:
        return None
    v, tag = max(found)
    return tag, v


def newest(fresh=False):
    """the newest release, asked of GitHub (kept CACHE_FOR s) -> ((tag, version) or None, an error message when
    GitHub couldn't be asked)"""
    if not fresh:
        try:
            cached = json.loads(CACHE.read_text())
            if time.time() - cached["time"] < CACHE_FOR:
                return (cached["tag"], tuple(cached["version"])) if cached["tag"] else None, None
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        request = urllib.request.Request(TAGS, headers={"Accept": "application/vnd.github+json",
                                                        "User-Agent": "xoxo-studio"})
        with urllib.request.urlopen(request, timeout=10) as reply:
            tags = [t["name"] for t in json.load(reply)]
    except urllib.error.HTTPError as e:      # (an OSError too: first)
        if e.code == 404:
            return None, "no releases on GitHub yet (or the project isn't public)"
        return None, f"couldn't ask GitHub ({str(e)[:60]})"
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, f"couldn't ask GitHub ({str(e)[:60]}): is the Studio online?"
    found = newest_of(tags)
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"time": time.time(), "tag": found and found[0],
                                     "version": found and list(found[1])}))
    except OSError:
        pass
    return found, None


def read_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def write_state(state, message, **extra):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(dict(extra, state=state, message=message, time=time.time())))
    log(f"{state}: {message}")


def log(line):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line.rstrip() + "\n")
    except OSError:
        pass


def busy(status=None):
    """why an update can't start now (it restarts the app), or None"""
    status = library.read_status() if status is None else status
    if status and status.get("recording") is not None:
        return "a recording is running: stop it first"
    if read_state().get("state") in ("installing", "restarting"):
        return "an update is already running"
    return None


def root_ready():
    """fm1-update can run here: the Studio's own (not FM-1 Companion's, left by a box that was one) and allowed
    without a password (install.sh's sudoers). Else an update installs the Studio's own files without root."""
    try:
        if f"REPO={REPO}\n" not in Path(HELPER).read_text():
            return False
        return subprocess.run(["sudo", "-n", "-l", HELPER], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check(fresh=False):
    """for the web page: the installed version, the newest, whether there's one to install, and how the last
    update went. helper: an update can run here (always, now: without fm1-update it installs the Studio's own
    files); root: with fm1-update (the system's files too)"""
    have = installed()
    found, error = newest(fresh)
    newer = bool(found and have and found[1] > have)
    return {"build": "studio", "installed": label(have), "newest": found and label(found[1]),
            "tag": found and found[0], "newer": newer, "error": error, "notes": NOTES,
            "helper": True, "root": root_ready(), "last": read_state(), "busy": busy()}


def start():
    """once the Studio has its hold-press: run() as a unit of its own, so the app's restart doesn't stop it -> an
    error message, or None"""
    why = busy()
    if why:
        return why
    command = [sys.executable, str(Path(__file__).resolve()), "run"]
    if shutil.which("systemd-run"):
        command = ["systemd-run", "--user", "--collect", "--quiet", f"--unit=fm1-update-{int(time.time())}",
                   *command]
    write_state("installing", "Starting the update", started=time.time())
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        write_state("error", str(e))
        return str(e)
    return None


def helper(*args):
    """fm1-update as root (sudo, no password) -> (ok, its last line)"""
    try:
        done = subprocess.run(["sudo", "-n", HELPER, *args], capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    for line in (done.stdout + done.stderr).splitlines():
        log("  " + line)
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    return done.returncode == 0, lines[-1] if lines else ""


def fetch(tag, dest):
    """a release's source, as GitHub packs it, to dest"""
    request = urllib.request.Request(f"https://codeload.github.com/{REPO}/tar.gz/refs/tags/{tag}",
                                     headers={"User-Agent": "xoxo-studio"})
    with urllib.request.urlopen(request, timeout=120) as reply, open(dest, "wb") as out:
        shutil.copyfileobj(reply, out)


def user_install(tag):
    """without root (no fm1-update here): the release's install-app.sh, as the Studio's user: its code, fonts,
    icons, kits, PipeWire and WirePlumber settings, user services. The code before kept to go back to (user_back).
    -> (ok, its last line)"""
    import tarfile
    shutil.rmtree(WORK / "new", ignore_errors=True)
    (WORK / "new").mkdir(parents=True)
    try:
        fetch(tag, WORK / "release.tar.gz")
        with tarfile.open(WORK / "release.tar.gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(WORK / "new", filter="data")
            else:
                tar.extractall(WORK / "new")
    except (OSError, tarfile.TarError) as e:
        return False, f"couldn't download {tag} ({str(e)[:60]})"
    finally:
        (WORK / "release.tar.gz").unlink(missing_ok=True)
    found = sorted((WORK / "new").glob("*/fm1-bt-bridge/install-app.sh"))
    if not found:
        return False, f"{tag} can't be installed without root here: install it over SSH (README)"
    shutil.rmtree(WORK / "previous", ignore_errors=True)
    if APP.is_dir():
        shutil.copytree(APP, WORK / "previous", symlinks=True)
    try:
        done = subprocess.run(["bash", str(found[0])], capture_output=True, text=True, timeout=1800,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    finally:
        shutil.rmtree(WORK / "new", ignore_errors=True)
    try:                                      # (its user services may have changed)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    for line in (done.stdout + done.stderr).splitlines():
        log("  " + line)
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    return done.returncode == 0, lines[-1] if lines else f"Installed {tag}"


def user_back():
    """user_install's code from before put back -> (ok, a line)"""
    if not (WORK / "previous").is_dir():
        return False, "Nothing to go back to."
    try:
        shutil.rmtree(APP, ignore_errors=True)
        shutil.copytree(WORK / "previous", APP, symlinks=True)
    except OSError as e:
        return False, str(e)
    return True, "Put back the code from before the update."


def came_back(within=BACK_WITHIN):
    """after the restart: the app running and writing its status again"""
    end = time.monotonic() + within
    time.sleep(5)
    while time.monotonic() < end:
        active = subprocess.run(["systemctl", "--user", "is-active", "fm1-bridge"], capture_output=True,
                                text=True).stdout.strip() == "active"
        status = library.read_status()
        if active and status and status.get("time", 0) > time.time() - 5:
            return True
        time.sleep(3)
    return False


def restart():
    subprocess.run(["systemctl", "--user", "restart", "fm1-bridge", "fm1-web"], capture_output=True, timeout=120)


def run():
    """the update itself (its own systemd unit): install, restart, check it came back, else go back"""
    have = installed()
    found, error = newest(fresh=True)
    if error or not found:
        write_state("error", error or "no release found on GitHub")
        return 1
    if have and found[1] <= have:
        write_state("done", f"Already up to date ({label(have)})")
        return 0
    why = busy()
    if why and "update is already" not in why:
        write_state("error", why)
        return 1
    write_state("installing", f"Installing {label(found[1])} (a few minutes)",
                started=time.time(), to=label(found[1]), before=label(have))
    root = root_ready()                       # (else the Studio's own files, no password: user_install)
    ok, last = helper() if root else user_install(found[0])
    if not ok:
        write_state("error", f"The install didn't finish: {last[:100].rstrip('.')}. Nothing was restarted.",
                    before=label(have))
        return 1
    write_state("restarting", "Restarting the Studio's app", to=label(found[1]), before=label(have))
    restart()
    if came_back():
        write_state("done", f"Updated to {label(found[1])}", to=label(found[1]), before=label(have))
        return 0
    back, last = helper("--back") if root else user_back()
    restart()
    write_state("error", f"{label(found[1])} didn't start, so {label(have)} was put back"
                + ("" if back else f" (that failed too: {last[:60]}; install over SSH)"), before=label(have))
    return 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["check"]:
        print(json.dumps(check(fresh=True), indent=1))
        return 0
    if argv == ["run"]:
        return run()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
