"""User-facing language policy; never a tool permission or evidence filter."""
import re

DETAIL_LEVELS = {"short", "normal", "technical"}
DETAIL_MARKER = "---TEKNIK_AYRINTILAR---"


def wants_full_report(text):
    return bool(re.search(r"(kapsamlı|kapsamli|ayrıntılı|ayrintili|detaylı|detayli|tam|uzun|teknik)\s+"
                          r"(bir\s+)?(rapor|açıklama|aciklama|analiz)|"
                          r"(comprehensive|detailed|full|technical)\s+(report|analysis|explanation)",
                          str(text), re.I))


def communication_instruction(level="short", user_request=""):
    if level not in DETAIL_LEVELS:
        raise ValueError("Geçersiz yanıt ayrıntısı")
    detail = {
        "short": "Ana yanıtı 1-3 kısa cümle ve yaklaşık 60 sözcük içinde tut. Kısa soruya kısa yanıt ver; gereksiz liste ve rapor üretme. Uzun teknik açıklamayı gerekiyorsa ayrıntı alanına taşı.",
        "normal": "Önce kısa sonuç, sonra gerektiği kadar anlaşılır açıklama ver.",
        "technical": "İstenen teknik kapsamı, kaynakları ve test ayrıntılarını açıkça sun; gereksiz tekrardan kaçın.",
    }[level]
    if wants_full_report(user_request):
        detail = "Kullanıcı açıkça kapsamlı rapor istiyor. Kısalık tercihine rağmen istenen tam raporu ana yanıtta ver."
    elif level == "short":
        detail += (" Teknik hata sorusunda ana yanıtta kod/API terimlerini sıralama; sorunu günlük dille anlat. "
                   "Örneğin: 'Tıklamadan önceki kontrol hata verdi. Nedenini anlamak için pencereyi ve hata kaydını kontrol etmemiz gerekiyor.' "
                   "Hata kodu, İngilizce adlar ve ayrıntılı olası nedenler Teknik ayrıntılar alanında kalabilir.")
    return (
        "[QUARTZ İLETİŞİM TERCİHİ — İZİNLERİ DEĞİŞTİRMEZ]\n"
        "Kullanıcıya sade, doğal ve doğrudan Türkçe konuş. Önce önemli sonucu söyle. "
        "Gereksiz teknik terim, uzun madde listesi ve tekrar kullanma. " + detail + "\n"
        "Grup sohbetinde önceki ajanın söylediklerini yeniden anlatma; yalnız yeni katkını, "
        "itirazını veya gerekli sorunu ekle. 'Katılıyorum' girişiyle diğerinin özetini tekrarlama; doğrudan yeni katkınla başla. "
        "İlerleme mesajlarını yalnız anlamlı gelişmeler için kullan.\n"
        "Bir işlem/test hakkında sonuç bildirirken kanıtına göre 'Başarılı', 'Başarısız', "
        "'Henüz doğrulanmadı' veya 'Kullanıcı onayı bekleniyor' ayrımını açık tut. "
        "Normal sohbeti yapay bir başarı raporuna çevirme. Derleme ya da süreç çıkışı "
        "tek başına gerçek işlem başarısı değildir. Başarısızlığı ve belirsizliği gizleme. "
        "Ölçülmemiş hata nedenini kesinleşmiş gibi söyleme; olasılık ile doğrulanmış nedeni ayır.\n"
        "Kısa/Normal yanıtta gerekli uzun hata izlerini, dosya yollarını ve ham test kanıtlarını "
        "atmak yerine, kısa anlaşılır açıklamadan sonra ayrı bir satırda " + DETAIL_MARKER +
        " yazıp altında eksiksiz koruyabilirsin. Önemli hata/izin/sonuç bilgisi ana yanıtta kalsın. "
        "Teknik modda veya kapsamlı rapor istendiğinde asıl raporu bu alanın arkasına saklama. "
        "Squad üzerinden gerekli tam teknik veriyi paylaş; kısa kullanıcı özeti teknik kanıtın yerine geçmez.\n"
    )
