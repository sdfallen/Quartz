"""Conservative local routing; permission selection is not an action request.

No extra model round-trip. Ambiguous/discussion messages stay text-only; this
decision never grants access. Active-task continuation is handled by the host.
"""
import re


def instruction_text(text):
    """Only current, unquoted prose participates in task routing."""
    value = str(text or '').casefold().replace('\u0307', '')
    return re.sub(r'```[\s\S]*?```|`[^`]*`|[“"].*?[”"]', ' ', value)


def tools_disallowed(text):
    value = instruction_text(text)
    return bool(re.search(r'sadece (?:sohbet edelim|konuşalım|konusalım)|'
                         r'(?:araç|tool) kullanma(?:dan|yın|yin)?\b|işlem yapma(?:dan|yın|yin)?\b|'
                         r'hiçbir işlem yapma\b|hiçbir araç kullanma\b', value)
                or re.search(r"\b(?:do not|don't|never) use (?:any )?tools\b|\bwithout (?:using )?tools\b|"
                             r"\b(?:just chat|chat only|no tools)\b|\bdo not (?:run|execute) anything\b", value)
                or re.fullmatch(r'\s*(?:lütfen )?sadece sohbet[.!]?\s*', value))


def message_intent(text):
    value = instruction_text(text).strip()
    if tools_disallowed(value):
        return 'conversation'
    if re.fullmatch(r'\s*(?:devam et|devam|sürdür|evet|olur|tamam|dur|durdur|görevi durdur|kontrolü durdur|iptal et)[.!]?\s*', value):
        return 'continuation'
    # Explanations can mention an imperative without requesting its execution.
    # Filter individual clauses so "Chrome'u aç; oynat ne işe yarıyor?" still
    # executes the explicit first clause rather than suppressing the whole task.
    explanation = re.compile(r'ne işe yar(?:ıyor|ar)|ne (?:anlama gelir|demek)|'
                             r'\bdemek\b.{0,60}\bm[ıiuü]\b|'
                             r'hakkında (?:ne düşün|konuş)|what (?:does|is).{0,80}mean|'
                             r'\bset theory\b')
    value = '. '.join(part for part in re.split(r'[.!?;,\n]+',value) if not explanation.search(part))
    # Explanatory questions do not execute the operation being discussed.
    explicit = re.search(
        r'\b(?:incele(?:yin|yiniz|yip|yerek)?|düzelt(?:in|iniz)?|derle(?:yin)?|geliştir(?:in)?|'
        r'çalıştır(?:ın|in)?|başlat(?:ın)?|başla(?:yın|yınız)?|aç(?:ın|in|ıp)?|oku(?:yun)?|araştır(?:ın)?|'
        r'tıkla(?:yın)?|yükle(?:yin)?|kaydet|sil|ekle(?:yin)?|oluştur(?:un)?|'
        r'bak(?:ın|ınız)?|gir(?:in|iniz|ip)?|geç(?:in|iniz)?|bas(?:ın|ınız)?|seç(?:in|iniz|imi\s+yap)?|'
        r'kaydır(?:ın|ınız)?|göster(?:in|iniz)?|yönet(?:in|iniz)?|kullan(?:ın|ınız)?|ekran görüntüsü al|kontrol(?:ünü|unu)?\s+al|'
        r'yap(?:ın|ınız)?|ayarla(?:yın|yınız)?|düzenle(?:yin|yiniz)?|onar(?:ın)?|indir(?:in)?|kur(?:un)?|kaldır(?:ın)?|'
        r'taşı(?:yın)?|yenile(?:yin)?|sıfırla(?:yın)?|temizle(?:yin)?|kopyala(?:yın)?|yapıştır(?:ın)?|'
        r'çal(?:ın)?|oynat(?:ın)?|durdur(?:un)?|duraklat(?:ın)?|kıs(?:ın)?|artır(?:ın)?|yükselt(?:in)?|'
        r'ara(?:yın)?|izle(?:yin)?|dinle(?:yin)?|uygula(?:yın)?|tamamla(?:yın)?|bitir(?:in)?|harekete\s+geç(?:in)?|'
        r'analiz\s+(?:et|edin|ediniz|yap|yapın)|'
        r'test (?:et|edin|ediniz)|kontrol (?:et|edin|ediniz)|test edip|kontrol edip|debug yap|test yap|bi(?:r)? test bakalım|dene(?:yin)?|bul|tara|yaz|güncelle|değiştir|çöz(?:ün)?|kapat(?:ın)?)\b', value)
    polite = re.search(
        r'\b(?:inceleyebilir|inceler|düzeltebilir|düzeltir|açabilir|açar|çalıştırabilir|çalıştırır|'
        r'bakabilir|bakar|test edebilir|test eder|kontrol edebilir|kontrol eder|çözebilir|çözer|'
        r'kapatabilir|kapatır|güncelleyebilir|günceller|araştırabilir|araştırır|derleyebilir|derler|'
        r'ekleyebilir|ekler|silebilir|siler|girebilir|girer|geçebilir|geçer|'
        r'seçebilir|seçer|tıklayabilir|tıklar|basabilir|basar|gösterebilir|gösterir|'
        r'yapabilir|yapar|ayarlayabilir|ayarlar|düzenleyebilir|düzenler|çalabilir|çalar|oynatabilir|oynatır|'
        r'kısabilir|kısar|artırabilir|artırır|arayabilir|arar|kopyalayabilir|kopyalar|yapıştırabilir|yapıştırır|'
        r'kaydırabilir|kaydırır|yönetebilir|yönetir|kullanabilir|kullanır)\s*m[iıuü]s[iıuü]n(?:[iıuü]z)?\b', value)
    # Recognize English directives at clause starts, not verbs inside questions
    # such as "How do I run tests?" or "What happens if I open Notepad?".
    english = re.search(
        r'(?:^|[.!?;\n]\s*)(?:(?:codex|gemini|antigravity)[,:]?\s+)?'
        r'(?:(?:can|could|would) you\s+)?(?:please\s+)?'
        r'(?:open(?!\s+source\b)|inspect|fix|run|debug|update|build|close|check|search|'
        r'create|delete|remove|save|read|review|implement|click|press|scroll|navigate|switch|'
        r'play|pause|mute|set|configure|analyze|solve|'
        r'take a screenshot|test(?=\s+(?:the|this|our|my|an?)\b))\b', value)
    observation = re.search(r'\b(?:ekranda|ekranımda|pencerede|penceremde|açık uygulamada)\s+'
                            r'(?:şu an\s+)?(?:ne görüyorsun|neler var)\s*[?!.]?\s*$',value)
    # "nasıl düzeltiriz?" is discussion, "önce dosyayı incele, sonra anlat" is work.
    if explicit or polite or english or observation:
        return 'task'
    return 'conversation'
