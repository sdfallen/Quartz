# Dalga 0 teknik kapanışı / Dalga 1 alan sahibi değerlendirmesi

Tarih: 5 Kasım 2026. İnceleyen: Codex. Üretim kodu bu teslimde değiştirilmedi.
Kendi dal/worktree: `codex/wave0-close-wave1-review-20261105` / `quartz-wave0-close-20261105`.
Kaynaklar: plan dalı `7b372f2`, Gemini raporu `8148d83`, R1 düzeltmesi `1a18556`.
Not: önceki `CODEX_WAVE0_REVIEW_20261105.md` tarihsel ret kaydıdır; onun R1 kararı
bu yeniden incelemeyle güncellenir, eski başarısız kanıt silinmez.

## 1. R1 — ACCEPT / SOURCE + TESTED

`core/desktop_broker.py:137–148` artık `renew(token)` alır, token'ı
`hmac.compare_digest` ile mevcut oturumun bearer'ıyla karşılaştırır. Eşleşmeyen,
bitmiş ve bounded oturumların expiry değeri değişmez. `core/natural_desktop.py:1119`
yalnız kendi `self.connection["token"]` değerini geçirir. Stop, pencere kimliği,
UAC ve 15 saniyelik taze gözlem sınırları değişmedi.

Eski `renewal_owner_probe.py` aynen çalıştırıldı: yeni imza nedeniyle
`TypeError: DesktopBroker.renew() missing 1 required positional argument: 'token'`.
Bu sonuç tek başına R1'in kapandığı iddiası değildir. Aynı fixture'daki callback,
yeni API'ye uygun olarak eski oturumun token'ını geçirecek şekilde uyarlandı.

Komutlar (kanıt dizini repo dışında):

```text
python -X utf8 -B <wave0-evidence>/renewal_owner_probe.py <current-worktree>
python -X utf8 -B <close-evidence>/renewal_owner_probe_token.py <current-worktree>
python -X utf8 -B scripts/run_safe_tests.py tests.test_desktop_broker tests.test_natural_desktop tests.test_elevation tests.test_stop_discovery_failure
```

Gerçek uyarlanmış çıktı:

```json
{"expected":false,"actual":false,"before":61,"after":61,"missing_token_rejected":true,"current_owner_renewed":true,"stopped_token_rejected":true}
```

İlgili test: 109 vaka OK, skip0, 37.985s. Fixture gerçek DesktopBroker ve bellek
içi FakeBackend kullanır; yerel masaüstü/hesap veya GUI kabulü değildir.

## 2. Entegrasyon ve paket eşliği

Temiz, zaten `main` üzerinde bulunan entegrasyon worktree'sinde yalnız
`git merge --ff-only 1a18556` yapıldı. Ortak Desktop checkout'ta dal değiştirilmedi.
`main = 1a185561ad003cbed9be6febda03dc82dd351186`.

Koşucu `837b44f` ve `e6e1170`, bu yeni main üzerine kendi dalımda cherry-pick:
`5f48657` ve `2930942`. Koşucu/report commit'leri henüz main'e alınmadı. Böylece
main'in SHA'sı bildirilen kurulu paket kaynak commit'iyle **birebir aynı** kaldı.
Koşucu çalışma dalı SHA'sı farklıdır; onun paketlenmiş olduğu söylenmiyor.

Kurulu EXE SHA256:
`4a42e09dde30286e7c3626aa80e677650d946891e50fce2679c53cc0595238ce`.
Hash kullanıcı bildirimiyle eşleşti; on ilgili paket modülü pasif bytecode
karşılaştırmasında kaynakla eşleşti. Bu paket açma/derleme/kurulum değildir.
BUILT: bu oturumda yapılmadı. LIVE VERIFIED: bu oturumda yapılmadı.

## 3. Gemini'nin beş yanlış başarı yolu

Hükümler mevcut 1a18556 üretim koduna göre SOURCE/STATIC'tir. Bir `completed`
alanının varlığıyla gerçek kullanıcı hedefinin başarıyla doğrulandığı aynı şey
değildir. Kanıtlanmış uçtan uca yanlış başarı sayısı bu incelemede ölçülmedi.

