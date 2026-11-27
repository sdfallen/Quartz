"""Ücretsiz sohbet in the chat service (27 Nov 2026): a conversation marked free talks only to the
user's consented free channels (core.free_chat). It is routed before every other branch of
send_message, so no job, repair, skill, desktop, research or project path is ever reached from it.

Fides 27 Nov (FS1, FS2, FS4):
- A free conversation's id starts with ``free-``: SpeS gives it at creation and it never changes,
  so the page layer can refuse every tool path from the id alone, before any side effect.
- A round is owned: one generation per conversation, a Stop (cancel_active), a newer message or
  closing SpeS ends it, and nothing is published after that — the check sits under the service
  lock right before every write. A reply that arrives after Stop is dropped, never "completed".
- A refusal ends the whole round: no other speaker is asked the same thing in that round.
"""
from __future__ import annotations

import threading

from core.free_chat import CHANNELS, FreeChat, FreeChatError, EXPLAIN, build_messages, history_messages

FREE_AGENT = "free"
FREE_PREFIX = "free-"


def is_free_id(conversation_id) -> bool:
    return str(conversation_id or "").startswith(FREE_PREFIX)


def is_free(conversation) -> bool:
    return bool(isinstance(conversation, dict) and (conversation.get("free") or is_free_id(conversation.get("id"))))


