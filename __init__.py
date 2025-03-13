bl_info = {
    "name": "Playback Options",
    "author": "Pluglug",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "",
    "description": "Enhances animation playback by disabling overlays during playback",
    "warning": "",
    "doc_url": "",
    "category": "Animation",
}

use_reload = "addon" in locals()
if use_reload:
    import importlib

    importlib.reload(locals()["addon"])
    del importlib

from . import addon

addon.init_addon(
    module_patterns=[
        "core.*",
        "utils.*",
        "ui.*",
        "preferences",
    ],
    use_reload=use_reload,
)


def register():
    addon.register_modules()


def unregister():
    addon.unregister_modules()
