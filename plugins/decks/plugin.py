"""The DJ decks, a default plug-in of the Studio's: the DECKS tab (deskdecks.py), the decks' own program (decks.py,
started when the tab first opens), their sound as DECKS in the mixer while they run, MORE > AUDIO > DJ decks out,
and the web page's DJ decks. The Hercules and the learnt controllers are theirs (plugin.json "controllers"): off,
they're MIDI devices in the routes."""
API = 1

OUTS = {"studio": "DJ decks: through the Studio's mixer", "hercules": "DJ decks: the Hercules's own outputs"}


def setup(studio):
    from deskdecks import DecksTab
    tabs = []

    def make(ui, s):
        tab = DecksTab(ui, s)
        tabs.append(tab)
        return tab

    def running():
        return any(t.running() for t in tabs)

    def out():
        return studio.settings.get("out", "studio")

    def change_out():
        studio.settings["out"] = "hercules" if out() == "studio" else "studio"
        studio.save()
        for t in tabs:
            if t.proc:
                t.proc.send("output", out())
        studio.say(OUTS[out()], 2)

    def status():
        """each deck's track, tempo, key, playing, FX while they run; None: not running"""
        proc = next((t.proc for t in tabs if t.running()), None)
        state = proc and proc.status
        if not state:
            return None
        keep = ("title", "artist", "bpm", "camelot", "playing", "fx", "fx_on")
        return {"decks": [{k: (d or {}).get(k) for k in keep} for d in (state.get("decks") or [])]}

    studio.add_tab("DECKS", make)
    studio.add_app_sound("decks", "fm1-decks", "DECKS", shown=running)
    studio.add_setting("audio", "DJ decks out", out, change_out)
    studio.add_web(status=status)
