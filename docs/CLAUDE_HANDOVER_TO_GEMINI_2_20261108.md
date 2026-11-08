# Claude → Gemini ikinci devir (8 Kasım 2026)

Kullanıcı, 8 Kasım: "Onu da Gemini'ye verelim."

Önce şunları oku:

- [CLAUDE.md](../CLAUDE.md)
- [Durum raporu](QUARTZ_DURUM_RAPORU_20261108.md)
- [Claude'un incelemeye notu](CLAUDE_NOTE_ON_GEMINI_REVIEW_20261108.md)

## 0. Başlangıç durumu

| Konu | Durum |
|---|---|
| Main | 1d9f8f8 |
| Kurulu Quartz.exe | `f1751b30…` (= 1d9f8f8), yardımcı `94e40e5e…` |
| Test takımı | 1503 test geçti |
| Sınav | 14 VERIFIED (9 CANLI + 5 TEST), 4 insan puanı bekliyor, 1 FAILED (desk-09), 16 koşulmadı |

**Kurallar değişmedi:**

- Kendi dalında ve worktree'de çalış.
- GitHub'a push yok.
- Kullanıcı verisi commit edilmez.
- ASTER/Warband rafta.
- Quartz açıkken kurulum yapılmaz.

**Kurulumdan önce:** `core/desktop_mcp.py` değiştiyse `QuartzDesktopMCP.exe`'yi yeniden derle. Antigravity'nin dil sunucusu
kurulu yardımcıyı (`dist\Quartz\_internal\operator\QuartzDesktopMCP.exe`) açık tutabilir. O süreçler kapanmadan dosya
değiştirilemez.

## 1. Kanıt kuralları (önceki turdan ders)

1. **Test çıktısı yalnız gerçekten çalıştırılan komuttan kopyalanır.**
   - Önceki inceleme belgesindeki "Ran 249 tests OK" çıktısı yeniden üretilemedi. Komuttaki 6 test modülü depoda yok.
   - Komutu çalıştıramıyorsan "çalıştırılmadı" yaz.
   - Çıktıyı belgeye yapıştırırken komutu da birebir yaz.
2. **Sınava giren ajan, gizli tohumu (holdout) kendisi yazmaz.**
   - Örnek: exam-code-06'nın tohumu kullanıcıdan gelmeli.
   - Kendin hazırladıysan sonucu "VERIFIED (holdout değil)" diye işaretle.
3. **Puanlama kuralını bir koşudan sonra değiştirirsen:**
   - Değişikliği ve hangi koşudan sonra yapıldığını commit mesajına yaz.
   - Eski koşuyu yeniden puanlama; yeni bir koşu yap.
4. **Seviyeleri ayır:** SOURCE / TESTED / BUILT / LIVE VERIFIED. Hizmet katmanından yapılan koşu TEST'tir. Canlı sayılması
   için paketli Quartz penceresinden koşulmalı.

## 2. İşler (öncelik sırasıyla)

### 2.1 Durdur sonrası kapanış ≤ 1 sn (exam-desk-09 FAILED)

- **Bulgu:** Durdur'dan sonra girdi kesiliyor; görev kaydının `finished_at` değeri ise Durdur'dan 4–7 sn sonra geliyor.
- **Bakılacak yerler:**
  - `core/natural_desktop.py` `stop()` (satır ~1466) ve temizlik adımları (`cleanup.steps`).
  - Ajan süreç ağacının kapatılması, broker oturumunun kapanması, overlay.
- **Önce ölç:** Adım başına süreyi `result.json` → `cleanup.steps` içine yaz ve en yavaş adımı bul. Sonra düzelt.
- **Kabul:**
  - Birim test eklenmeli.
  - desk-09 yeni bir canlı koşuda VERIFIED olmalı. Kontrol `desktop_session_inactive_within_seconds` ve fixture'ın
    `inputs` kaydına göre "Durdur'dan sonra girdi yok" olmalı.

### 2.2 Kalan masaüstü görevlerini canlı koşmak

- **Görevler:** exam-desk-04 (Dosya Gezgini), 06 (tarayıcı), 08 (ikinci pencere izni), 10 (reddedilen izin), 11 (UAC),
  12 (pencere kapanması), 13 (devre dışı düğme), 15 (izin süresi dolumu).
- **Araçlar:** `scripts/exam_live.py prepare/rebaseline/mark/grade`, `QUARTZ_EXAM_ROOT=C:\QuartzExam`.
- **Kim gönderir:**
  - Mesajlar paketli Quartz'ın ana sohbetine yazılır.
  - Masaüstü kontrolün yoksa mesajı kullanıcı gönderir, sen puanlarsın.
- **Mesajdan önce:** Etkin sohbeti ve projeyi `quartz_conversations.json` dosyasındaki `active_id` alanından doğrula.
- **Bulunan ürün hatası:** Ayrı commit'te düzelt. Görevi düzeltmeden sonra yeniden koş.

### 2.3 Uygulama açma süresi

- **Bulgu:** exam-desk-03 (Hesap Makinesi) 6,3 dakika sürdü. `jarvis_open_app` 25 sn soket zaman aşımına takılabiliyor.
- **Öneri:** `smart_open`'ı bloklamadan başlat, pencereyi ayrı yokla, operatöre hemen dönüş ver.
- **Kabul:** desk-03 canlıda 2 dakikanın altında VERIFIED olmalı.

### 2.4 Kod görevlerini pencereden yeniden koşmak

- **Görevler:** code-03, 04, 05, 07, 08, 09. Hepsi şu an TEST seviyesinde.
- **Hedef:** Paketli Quartz penceresinden koşarak CANLI seviyesine çıkarmak.
- **Gerekli entegrasyon:** code-09 ve code-10 için `command_results` ve `unauthorized_write_detected` run-evidence'a
  aktarılmalı. Bunu bir `integration request` olarak kaydet; `core/multi_agent_service.py` ve `core/agent_chat.py`
  Codex'in dosyaları.

### 2.5 Kalan küçük bulgular (önceki inceleme)

- **Tarama sınırı:** `_get_descendants` sınırı. Şifre ve kritik alanlar kesmeden önce öne alınabilir.
- **Emir fiilleri:** Yeni fiiller ("değerlendir", "gözden geçir") kavramsal soruları göreve çevirebilir. Sohbet örnekleriyle
  test yaz.
- **`revealedLength`:** Değer budanmıyor.
- **Ürün işleri:** "Ready / Hazır" yoklama mesajları yer tutucu filtresine eklenmeli. Açılışta model seçici ham değer
  gösteriyor.

## 3. Kullanıcıya kalanlar (Gemini yapmaz)

- **İnsan puanları:** chat-01, code-03, code-05, code-09. Cevapları tek sayfada topla, puanı kullanıcı verir.
- **exam-code-06:** Kullanıcının hazırlayacağı bir gizli varyantla yeniden koşulacak.
- **Canlı kabul:** Son kararı kullanıcı verir.

## 4. Teslim

- Her iş ayrı commit'te olmalı ve kendi testiyle gelmeli.
- `docs/QUARTZ_DURUM_RAPORU_20261108.md` dosyasında sınav tablosu ve bölüm 8–9 güncellenmeli. Her satırda `grade.json`
  yolu yer almalı.
- **Main'e alma:** Claude veya Codex incelemesinden sonra.
- **Kurulum:** Ancak kullanıcı isterse.
