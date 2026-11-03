"""Tests for the web app's one-click update (update.py, config/fm1-update, install.sh's update mode, Library >
Software in web.py, weblink's hold-press): the versions, picking the newest release, not starting while the Studio
is busy, the update itself with fm1-update stood in for (installed, and put back when the new version doesn't
start), and the page asking the Studio. No network, no root. From FM-1 Companion's test_update.py.

  python tests/test_update.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))
TMP = Path(tempfile.mkdtemp(prefix="xoxo-update-"))
os.environ.update(FM1_LIBRARY=str(TMP / "library"), XDG_RUNTIME_DIR=str(TMP / "run"), FM1_SD_LIBRARY=str(TMP / "sd"))
(TMP / "run").mkdir()

import library  # noqa: E402
import update  # noqa: E402
import web  # noqa: E402

TAGS = ["v0.1", "v0.2", "v0.10", "v0.9", "studio-v1.6", "v1.0-beta", "test"]


def cached(tag):
    """GitHub's answer, as if asked a moment ago (no network in the tests)"""
    update.CACHE.write_text(json.dumps({"time": time.time(), "tag": tag,
                                        "version": list(update.version(tag)) if tag else None}))


def test_versions():
    assert update.version("v0.2") == (0, 2) and update.version("0.1 BETA") == (0, 1)
    assert update.version("1.0.3") == (1, 0, 3) and update.version("nothing") is None
    assert update.label((0, 2)) == "v0.2" and update.version("v0.9") < update.version("v0.10")   # numbers, not text
    assert update.newest_of(TAGS) == ("v0.10", (0, 10))            # v-tags only: not studio-v1.6, not v1.0-beta
    assert update.newest_of(["studio-v1.6", "test"]) is None
    import deskboot
    assert update.installed() == update.version(deskboot.VERSION)


def test_not_found():
    """GitHub's 404 (no such repo to the public, or no tags yet) says so, not "offline\""""
    import io
    real = update.urllib.request.urlopen

    def gone(*a, **k):
        raise update.urllib.error.HTTPError(update.TAGS, 404, "Not Found", {}, io.BytesIO())
    try:
        update.urllib.request.urlopen = gone
        found, error = update.newest(fresh=True)
        assert found is None and "isn't public" in error
    finally:
        update.urllib.request.urlopen = real


def test_busy():
    assert update.busy(status={}) is None
    assert "recording" in update.busy(status={"recording": 12})
    update.write_state("installing", "Installing v0.2")
    assert "already" in update.busy(status={})
    update.STATE.unlink()


def test_check():
    was = update.installed
    try:
        update.installed = lambda: (0, 1)
        cached("v0.2")
        info = update.check()
        assert info["installed"] == "v0.1" and info["newest"] == "v0.2" and info["newer"] and not info["error"]
        cached("v0.1")
        assert not update.check()["newer"]                             # up to date
    finally:
        update.installed = was


def test_run():
    """run(): installs with fm1-update, restarts, waits for the app; put back when it doesn't come up"""
    calls = []
    was = (update.installed, update.helper, update.restart, update.came_back, update.busy, update.newest)
    try:
        update.installed = lambda: (0, 1)
        update.busy = lambda *a, **k: None
        update.helper = lambda *args: (calls.append(("helper",) + args), (True, "Installed v0.2"))[1]
        update.restart = lambda: calls.append(("restart",))
        update.newest = lambda fresh=False: (("v0.2", (0, 2)), None)
        update.came_back = lambda within=0: True
        assert update.run() == 0 and calls == [("helper",), ("restart",)]
        assert update.read_state()["state"] == "done" and "v0.2" in update.read_state()["message"]
        calls.clear()
        update.came_back = lambda within=0: False                      # the new version doesn't start
        assert update.run() == 1 and calls == [("helper",), ("restart",), ("helper", "--back"), ("restart",)]
        state = update.read_state()
        assert state["state"] == "error" and "v0.1 was put back" in state["message"]
        calls.clear()
        update.helper = lambda *args: (calls.append(("helper",) + args), (False, "No release on GitHub."))[1]
        assert update.run() == 1 and calls == [("helper",)]            # didn't install: nothing restarted
        assert "Nothing was restarted" in update.read_state()["message"]
        update.installed = lambda: (0, 2)
        calls.clear()
        assert update.run() == 0 and calls == [] and "up to date" in update.read_state()["message"]
    finally:
        (update.installed, update.helper, update.restart, update.came_back, update.busy, update.newest) = was


