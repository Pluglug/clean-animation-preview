import bpy
from bpy.app.handlers import persistent

from ..debug_utils import Log, DBG


class PlaybackViewportManager:
    """Manages View3D viewport settings during animation playback"""

    def __init__(self):
        self._original_states = {}
        self._is_active = False
        self._frame_handler = None
        self._playback_start_handler = None
        self._playback_end_handler = None
        self._is_playing = False
        DBG and Log.info("PlaybackViewportManager initialized")

    @property
    def is_active(self):
        return self._is_active

    def activate(self):
        """register handlers"""
        if not self._is_active:
            DBG and Log.info("Activating viewport manager...")
            try:
                bpy.app.handlers.frame_change_pre.append(self._frame_change_handler)
                bpy.app.handlers.animation_playback_pre.append(
                    self._playback_start_handler_fn
                )
                bpy.app.handlers.animation_playback_post.append(
                    self._playback_end_handler_fn
                )

                self._frame_handler = self._frame_change_handler
                self._playback_start_handler = self._playback_start_handler_fn
                self._playback_end_handler = self._playback_end_handler_fn

                self._is_active = True
                DBG and Log.info("Viewport manager activated successfully")
            except Exception as e:
                Log.error(f"Failed to activate viewport manager: {str(e)}")
                self.deactivate()  # error then deactivate

    def deactivate(self):
        """unregister handlers"""
        DBG and Log.info("Deactivating viewport manager...")
        try:
            # if playing, force end
            if self._is_playing:
                self._is_playing = False
                self._restore_viewport_states()

            # safely remove handlers
            if self._frame_handler is not None:
                if self._frame_handler in bpy.app.handlers.frame_change_pre:
                    bpy.app.handlers.frame_change_pre.remove(self._frame_handler)
                    DBG and Log.info("Frame handler removed")
                self._frame_handler = None

            if self._playback_start_handler is not None:
                if (
                    self._playback_start_handler
                    in bpy.app.handlers.animation_playback_pre
                ):
                    bpy.app.handlers.animation_playback_pre.remove(
                        self._playback_start_handler
                    )
                    DBG and Log.info("Playback start handler removed")
                self._playback_start_handler = None

            if self._playback_end_handler is not None:
                if (
                    self._playback_end_handler
                    in bpy.app.handlers.animation_playback_post
                ):
                    bpy.app.handlers.animation_playback_post.remove(
                        self._playback_end_handler
                    )
                    DBG and Log.info("Playback end handler removed")
                self._playback_end_handler = None

            self._is_active = False
            DBG and Log.info("Viewport manager deactivated successfully")
        except Exception as e:
            log.error(f"Error during viewport manager deactivation: {str(e)}")

    def _store_viewport_states(self):
        """store current viewport states"""
        self._original_states.clear()
        for area in bpy.context.screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                self._original_states[space] = {
                    "show_overlays": space.overlay.show_overlays,
                    "show_gizmo": space.show_gizmo,
                }
        DBG and Log.info(f"Stored viewport states: {len(self._original_states)} areas")

    def _restore_viewport_states(self):
        """restore saved viewport states"""
        if not self._original_states:
            DBG and Log.info("No viewport states to restore")
            return

        restored_count = 0
        for space, states in self._original_states.items():
            try:
                space.overlay.show_overlays = states["show_overlays"]
                space.show_gizmo = states["show_gizmo"]
                restored_count += 1
            except ReferenceError:
                log.warning(
                    "Failed to restore viewport state: Space reference is invalid"
                )
            except Exception as e:
                log.error(f"Error restoring viewport state: {str(e)}")

        DBG and Log.info(f"Restored {restored_count} viewport states")
        self._original_states.clear()

    def _disable_viewport_features(self):
        """disable viewport features"""
        disabled_count = 0
        for area in bpy.context.screen.areas:
            if area.type == "VIEW_3D":
                try:
                    space = area.spaces.active
                    space.overlay.show_overlays = False
                    space.show_gizmo = False
                    disabled_count += 1
                except Exception as e:
                    log.error(f"Error disabling viewport features: {str(e)}")
        DBG and Log.info(f"Disabled features in {disabled_count} viewport areas")

    @persistent
    def _frame_change_handler(self, scene, depsgraph):
        """frame change handler"""
        if not self._is_playing:
            return

        frame = scene.frame_current
        try:
            if scene.use_preview_range:
                if (
                    frame >= scene.frame_preview_start
                    and frame <= scene.frame_preview_end
                ):
                    if not self._original_states:
                        self._store_viewport_states()
                    self._disable_viewport_features()
                else:
                    if self._original_states:
                        self._restore_viewport_states()
            else:
                if frame >= scene.frame_start and frame <= scene.frame_end:
                    if not self._original_states:
                        self._store_viewport_states()
                    self._disable_viewport_features()
                else:
                    if self._original_states:
                        self._restore_viewport_states()
        except Exception as e:
            log.error(f"Error in frame change handler: {str(e)}")

    @persistent
    def _playback_start_handler_fn(self, scene, depsgraph):
        """playback start handler"""
        DBG and Log.info("Animation playback started")
        self._is_playing = True

    @persistent
    def _playback_end_handler_fn(self, scene, depsgraph):
        """playback end handler"""
        DBG and Log.info("Animation playback ended")
        self._is_playing = False
        if self._original_states:
            self._restore_viewport_states()


playback_manager = PlaybackViewportManager()
