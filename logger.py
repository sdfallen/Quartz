"""
logger.py  —  Quartz Logger
"""
import logging
import os
import time
import threading
import contextlib
import contextvars
from logging.handlers import RotatingFileHandler
import config
from config import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT


_request_id = contextvars.ContextVar("quartz_request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


@contextlib.contextmanager
def request_context(request_id: str):
    token = _request_id.set(request_id or "-")
    try:
        yield
    finally:
        _request_id.reset(token)


class SafeRotatingFileHandler(RotatingFileHandler):
    """Windows-safe rotating file handler that catches and retries or gracefully handles WinError 32."""

    def doRollover(self):
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # On Windows, if another handle momentarily holds the log file open,
            # close stream, sleep briefly, and retry rollover.
            if self.stream:
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            time.sleep(0.05)
            try:
                super().doRollover()
            except (PermissionError, OSError):
                # If still locked by an external process/tailer, continue appending
                # without crashing or terminating the application.
                if not self.stream:
                    self.stream = self._open()


_handlers_lock = threading.Lock()
_shared_console_handler: logging.StreamHandler | None = None
_shared_file_handlers: dict[tuple[str, int, int], SafeRotatingFileHandler] = {}


def _get_shared_console_handler(fmt: logging.Formatter) -> logging.StreamHandler:
    global _shared_console_handler
    with _handlers_lock:
        if _shared_console_handler is None:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            ch.setFormatter(fmt)
            ch.addFilter(RequestIdFilter())
            _shared_console_handler = ch
        return _shared_console_handler


def _get_shared_file_handler(fmt: logging.Formatter) -> SafeRotatingFileHandler | None:
    current_log_file = getattr(config, "LOG_FILE", LOG_FILE)
    max_bytes = getattr(config, "LOG_MAX_BYTES", LOG_MAX_BYTES)
    backup_count = getattr(config, "LOG_BACKUP_COUNT", LOG_BACKUP_COUNT)
    key = (os.path.abspath(current_log_file), max_bytes, backup_count)
    with _handlers_lock:
        if key not in _shared_file_handlers:
            try:
                fh = SafeRotatingFileHandler(
                    current_log_file, maxBytes=max_bytes,
                    backupCount=backup_count, encoding="utf-8")
                fh.setLevel(logging.DEBUG)
                fh.setFormatter(fmt)
                fh.addFilter(RequestIdFilter())
                _shared_file_handlers[key] = fh
            except Exception:
                return None
        return _shared_file_handlers[key]


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] "
        "%(name)s [req=%(request_id)s]: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Attach singleton console handler
    ch = _get_shared_console_handler(fmt)
    if ch not in logger.handlers:
        logger.addHandler(ch)

    # Attach singleton file handler
    fh = _get_shared_file_handler(fmt)
    if fh is not None and fh not in logger.handlers:
        logger.addHandler(fh)

    return logger
