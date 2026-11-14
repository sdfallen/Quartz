"""Research results as cards, not bare links (user request 14 Nov 2026).

"Kriterlere uyan freelance işleri araştırın, en uygunlarını liste yapın": the answering
agent appends one fenced ``spes-kartlar`` JSON block; SpeS removes it from the text and
shows cards (title, description, source, why it fits, link inside the card) in Sohbet,
Workspace and on the phone. Card content is the agent's claim: links are http/https
only, every field is bounded, and the UI renders it as text.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

BLOCK = re.compile(r"```\s*spes-kartlar\s*\n(.*?)```", re.S | re.I)
OPEN_BLOCK = re.compile(r"```\s*spes-kartlar\b.*\Z", re.S | re.I)  # still streaming
MAX_CARDS = 12
LIMITS = {"title": 140, "description": 420, "source": 80, "url": 500, "price": 60, "deadline": 60}

_ASKS_FOR_LIST = re.compile(
    r"(araştır|listele|liste\s+(?:halinde|yap|olarak|çıkar)|en\s+uygun(?:lar)?ı|seçenekleri|öner(?:ir\s+misin|in|)\b|"
    r"\bbul(?:un|ur\s+musun|abilir\s+misin)?\b|karşılaştır|search\s+for|find\s+me|list\s+(?:the|some))", re.I)

CARDS_RULE = (
    "SONUÇ KARTLARI: Kullanıcı bir araştırma ya da liste istiyor. Cevabının sonuna tek bir blok ekle; "
    "bağlantıları metne yazma, kartlara koy:\n"
    "```spes-kartlar\n"
    '[{"title": "kısa başlık", "description": "1-2 cümle açıklama ve neden uygun", '
    '"url": "https://...", "source": "site adı", "price": "varsa bütçe", "deadline": "varsa süre", '
    '"tags": ["en fazla 3 kısa etiket"]}]\n'
    "```\n"
    f"En fazla {MAX_CARDS} kart. Yalnız gerçekten gördüğün sonuçları yaz; bağlantı uydurma. "
    "Kart bulamadıysan bloğu hiç ekleme ve nedenini söyle.\n")


def wants_cards(text: str) -> bool:
    return bool(_ASKS_FOR_LIST.search(str(text or "")))


def _clean_url(value) -> str:
    url = str(value or "").strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc or any(c in url for c in " \n\r\t\"'<>"):
        return ""
    return url[:LIMITS["url"]]


def _card(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    card = {key: " ".join(str(raw.get(key) or "").split())[:limit]
            for key, limit in LIMITS.items() if key != "url"}
    card["url"] = _clean_url(raw.get("url"))
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    card["tags"] = [" ".join(str(t).split())[:40] for t in tags[:3] if str(t).strip()]
    if not card["title"]:
        return None
    return {k: v for k, v in card.items() if v}


def extract_cards(text: str) -> tuple[str, list[dict]]:
    """``(text without the block, cards)``; a malformed block is removed and yields no cards."""
    source = str(text or "")
    cards: list[dict] = []
    for match in BLOCK.finditer(source):
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            data = data.get("cards") or data.get("kartlar") or []
        for raw in data if isinstance(data, list) else []:
            card = _card(raw)
            if card and len(cards) < MAX_CARDS:
                cards.append(card)
    cleaned = OPEN_BLOCK.sub("", BLOCK.sub("", source)).strip()
    return cleaned, cards


def hide_open_block(text: str) -> str:
    """While a reply streams, never show the half-written JSON."""
    return OPEN_BLOCK.sub("", BLOCK.sub("", str(text or ""))).rstrip()
