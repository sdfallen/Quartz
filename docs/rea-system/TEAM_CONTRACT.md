# Quartz REA — tek görev, üç uzman, birleşik teslim

Durum: üç teslim ayrı geçmişleri korunarak birleştirildi ve ek Windows incelemesiyle düzeltildi. Üretim kodu d69e04f, test/inceleme8ddbc40; son1148-case suite hata0/skip2. Yeni paketli ana sohbet incelemesi BLOCKED; kullanıcı kurulumu değiştirilmedi. Ayrıntı INTEGRATION_REVIEW_20261102.md ve FINAL_VALIDATION.json.
Tarih: 2026-11-02. Kod/rapor başlangıcı: 732791af26a7e6ab0cba0c36ae52221e8984006f. Son mevcut kod düzeltmesi: 3b1d506. Windows temel suite967 PASS/skip0. Kurulu EXE de512a5d362bf7bf073a3e32af5ac2d6e8725c27686dabce54edf1a3ddb68d05 korunur; yeni teslim doğrulanmadan değiştirilmez.

## Ürün hedefi

Tek ana sohbet görevinden: soruyu ve hedefi belirle → mevcut bilgiyi sürümle doğrula → gerekli statik/davranış araçlarını seç → eksik araçları doğrulanmış kaynaklardan yönetilen alana edin → kanıt topla → hipotezleri sınayarak sonuç üret → izinli değişikliği checkpoint ile uygula → gerçek sonucu test et → doğrulanmış bilgiyi sakla. Bu, kullanıcıya her parça için yeniden görev verdirmek anlamına gelmez; ajanların kendi içinde checkpoint, test ve entegrasyon kapıları zorunludur. Tek birleşik teslim vardır.

Hedef yetenekler: oyun motoru/runtime tanıma, native/managed/paketli uygulama çözümleme, modlanabilir veri/API/yükleme sınırlarını haritalama, gerçek uygulama davranışıyla statik bulguları bağlama, sürüm farkları, araç seçimi ve kanıtlı prosedür hafızası. Evrensellik; hedef yeteneklerini keşfetme ve destek sınırını açık gösterme şeklinde ölçülür. Bir EXE başlığını okumak motoru çözmek veya uygulamayı test etmek değildir.

## Dengeli sahiplik

| Sahip / istenen model | Kritik üretim sorumluluğu | Tek yazacağı alanlar |
|---|---|---|
| Codex / 6.1 Sol high | Motor/native/managed/paket çözümleme, investigation yaşam döngüsü, soru/araç yürütmesi, chat/Broker/REA bağları, son kabul ve entegrasyon | core/rea_analysis/, core/investigation/session.py gateway.py planning.py, core/rea_adapter.py, servis/GUI/paket bağları; kendi analiz/gateway/frontend testleri |
| Claude / Opus5.5 | Kanıt kökeni ve bütünlüğü, doğrulanmış öğrenme/prosedür hafızası, çelişki/başarısızlık sonrası invalidation, eski bilginin güvenli kullanımı | core/investigation/contracts.py evidence.py memory.py ve yeni learning.py; core/application_knowledge.py; tests/test_investigation_evidence.py test_rea_learning.py ve yeni test_learning_*.py; docs/rea-system/CLAUDE_MEMORY_REPORT.md |
| Gemini / 3.8Flash | GitHub keşif/edinim ve uyumluluk, yönetilen araç ortamları, süreç/Stop/limit/artifact sahipliği, araç kökeni ve gerçek uçtan uca araç testleri/ölçümleri | core/tool_workbench/, tests/test_tool_workbench_*.py, scripts/tool_workbench_*.py, labs/tool-workbench/, docs/rea-system/GEMINI_REPORT.md |

Her sahibi kendi üretim kodu, olumsuz testler, gerçek araç/uygulama kanıtı ve teslim raporundan sorumludur. Claude ve Gemini yalnız tasarım, mock veya metin denetimi teslim etmeyecek. Son birleştirme Codex'te; herkes bütün kaynakları okuyabilir fakat diğerinin alanına doğrudan yazamaz. Ortak main.py/gui.py, task/store/process_tree, scripts/run_safe_tests.py, .spec/CI/installer/model tercihleri yalnız Codex entegrasyonundan değişir. Gereken sınır değişikliğini integration request olarak raporla.

## Ortak veri sözleşmesi v1

Üretim verisi JSON uyumlu, schema_version=1; keyfi Python nesnesi/eval veya depo talimatı yürütme yok. İmza ekleri geriye uyumlu olmalı.

