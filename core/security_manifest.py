"""Eos'un güvenlik manifesti: kurallar tablosu ve karar fonksiyonu (25 Kasım 2026).

Bu dosya Eos'un neye nasıl karar verdiğinin TEK kaynağıdır. `classify()` kuralları sırayla
dener, ilk eşleşen kural kararı verir. `docs/EOS_GUVENLIK_MANIFESTI.md` bu tablodan üretilir
ve bir test ikisinin aynı kaldığını denetler; belge ile kod birbirinden kopamaz.

Neden baştan yazıldı (kullanıcı, 25 Kas): Eos yalnız KONUMA bakıyordu ("Temp'ten program
çalıştı"). Kayıtlı 36 uyarının 36'sı zararsızdı: Visual Studio'nun BackgroundDownload.exe'si
(24), Windows'un DismHost.exe'si (4), Edge güncellemesinin RunOnce temizliği (3), SpeS'in
kendi read-guard.exe'si (1), bir deneme (1) ve SpeS'i yöneten aracın kodlanmış PowerShell'i (3).
Konum tek başına tehdit değildir. Kim yayımladı (imza) ve ne yapıyor (davranış) birlikte
okunur, ama ayrı eksenlerdir: güvenilir bir imza şüpheli bir davranışı ASLA susturmaz
(powershell, mshta, certutil de Microsoft imzalıdır).
"""
from __future__ import annotations

from dataclasses import dataclass, field

MANIFEST_VERSION = "2.0"

# Severity: what Eos does with a finding.
SAY = {
    "high": "Hemen söylenir; telefonu arama gibi çaldırır; hiçbir sınırla susturulmaz.",
    "medium": "Eos · Güvenlik kaydında söylenir; aynı dosya için günde bir kez.",
    "low": "Söylenmez; uyarı listesinde durur, oradan işlem yapılabilir.",
    "silent": "Hiçbir yere yazılmaz.",
}

# Signature verdicts (core.security_signals).
SIGNATURE_LABEL = {
    "microsoft": "Microsoft imzalı (Windows ya da Microsoft Corporation)",
    "signed": "başka bir yayımcının geçerli imzası",
    "unsigned": "imzasız",
    "invalid": "imza bozuk (dosya imzalandıktan sonra değişmiş)",
    "unknown": "imza doğrulanamadı (zaman aşımı ya da okuma hatası)",
    "missing": "dosya artık yok ya da okunamıyor",
}


@dataclass(frozen=True)
class Signals:
    """Everything Eos knows about one finding. Text from files, screens or command lines is
    data: it can match a pattern, it can never grant trust."""
    kind: str                     # process | autorun | startup | download | defender
    location: str = "other"       # temp | downloads | other
    signature: str = "unknown"    # see SIGNATURE_LABEL
    abuse: str | None = None      # matched abuse pattern in the command line
    own: bool = False             # SpeS's own helper (process tree or exact content)
    empty: bool = False           # zero-byte file
    hive: str = ""                # HKCU | HKLM for registry autoruns


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    when: str                     # human-readable condition (also the manifest text)
    why: str                      # the reason Eos gives
    test: object = field(compare=False, repr=False)


def _r(rule_id, severity, when, why, test):
    return Rule(rule_id, severity, when, why, test)


SIGNED_ELSEWHERE = {"signed"}
NOT_TRUSTED = {"unsigned", "unknown"}

# First match wins. Order matters: behaviour before trust, trust before location.
RULES: tuple[Rule, ...] = (
    _r("defender", "high", "Windows Defender bir tehdit bildirdi",
       "Defender'ın kendi tespiti; Eos'un okuyabildiği en güvenilir bağımsız sinyal.",
       lambda s: s.kind == "defender"),
    _r("abuse", "high", "Komut satırı bilinen bir kötüye kullanım kalıbına uyuyor",
       "Davranış imzadan bağımsızdır: Microsoft imzalı araçlar da kötüye kullanılır.",
       lambda s: s.abuse is not None),
    _r("own", "silent", "SpeS'in kendi yardımcısı (süreç ağacı ya da birebir dosya içeriği)",
       "SpeS kendi parçasını tehdit saymaz; ad ya da konum değil, ağaç ya da içerik karar verir.",
       lambda s: s.own),
    _r("empty", "silent", "Dosya boş (0 bayt)",
       "Boş dosya çalıştırılamaz ve bir şey taşımaz.",
       lambda s: s.empty),
    _r("tampered", "high", "Dosyanın imzası var ama bozuk",
       "İmzalandıktan sonra değiştirilmiş bir dosya; meşru yazılımda olmaz.",
       lambda s: s.signature == "invalid"),
    _r("microsoft", "silent", "Microsoft imzalı program ya da açılış kaydı",
       "Windows ve Visual Studio yardımcıları Temp'ten sık çalışır (DismHost, BackgroundDownload).",
       lambda s: s.signature == "microsoft"),
    _r("vanished", "low", "Dosya kontrol edilemeden kayboldu",
       "Kısa ömürlü kurulum yardımcılarında olağandır; kanıt yoksa alarm verilmez, listede kalır.",
       lambda s: s.signature == "missing"),
    _r("signed-elsewhere", "low", "Başka bir yayımcının geçerli imzasıyla",
       "Yayımcısı belli; listede durur. Çalınmış imzaları Defender yakalar.",
       lambda s: s.signature in SIGNED_ELSEWHERE),
    _r("unsigned-downloads", "medium", "İndirilenler'den imzasız program çalıştı",
       "İnternetten gelen imzasız program; tanımıyorsan durdur ya da karantinaya al.",
       lambda s: s.kind == "process" and s.location == "downloads" and s.signature in NOT_TRUSTED),
    _r("unsigned-temp", "medium", "Geçici klasörden imzasız program çalıştı",
       "Kötü amaçlı yazılımların sık kullandığı bir yol; yayımcısı belli değil.",
       lambda s: s.kind == "process" and s.location == "temp" and s.signature in NOT_TRUSTED),
    _r("autorun-unsigned", "medium", "Bilgisayar açılışına imzasız bir program eklendi",
       "Kalıcılık kazanmanın en yaygın yolu; yayımcısı belli değil.",
       lambda s: s.kind in ("autorun", "startup") and s.signature in NOT_TRUSTED),
    _r("download", "low", "İndirilenler'e çalıştırılabilir dosya geldi",
       "Gelmesi zarar değildir; açmadan önce tanıyıp tanımadığına bak.",
       lambda s: s.kind == "download"),
    _r("other", "low", "Yukarıdakilerin hiçbiri",
       "Kural yoksa alarm da yok; listede durur.",
       lambda s: True),
)