| ID | Gemini iddiası | Hüküm | Dosya:satır ve gerekçe |
|---|---|---|---|
| F1 | İç komut hatası/no-diff olsa da CLI metniyle completed | **Kısmen doğru** | `core/codex_runtime.py:474–478,548–549`; `core/antigravity_runtime.py:421–425,532–534`: alt komut sonucu kaydedilir, final predicate her iç exit code'u değerlendirmez. Ama beklenen negatif test veya doğru no-op da nonzero/no-diff üretebilir; bunlar otomatik hedef başarısızlığı değildir. `core/task_outcome.py:4–10` hedef kabulünü yürütmeden ayırır. Bağımsız görev oracle'ı açığı var; her nonzero'yu koşulsuz fail yapmak doğru çözüm değil. |
| F2 | Writer doğrulaması başarısızken sohbet completed kalır | **Kısmen doğru** | `core/multi_agent_service.py:136–158`; `core/agent_chat.py:1255,1402,761–770`: durum ile geç gelen receipt ayrı. Fakat `ui/js_messages.py:141–147` başarısız kaynak kontrolünü ve henüz çalışma/test kanıtı olmadığını açıkça gösteriyor; mevcut UI bunu verified başarı diye etiketlemiyor. Veri tüketicisinin status-only kabul etmesi hâlâ risk. `agent_chat.py:933–947` takip talimatında writer bariyeri de var; bu güvence raporda eksik. |
| F3 | Read-only AGY yan etkisi host diff olmadan gözden kaçabilir | **Kısmen doğru** | `core/multi_agent_service.py:41–45,535–560`; `core/antigravity_runtime.py:247–250`: Windows sandbox'ın katı dosya yalıtımı sağlamadığı açıkça belgelenmiş; readonly dispatch writer watcher başlatmaz. Bu gerçek gözlem boşluğu, ama somut izinsiz yazma veya yanlış başarı koşusu değil. Eşzamanlı yazıcının diff'ini inceleyene mal etmek de yanlış olur. |
| F4 | Read-only grupta bir ajan başarılıysa genel tur completed | **Doğru** | `core/agent_chat.py:1755–1756`: write=False için OR, write=True için AND. Bir katılımcı failed iken completed turn mümkündür. Başarısız balon korunur, fakat ortak verdict'in degraded/partial ayrımı yok. `:816–839,933–938` bu step sonucunu terminal tur durumuna taşır. |
| F5 | Desktop verify olmadan doğal görev completed olabilir | **Kısmen doğru** | `core/natural_desktop.py:621,1028,1086,1153,1219`: yeni eylem doğrulamayı siler, CLI terminalinden execution completed üretilebilir. Ancak `core/task_outcome.py:4–10,24–25` goal_accepted=False ve NOT VERIFIED bilgisini korur, tamamlanma metni de bunu söyler. Risk status-only tüketicidedir; mevcut sözleşmenin kaldırılması değil her tüketicide korunması gerekir. |

## 4. Gemini'nin beş çift otorite bulgusu

| ID | Bulgu | Hüküm | Dosya:satır ve gerekçe |
|---|---|---|---|
| D1 | Runtime/service/journal üç yazıcı otoritesi | **Kısmen doğru** | `core/multi_agent_service.py:80–134,136–167,854–867`; `core/codex_runtime.py:224–246,571–576`; `core/antigravity_runtime.py:213–238,554–559`; `core/writer_journal.py:100–135`: üç kayıt var, ama runtime süreç ömrünü, service doğrulama/kapanış bariyerini, journal süreçler arası kurtarmayı korur. Farklı release zamanı kasıtlı güvenlik katmanıdır; doğrudan çelişki veya çift yazıcı kanıtı değil. Kilit kaldırılmamalı. |
| D2 | Active turn/store/GUI job üç aktif görev kaynağı | **Kısmen doğru** | `core/agent_chat.py:27–33,549–569,816–839`; `core/natural_desktop.py:254–258`; `core/chat_coordination.py:183`; `gui.py:393–394,495–501`: kayıtlar var, fakat store bir projection/geçmiş, GUI job ayrı yürütme dalıdır. Aynı kaydın eşit yetkili üç kopyası oldukları kanıtlanmıyor. Ortak correlation ve admission sözleşmesi ihtiyacı doğru; yeni global görev tablosu gerektiği sonucu çıkmaz. |
| D3 | CLI ile host iki files_changed otoritesi | **Kısmen doğru** | `core/codex_runtime.py:480–484`; `core/antigravity_runtime.py:427–434`; `core/multi_agent_service.py:142–150,695–701`; `core/run_evidence_store.py:34–57`: union özet alanında reported/observed kökenleri karışır. Fakat host receipt ayrıca saklanır ve historical olarak okunur; iki kaynak aynı kanıt ağırlığında değildir. Alanları reported/observed diye açık adlandırmak uygun, birini silmek değil. |
| D4 | task_id katmana göre farklı nesneyi ifade eder | **Doğru** | `core/agent_chat.py:505`; `core/natural_desktop.py:395,997`; `core/multi_agent_service.py:465–467,562–564`: context'te yerel job.id, task_message yanıtında Squad task_id kullanılıyor. Token kapsamı bundan türetilmediği için tek başına yetki aşımı kanıtı yok; korelasyon sözleşmesi belirsiz. |
| D5 | 15/60/300 sn üç probe cache otoritesi | **Kısmen doğru** | `core/agent_chat.py:32`; `core/async_snapshot.py:13–46`; `core/multi_agent_service.py:234–249,894–897`; `core/codex_runtime.py:21`; `core/antigravity_runtime.py:26`: TTL zinciri doğru. AsyncSnapshot açıkça read model, izin/ready otoritesi değil. Farklı cache seviyeleri kendiliğinden tutarsız yetki demek değil; freshness ve yenileme maliyeti ölçülmeli. Squad alt süreçleri model çağrısı değildir. |