def test_page_and_screen():
    """Library > Software: the page shows the versions; Update is a command the Studio takes, asking for its
    hold-press (weblink.web_update); refused while there's no helper or nothing newer"""
    import weblink
    server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    was = update.installed, update.HELPER, update.start
    helper = TMP / "fm1-update"

    class Studio:
        def __init__(self):
            self.said, self.asked, self.screen = [], None, "status"

        def say(self, text, seconds=1.0):
            self.said.append(text)

        def ask(self, title, lines, action, back="pick"):
            self.asked = (title, lines, action, back)

    studio = Studio()
    web_update = weblink.WebLink.web_update
    try:
        update.installed = lambda: (0, 1)
        cached("v0.2")
        page = urllib.request.urlopen(base + "/", timeout=10).read()
        assert b"<h2>Software</h2>" in page and b"function updateNow(" in page
        info = json.load(urllib.request.urlopen(base + "/api/update", timeout=10))
        assert info["installed"] == "v0.1" and info["newer"] and not info["helper"]
        assert web.check_command({"cmd": "update"}) == {"cmd": "update"}
        assert "install.sh" in web_update(studio) and studio.asked is None   # no fm1-update yet: once by hand
        helper.write_text("#!/bin/sh\n")
        update.HELPER = str(helper)
        assert web_update(studio) is None
        title, lines, action, back = studio.asked
        assert title == "Update?" and lines[0] == "v0.1 > v0.2" and back == "status"
        started = []
        update.start = lambda: started.append(1)
        action()                                                       # held: it starts
        assert started and "Updating" in studio.said[-1]
        cached("v0.1")
        assert "up to date" in web_update(studio)
    finally:
        update.installed, update.HELPER, update.start = was
        server.shutdown()


def test_scripts():
    """fm1-update takes nothing but --back and installs only what install.sh can install as an update; install.sh
    has that update mode (root for the user, nothing asked, the boot settings left alone) and gives the user's
    files back"""
    helper = (ROOT / "fm1-bt-bridge/config/fm1-update").read_text()
    assert "REPO=xoxoaudiolabs/XOXO-Studio" in helper and '*) echo "Usage: fm1-update [--back]"' in helper
    assert "grep -q FM1_UPDATE_USER" in helper and 'cp -a "$APP" "$WORK/previous"' in helper
    install = (ROOT / "fm1-bt-bridge/install.sh").read_text()
    for needed in ('if [ -z "${FM1_UPDATE_USER:-}" ]; then', "/usr/local/sbin/fm1-update\\n", 'chown -R "$USER:"',
                   '"$DIR/update.py"', 'if [ -z "$UPDATE" ] || ! all_installed; then',
                   "as_user systemctl --user daemon-reload",
                   'if [ -z "$UPDATE" ]; then                  # the boot settings'):
        assert needed in install, needed
    boot = install.index("# the boot settings, to the DAC's below")
    assert boot < install.index('SCREEN="dtoverlay=xoxo35') < install.index("fi                                          # (the boot settings)")
    bash = shutil.which("bash")
    if bash:
        for script in ("fm1-bt-bridge/install.sh", "fm1-bt-bridge/config/fm1-update"):
            assert subprocess.run([bash, "-n", str(ROOT / script)]).returncode == 0, script


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
