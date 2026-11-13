"""Birlikte (team) mode: three agents plan, critique and build together in the chat.

User request, 13 Nov 2026: in Birlikte mode the agents must not take turns blindly.
They split the work by talking in the chat, plan and criticise the plan in front of
the user, and every team message is at most two or three sentences.

Flow (one user turn):
1. Usta (Claude, lead developer) posts the plan and who does what.
2. Atlas (Codex) and Vision (Antigravity) criticise it in parallel.
3. Usta posts the decision.
4. Conversation turn: Usta answers. Task turn: Usta builds (single writer) while
   Atlas prepares acceptance checks and Vision lists risks in parallel; then Atlas
   and Vision check the result in parallel, read-only; Usta closes.

Planning messages are tool-less runs; only the lead's build step may write. The
existing writer lock, Stop and evidence rules apply unchanged to every run.
"""
from __future__ import annotations

import re
import threading

from core.agent_character import PERSONAS, character_instruction

TEAM = ("claude", "codex", "antigravity")
LEAD = "claude"
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÇĞİÖŞÜ0-9\"'(“])")


CHARS_PER_SENTENCE = 160  # semicolon chains still read as a paragraph (live 13 Nov)


def clamp_sentences(text: str, limit: int) -> str:
    """Keep at most ``limit`` sentences and about ``limit * 160`` characters (one paragraph)."""
    flat = " ".join(str(text or "").split())
    if not flat:
        return ""
    short = " ".join(_SENTENCE_END.split(flat)[:limit]).strip()
    budget = limit * CHARS_PER_SENTENCE
    if len(short) > budget:
        cut = short[:budget].rsplit(" ", 1)[0].rstrip(",;:—-")
        short = cut + "…"
    return short


def persona_name(agent: str) -> str:
    return PERSONAS.get(agent, {}).get("name", agent)