Bu on iddia içinde tamamen yanlış sayılan yok; kısmen doğru olanlarda olgu
korunup aşırı yorum sınırlandı. Gemini'nin `/model --print-timeout 1440m` çıktısı
CLI bayrağının kabulünü rapor ediyor; iki saatlik model görevi kanıtlamaz.
Tekrar gerçek hesap çağrısı yapılmadı. Headless RSS/CPU ölçümü de paketli GUI
performansı olarak genellenmez.

## 5. Dalga 2 öncelikli iş listesi — önce yanlış başarı

| Öncelik | İş / sahip | Kapsam ve kabul testi |
|---|---|---|
| P0-1 | Sonuç sözleşmesini tüm tüketicilerde koru / Codex; UI Claude | execution/evidence/goal acceptance/cleanup ayrı kalır. Source validation failed/pending veya veri yokken VERIFIED çıkmaz. Fixture: CLI completed + syntax error; receipt gecikmesi; receipt disk hatası; failed → polling; yeniden açılış historical. Mevcut UI uyarısı korunur. F2/F5. |
| P0-2 | Ortak grup verdict'i / Codex; UI Claude | İstenen katılımcı failed ise birlikte görev VERIFIED olamaz; explicit fallback yalnız degraded/partial olarak gösterilir. İki sağlayıcı fail/success/timeout/cancel kombinasyonları, Stop sonrası geç yanıt testi. F4. |
| P0-3 | Görev oracle'ı / Codex; runtime olay alanları Gemini | Final metin veya exit0 hedef sonucu değildir. Gerçek hedef koşulu/test sonucu ayrı kanıt olur; beklenen nonzero ve geçerli no-op reddedilmez. Eksik oracle NOT VERIFIED. İç komut hata→onarım→başarılı test ve no-op fixture'ları. F1. |
| P1-1 | Yanıtsız izin beklemesinde gerçek pause / Codex; broker+UI Claude | Aşağıdaki ayrı tasarım uygulanır; bu teslim kod değişikliği yapmaz. Expiry görevi bitirmez, stale izin canlanmaz. |
| P1-2 | task/turn/run/Squad kimliklerini açık eşle / Codex | Mevcut ID'ler değiştirilmeden yeni açık isimler/korelasyon eklenir. Aynı chat'te iki görev, eski callback, yanlış conversation/generation, restart ve message route testleri. D4/D2. |
| P1-3 | Salt okunur incelemenin sınırını dürüstçe ölç / Gemini; Codex inceleme | OS yalıtımı varmış gibi konuşulmaz. Reader ve izinli writer aynı projedeyken değişiklikler kaynağı olmadan reader'a mal edilmez. İzole fixture'da yetkisiz yan etki fark edilir ve kabul engellenir. Yeni full/yönetici yetkisi verilmez. F3. |
| P2-1 | Yazıcı bariyerlerinin tek sözleşmesi / Codex+Gemini | Üç kilit silinmez; CLI exit→receipt pending→journal release sırası assertion'larla sabitlenir. Canonical path/overlap, watcher error ve crash-recovery testleri. D1. |
| P2-2 | Bildirilen ve gözlenen diff'i ayır / Codex; UI Claude | reported_changes/observed_changes ve gözlem kapsamı ayrı, union yalnız sunum. Shell write, tool write, readonly bilinmeyen ve concurrent writer fixture'ları. D3. |
| P2-3 | Cache freshness / Gemini; Codex tüketici incelemesi | TTL seviyeleri gelişigüzel birleştirilmez; age/generation/source ve invalidation ölçülür. Idle model start=0, gerçek CLI/Squad process sayısı ayrı; login değişimi ve cache eskiyken launch testi. D5. |

