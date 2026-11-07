# Claude → Gemini devri (8 Kasım 2026)

Kullanıcı, 8 Kasım: "Geriye kalanları Gemini halletsin." Bu belge, Claude'un bıraktığı yeri ve Gemini'nin
yapacağı işleri tanımlar. Önce [Quartz Durum Raporu](QUARTZ_DURUM_RAPORU_20261108.md) okunmalı.

## 0. Bilinmesi gerekenler

- **Main:** 9acdfd7. Kurulu Quartz: `c14b968d…` (= main 71fa6fd; 9acdfd7 yalnız belge ve sınav aracı ekler).
- **Kurallar:** CLAUDE.md geçerli.
  - Kendi dalında ve worktree'de çalış.
  - GitHub'a push yok.
  - Kullanıcı verisi commit edilmez.
  - ASTER/Warband rafta, dokunulmaz.
- **Kurulum:**
  - Paket derlemeden önce masaüstü yardımcısını derle: `python -B build.py` adımları ya da `core/desktop_mcp.py` için
    `PyInstaller --onefile --console --name QuartzDesktopMCP --distpath build/desktop-helper`.
  - Atlanırsa `verify_desktop_package.py` `helper_schema_matches=false` verir.
  - Quartz açıkken kurulum yapılmaz.
- **Bu bilgisayar düşük donanım sayılıyor** (7,9 GB, 4 çekirdek). Masaüstü görevleri 1,5–6 dakika sürer.

## 1. Önce: bağımsız inceleme (zorunlu)

PARALLEL_OWNERSHIP kuralı: Claude'un üretim değişiklikleri Gemini incelemeden main'e alınmamalıydı. Kullanıcı bu
oturumda yetkiyi Claude'a verdi ("Kararlar sende", "Tüm kontrol sende", "Evet, al ve kur"). Bu yüzden aşağıdaki
birleştirmeler yalnız Claude'un incelemesiyle main'e girdi. Hepsini incele; bulguları `docs/GEMINI_REVIEW_CLAUDE_20261108.md`
dosyasına `BULGU: <dosya>:<satır> — <neden>` biçiminde yaz.

Öncelik sırası (güvenlik ve giriş yolu önce):

| Birleştirme | Ne değişti | Bakılacak |
|---|---|---|
| 0f188b0 | `desktop_act` ref ile yazma/tıklama, `ui` varsayılan işlem, tuş adı küçük harf; görev kaydında yalnız o görevin girdileri | `core/desktop_native.py` `act()`: ref yolu kritik ad denetimini, şifre alanını, ön plan ve kimlik denetimini atlıyor mu? |
| cd1249d | Tek odak (`focused_control`, UIA GetFocusedElement), WebView2 alt süreç kuralı (`_same_application`) | Odaklanan öğenin gerçekten hedef pencerede olması; alt süreç kuralının başka uygulamaya kapı açmaması |
| 1e6e7fc | UIA taramasında sarmalayıcı Pane'ler derinlik saymıyor | `core/desktop_control.py` `_get_descendants`: eleman bütçesi ve mutlak derinlik sınırı; şifre alanı denetimi kaçıyor mu? |
| 35b23bc | `DENIED_EXES` içine claude/copilot/cursor/windsurf/ollama | Eksik asistan var mı? |
| f602a5d | `\bcalc\b`, yeni emir fiilleri (getir, geçir, değerlendir…) | Sohbet sorularının göreve dönüşmesi (yanlış pozitif) |
| 71fa6fd | `jarvis_open_app` yeni pencereyi 8 sn bekler; adımlar sohbete bağlı | 25 sn araç zaman aşımıyla çakışma |
| 7ea2fcf / 8c0b1e8 | Arayüz sıfırdan (simge çubuğu, çekmece, ajan sütunları, kristal), yazı kutusu grid düzeltmesi | Tüm Durdur düğmelerinin erişilebilirliği, kompakt mod |
| b4f014d | Düşük donanımda hafif animasyon, zamanlayıcıyla yazılarak açılma | Performans |
| f1e59cd, b8e17bd | Onay sonrası yeniden başlatma yok; salt okuma gözlem doğrulamayı silmez; yer tutucu mesaj filtresi | `core/natural_desktop.py` |
| 8b24e6b, 374b9f8, 441967a, c943c9d | 7 Kasım tema, host check, gece düzeltmeleri, desktop_act sırası | Önceki devir belgesinde (CLAUDE_HANDOVER_TO_CODEX_20261107.md) listeli |

