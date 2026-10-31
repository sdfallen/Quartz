"""Narrow chat commands; quoted examples and discussion never authorize work."""
import re
from core.message_intent import instruction_text, tools_disallowed


def diagnostics_intent(text):
    if tools_disallowed(text):
        return None
    value = instruction_text(text).strip().rstrip('.!').strip()
    value = re.sub(r'^(?:lütfen|codex|gemini|antigravity)[,:]?\s+', '', value)
    if re.fullmatch(r"quartz(?:['’]?[ıi])?\s+(?:kontrol et|incele|teşhis et)", value):
        return 'self'
    if re.fullmatch(r"quartz(?:['’]?[ıi])?\s+(?:onar|onarım planı hazırla)", value):
        return 'repair'
    if re.fullmatch(
        r'(?:başka (?:bir )?uygulamayı|uygulama dosyasını|seçtiğim uygulamayı|bir uygulamayı)\s+'
        r'(?:incele|teşhis et|analiz et|(?:rea|tersine mühendislik)\s+ile\s+(?:incele|analiz et))',
        value,
    ):
        return 'artifact'
    if re.fullmatch(
        r'(?:(?:öğrenilen|incelenen|kayıtlı)\s+uygulamaları|uygulama\s+(?:hafızasını|bilgisini))\s+(?:göster|listele)',
        value,
    ):
        return 'knowledge'
    return None
