"""Two spaces, one rule (user request 14 Nov 2026).

SpeS has two sides, like Claude's chat and code apps:

- **Sohbet** ("chat"): a place to talk. Agents are warm and friendly, answer briefly and
  never start work: no project files, no desktop control, no writes. They may search
  the web (core.web_policy). A work request here is answered with a pointer to the
  Workspace, and the user gets a one-click "open it in Workspace" chip.
- **Workspace** ("work"): a place to get work done. Agents are formal, precise and
  task-focused; tasks, desktop control, file writes and finish reports live here.

The space is a stored property of each conversation, not a guess from the wording, so
task messages and small talk never mix. Older conversations (and phone clients that
send no space) count as Workspace: that is how they behaved before the split.
"""
from __future__ import annotations

SPACES = ("chat", "work")
DEFAULT_SPACE = "work"
LABELS = {"chat": "Sohbet", "work": "Workspace"}


def normalize(space) -> str:
    value = str(space or "").strip().lower()
    return value if value in SPACES else DEFAULT_SPACE


def space_of(conversation) -> str:
    return normalize((conversation or {}).get("space") if isinstance(conversation, dict) else None)


def is_chat(conversation) -> bool:
    return space_of(conversation) == "chat"


# One voice per agent and space. The names and points of view stay; the register changes.
CHAT_VOICE = {
    "claude": ("Sohbet alanındasın: sıcak, samimi ve içten konuş; kullanıcıyla eski bir arkadaş gibi. "
               "Merak et, kısa bir soru sorabilirsin; ince bir espri uygunsa kaçırma."),
    "codex": ("Sohbet alanındasın: rahat, güler yüzlü ve doğal konuş; arkadaşça bir dille, "
              "gerektiğinde hafif esprilere yer ver."),
    "antigravity": ("Sohbet alanındasın: sakin ama sıcak konuş; düşünceli ve nazik bir arkadaş gibi, "
                    "kısa ve içten cümlelerle."),
}
WORK_VOICE = {
    "claude": ("Workspace'tesin: ekibin orkestratörüsün. Resmi, net ve profesyonel yaz; iş bölümünü sen "
               "yaparsın, kararı kanıta dayandırırsın. Samimiyet, espri ve dolgu cümlesi yok."),
    "codex": ("Workspace'tesin: resmi ve kesin yaz. Yapılan işi, kanıtı ve açık kalan konuyu net söyle; "
              "espri ve dolgu cümlesi yok."),
    "antigravity": ("Workspace'tesin: resmi, analitik ve kısa yaz. Riski ve doğrulama sonucunu açıkça "
                    "belirt; espri ve dolgu cümlesi yok."),
}

CHAT_SPACE_RULE = (
    "[SOHBET ALANI] Burası SpeS'in sohbet alanı, iş alanı değil. Bu alanda dosya okumaz, yazmaz, "
    "bilgisayarı kontrol etmez ve görev başlatmazsın. Kullanıcı bir iş isterse bunu yapmış gibi "
    "davranma; samimi bir cümleyle işi Workspace'te görev olarak vermesini öner (SpeS ona tek "
    "tıkla Workspace'e taşıma düğmesi gösteriyor).\n")
WORK_SPACE_RULE = (
    "[WORKSPACE] Burası SpeS'in çalışma alanı. Yanıtların resmi, net ve göreve odaklı olsun: "
    "ne yapıldı, kanıt ne, açık kalan ne. Selamlaşma gibi kısa mesajlara da kısa ve resmi cevap ver.\n")

# Team small talk keeps its length limits; the register follows the space.
CHAT_TEAM_RULE = ("SOHBET MODU: Bu bir iş değil, arkadaşça bir sohbet. Sıcak, samimi ve doğal konuş, sade "
                  "Türkçe kullan. En fazla 2 kısa cümle (yaklaşık 25 kelime). Plan, süreç, iş bölümü, "
                  "mimari veya risk anlatma; teknik terim kullanma. Başlık, liste ve kod yok. Dahili kimlik "
                  "veya araç adı yazma.\n")
WORK_BRIEF_RULE = ("KISA YANIT: Bu mesaj bir görev değil. Resmi ve net, en fazla 2 kısa cümleyle cevap ver; "
                   "gerekiyorsa işi görev olarak nasıl verebileceğini söyle. Başlık, liste ve kod yok. Dahili "
                   "kimlik veya araç adı yazma.\n")


def voice(agent: str, space: str) -> str:
    table = CHAT_VOICE if normalize(space) == "chat" else WORK_VOICE
    return table.get(agent, "")


def space_rule(space: str) -> str:
    return CHAT_SPACE_RULE if normalize(space) == "chat" else WORK_SPACE_RULE


def team_chat_rule(space: str) -> str:
    return CHAT_TEAM_RULE if normalize(space) == "chat" else WORK_BRIEF_RULE
