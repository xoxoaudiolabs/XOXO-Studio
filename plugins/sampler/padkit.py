"""The sampler plug-in's kit in use: kept in its settings (studio.settings["kit"]), the 808 KIT the first time."""
import pads


def kit(studio):
    """the kit in use; none yet (a first start): the ready-made 808 KIT"""
    if not studio.settings.get("kit"):
        pads.factory_kits()
        studio.settings["kit"] = pads.load_kit(pads.kit_path(pads.FACTORY_KITS[0][1])) or pads.empty_kit()
    return pads.clean_kit(studio.settings["kit"])


def set_kit(studio, new):
    """a kit to use: kept, and sent to the pads' process"""
    studio.settings["kit"] = pads.clean_kit(new)
    studio.save()
    proc = studio.process()
    if proc:
        proc.send("kit", studio.settings["kit"])
