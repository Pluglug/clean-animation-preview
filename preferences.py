import bpy
from bpy.props import BoolProperty
from bpy.types import AddonPreferences

from .addon import ADDON_ID, prefs
from .core.playback_manager import playback_manager


class PlaybackOptionsPreferences(AddonPreferences):
    """Playback options preferences"""

    bl_idname = ADDON_ID

    enable_viewport_features: BoolProperty(
        name="Enable Viewport Features",
        description="Disable viewport overlays and gizmos during animation playback",
        default=True,
        update=lambda self, context: self.update_viewport_features(context),
    )

    def draw(self, _):
        layout = self.layout
        layout.prop(self, "enable_viewport_features")

    def update_viewport_features(self, _):
        """Toggle viewport features"""
        if self.enable_viewport_features:
            playback_manager.activate()
        else:
            playback_manager.deactivate()


def draw_dopesheet_header(self, context):
    """Add button to DOPESHEET header"""
    layout = self.layout
    layout.separator()
    layout.prop(
        prefs(context),
        "enable_viewport_features",
        text="",
        icon="SHADERFX",
    )


def register():
    pr = prefs()
    if pr.enable_viewport_features:
        playback_manager.activate()
    bpy.types.DOPESHEET_HT_header.append(draw_dopesheet_header)


def unregister():
    playback_manager.deactivate()
    bpy.types.DOPESHEET_HT_header.remove(draw_dopesheet_header)
