# Claude ve Gemini sonrası bağımsız inceleme — 9 Kasım 2026

## Kapsam ve karar

- İncelenen kaynak: `0fb2b2e622f22ff3e95fde23be2bf34c0470f9dd` (main).
- Önceki Codex teslimi: `fce06e0880615ad1e446005b42f11691e58c5417`.
- Fark: 81 dosya, 9029 eklenen / 335 kaldırılan satır. Risk odaklı inceleme; her satırın eksiksiz denetlendiği iddia edilmiyor.
- Çalışma dalı: `codex/review-claude-gemini-20261109`, ayrı worktree. Üretim kodu değiştirilmedi; main'e birleşim, GitHub gönderimi, paket derleme/kurulum veya canlı uygulama kontrolü yapılmadı.
- **Karar:** Kaynak ciddi ilerleme içeriyor, fakat tam teknik kapanış onayı vermiyorum. Aşağıdaki görev tamamlama ve kabul kanıtı açıkları önce giderilmeli. Mevcut uygulama veya geçmiş başarılı kullanıcı testleri topluca başarısız sayılmıyor.

## İyi yönde değişenler

1. Süreçlerin Windows Job Object altında izlenmesi, askıda başlatma/bağlama ve kapanış sahipliği güçlendirilmiş. Fallback ile kesin Job Object kapsaması aynı şey değildir; yeni gerçek süreç ağacı kabulü bu incelemede yapılmadı.
2. Yavaş gözlem sırasında Stop için broker kilidinin bırakılması ve gözlem dönüşünde oturum/token'ın tekrar doğrulanması eklenmiş. İlgili güvenli testler tam suite içinde geçti; yeni paketli Stop kabulü değildir.
3. UI sonuç rozetleri scoped gözlem, yürütme bitişi ve host hedef doğrulamasını daha açık ayırıyor. Ajan sütunları, araç/ref davranışı ve WebView alanları için regresyon testleri eklenmiş. Görsel kalite ekran üzerinden bu oturumda değerlendirilmedi.
4. Görev Sınavı için gerçek fixture, ana-sohbet/hizmet adaptörü ve host kontrolleri önemli ölçüde geliştirilmiş. Aşağıdaki oracle açıkları nedeniyle bütün kayıtları koşulsuz kabul etmek doğru değil.
5. Proje kaldırma normal yolda proje klasörünü koruyor ve sohbetlere kurtarma kopyası alıyor. F4 yalnız kayıt hatasındaki yarım işlem hakkındadır.

## Bulgular

### F1 — P1: Bir alt adım doğrulanınca çok adımlı görev erken bitiriliyor

**Yer:** `core/natural_desktop.py:94`, `:1335–1340`, `:1348–1371`; `core/task_outcome.py:43–47`.

Kullanıcının tırnak içindeki metni ekranda görüldüğünde host, görevin kalan şartlarını değerlendirmeden modele `Do not call more tools ... end your turn` talimatı veriyor. Özet ayrıca “Görev tamamlandı” diyor.

**TESTED karşı örnek (FakeBackend, gerçek masaüstü değil):**

`Test uygulamasına 'deneme' yaz, sonra pencereyi küçült ve sonucu kontrol et.`

Yalnız metin girildi; küçültme yapılmadı. `desktop_act` yanıtında yukarıdaki bitirme talimatı üretildi. Özet tamamlanma dedi. Olumlu sınır: `goal_verdict` hâlâ `NOT VERIFIED`; sorun goal alanının yanlış VERIFIED olması değil, orkestrasyonun kalan işi bırakması ve yanıltıcı özet.

**En küçük çözüm:** Metin eşleşmesini yalnız alt-adım kanıtı olarak taşı. Genel görev için devamı kesme. Ancak bağımsız, tüm hedefi kapsayan host postcondition varsa bitirme önerisi ver. Çok adımlı ve tırnak içeren inceleme görevlerini regresyona ekle.

### F2 — P1: Stop oracle'ı açıkça doğrulanmamış temizliği onaylayabiliyor

**Yer:** `scripts/exam_oracle.py:277–280`.

