"""First window placement: always inside the work area, so the composer is never off screen."""
import sys

DEFAULT_SIZE = (1160, 740)
# A frameless pywebview window opens this much smaller than requested.
FRAME_LOSS = (16, 39)


def fit_window(work_area, size=DEFAULT_SIZE, loss=FRAME_LOSS):
    """Return (width, height, x, y) to request for a work area (left, top, right, bottom)."""
    left, top, right, bottom = work_area
    available_w, available_h = right - left, bottom - top
    width = min(size[0], available_w + loss[0])
    height = min(size[1], available_h + loss[1])
    actual_w, actual_h = width - loss[0], height - loss[1]
    return width, height, left + max(0, (available_w - actual_w) // 2), top + max(0, (available_h - actual_h) // 2)


def work_area():
    """Primary monitor area without the taskbar, or None when Windows cannot report it."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def full_window_rect(area=None):
    """(width, height, x, y) when returning from compact; resize has no frame loss."""
    try:
        area = area or work_area()
    except (OSError, AttributeError, ValueError):
        area = None
    if area is None or area[2] <= area[0] or area[3] <= area[1]:
        return DEFAULT_SIZE[0], DEFAULT_SIZE[1], None, None
    return fit_window(area, loss=(0, 0))


def initial_geometry():
    """Keyword arguments for ``webview.create_window``."""
    try:
        area = work_area()
    except (OSError, AttributeError, ValueError):
        area = None
    if area is None or area[2] <= area[0] or area[3] <= area[1]:
        return {"width": DEFAULT_SIZE[0], "height": DEFAULT_SIZE[1]}
    width, height, x, y = fit_window(area)
    return {"width": width, "height": height, "x": x, "y": y}
