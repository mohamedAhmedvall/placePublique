# Imports différés pour éviter les erreurs si cv2/ultralytics ne sont pas installés
def detect(*args, **kwargs):
    from .detector import detect as _detect
    return _detect(*args, **kwargs)


def start_scheduler(*args, **kwargs):
    from .scheduler import start_scheduler as _start
    return _start(*args, **kwargs)


__all__ = ["detect", "start_scheduler"]
