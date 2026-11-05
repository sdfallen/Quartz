# Sohbette görev durumu gösterimi: bulgular ve tasarım (5 Kasım 2026)

Dal: `claude/status-display-20261105`, taban `main` `1a18556`. Plan Dalga 2, P0-1 ve P0-2'nin arayüz kısmı.
Durum: **tasarım; kod değişmedi.** Codex'in yeni sonuç alanları belirlenince uygulanır. Seviye SOURCE/STATIC.

## 1. Bugünkü gösterim

| Yer | Kaynak | Ne gösteriyor |
|---|---|---|
| Ajan balonu üst satırı | `ui/js_messages.py:132–155` `agentMessageView` | `failed`, `cancelled`, `interrupted`, `blocked`, `awaiting_approval` için Türkçe etiket. `completed` için yalnız yazma izinli (`project`/`full`) turlarda kaynak kontrolü özeti |
| Balon rengi | `ui/js_messages.py:497–498` | Yalnız `failed` hata stilinde; diğer her durum normal yanıt gibi |
| Masaüstü/koordinasyon kartı | `ui/js_desktop.py` `pollCoordination` | `completed` için "Çalışma sona erdi; hedefin sonucunu ajan kanıtlarından kontrol edin." |
| Doğal görev kapanış mesajı | `core/task_outcome.py` `stop_summary` | "Ajan yürütmesi tamamlandı; bu, tüm hedefin doğrulandığı anlamına gelmez." |
| Yerel asistan görev kartı | `ui/js_messages.py:611–630` `renderTasks` | `✓ <başlık>` ve `n/m adım · completed` |

Masaüstü görev kartı ve doğal görev kapanış mesajı dürüst: yürütmenin bitmesiyle hedefin doğrulanmasını ayırıyorlar.

## 2. Yanıltıcı veya eksik noktalar

1. **Kısmi grup sonucu görünmüyor (F4).** Salt okunur Birlikte turunda bir ajan başarısız olunca tur `completed` kapanıyor.
   Balonun üst satırı salt okunur turda boş kaldığı için ortak sonuçta hiçbir uyarı yok. Yalnız başarısız ajanın kendi balonu hata gösteriyor.
2. **Salt okunur inceleme turu doğrulama bilgisi taşımıyor.** "İncele, test et" gibi araç kullanan ama yazmayan turlarda `completed` iken
   üst satır boş. Kullanıcı bunu sonucun doğrulandığı şeklinde okuyabilir.
3. **`blocked` yanlış etiketleniyor.** `blocked` "Henüz doğrulanmadı" yazıyor. Oysa görev engellendi (UAC, kilit ekranı, takılma);
   kullanıcı ne yapması gerektiğini bilemiyor.
4. **Durduruldu ve kesildi normal yanıt gibi görünüyor.** Stil yalnız `failed` için değişiyor; `cancelled`, `interrupted` ve `blocked`
   yalnız küçük üst satırla ayrışıyor.
5. **Yerel asistan görev kartı İngilizce ve onay işareti taşıyor.** `n/m adım · completed` İngilizce durum adını gösteriyor;
   `✓` hedefin başarıldığı izlenimini veriyor. Bu kart yerel asistan yolunun kendi görevleri içindir; doğrulama kavramı orada yok.
6. **Kanıt kapsamı görünmüyor.** Doğal görevde `desktop_verify` başarılı olsa bile (`OBSERVED UI CRITERION VERIFIED`) neyin doğrulandığı,
   yani kapsam metni (`evidence_scope`), sohbette ayrı gösterilmiyor; yalnız teknik ayrıntıda kalıyor.

## 3. Önerilen durum dili

Her balon ve kart, iki ayrı bilgiyi tek bir kısa rozetle gösterir: **yürütme ne oldu** ve **kanıt ne diyor**. Renk tek başına anlam taşımaz;
her rozette metin ve simge bulunur.

