"""Conservative local routing; permission selection is not an action request.

No extra model round-trip. Ambiguous/discussion messages stay text-only; this
decision never grants access. Active-task continuation is handled by the host.
"""
import re


def tools_disallowed(text):
    value = str(text or '').casefold().replace('\u0307', '')
    value = re.sub(r'```[\s\S]*?```|`[^`]*`|[“"].*?[”"]', ' ', value)
    return bool(re.search(r'sadece (?:sohbet edelim|konuşalım|konusalım)|'
                         r'(?:araç|tool) kullanma(?:dan|yın|yin)?\b|işlem yapma(?:dan|yın|yin)?\b|'
                         r'hiçbir işlem yapma\b|hiçbir araç kullanma\b', value)
                or re.fullmatch(r'\s*(?:lütfen )?sadece sohbet[.!]?\s*', value))


def message_intent(text):
    value = str(text or '').casefold().replace('\u0307', '').strip()
    value = re.sub(r'```[\s\S]*?```|`[^`]*`|[“"].*?[”"]', ' ', value)
    if tools_disallowed(value):
        return 'conversation'
    if re.fullmatch(r'\s*(?:devam et|devam|sürdür|evet|olur|tamam|dur|durdur|görevi durdur|kontrolü durdur|iptal et)[.!]?\s*', value):
        return 'continuation'
    # Explanatory questions do not execute the operation being discussed.
    explicit = re.search(
        r'\b(?:incele(?:yin|yiniz|yip|yerek)?|düzelt(?:in|iniz)?|derle(?:yin)?|geliştir(?:in)?|'
        r'çalıştır(?:ın|in)?|başlat(?:ın)?|aç(?:ın|in)?|oku(?:yun)?|araştır(?:ın)?|'
        r'tıkla(?:yın)?|yükle(?:yin)?|kaydet|sil|ekle(?:yin)?|oluştur(?:un)?|'
        r'test et|kontrol et|test edip|kontrol edip|debug yap|test yap|bi(?:r)? test bakalım|dene(?:yin)?|bul|tara|yaz|güncelle|değiştir)\b', value)
    polite = re.search(r'(?:inceleyebilir|düzeltebilir|açabilir|çalıştırabilir|bakabilir|test edebilir|kontrol edebilir)\s+misin', value)
    # "nasıl düzeltiriz?" is discussion, "önce dosyayı incele, sonra anlat" is work.
    if explicit or polite:
        return 'task'
    return 'conversation'
