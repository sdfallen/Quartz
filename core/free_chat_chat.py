"""Ücretsiz sohbet in the chat service (27 Nov 2026): a conversation marked free talks only to the
user's consented free channels (core.free_chat). It is routed before every other branch of
send_message, so no job, repair, skill, desktop, research or project path is ever reached from it
(Fides F-cond. 2: a server-side capability, not a hidden button)."""
from __future__ import annotations

import threading

from core.free_chat import CHANNELS, FreeChat, FreeChatError, EXPLAIN, build_messages, history_messages

FREE_AGENT = "free"


def is_free(conversation) -> bool:
    return bool(isinstance(conversation, dict) and conversation.get("free"))


class FreeChatMixin:
    _free_chat_service = None

    def _free(self) -> FreeChat:
        if self._free_chat_service is None:
            self._free_chat_service = FreeChat()
        return self._free_chat_service

    # ── the Bağlantılar screen ─────────────────────────────────────────────────────────
    def free_chat_action(self, action: str, data: dict | None = None) -> dict:
        data = dict(data or {})
        free = self._free()
        if action == "status":
            return free.status()
        if action == "connect":
            return free.connect(str(data.get("channel") or ""), str(data.get("key") or ""),
                                send=bool(data.get("send", True)), backup=bool(data.get("backup", True)))
        if action == "disconnect":
            return free.disconnect(str(data.get("channel") or ""))
        if action == "consent":
            return free.consent(str(data.get("channel") or ""), send=data.get("send"), backup=data.get("backup"))
        if action == "order":
            free.settings.set_order(list(data.get("order") or []))
            return free.status()
        if action == "new":
            return self.new_free_conversation()
        if action == "is_free":
            try:
                return {"free": is_free(self.store.get(str(data.get("conversation_id") or "")))}
            except Exception:
                return {"free": False}
        raise FreeChatError("Bilinmeyen işlem.")

    def new_free_conversation(self) -> dict:
        conversation = self.store.create(title="Ücretsiz Sohbet", agent=FREE_AGENT, space="chat")
        self.store.mark_free(conversation["id"])
        return self.store.get(conversation["id"])

    # ── one turn ───────────────────────────────────────────────────────────────────────
    def _free_chat_turn(self, conversation: dict, text: str) -> dict:
        cid = conversation["id"]
        free = self._free()
        speakers = free.speakers()
        with self._lock:
            user = self.store.append_message(cid, "user", text, sender="user", metadata={
                "sender": "user", "recipient": "all", "free_chat": True,
                "sequence": self._next_sequence(self.store.get(cid))})
        if not speakers:
            with self._lock:
                note = self.store.append_message(cid, "assistant", (
                    "Ücretsiz sohbet için henüz bir hesap bağlanmadı. Ayarlar → Ücretsiz bağlantılar'dan "
                    "Gemini, OpenRouter (Kimi) ya da Groq için ücretsiz bir anahtar ekle; SpeS gerisini halleder."),
                    sender="quartz", metadata={"sender": "quartz", "recipient": "user", "status": "completed",
                                               "free_chat": True, "sequence": self._next_sequence(self.store.get(cid))})
            return {"conversation_id": cid, "user_message": user, "assistant_message": note, "agent": "quartz"}
        cancel = threading.Event()
        with self._lock:
            self._free_cancels = getattr(self, "_free_cancels", {})
            previous = self._free_cancels.get(cid)
            if previous is not None:
                previous.set()  # a new message supersedes a round still talking
            self._free_cancels[cid] = cancel
        threading.Thread(target=self._free_round, args=(cid, speakers, cancel), daemon=True,
                         name="spes-free-chat").start()
        return {"conversation_id": cid, "user_message": user, "agent": FREE_AGENT, "status": "running"}

    def free_chat_stop(self, cid) -> None:
        with self._lock:
            event = (getattr(self, "_free_cancels", {}) or {}).get(cid)
        if event is not None:
            event.set()

    def _free_round(self, cid, speakers, cancel):
        """Each consented speaker answers once, in order, seeing what was said before it in this
        round: a conversation, a discussion — like the free apps, with several minds."""
        free = self._free()
        personas = [CHANNELS[c]["persona"] for c in speakers]
        round_replies = []
        for channel in speakers:
            if cancel.is_set():
                return
            persona = CHANNELS[channel]["persona"]
            with self._lock:
                bubble = self.store.append_message(cid, "assistant", "", sender=FREE_AGENT, metadata={
                    "sender": FREE_AGENT, "recipient": "user", "status": "running", "free_chat": True,
                    "free_channel": channel, "free_persona": persona,
                    "sequence": self._next_sequence(self.store.get(cid))})
            try:
                history = history_messages(self.store.get(cid).get("messages", []),
                                           lambda c: CHANNELS.get(c, {}).get("persona", c))
                messages = build_messages(persona, personas, history, round_replies)
                result = free.reply(channel, messages, cancel)
            except Exception as exc:  # a bug here never leaves a bubble running
                result = {"text": "", "channel": None, "attempts": [], "outcome": f"other:{type(exc).__name__}"}
            answered = result.get("channel")
            if result["outcome"] == "ok":
                speaker = CHANNELS[answered]["persona"]
                meta = {"status": "completed", "free_channel": answered, "free_persona": speaker,
                        "free_attempts": result["attempts"]}
                if answered != channel:
                    meta["free_backup_for"] = persona
                self.store.update_message_content(cid, bubble["id"], result["text"], metadata=meta)
                round_replies.append((speaker, result["text"]))
                continue
            if result["outcome"] == "cancelled" or cancel.is_set():
                self.store.update_message_content(cid, bubble["id"], "(durduruldu)", metadata={
                    "status": "cancelled", "free_attempts": result["attempts"]})
                return
            self.store.update_message_content(cid, bubble["id"], self._free_failure_text(persona, result),
                                              metadata={"status": "completed", "free_failed": True,
                                                        "free_attempts": result["attempts"]})

    @staticmethod
    def _free_failure_text(persona, result) -> str:
        """Every attempt said plainly: which service, what happened (Fides F2)."""
        lines = []
        for attempt in result.get("attempts") or []:
            label = CHANNELS.get(attempt.get("channel"), {}).get("label", attempt.get("channel"))
            lines.append(f"• {label}: {EXPLAIN.get(attempt.get('result'), attempt.get('result'))}")
        head = {"exhausted": f"{persona} şu an yanıt veremedi; bağlı ücretsiz kanalların hepsi denendi.",
                "refused": f"{persona} bu isteği yanıtlamadı; SpeS bunu başka bir modelle aşmaya çalışmaz."
                }.get(result.get("outcome"), f"{persona} yanıt veremedi.")
        return head + ("\n" + "\n".join(lines) if lines else "")