| Rozet | Koşul | Ek satır |
|---|---|---|
| Çalışıyor | `running`, `starting` | yok |
| Onay bekleniyor · görev duraklatıldı | `awaiting_approval` / `paused` | "Onay vermeden ajan bilgisayarda işlem yapmaz." |
| İzin süresi doldu · yeniden onay gerekli | duraklatılmış görevde süresi dolan kart (Dalga 2 P1-1) | Yeniden onay düğmesi |
| Bitti · doğrulanmadı | `completed`, kanıt `NOT VERIFIED` veya yok | Varsa kaynak kontrolü özeti (bugünkü metin korunur) |
| Bitti · kısmen doğrulandı: \<kapsam\> | `completed`, kapsamlı kanıt `VERIFIED` (ör. UIA metni), `goal_accepted` false | Kapsam metni, kısaltılmadan |
| Kısmi sonuç · \<ajan\> başarısız | grup turunda istenen ajanlardan biri `failed` (P0-2) | Başarısız ajan adı ve tek satır neden |
| Engellendi | `blocked`, `blocked: ...` | Neden ve kullanıcının yapabileceği tek şey (ör. "UAC penceresini siz onaylayın") |
| Durduruldu | `cancelled` | Durdur makbuzu `confirmed` değilse "temizlik doğrulanmadı" |
| Kesildi | `interrupted` | Bugünkü taslak oluşturma düğmesi korunur |
| Başarısız | `failed` | Bugünkü hata metni |

**"Doğrulandı" rozeti yoktur.** `goal_accepted` bugün hiçbir yolda `true` olmuyor; olsa bile yalnız kanıt kapsamıyla birlikte gösterilir.
Kapsam bilgisi olmayan bir kanıtta en fazla "Bitti · doğrulanmadı" yazılır.

Sade sohbet yanıtlarına rozet konmaz: araç, yazma, masaüstü veya grup turu olmayan normal soru-cevap bugünkü gibi temiz kalır.

Yerel asistan görev kartında `✓` kaldırılır, durum adları Türkçeye çevrilir: tamamlandı, başarısız, iptal edildi, çalışıyor.

## 4. Codex'ten beklenen alanlar (integration request)

UI yalnız backend'in verdiği alanları okur; başarıyı kendisi çıkarmaz. P0-1 ve P0-2 için önerilen, mevcut `execution_outcome`
sözlüğüyle uyumlu alanlar:

| Alan | Değerler | Not |
|---|---|---|
| `execution_status` | bugünkü durum adları | Değişmez |
| `evidence_status` | `NOT VERIFIED`, `VERIFIED`, `FAILED` | Mesaj metadata'sında da bulunmalı, yalnız görev `result.json`'da değil |
| `evidence_scope` | kısa Türkçe metin | `VERIFIED` ise zorunlu |
| `goal_accepted` | `false` (bugün her zaman) | Değişmez |
| `participants` | `[{agent, status}]` | Yalnız grup turunda; ortak tur `partial` ise UI başarısız ajanı buradan okur |
| `partial` | `true` / yok | İstenen katılımcı başarısız ama tur bir yanıt üretmişse |
| `blocked_reason` | kısa kod: `uac`, `locked`, `stalled`, `window_closed`, `permission_expired` | UI metni koddan seçer; serbest model metni rozet olmaz |

Adlar Codex'in son kararıdır; farklı ad seçerse UI ona uyar. Alanlar yoksa UI bugünkü gibi davranır.

## 5. Uygulama ve testler (Codex alanları gelince)

Dosyalar Claude alanında: `ui/js_messages.py`, `ui/js_desktop.py`, `assets/workspace.css`, `tests/test_gui_*`.

- Rozet eşlemesi için tablo testi: yukarıdaki her satır, bir de alanların hiç olmadığı eski kayıt.
- "Doğrulandı" kelimesi kapsam metni olmadan hiçbir rozette çıkmaz.
- Grup turu: bir ajan `failed` iken ortak balon "Kısmi sonuç" gösterir; iki ajan başarılıyken göstermez.
- `blocked` her kod için anlamlı Türkçe metin verir; bilinmeyen kod "Engellendi" olarak kalır, model metni gösterilmez.
- Yerel asistan kartında İngilizce durum adı ve `✓` kalmaz.
- Rozetler metin içerir, renk tek başına anlam taşımaz; ekran okuyucu için `role="status"`.
- Gerçek görünüm ayrıca canlı denenir; testler bunu kanıtlamaz.