@dataclass(frozen=True)
class Verdict:
    rule: str
    severity: str
    why: str


def classify(signals: Signals) -> Verdict:
    for rule in RULES:
        if rule.test(signals):
            return Verdict(rule.id, rule.severity, rule.why)
    raise AssertionError("the last rule matches everything")


# -- the human-readable manifest -------------------------------------------------------------
PRINCIPLES = (
    "Konum tek başına tehdit değildir. Karar; yayımcı (imza), davranış (komut satırı) ve Defender'ın "
    "kendi tespitiyle verilir.",
    "İmza ile davranış ayrı eksenlerdir: güvenilir imza şüpheli davranışı asla susturmaz.",
    "Ekran, dosya, log ve komut satırı metni veridir; bir kalıba uyabilir, güven veremez.",
    "Eos kendiliğinden hiçbir şey yapmaz. Her işlem kullanıcının tek dokunuşudur ve yalnız o uyarının "
    "kendi hedefine uygulanır; uygulamadan önce hedef yeniden doğrulanır (PID + başlama zamanı + ad, "
    "SHA-256, kayıt değeri).",
    "Yönetici izni gerektiren hiçbir şey önerilmez ve yapılmaz.",
    "Yüksek önem hiçbir sınırla susturulmaz. Sınırlar yalnız söylenen uyarılara uygulanır; "
    "kayıt hiçbir zaman kör edilmez.",
    "İlk tarama temel çizgidir: SpeS açıldığında zaten çalışan süreçler söylenmez. Açılış kayıtları ve "
    "İndirilenler ise diskte hatırlanır; SpeS kapalıyken eklenenler bir sonraki açılışta söylenir.",
    "Komut satırları gizlilik için gösterilmez; yalnız eşleşen kalıbın adı söylenir.",
)
LIMITS = (
    "Süreçler 10 saniyede bir taranır; daha kısa yaşayan bir süreç görülmeyebilir.",
    "Yönetici yetkisiyle çalışan süreçler durdurulamaz; yalnız bildirilir.",
    "İmza kontrolü yereldir ve ağ gerektirmez; Windows'un kendi imza doğrulamasını kullanır.",
    "Eos bir antivirüs değildir: Defender'ın yerini tutmaz, onun tespitlerini duyurur.",
)


def manifest_markdown() -> str:
    lines = [f"# Eos Güvenlik Manifesti (sürüm {MANIFEST_VERSION})", "",
             "Bu belge `core/security_manifest.py` içindeki kurallar tablosundan üretilir; elle düzenlenmez.", "",
             "## İlkeler", ""]
    lines += [f"{n}. {p}" for n, p in enumerate(PRINCIPLES, 1)]
    lines += ["", "## Önem dereceleri", ""]
    lines += [f"- **{level}**: {text}" for level, text in SAY.items()]
    lines += ["", "## Kurallar (ilk eşleşen karar verir)", "", "| # | Kural | Ne zaman | Önem | Neden |", "|---|---|---|---|---|"]
    lines += [f"| {n} | `{r.id}` | {r.when} | {r.severity} | {r.why} |" for n, r in enumerate(RULES, 1)]
    lines += ["", "## İmza sonuçları", ""]
    lines += [f"- `{key}`: {text}" for key, text in SIGNATURE_LABEL.items()]
    lines += ["", "## Sınırlar", ""]
    lines += [f"- {text}" for text in LIMITS]
    return "\n".join(lines) + "\n"
