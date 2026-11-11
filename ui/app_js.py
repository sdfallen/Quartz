"""Static composition of the application script; no GUI/provider imports or side effects."""

from ui.js_setup import JAVASCRIPT as SETUP
from ui.js_messages import JAVASCRIPT as MESSAGES
from ui.js_chat import JAVASCRIPT as CHAT
from ui.js_repair_plan import JAVASCRIPT as REPAIR_PLAN
from ui.js_desktop import JAVASCRIPT as DESKTOP
from ui.js_diagnostics import JAVASCRIPT as DIAGNOSTICS
from ui.js_advanced import JAVASCRIPT as ADVANCED
from ui.js_workspace import JAVASCRIPT as WORKSPACE
from ui.js_lifecycle import JAVASCRIPT as LIFECYCLE

SCRIPT_PARTS = (SETUP, MESSAGES, CHAT, REPAIR_PLAN, DESKTOP, DIAGNOSTICS, ADVANCED, LIFECYCLE, WORKSPACE,)
APPLICATION_JS = "".join(SCRIPT_PARTS)
SCRIPT_DOCUMENT = '<script>' + APPLICATION_JS + '</script>\n\n</body>\n</html>\n'
