"""The Studio's MORE > PLUG-INS: every plug-in found (plugins.py), switched on or off with a tap, and the screens the
ones switched on add, each opened full screen with "< PLUG-INS" (top left). Mixed into deskui.DeskUI.

A plug-in's screen (Studio.add_screen) is a class: screen(ui, studio), with draw(img, d, now) drawing below the
header (y from HDR_H) with ui's widgets (ui.button, ui.widget, ui.centre, ui.theme), and view(now), anything that
changes when it should be drawn again (without one: once a second). A screen that raises an error switches its
plug-in off (plugins.Host.fail), and the list comes back.
"""
import sloopstyle as st

W, H, HDR_H, TAB_H = 480, 320, 34, 44
RED = (255, 112, 92)


class DeskPlugins:
    def plugins_init(self):
        self.plugin_screen = None                # (plug-in id, label, the screen) open, or None
        self.plugins_top = 0

    def plugins_view(self, now):
        host = self.app.plugin_host
        base = (tuple((p["id"], p["on"], p["error"]) for p in host.listing()), self.plugins_top,
                tuple((pid, label) for pid, label, _ in host.screens()))
        if self.tab == "PLUGIN" and self.plugin_screen:
            pid, _, screen = self.plugin_screen
            view = getattr(screen, "view", None)
            base += (host.call(pid, view, now) if view else int(now),)
        return base

    def draw_plugins(self, img, d, now):
        """the list: a row a plug-in (its name, version, author; ON/OFF), then a button a screen of those on"""
        t, host = self.theme, self.app.plugin_host
        self.button(img, d, (4, 3, 84, HDR_H - 5), "< MORE", lambda: self.open_tab("MORE"), key="plugins-back")
        st.text(img, (96, 9), "PLUG-INS", t.hi)
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        rows = host.listing()
        screens = host.screens()
        if not rows:
            self.centre(img, (0, HDR_H + 30, W, HDR_H + 60), "NO PLUG-INS FOUND", t.c[3])
            self.centre(img, (0, HDR_H + 64, W, HDR_H + 94), "PUT ONE IN ~/xoxo-plugins", t.c[2])
            return
        y = HDR_H + 6
        for p in rows[self.plugins_top:self.plugins_top + 4]:
            box = (4, y, W - 4, y + 40)
            d.rectangle(box, fill=t.grey[0])
            st.text(img, (12, y + 4), p["name"].upper()[:24], t.hi)
            sub = p["error"] or f"{p['version']}  {p['author']}".upper()
            st.text(img, (12, y + 21), sub[:40], RED if p["error"] else t.c[2])
            self.button(img, d, (W - 84, y + 6, W - 10, y + 34), "ON" if p["on"] else "OFF",
                        lambda pid=p["id"], on=p["on"]: self.plugin_switch(pid, not on), on=p["on"],
                        key=("plugin-on", p["id"]))
            y += 44
        y = H - TAB_H - 40                         # the screens of those on, along the bottom
        for i, (pid, label, screen) in enumerate(screens[:4]):
            box = (4 + i * 118, y, 4 + i * 118 + 114, y + 34)
            self.button(img, d, box, label.upper(), lambda s=(pid, label, screen): self.open_plugin(s),
                        key=("plugin-screen", pid, label))

    def plugin_switch(self, pid, on):
        a = self.app
        if on and pid in a.plugin_host.found and not a.plugin_host.entry(pid)["on"]:
            name = a.plugin_host.found[pid][1]["name"]   # (a plug-in is code: said once, before it first runs)
            a.ask(f"Switch on {name[:16]}?", ["A plug-in runs as the Studio does.", "Only ones you trust."],
                  lambda: a.say(a.plugin_host.set_on(pid, True), 2), back="status")
            return
        a.say(a.plugin_host.set_on(pid, on), 2)
        if not on and self.plugin_screen and self.plugin_screen[0] == pid:
            self.plugin_screen = None

    def open_plugin(self, entry):
        pid, label, screen = entry
        host = self.app.plugin_host
        made = host.call(pid, screen, self, host.loaded.get(pid))
        if made is not None:
            self.plugin_screen = (pid, label, made)
            self.open_tab("PLUGIN")

    def draw_plugin(self, img, d, now):
        """an open plug-in screen, below its header"""
        t, host = self.theme, self.app.plugin_host
        if not self.plugin_screen or self.plugin_screen[0] not in host.loaded:
            self.plugin_screen = None
            self.tab = "PLUGINS"
            return self.draw_plugins(img, d, now)
        pid, label, screen = self.plugin_screen
        self.button(img, d, (4, 3, 108, HDR_H - 5), "< PLUG-INS", lambda: self.open_tab("PLUGINS"),
                    key="plugin-back")
        st.text(img, (120, 9), label.upper(), t.hi)
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        host.call(pid, screen.draw, img, d, now)
