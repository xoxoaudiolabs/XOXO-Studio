"""The sampler, a plug-in: 16 pads in a kit (pads.py), their own process started with the Studio app while this is
on (plugin.json "process": pads.start_process, before the MIDI process, which sends it the routes' SMP notes), so
switching it on or off starts the app again ("restart"). Its PADS tab (deskpads.py), its sound PADS in the mixer
(its channel "fm1-xo4"), and the web page's kits."""
API = 1


def setup(studio):
    import padkit
    import pads
    from deskpads import PadsTab

    proc = studio.process()
    if proc:                                    # the kit, note repeat and MIDI IN to the pads' process
        proc.send("kit", padkit.kit(studio))
        proc.send("repeat", studio.settings.get("repeat"))
        proc.send("midi_in", bool(studio.settings.get("midi_in")))

    def status():
        return {"kits": {"current": padkit.kit(studio)["name"], "list": pads.list_kits()},
                "midi_in": bool(studio.settings.get("midi_in"))}

    def load(args):
        name = args.get("name")
        if name not in pads.list_kits():         # (said, not raised: a plug-in's error switches it off)
            return "Web: no such kit"
        kit = pads.load_kit(pads.kits_folder() / f"{name}.json")
        if kit:
            padkit.set_kit(studio, kit)
            return f"Web: Kit {kit['name']}"

    studio.add_tab("PADS", PadsTab)
    studio.add_sound_source(pads.SOURCE, "PADS")
    studio.add_web(status=status, commands={"kit": load})
