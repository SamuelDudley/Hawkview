from vispy.scene import BaseCamera
from vispy.geometry import Rect

class XSyncCamera(BaseCamera):
    def set_state(self, state=None, **kwargs):
        D = state or {}
        if 'rect' not in D:
            return
        
        for cam in self._linked_cameras:
            #print 'linked', cam
            r = Rect(D['rect'])
            if cam is self._linked_cameras_no_update:
                #print 'no up'
                continue
            try:
                cam._linked_cameras_no_update = self
                cam_rect = cam.get_state()['rect']
                #print 'cam_rect', cam_rect
                r.top= cam_rect.top
                r.bottom = cam_rect.bottom
                cam.set_state({'rect':r})
            finally:
                cam._linked_cameras_no_update = None