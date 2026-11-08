"""Conservative local routing; permission selection is not an action request.

No extra model round-trip. Ambiguous/discussion messages stay text-only; this
decision never grants access. Active-task continuation is handled by the host.
"""
import re


def turkish_fold(text):
    """Accept keyboard spellings without changing the user's original text."""
    return str(text).casefold().translate(str.maketrans('ıöüçşğ', 'ioucsg')).replace('\u0307', '')


def request_withdrawn(text):
    # Unqualified final withdrawal cancels the preceding request. A scoped
    # exception ("ama geçmişi silmene gerek yok") does not cancel another action.
    value = turkish_fold(instruction_text(text)).strip()
    return bool(re.search(r'\b(?:ama|fakat|ancak)\s+(?:(?:artik|simdilik|buna)\s+)?'
                          r'(?:gerek yok|vazgectim|bos\s*ver|istemiyorum)[.!?\s]*$', value))


def _directive_search(pattern, value):
    return re.search(turkish_fold(pattern), turkish_fold(value))


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
    if tools_disallowed(value) or request_withdrawn(value):
        return 'conversation'
    if re.fullmatch(r'\s*(?:(?:tamam\s+)?(?:devam et|devam|sürdür)|evet|olur|tamam|dur|durdur|görevi durdur|kontrolü durdur|iptal et)[.!]?\s*', value):
        return 'continuation'
    # Explanations can mention an imperative without requesting its execution.
    # Filter individual clauses so "Chrome'u aç; oynat ne işe yarıyor?" still
    # executes the explicit first clause rather than suppressing the whole task.
    explanation = re.compile(r'ne işe yar(?:ıyor|ar)|ne (?:anlama gelir|demek)|'
                             r'\bdemek\b.{0,60}\bm[ıiuü]\b|'
                             r'hakkında (?:ne düşün|konuş)|what (?:does|is).{0,80}mean|'
                             r'\bset theory\b')
    # A bare "değerlendir?" about an idea stays a conversation; about code, files
    # or the project it is still a review task. The context words are matched on
    # folded text as stems, so Turkish suffixes ("kodu", "dosyayı", "modülü") count.
    code_context = re.search(
        r'\b(?:dosya|kod|proje|test|log|ekran|pencere|uygulama|modul|fonksiyon|sinif|metot|satir|hata|bug|'
        r'commit|branch|todo)|\b[\w-]+\.(?:py|js|ts|md|json|txt|log|html|css)\b', turkish_fold(value))
    conceptual_question = re.compile(
        r'\b(?:degerlendir(?:in|iniz)?|gozden\s+gecir(?:in|iniz)?|getir(?:in)?|gecir(?:in)?)\s*\?$')
    # Clauses split at commas too ("bu hata ne demek, düzelt" keeps "düzelt");
    # sentence punctuation stays on its clause so a trailing "?" can be seen.
    parts = [part.strip() for part in re.split(r'(?<=[.!?])(?=\s|$)|[;,\n]+', value)]
    value = '. '.join(
        part.rstrip('.!?').strip() for part in parts
        if part.rstrip('.!?').strip() and not explanation.search(part)
        and not (not code_context and conceptual_question.search(turkish_fold(part)))
    )
    # Explanatory questions do not execute the operation being discussed.
    explicit = _directive_search(
        r'\b(?:incele(?:yin|yiniz|yip|yerek)?|düzelt(?:in|iniz)?|derle(?:yin)?|geliştir(?:in)?|'
        r'çalıştır(?:ın|in)?|başlat(?:ın)?|başla(?:yın|yınız)?|aç(?:ın|in|ıp)?|oku(?:yun)?|araştır(?:ın)?|'
        r'tıkla(?:yın)?|yükle(?:yin)?|kaydet|sil|ekle(?:yin)?|oluştur(?:un)?|'
        r'bak(?:ın|ınız)?|gir(?:in|iniz|ip)?|geç(?:in|iniz)?|bas(?:ın|ınız)?|seç(?:in|iniz|imi\s+yap)?|'
        r'kaydır(?:ın|ınız)?|göster(?:in|iniz)?|yönet(?:in|iniz)?|kullan(?:ın|ınız)?|ekran görüntüsü al|kontrol(?:ünü|unu)?\s+al|'
        r'yap(?:ın|ınız)?|ayarla(?:yın|yınız)?|düzenle(?:yin|yiniz)?|onar(?:ın)?|indir(?:in)?|kur(?:un)?|kaldır(?:ın)?|'
        r'taşı(?:yın)?|yenile(?:yin)?|sıfırla(?:yın)?|temizle(?:yin)?|kopyala(?:yın)?|yapıştır(?:ın)?|'
        r'çal(?:ın)?|oynat(?:ın)?|durdur(?:un)?|duraklat(?:ın)?|kıs(?:ın)?|artır(?:ın)?|yükselt(?:in)?|büyüt(?:ün)?|küçült(?:ün)?|'
        r'ara(?:yın)?|izle(?:yin)?|dinle(?:yin)?|uygula(?:yın)?|tamamla(?:yın)?|bitir(?:in)?|harekete\s+geç(?:in)?|'
        # Live exam 7 Nov: "parse fonksiyonunu daha okunur hale getir" was read as chat.
        r'(?:hale\s+|yerine\s+|bir\s+araya\s+|geri\s+)?getir(?:in)?|'
        r'iyileştir(?:in)?|sadeleştir(?:in)?|dönüştür(?:ün)?|adlandır(?:ın)?|refactor\s+et|'
        r'gözden\s+geçir(?:in|iniz)?|geçir(?:in)?|değerlendir(?:in|iniz)?|'
        r'analiz\s+(?:et|edin|ediniz|yap|yapın)|'
        r'test (?:et|edin|ediniz)|kontrol (?:et|edin|ediniz)|test edip|kontrol edip|debug yap|test yap|bi(?:r)? test bakalım|dene(?:yin)?|bul|tara|yaz|güncelle|değiştir|çöz(?:ün)?|kapat(?:ın)?|öğren(?:in)?|bilgi\s+(?:al|topla))\b', value)
    polite = _directive_search(
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