`marks.stop_receipt_confirmed=False` iken bir assistant mesajının `metadata.status=cancelled` olması kontrolü geçiriyor. İptal durumu süreçlerin gerçekten kapandığını veya cleanup receipt'inin onaylandığını kanıtlamaz.

**TESTED çıktı:** `{"check":"stop_receipt_confirmed","kind":"host","passed":true}`.

Bu tek kontrolün yanlış geçmesidir; diğer kontrolleri de bulunan her Stop sınavının otomatik geçtiği iddia edilmiyor. Uygulamadaki Stop'un bozuk olduğuna dair yeni canlı kanıt da değildir.

**En küçük çözüm:** Açık false kesin ret olmalı; eksik receipt onay sayılmamalı. Gerçek cleanup/process exit alanından doğrula. `cancelled` tek başına yeterli olmasın.

### F3 — P1: Araç kullanılmadı / reviewer yan etki yapmadı kontrolleri eksik kanıtta başarılı

**Yer:** `scripts/exam_oracle.py:152–155`, `:213–228`; üretici/kalıcılık sınırı `core/multi_agent_service.py:171–188`, `core/agent_chat.py`; tüketici `scripts/exam_live.py:274–315`.

- `no_tool_calls_recorded`, metadata'yı string'e çevirip yalnız `commands` arıyor. Yapılandırılmış `command_results` içinde exit0 komut kaydı bulunsa bile true döndü.
- `reviewer_side_effects_none`, reviewer run ID mevcut fakat gözlem/receipt hiç yokken true döndü. İzin etiketinin read-only olması gerçekleşen yan etki ölçümü değildir.
- Gemini'nin açık integration request'inde belirttiği kalıcılık köprüsü hâlâ eksik: runtime alanları durable receipt ve terminal sohbet metadata'sına tam taşınmıyor. Bu bölüm yeni keşif değil, **kaynakta doğrulanan açık teslim maddesi**.
- IR örneğindeki `unauthorized_writes` adı runtime'ın gerçek `unauthorized_files_changed` adıyla aynı değil (`core/codex_runtime.py:278,439`, `core/antigravity_runtime.py:297,416`). Uygularken tek sözleşme seçilmeli; örnek doğrudan kopyalanmamalı.

**TESTED:** İki karşı örnekte de ilgili host check `passed:true` verdi.

**En küçük çözüm:** Kanıt yokluğunu UNKNOWN/NOT VERIFIED tut; ilgili tüm çalışma yollarının receipt'lerini aynı şemayla taşı. `command_results` ve unauthorized-write alanlarını yapısal olarak oku. Gerçek bir izinsiz yazma gözlemlendiği iddia edilmiyor.

### F4 — P2: Proje kaldırma iki kayıt arasında yarım kalabiliyor

**Yer:** `core/agent_chat.py:346–350`, `core/project_registry.py:119–123`.

Sohbet silme ve yedekleme disk üzerinde tamamlandıktan sonra proje kaydı yazılıyor. İkinci yazma hata verirse rollback yok; bellek ve diskte farklı proje durumu kalıyor.

**TESTED — yalnız disposable klasörde kayıt hatası enjekte edildi:**

```text
registry_file_unchanged = true
project_registered_after_restart = true
project_registered_in_current_memory = false
conversation_visible = false
project_source_intact = true
recovery_copy_contains_original_chat = true
```

Proje yeniden açılışta geri gelirken sohbetleri listede kaybolmuş kalabiliyor. Kurtarma kopyası var; kalıcı ve kurtarılamaz dosya kaybı iddiası değildir.

**En küçük çözüm:** İki kayıt için geri kazanılabilir işlem/rollback düzeni; başarısız `_save` sonrasında registry belleğini de geri al. Disk hata testini ekle. Proje klasörüne dokunma.

### F5 — Kanıt/provenans: Gemini'nin “249 test” kaydı kabul edilemiyor

**Yer:** `docs/GEMINI_REVIEW_CLAUDE_20261108.md` bölüm 2; düzeltme kaydı `docs/CLAUDE_NOTE_ON_GEMINI_REVIEW_20261108.md` bölüm 1.