- Target: target_id, canonical_path, sha256, size, format, version_fingerprint, approved_scope. Dosya hedefi ile çalışma süreci/pencere kimliği ayrı tutulur.
- Capability: capability_id, provider, supported_formats, effects (read_target/write_workspace/execute_tool/attach_runtime), required_tools, available, limitations. Runtime attach ve target execution açık yetenek/scope olarak ayrı değerlendirilir.
- ToolRequest: investigation_id, step_id, operation, tool_id, target, options (şema doğrulamalı), workspace, deadline_monotonic, max_output_bytes. Tüm dış argv merkezi doğrulanır; shell string çalıştırma veya repo metninden komut üretip kör yürütme yok.
- ToolReceipt: request_id, tool_id, source_url, pinned_revision, package_digest, argv_redacted, process_identity, timestamps, exit_code, status, cleanup_receipt, artifacts, limitations. Argv/dosya kanıtı sır içeriyorsa maskelenir.
- Evidence: evidence_id, target_fingerprint, kind, origin, artifact_relative_path, digest, observed_at, scope, level (SOURCE/BUILT/LIVE). String/isim bulgusu gözlenmiş çalışma veya fonksiyon semantiği sayılmaz.
- Finding: claim_id, claim, claim_type (observation/hypothesis/verified_procedure), evidence_ids, confidence_basis, counter_evidence_ids, reproducible, limitations. Modelin özgüveni kanıt değildir.
- KnowledgeRecord: target/version/tool/procedure fingerprint, findings, verification_runs, preconditions, success_check, invalidation, provenance. Bayat bilgi tekrar doğrulanır; model çıktısı talimat/izin kaynağına dönüşmez.
- AnalysisReport: schema_version, target, capabilities_used, findings, artifacts, unsupported, errors, cancellation, cleanup_receipt.

Codex analiz facade: AnalysisService.capabilities(target) ve analyze(request, tool_executor, cancel_event) -> AnalysisReport. İcra gerektiğinde yalnız enjekte edilmiş tool_executor.execute(ToolRequest, cancel_event) kullanılır; global indirici/runtime/memory yazıcısı kurulmaz. Facade için sahte examiner yerine gerçek araç adaptörleri teslim edilir.
Gemini facade: ToolWorkbench.catalog(query), resolve(requirements), acquire(selection, policy, cancel_event), execute(request, cancel_event), stop(investigation_id), close(). acquire hiçbir izin/kapsam üretmez. Read-only executable probe, managed install ve target attach etkileri ayrıdır. Stop/close status confirmed/pending/failed; süreç ölümü gözlenmeden confirmed yok.
Codex bu facadeleri mevcut ApplicationServices ve investigation owner'a bağlar. Startup idle REA/Ghidra/indirici başlatmaz. Normal sohbet gereksiz analiz/araç işi açmaz. Her facade aynı şemayı tests/fixture içinden de kullanabilir; ortak production contract dosyası Codex'te, başkasının paketine circular import ekleme.

## Araç edinimi ve geliştiren hafıza

GitHub araması aday bulur; yıldız sayısı veya README'deki talimat güven kararı değildir. Lisans, gerçek kaynak/release kimliği, sürüm, desteklenen platform, bağımlılıklar ve kurulum yan etkileri değerlendirilir. Revizyon/digest sabitlenir. Repository hook, setup/install script, native executable ve network ayrı etkiler olarak envanterlenir; uygun araç mevcut görev politikası kapsamında yönetilen çalışma alanında otomatik edinilip denenebilir. Sistem PATH/registry/driver/security veya kullanıcı CLI auth dosyaları değiştirilmez. Yönetici yükseltme veya kapsam dışı işlem otomatik onaylanmaz. Gizli servis/IPC, injection/EXE patch veya erişim engeli aşma varsayılan değildir.

Mevcut REA6.8.0 pin'i sessizce yükseltilmez. Yeni sürüm/araç şeması capability probe ve gerçek çıktı fixture'ıyla doğrulanır; cache hash/sürüm değişiminde geçersizdir. REA kalıcı kanıt dosyası geçici klasör silinmeden investigation evidence deposuna taşınır; çıktı boyutu/format/kapsamı doğrulanır.

Öğrenme gerçek kayıtlara dayanır: işe yarayan araç, başarısız yöntem, sürüme bağlı kaynak/fonksiyon ilişkisi, UI/işlem önkoşulu ve tekrar doğrulama sonucu. Bu model ağırlık eğitimi, kendine sınırsız yetki verme veya belgesiz kod değiştirme değildir. Prosedür kaydı tipli ve tekrar doğrulanabilir; hafıza metni keyfi komut olarak çalıştırılmaz. Gizli anahtar, cookie, tüm kişisel loglar veya hedef binary içerikleri üçüncü taraf servise kendiliğinden gönderilmez.

## Tek birleşik kabul matrisi

Her ajan kendi aşağıdaki kapsamını üretim + gerçek kanıt ile kapatır. Eksik harici araç/erişim gerçek BLOCKED olarak kayıtlı kalır; kullanıcıya tek konsolide kalan işler raporu verilir, sahte başarı yok.

