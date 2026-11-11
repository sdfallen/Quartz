# Kanıt/hafıza başlangıcı — Claude'a veri mühendisliği devri

2026-11-02. Bu checkpoint geliştirme başlangıcıdır; üretim dağıtımı değildir. Kullanıcı ekran görüntülerinde Claude eski analiz görevini kendi oturumundaki filtre nedeniyle kod yazmadan bıraktığını bildiriyor. Kesin filtre nedeni bilinmiyor ve filtreyi aşmak için aynı görev yeniden ifade edilmedi. Yeni görev CLAUDE_MEMORY_PROMPT.md; native/engine analizi Codex'e geçti. Gemini'nin workbench görevi değişmedi.

## Gerçek mevcut kod ve sınırlar

- core/investigation/contracts.py: JSONv1/Target, iptal/deadline, observation/hypothesis/verified_procedure. Yeni dosya/yol veya grant kendiliğinden üretilmez.
- evidence.py: mevcut owner içinde bounded immutable artifact kopyaları ve manifest; source tool output ile host LIVE kaydı ayrımı. Kaynak tipli metadata güveninin güçlendirilmesi hâlâ gerekli.
- memory.py: hedef/soru/araç fingerprint key, bounded atomic JSON, OS publication lock, prepare/commit, version/hash/TTL invalidation, ilgili host failure ile eski prosedürü düşürme, path-free model context ve güncel grant isteyen data-only prosedür seçimi.
- session.py/gateway.py/planning.py: mevcut job worker'ı içinde çalışır, yeni background task engine kurmaz. Bu dosyalar Codex'te kalır. Workbench/AnalysisService gerçek dış teslimi henüz birleştirilmedi.
- ArtifactDiagnostics sınıfı REA'nın geçici full evidence dosyasını kalıcı depoya taşır. UI'de önceki kanıtın tekrar kullanımı yeni CLI çalıştırması olarak gösterilmez.
- SelfDiagnostics dışındaki yeni publication hazırlığı ağır IO'yu owner lock dışında yapar; yalnız son commit cancellation fence içindedir. Mevcut shutdown/tek writer/fresh-observation/Broker sınırları korunur.

## Kanıt düzeyleri

SOURCE: hedef grup83, sonra genişleyen yeni/ilgili grup63 test PASS. Daha önceki Node harness eksik DOM stub hataları düzeltildi; başarısız loglar korundu. Tam suite1008 test koştu, hata0,12 built-helper önkoşulu skip; bu sayı1008 koşunun tamamı canlı veya skip0 demek değildir. Helper için baseline kaynak kodunun CRLF-normalize eşitliği ve binary hash eşitliği doğrulanıp mevcut22 coordination testi ayrıca çalıştırıldı; sonucuna investigation-helper-tests.log'dan bak.

LIVE SOURCE: Gerçek REA6.8.0 ve yerel uyumlu Node ile derlenmiş QuartzDesktopMCP.exe'nin izole kopyası incelendi; hedef çalıştırılmadı. İlk koşuda gerçek REA kullanıldı ve kalıcı full artifact yazıldı. İkinci fresh service koşusunda artifact/target/tool identity yeniden doğrulanarak cached inventory kullanıldı; rea_used=false, knowledge_reused=true. İki koşuda evidence_count2, findings_count3; kaynak ve hedef test boyunca değişmedi, shutdown sonrası worker0. Son source-bound kayıt: .codex/backups/quartz-final-integration-20261102/live-investigation-2aece52739f74677b8e38b3a16bdd237/result.json; source-hashes.json ve source-snapshot.zip aynı dizinde. Bu, native fonksiyon semantiği, UI prosedürü, motor modlama veya paketli sohbet kabulü değildir.

BUILT/LIVE GUI: Yeni REA sistemine ait paket henüz üretilip kabul edilmedi. Kullanıcının çalışan de512a5d... EXE'si değiştirilmedi. Yeni araştırma görevinde C:/WarbandIsland/ASTER, kullanıcı save veya auth dosyalarına işlem yapılmadı.

## Claude'un kapatacağı mevcut boşluklar

Bunlar production-deploy engelleri olarak izlenir; temelin bütün güven/öğrenme sınırları tamamlanmış sayılmamalı:

1. verify_record şu an çoğunlukla artifact digest doğrular. Memory JSON'da level/origin değişiminin host LIVE ispatı olmasına izin verme; manifest/köken eşleşmesi ve güven sınırını tasarla/test et.
2. Aynı referansı iki kez yazmak mevcut len(live)>=2 kontrolünü doyurabilir. Bağımsız/tekil doğrulama ve typed success-check doğru olmalı. Başarısız veya çelişkili prosedür yeniden sunulmasın.
3. ApplicationLearning legacy cache hit yolunda service=None kalabilir ve yeni investigation context kaybolabilir. Eski API'yi bozmadan ilgili kanıt/hafızayı sonraki göreve taşı.
4. Kayda geçen finding/coverage/reusable_inventory/procedure/outcome için tüm nested/bozuk tipler typed failure veya cache miss olmalı; AttributeError/NaN/forged coverage sessiz promotion yaratmamalı.
5. Hafıza sadece sabit statik gözlemlere kilitlenmesin. Bağımsız doğrulanmış uygulama/prosedür bilgisini hipotezden ayır; ilgili soru için bounded retrieval ve açıklanabilir kalite/failure bilgisi üret. Modelin kendi başarı sözü proof değildir.
6. Tool cache version/scope, output limits, metadata mutation, disk büyümesi, process/file concurrency, cancellation ve crash öykülerini gerçek dosya/yeni süreçlerle test et. İlgisiz kullanıcı dosyası silme veya otomatik broad cleanup yok.

Ana facade imzalarını geriye uyumlu koru. Önerilen daha güvenli schema değişikliği varsa migration ve integration request ekle; diğer sahibin session/gateway/GUI kodunu sessizce değiştirme. Bu checkpoint ilk çalışan bounded data yoludur; tüm öğrenme sisteminin tamamlandığı iddiası değildir.
