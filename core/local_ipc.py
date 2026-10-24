"""Same-process GUI/backend IPC capability. Never written to disk or UI logs.

Quartz's entrypoint loads both components in one process. Independently started
legacy clients have no capability; use quartz_entry.py rather than separate
main.py/gui.py processes. This is not isolation from a compromised same-user OS.
"""
import hmac
import secrets

_PROCESS_TOKEN = secrets.token_urlsafe(32)


def request_token():
    return _PROCESS_TOKEN


def authorized(value):
    return isinstance(value, str) and value.isascii() and hmac.compare_digest(value, _PROCESS_TOKEN)