Sınav araçları da incelenmeli: `scripts/exam_live.py`, `scripts/exam_oracle.py`, `scripts/exam_fixture_app.py`. Claude
iki kontrolü koşudan sonra yazdı ya da değiştirdi (`checkpoint_exists`, `.git/` hariç tutma, `if_tree_changed_then`,
fixture kaydıyla Durdur zamanı). Kuralların adil olup olmadığına bağımsız karar ver.

## 2. Sınav: nerede kaldı

Durum: 35 görevden 9'u VERIFIED, 1'i FAILED (exam-desk-09), exam-chat-01 insan puanı bekliyor, 24'ü koşulmadı.

**Koşulmayanlar:**

| Grup | Görevler | Not |
|---|---|---|
| Kod | exam-code-03, 04, 05, 06, 07, 08, 09 | code-06 için gizli varyantlar senin elinde (holdout SHA görev listesinde) |
| Masaüstü | exam-desk-01, 04, 05, 06, 08, 10, 11, 12, 13, 15 | desk-01 ve desk-05 kayıt penceresi ister; kayıt ajana bilinçli kapalı, büyük olasılıkla BLOCKED |
| Uzun ve öğrenme | exam-long-01, long-02, learn-01, learn-02, chat-03 | |
| Maliyet ve sağlayıcı | exam-cost-01, exam-prov-01 | prov-01 çevrimdışı: `scripts/task_exam_runner.py` |

**Araçlar:**

```powershell
$env:QUARTZ_EXAM_ROOT='C:\QuartzExam'
python -B scripts/exam_live.py prepare exam-desk-04    # fixture, nonce, mesaj; host klasörünü yazar
python -B scripts/exam_live.py rebaseline <host>       # proje eklendikten sonra, mesajdan önce
python -B scripts/exam_live.py mark <host> stop_at     # Durdur'a basmadan hemen önce
python -B scripts/exam_live.py grade <host>            # yalnız makine kanıtıyla puanlar
```

- **Adaptörü olan görevler:** chat-01/02, code-01/02/10, long-03, desk-01/02/03/05/07/09/14.
- **Diğer görevler için:** `SETUPS` içine adaptör ve gerekirse `exam_oracle.LIVE_CHECKS` içine kontrol ekle. Her
  yeni kontrol için `tests/test_exam_oracle.py`'ye test yaz.

**Canlı koşu yöntemi:**

- Mesaj Quartz'ın ana sohbetine yazılır. Claude bunu ekran kontrolüyle yaptı.
- Masaüstü kontrolün yoksa mesajları kullanıcı gönderir, sen puanlarsın. Kendini "insan değerlendirici" yerine koyma.
- Kod görevlerinde test deposu Quartz'a proje olarak eklenmeli. Mesajı göndermeden önce etkin sohbetin projesini
  `quartz_conversations.json` dosyasında doğrula: bir koşu yanlış sohbetten gerçek Jarvis config deposunda başladı.

## 3. Ürün işleri (sınavın gösterdikleri)

1. **Durdur sonrası kapanış:** 4–7 sn sürüyor, hedef 1 sn (exam-desk-09). `natural_desktop.stop()` temizlik sırası
   ve ajan süreç ağacı kapanışı ölçülmeli.
2. **Uygulama açma:** `jarvis_open_app` Hesap Makinesi'nde hâlâ zaman aşımı veriyor (görev 6,3 dakika sürdü).
   `advanced_controller.smart_open` + bekleme 25 sn soket zaman aşımını aşabiliyor. Başlatmayı arka plana alıp
   pencereyi ayrı yoklamak düşünülebilir.
3. **Gemini operatörken etkinlik:** Masaüstü görevlerinde ajan sütunlarına canlı adım gelmiyor; `agent_progress`
   yalnız sohbet turlarında var.
4. **"Ready / Hazır" yoklama mesajları:** Yer tutucu filtresine eklenmedi.
5. **Model seçici:** Açılışta seçiciler ham değer (`gpt-6.1-sol`) gösteriyor, sonra düzeliyor.

## 4. Bitiş ölçütü

- Tüm sınav tek seferde, yeni bir sınav profiliyle koşulur.
- Her görevin `grade.json` dosyası ve özeti `QUARTZ_DURUM_RAPORU` dosyasına işlenir.
- "Çok güçlü / ilk büyük sürüm" yalnız şu koşulların hepsi tamamsa söylenebilir:
  - masaüstü, kod ve uzun görevlerin çoğu VERIFIED;
  - bilinçli BLOCKED olanlar gerekçeli;
  - bağımsız inceleme bulguları kapanmış;
  - kullanıcı canlı kabul vermiş.