class FreeChatMixin:
    _free_chat_service = None

    def _free(self) -> FreeChat:
        if self._free_chat_service is None:
            from core.free_chat import home
            from core.free_chat_codex import CodexAccountChannel
            service = getattr(self, "agent_service", None)
            # The ChatGPT-account channel runs on the app's own CodexRuntime (one owner of Codex
            # processes); its turns get folders under free_chat\codex-rooms.
            account = CodexAccountChannel(lambda: getattr(service, "codex", None), home())
            self._free_chat_service = FreeChat(account=account)
        return self._free_chat_service

    def _free_rounds(self) -> dict:
        rounds = self.__dict__.get("_free_round_state")
        if rounds is None:
            rounds = self.__dict__["_free_round_state"] = {}
        return rounds

    # ── the Bağlantılar screen ─────────────────────────────────────────────────────────
    def free_chat_action(self, action: str, data: dict | None = None) -> dict:
        data = dict(data or {})
        free = self._free()
        if action == "status":
            return free.status()
        if action == "connect":
            return free.connect(str(data.get("channel") or ""), str(data.get("key") or ""),
                                send=bool(data.get("send")), backup=bool(data.get("backup")))
        if action == "account_login":
            return free.account_login()
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
        conversation = self.store.create(title="Ücretsiz Sohbet", agent=FREE_AGENT, space="chat", free=True)
        return self.store.get(conversation["id"])

    # ── one turn ───────────────────────────────────────────────────────────────────────
    def _free_chat_turn(self, conversation: dict, text: str) -> dict:
        cid = conversation["id"]
        free = self._free()
        speakers = free.speakers()
        with self._lock:
            if self._closed:
                raise RuntimeError("SpeS kapanıyor; yeni mesaj alınmadı.")
            user = self.store.append_message(cid, "user", text, sender="user", metadata={
                "sender": "user", "recipient": "all", "free_chat": True,
                "sequence": self._next_sequence(self.store.get(cid))})
            if not speakers:
                note = self.store.append_message(cid, "assistant", (
                    "Ücretsiz sohbet için henüz bir hesap bağlanmadı. Ücretsiz bağlantılar ekranından "
                    "Gemini, OpenRouter (Kimi) ya da Groq için ücretsiz bir anahtar ekle; SpeS gerisini halleder."),
                    sender="quartz", metadata={"sender": "quartz", "recipient": "user", "status": "completed",
                                               "free_chat": True, "sequence": self._next_sequence(self.store.get(cid))})
                return {"conversation_id": cid, "user_message": user, "assistant_message": note, "agent": "quartz"}
            rounds = self._free_rounds()
            previous = rounds.get(cid)
            if previous is not None:
                previous["cancel"].set()  # a new message supersedes a round still talking
            generation = (previous or {}).get("generation", 0) + 1
            cancel = threading.Event()
            state = {"generation": generation, "cancel": cancel, "running": True}
            rounds[cid] = state
            first = self._free_bubble(cid, speakers[0])
        threading.Thread(target=self._free_round, args=(cid, speakers, state, first), daemon=True,
                         name="spes-free-chat").start()
        return {"conversation_id": cid, "user_message": user, "assistant_message": first, "agent": FREE_AGENT,
                "status": "running"}

    def _free_bubble(self, cid, channel):
        persona = CHANNELS[channel]["persona"]
        return self.store.append_message(cid, "assistant", "", sender=FREE_AGENT, metadata={
            "sender": FREE_AGENT, "recipient": "user", "status": "running", "free_chat": True,
            "free_channel": channel, "free_persona": persona, "sequence": self._next_sequence(self.store.get(cid))})

    def _free_owned(self, cid, state) -> bool:
        """Under self._lock: this round may still write (not stopped, not superseded, not closing)."""
        return (not self._closed and not state["cancel"].is_set()
                and self._free_rounds().get(cid) is state)

    def free_stop(self, cid=None) -> int:
        """Stop the free rounds of one conversation (or all); returns how many were running."""
        with self._lock:
            stopped = 0
            for key, state in list(self._free_rounds().items()):
                if cid is None or key == cid:
                    if state.get("running"):
                        stopped += 1
                    state["cancel"].set()
            return stopped

    def free_poll(self):
        """The running free round of the active conversation, for the page's polling."""
        with self._lock:
            try:
                active = self.store.get_active()
            except Exception:
                return None
            state = self._free_rounds().get(active.get("id"))
            if not state or not state.get("running"):
                return None
            cid = active["id"]
        messages = self.store.get(cid).get("messages", [])
        running = next((m for m in reversed(messages) if m.get("status") == "running"
                        and (m.get("metadata") or {}).get("free_chat")), None)
        return {"active": True, "status": "running", "outcome": "running", "agent": FREE_AGENT,
                "task_id": f"free-{state['generation']}", "queued_instructions": 0, "stop_receipt": None,
                "conversation_id": cid, "message_id": (running or {}).get("id"),
                "content": (running or {}).get("content", ""), "metadata": dict((running or {}).get("metadata") or {}),
                "agent_progress": {}, "messages": messages, "single_writer": {}}

    def _free_round(self, cid, speakers, state, first):
        """Each consented speaker answers once, in order, seeing what was said before it in this
        round. Stop, a newer message or closing ends it; nothing is written after that."""
        free = self._free()
        personas = [CHANNELS[c]["persona"] for c in speakers]
        round_replies, bubble = [], first
        try:
            for index, channel in enumerate(speakers):
                persona = CHANNELS[channel]["persona"]
                with self._lock:
                    if not self._free_owned(cid, state):
                        if bubble is not None:
                            self.store.update_message_content(cid, bubble["id"], "(durduruldu)",
                                                              metadata={"status": "cancelled"})
                        return
                    if bubble is None:
                        bubble = self._free_bubble(cid, channel)
                try:
                    history = history_messages(self.store.get(cid).get("messages", []),
                                               lambda c: CHANNELS.get(c, {}).get("persona", c))
                    messages = build_messages(persona, personas, history, round_replies)
                    result = free.reply(channel, messages, state["cancel"])
                except Exception as exc:  # a bug here never leaves a bubble running
                    result = {"text": "", "channel": None, "attempts": [], "outcome": f"other:{type(exc).__name__}"}
                with self._lock:
                    # Fides FS2: the publication barrier, right before the write.
                    if not self._free_owned(cid, state):
                        self.store.update_message_content(cid, bubble["id"], "(durduruldu; geç gelen yanıt yazılmadı)",
                                                          metadata={"status": "cancelled",
                                                                    "free_attempts": result.get("attempts")})
                        return
                    if result["outcome"] == "ok":
                        answered = result["channel"]
                        speaker = CHANNELS[answered]["persona"]
                        meta = {"status": "completed", "free_channel": answered, "free_persona": speaker,
                                "free_attempts": result["attempts"]}
                        if answered != channel:
                            meta["free_backup_for"] = persona
                        self.store.update_message_content(cid, bubble["id"], result["text"], metadata=meta)
                        round_replies.append((speaker, result["text"]))
                        bubble = None
                        continue
                    self.store.update_message_content(cid, bubble["id"], self._free_failure_text(persona, result),
                                                      metadata={"status": "completed", "free_failed": True,
                                                                "free_attempts": result["attempts"]})
                    bubble = None
                    if result["outcome"] in {"refused", "cancelled"}:
                        # Fides FS4: a refusal ends the round; no other speaker is asked the same thing.
                        return
        finally:
            with self._lock:
                state["running"] = False

    @staticmethod
    def _free_failure_text(persona, result) -> str:
        """Every attempt said plainly: which service, what happened (Fides F2)."""
        lines = []
        for attempt in result.get("attempts") or []:
            label = CHANNELS.get(attempt.get("channel"), {}).get("label", attempt.get("channel"))
            lines.append(f"• {label}: {EXPLAIN.get(attempt.get('result'), attempt.get('result'))}")
        head = {"exhausted": f"{persona} şu an yanıt veremedi; izin verdiğin ücretsiz kanalların hepsi denendi.",
                "refused": f"{persona} bu isteği yanıtlamadı. SpeS bunu başka bir modele sormaz; bu tur burada bitti."
                }.get(result.get("outcome"), f"{persona} yanıt veremedi.")
        return head + ("\n" + "\n".join(lines) if lines else "")