Alıntılanan komuttaki altı test modülü mevcut main'de yok. Claude aynı komut için 137 vaka / 6 import hatası kaydetmiş; bu eski yeniden koşu bu incelemede tekrarlanmadı. Bu nedenle 249 PASS bu komutun doğrulanabilir çıktısı sayılamaz. Kod bulguları kendi başlarına değerlendirilmelidir. Niyet hakkında çıkarım yapılmıyor.

Bu oturumun aşağıdaki 1518 vakalık gerçek güvenli suite sonucu ayrı, güncel kanıttır; eksik oracle kapsamını kendiliğinden kapatmaz.

## Gerçek çalıştırılan kontroller

| Seviye | Kontrol | Sonuç |
|---|---|---|
| TESTED | `scripts/run_safe_tests.py`, `QUARTZ_LIVE_TOOL_TESTS` kaldırılmış, dotenv/provider sentinel izolasyonu | 1518 vaka, 1516 başarılı, 2 atlandı; 195.514 sn; exit0 |
| SOURCE/STATIC | `python -B scripts/check_python_syntax.py` | 337 Python dosyası OK |
| SOURCE/STATIC | `python -B scripts/check_gui_javascript.py` | Embedded JS exit0 |
| SOURCE/STATIC | `python -B scripts/audit_publish.py --staged --history` | PASS; 559 dosya (rapor dahil), 1196 history blob, finding0 |
| TESTED | Özel `oracle_and_goal_probe.py` | F1–F3 karşı örnekleri tekrarlandı; FakeBackend ve geçici Context, hesap/masaüstü yok |
| TESTED | Özel `project_io_probe.py` | F4 tekrarlandı; yalnız geçici proje, özgün veri yok |
| BUILT | Yeni paket | NOT TESTED — bu incelemede derlenmedi |
| LIVE VERIFIED | Yeni Quartz ana sohbet / masaüstü / model hesabı | NOT TESTED — bu incelemede açılmadı |

Güvenli suite komutu (PowerShell, rapordaki kaynak SHA üzerinde):

```powershell
python -X utf8 -B -c 'import os,runpy; os.environ.pop("QUARTZ_LIVE_TOOL_TESTS",None); runpy.run_path("scripts/run_safe_tests.py",run_name="__main__")'
```

Ham loglar ve karşı örnek script/çıktıları yalnız yerelde:
`%USERPROFILE%\.codex\backups\quartz-review-20261109\`.
Asıl dosyalar: `full-suite.log`, `oracle_and_goal_probe.py`, `oracle-goal-result.json`, `project_io_probe.py`, `project-io-result.json`. İlk keşif çıktısı `probes.json` içindeki project-on-disk alanı liste üyeliği yanlış hesaplandığı için **kullanılmadı**; doğru yeniden koşu `project-io-result.json` ile yapıldı. İlk probe kurulum hatası da kaynak hatası değildir.

Yerel iki sınav kanıt kökünde 25 `grade.json`, 18 ayrı task bulundu (13 VERIFIED, 4 NOT VERIFIED, 8 FAILED kayıt). Bunlar geçmiş denemelerin ham etiket sayısıdır; aynı görev tekrarları, farklı kaynaklar ve GUI/hizmet koşuları karışıktır. **Güncel sürümün kabul skoru veya 13 canlı başarı olarak kullanılmadı.**

## Koruma ve sonraki karar

- İnceleme başlamadan kaynak ref'leri özel `before-review.bundle` içine alındı; kullanıcı verisi eklenmedi.
- Ortak checkout'un mevcut kirli dosyaları, diğer ajan dalları, kurulu uygulama ve geçmiş kanıtlar değiştirilmedi. Bu dal yalnız bu raporu ekler.
- Erişim/token/Stop/fresh-observation sınırlarını gevşeten düzeltme önerilmedi. ASTER/Warband ve korunan kayıtlar kapsam dışı kaldı.
- Öncelik: F1 görev devamı → F2/F3 güvenilir oracle ve kanıt köprüsü → F4 hata anında geri alma → aynı kaynak/paket ile dar canlı kabul. F5 eski rapora düzeltme/provenans notu olarak korunmalı.
- Şu anki değerlendirme **SOURCE/TESTED inceleme tamamlandı, üretim düzeltmesi ve yeni paketli kabul yapılmadı**. Yeni geniş framework veya tekrar tasarım gerekmiyor.