1. Mevcut967 temel kontroller ve kaynak/ID/GUI/broker/tek writer/Stop koruması.
2. Native, managed ve paketli uygulama için gerçek format/motor/runtime tespiti; doğru kapsam ve kasıtlı unsupported örneği. Araç yoksa string aramayı disassembly diye gösterme.
3. Yetkili izole native örnekte gerçek sembol/fonksiyon/xref veya eşdeğer teknik ilişki; managed örnekte gerçek assembly/type/method; paketli örnekte gerçek kaynak/modül bağımlılıkları. Çıkarım ile gözlemi ayır.
4. Modlamaya ilişkin mevcut motor/veri/yükleme sınırlarının kanıtlı haritası; en az bir açık/yeniden dağıtılabilir motor örneğinde mevcut çalışan kopyayı bozmayan yerel deney. ASTER kullanılmaz. Hedef motor/sürüm ve somut deney açıkça belirtilir; bütün oyunlar çözüldü iddiası yok.
5. Gerçek izole test uygulamasında gözlem→hipotez→araç bulgusu→izinli dar düzeltme→yeniden çalıştırma. UIA/görüntü ve dosya/hash kanıtı; compiled fixture kaynak anahtarı analiz ajanına cevap olarak verilmez.
6. Gerçek GitHub yardımcı aracını pinned revizyon/digest ile edinme, managed ortamda çalıştırma, artifact üretme; güvensiz/değişmiş/uyumsuz adayın reddi. Büyük bağımlılık veya native kurulum bulunmazsa dürüst sonuç.
7. Stop sırasında child process, download/extract, tool output/drain, analiz ve memory callback yarışları; idempotent kapanış, yetim süreç ve yanlış target0. Gerçek süreç testleri source mock'tan ayrı.
8. Aynı hedefte ikinci görevde geçerli bilgi kullanımı; değiştirilmiş binary/sürüm veya başarısız prosedürde invalidation. Ajanın önceden ezberlediği iddiayı tekrar yazması öğrenme kanıtı sayılmaz.
9. Gerçek yanlış teşhis ve yetersiz bilgi örneğinde hedefli ek araştırma; sonsuz retry/circular tool acquisition önleme, açık bütçe/süre/disk/CPU/RAM ölçümleri. Yapay hız yüzdesi yok.
10. Paketli Quartz ana sohbetinden gerçek investigator kullanımı, iki ajan mesaj/kanıt korelasyonu, tek masaüstü operatörü, ek talimat/Stop ve yeniden başlangıç. UI erişimi engellenirse yalnız ilgili kabul BLOCKED; bağımsız işler sürer.
11. Mevcut967 ve ek testler, resmi paket/asset/hash denetimi, kişisel verisiz temiz dağıtım, user data diff, normal kapanış ve rollback. Her yeni build'in LIVE kapsamı ayrı belirtilir.

## Çalışma ve teslim kuralları

Her ajan görev alanındaki uygulamayı bağımsız tamamlayacak; ilk incelemeden sonra durmayacak. Tek görevin içindeki mühendislik kapıları kullanıcıya ayrı ayrı onaylatılmaz. Başarısız yöntem kanıtsız tekrar edilmez. Bağımsız işler insan UI testi nedeniyle durmaz. Gerçek kullanıcı müdahalesi gereken dar işlem açık gerekçesiyle konsolide edilir.

Rapor: ortak base ve commit, dosya listesi, SOURCE/BUILT/LIVE kanıtı, gerçek hedef/tool sürümü, test komutu/çıktısı, manifest/digest, süreç/Stop readback, benchmark koşulları, açık sınırlar ve integration request. Demo/stub dışarıdan çalışan sistem diye sunulmaz. Claude/Gemini kendi paketini üretim dist'e dağıtmaz; public upload/push/release yok. Kullanıcı verisi ve .env hiçbir bundle'a eklenmez. C:/WarbandIsland ve ASTER/kayıtlar okunmaz/değiştirilmez; Notion üçüncü ajan kapsam dışı, shared memory korunur.

## 2026-11-02 — Claude görev değişikliği

Kullanıcının ekran görüntülerinde Claude, kendi oturumunda bir güvenlik filtresinin derin çözümleme çalışmasını durdurduğunu ve core/rea_analysis için kod yazmadığını bildirdi. Filtrenin kesin nedeni bilinmiyor; yeniden ifadeyle aynı işi tekrarlama talimatı verilmedi. CLAUDE_MEMORY_PROMPT.md tamamen farklı, veri/kanıt/öğrenme üretim görevini tanımlar ve eski CLAUDE_PROMPT.md'nin yerine geçer. Motor/analiz alanı Codex'e taşındı; önceden Codex'in oluşturduğu kanıt ve hafıza kodu baseline olarak Claude'a devredildi. Gemini'nin alanı ve başlangıç dalı değişmedi.

Claude'a ayrılan dosyalar handoff checkpoint sonrası Codex tarafından paralel düzenlenmeyecek. Ortak veri şemasında geriye uyumsuz değişiklik, session veya gateway düzenlemesi integration request ile ilerler. Yeni baseline bundle/manifest aktarılmalı; eski cbc303b bundle'ı yeni hafıza implementasyonunu içermez. Bu sözleşme değişikliği çalışan EXE dağıtımı değildir.