class TeamTurnMixin:
    """Methods mixed into AgentChatService; relies on its executors and store."""

    def _team_ready(self) -> bool:
        """Team mode needs a logged-in Claude lead; otherwise the classic pair runs."""
        try:
            return self.agent_service.claude.probe().get("ready") is True
        except Exception:
            return False

    # -- one team message ---------------------------------------------------
    def _team_say(self, cid, msg_id, agent, prompt, project_id, *, step, limit=3,
                  tool_less=True, write=False, confirm_write=False, full_access=False,
                  project_scope=False):
        """Run one agent into its bubble; planning messages are clamped to ``limit`` sentences."""
        base_meta = {"sender": agent, "agent": agent, "recipient": "all", "collaboration": True,
                     "team": True, "team_step": step, "persona": persona_name(agent)}
        if agent == "antigravity":
            text = self._execute_antigravity_bubble(
                cid, msg_id, prompt, project_id, write, confirm_write, use_session=False,
                base_meta=base_meta, full_access=full_access, tool_less=tool_less,
                project_scope=project_scope)
        else:
            text = self._execute_codex_bubble(
                cid, msg_id, prompt, project_id, write, confirm_write, use_session=False,
                base_meta=base_meta, full_access=full_access, agent=agent, tool_less=tool_less,
                project_scope=project_scope)
        short = clamp_sentences(text, limit) if (limit and text) else text
        with self._lock:
            # Same cancellation fence as the executors' own publishing.
            if text and not self._is_turn_cancelled(msg_id):
                message = next((m for m in self.store.get(cid).get("messages", []) if m["id"] == msg_id), None)
                if message is not None:
                    meta = {**(message.get("metadata") or {}), **base_meta}
                    if short != text:
                        meta["team_full_text"] = text[:8000]
                    self.store.update_message_content(cid, msg_id, short, metadata=meta)
        return short

    def _team_bubble(self, cid, agent, step, owner_msg_id):
        msg = self._create_group_bubble(cid, sender=agent, recipient="all", squad_task_id=None,
                                        round_num=step, owner_msg_id=owner_msg_id)
        return msg["id"]

    def _team_parallel(self, jobs):
        """Run ``{agent: callable}`` concurrently; return ``{agent: text}`` ('' on failure)."""
        results = {}

        def run(agent, job):
            try:
                results[agent] = job() or ""
            except Exception as exc:  # one failing critic must not sink the turn
                results[agent] = ""
                results[agent + ":error"] = str(exc)

        threads = [threading.Thread(target=run, args=(a, j), daemon=True, name=f"team-{a}") for a, j in jobs.items()]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return results

    # -- prompts -------------------------------------------------------------
    @staticmethod
    def _team_header(agent):
        others = ", ".join(f"{persona_name(a)} ({a.capitalize() if a != 'antigravity' else 'Antigravity'})"
                           for a in TEAM if a != agent)
        return (f"Quartz ekibindesin; ekip: sen, {others} ve kullanıcı. Herkes sohbeti görüyor.\n"
                + character_instruction(agent))

    @staticmethod
    def _team_rules(limit):
        return (f"KURAL: En fazla {limit} cümle, tek paragraf; başlık, liste ve kod bloğu yok. "
                "Dahili kimlik veya araç adı yazma. Görmediğini görmüş gibi yazma.\n")

    def _team_transcript(self, cid, since_msg_id):
        lines, seen = [], False
        for message in self.store.get(cid).get("messages", []):
            if message.get("id") == since_msg_id:
                seen = True
            if not seen or message.get("role") != "assistant":
                continue
            content = (message.get("content") or "").strip()
            sender = (message.get("metadata") or {}).get("sender") or message.get("sender")
            if content and sender in TEAM:
                lines.append(f"{persona_name(sender)}: {content[:1200]}")
        return "\n".join(lines)

    # -- the turn ----------------------------------------------------------
    def _run_team_turn(self, cid, first_msg_id, prompt, project_id, *, write=False, confirm_write=False,
                       full_access=False):
        if self._is_turn_cancelled(first_msg_id):
            return
        chat_only = self._conversation_only(cid) or not (write and confirm_write)
        user_block = f"\n--- KULLANICININ MESAJI ---\n{prompt}\n"

        # 1. Plan and work split by the lead (first bubble already belongs to Claude).
        self._set_turn_progress("Usta planı ve iş bölümünü yazıyor…", current_msg_id=first_msg_id)
        plan = self._team_say(cid, first_msg_id, LEAD, self._team_header(LEAD) + self._team_rules(3) + (
            "Görevin: kullanıcının isteği için kısa bir plan ve iş bölümü öner (kim ne yapacak: "
            "Usta, Atlas, Vision). Sohbet sorusuysa nasıl yanıtlayacağınızı söyle.\n") + user_block,
            project_id, step=1)
        if self._is_turn_cancelled(first_msg_id) or not plan:
            with self._lock:
                self._finish_turn(first_msg_id, "failed")
            return

        # 2. Atlas and Vision criticise the plan at the same time.
        self._set_turn_progress("Atlas ve Vision planı eleştiriyor…", current_msg_id=first_msg_id)
        critique_ids = {a: self._team_bubble(cid, a, 2, first_msg_id) for a in ("codex", "antigravity")}
        transcript = self._team_transcript(cid, first_msg_id)

        def critique(agent):
            return lambda: self._team_say(cid, critique_ids[agent], agent, self._team_header(agent) + self._team_rules(2) + (
                "Görevin: Usta'nın planını eleştir. Katılıyorsan nedenini ve eklediğin şeyi, katılmıyorsan "
                "riski ve önerdiğin değişikliği söyle.\n") + user_block + f"\n--- EKİP SOHBETİ ---\n{transcript}\n",
                project_id, step=2, limit=2)
        critiques = self._team_parallel({a: critique(a) for a in critique_ids})
        if self._is_turn_cancelled(first_msg_id):
            return

        # 3. The lead decides, taking the critiques into account.
        self._set_turn_progress("Usta kararı yazıyor…", current_msg_id=first_msg_id)
        decision_id = self._team_bubble(cid, LEAD, 3, first_msg_id)
        transcript = self._team_transcript(cid, first_msg_id)
        if chat_only:
            final = self._team_say(cid, decision_id, LEAD, self._team_header(LEAD) + (
                "Görevin: eleştirileri tart ve kullanıcıya ekibin ortak yanıtını ver. Açık kalan anlaşmazlık "
                "varsa bir cümleyle belirt. En fazla 5 cümle, sade.\n") + user_block
                + f"\n--- EKİP SOHBETİ ---\n{transcript}\n", project_id, step=3, limit=5)
            with self._lock:
                self._finish_turn(first_msg_id, "completed" if final else "partial")
            return
        decision = self._team_say(cid, decision_id, LEAD, self._team_header(LEAD) + self._team_rules(3) + (
            "Görevin: eleştirileri tart ve son kararı yaz: ne yapılacak, kim yapacak. Haklı itirazı benimse, "
            "katılmadığını gerekçesiyle reddet.\n") + user_block + f"\n--- EKİP SOHBETİ ---\n{transcript}\n",
            project_id, step=3)
        if self._is_turn_cancelled(first_msg_id):
            return

        # 4. Build (lead, the only writer) while Atlas and Vision prepare in parallel.
        self._set_turn_progress("Usta inşa ediyor; Atlas kontrolleri, Vision riskleri hazırlıyor…",
                                current_msg_id=first_msg_id)
        build_id = self._team_bubble(cid, LEAD, 4, first_msg_id)
        prep_ids = {a: self._team_bubble(cid, a, 4, first_msg_id) for a in ("codex", "antigravity")}
        transcript = self._team_transcript(cid, first_msg_id)
        build_prompt = self._team_header(LEAD) + (
            "Görevin: ekibin kararına göre işi şimdi sen yap; tek yazıcı sensin. Gerekli testleri çalıştır. "
            "Bitince en fazla 5 cümleyle ne yaptığını ve kanıtını (test sonucu, dosyalar) yaz.\n"
            + user_block + f"\n--- EKİP KARARI ---\n{transcript}\n")
        prep_tasks = {
            "codex": "Görevin: Usta inşa ederken bu iş için kabul kontrollerini belirle: neyi nasıl doğrulayacağız.",
            "antigravity": "Görevin: Usta inşa ederken en önemli riskleri ve gözden kaçabilecek noktaları belirt.",
        }
        jobs = {LEAD: lambda: self._team_say(cid, build_id, LEAD, build_prompt, project_id, step=4, limit=0,
                                             tool_less=False, write=write, confirm_write=confirm_write,
                                             full_access=full_access)}
        for agent, task in prep_tasks.items():
            jobs[agent] = (lambda a=agent, t=task: self._team_say(
                cid, prep_ids[a], a, self._team_header(a) + self._team_rules(3) + t + "\n" + user_block
                + f"\n--- EKİP KARARI ---\n{transcript}\n", project_id, step=4))
        built = self._team_parallel(jobs)
        if self._is_turn_cancelled(first_msg_id):
            return
        if not built.get(LEAD):
            with self._lock:
                self._finish_turn(first_msg_id, "failed")
            return

        # 5. Atlas and Vision check the result in parallel, read-only.
        self._set_turn_progress("Atlas ve Vision sonucu kontrol ediyor…", current_msg_id=first_msg_id)
        check_ids = {a: self._team_bubble(cid, a, 5, first_msg_id) for a in ("codex", "antigravity")}
        transcript = self._team_transcript(cid, first_msg_id)

        def check(agent):
            return lambda: self._team_say(cid, check_ids[agent], agent, self._team_header(agent) + self._team_rules(3) + (
                "Görevin: Usta'nın yaptığı işi proje dosyalarını okuyarak kontrol et; dosya yazma, komut çalıştırma. "
                "Kabul kontrollerine "
                "ve risklere göre ne gördüğünü, kanıtıyla söyle.\n") + user_block
                + f"\n--- EKİP SOHBETİ ---\n{transcript}\n", project_id, step=5, tool_less=False,
                project_scope=True)
        checks = self._team_parallel({a: check(a) for a in check_ids})
        if self._is_turn_cancelled(first_msg_id):
            return

        # 6. The lead closes: what is done, what the checks found, what is open.
        close_id = self._team_bubble(cid, LEAD, 6, first_msg_id)
        transcript = self._team_transcript(cid, first_msg_id)
        closing = self._team_say(cid, close_id, LEAD, self._team_header(LEAD) + self._team_rules(3) + (
            "Görevin: kullanıcıya kapanışı yaz: ne bitti, kontroller ne buldu, açık kalan ne.\n")
            + user_block + f"\n--- EKİP SOHBETİ ---\n{transcript}\n", project_id, step=6)
        complete = bool(closing) and all(checks.get(a) for a in check_ids) and all(critiques.get(a) for a in critique_ids)
        with self._lock:
            self._finish_turn(first_msg_id, "completed" if complete else "partial")