R1 yeniden açılmadan ve source/test regresyonu olmadan küçük dilimler halinde
ilerlenir. G1–G8 canlı skor kartı bu rapordan türetilmez.

## 6. Kontroller / devam

Tam kontrol ve smoke sonuçları aşağıdaki teslim ekine yazılır. Ham loglar,
hesap çıktıları ve ekran kanıtları repo dışında `<close-evidence>` dizinindedir.
`docs/APPROVAL_PAUSE_DESIGN_20261105.md` yalnız tasarımdır; aktif kod hâlâ on
dakikalık permission expiry'de stop eder. Bu karar uygulanmış gösterilmez.

### Tam kontrol sonuçları

Kontrol edilen kod tabanı `2930942`; sonraki değerlendirme commit'i yalnız
repo belgeleri/sahiplik durumu ekler, core/ui/GUI koduna dokunmaz.

| Komut | Sonuç | Kanıt dosyası |
|---|---|---|
| R1 hedefli safe-suite (yukarıdaki dört modül) | 109 OK, skip0 | r1-targeted.log |
| `python -B scripts/run_safe_tests.py` (explicit live tool env kaldırıldı) | 1325 vaka; 1323 başarılı, 2 skip; 223.368s | full-suite.log |
| `python -B scripts/check_python_syntax.py` | Published Python syntax: 314 files OK | syntax.log |
| `python -B scripts/check_gui_javascript.py` | Embedded JS exit: 0 | javascript.log |
| `python -B scripts/audit_publish.py --staged --history` | PASS; 505 dosya, 910 history blob, bulgu0 | publish-audit.log |
| `git diff --cached --check` | exit0 | teslim terminal kaydı |
| Pasif EXE hash / on modül code signature karşılaştırması | Kullanıcı SHA'sı ve main SHA'sı eşleşti; 10/10 kaynak eşliği | package-main-comparison.json |

Koşucu smoke komutu:
`python -B scripts/task_exam_runner.py --manifest docs/task_exam_manifest.example.json
--output <yeni-özel-dizin> --execute --package <kurulu-paket>`.
Yalnız safe-suite ve sentetik süreç adaptörü; gerçek hesap/masaüstü çağrısı yok.
Sonuçların kaynak SHA, süre, agent-step belirsizliği ve paket hash'i özel
`runner-smoke/result.json` dosyasında korunur; bu G1–G8 canlı skor kartı değildir.

### Geri alma ve açık işler

- Başlangıç bundle: `before-close.bundle`; son teslim bundle'ı ayrıca tutulur.
- Main'in kaynak değişimi yalnız 643b51f + 1a18556'dır. Gerekirse **yeni geri
  alma dalında** `git revert 1a18556 643b51f` ile önceki davranışa dönülür;
  bu oturumda geri alma yapılmadı, kurulu EXE bundan etkilenmez.
- Koşucu eski dalları değiştirilmeden cherry-pick edildi: 837b44f→5f48657,
  e6e1170→2930942. Ayrı dalında tutulur; main/kurulu kaynak SHA eşliği korunur.
- R1 teknik kapanışı sağlandı; iki saatlik gerçek görev, kullanıcı kabulü ve
  Claude'un 30 görev listesiyle G1–G8 ölçümü henüz bu oturumda yapılmadı.
- Dalga 2 izin pause tasarımı ve öncelik listesi hazır; uygulanması ayrı iştir.
- GitHub push, paket kurma/derleme, Quartz açma ve gerçek masaüstü testi yok.
