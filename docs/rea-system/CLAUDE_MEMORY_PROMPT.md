# Claude Opus 5.5 — Kanıt hafızası ve doğrulanmış öğrenme altyapısı

Bu, önceki derlenmiş ikili/motor çözümleme görevinden ayrı bir üretim görevidir. Önceki filtrenin engellediği içeriği yeniden üretmen veya onu başka ifadelerle sürdürmen istenmiyor. Bu görevde executable açma/çözümleme, disassembly/decompilation, debugger/injection, uygulama tersine mühendisliği veya araç edinimi yapmayacaksın. Konu yerel Python/JSON veri modeli, kanıt kökeni, kalıcı bilgi tutarlılığı, öğrenilmiş prosedürlerin doğrulanması ve otomatik testlerdir.

Quartz için Codex ve Gemini ile paralel çalışıyorsun. Model tercihi Claude Opus5.5. Senin kritik ürün alanın, sistemin gerçekten neyi öğrendiğini ve hangi koşullarda güvenebileceğini belirleyen production memory/evidence altyapısıdır. Yalnız danışmanlık veya rapor istemiyoruz; kod, regresyon ve gerçek kalıcılık/process testleri teslim et.

## Doğru başlangıç

Önce yeni sağlanan rea-memory-handoff bundle/manifest'ini al. Eski cbc303b checkpoint'i bu implementasyonu içermez. Yerel worktree C:/Users/LENAVO/.codex/worktrees/quartz-rea-claude-memory; uzaktaysan bundle'dan kendi çalışma dizinini aç. `git rev-parse HEAD` ile gerçek base'i rapora kaydet. docs/rea-system/TEAM_CONTRACT.md ve CODEX_OWNED_HANDOFF.md içindeki güncel kapsamı oku; eski CLAUDE_PROMPT.md görevini sürdürme.

Codex'in oluşturduğu başlangıç: core/investigation/contracts.py, evidence.py, memory.py; session/gateway/planning bunları tüketir. ArtifactDiagnostics mevcut worker'ı ve cancellation fence'i koruyarak evidence/knowledge yayınlar. Gerçek REA çağrısıyla iki kaynak koşusunda kalıcı kanıt ve aynı sürümde yeniden kullanım gözlemlendi; bu senin uygulayacağın JSON doğruluk kontrollerinin veya UI prosedürlerinin canlı kabulü değildir.

## Yazma sahipliğin

- core/investigation/contracts.py, evidence.py, memory.py
- Gerekirse yeni core/investigation/learning.py
- core/application_knowledge.py
- tests/test_investigation_evidence.py, tests/test_rea_learning.py, yeni tests/test_learning_*.py
- docs/rea-system/CLAUDE_MEMORY_REPORT.md; kendi test fixture'ların labs/learning-evidence/ içinde

core/rea_analysis, core/tool_workbench, session.py/gateway.py/planning.py, gui.py/main.py, broker/process helper, paket spec/verify, run_safe_tests.py ve diğer sahibin testlerine doğrudan yazma. İhtiyaç varsa somut API/patch talebi raporla; aynı dosyaya paralel yazma yok.

## Tamamlaman gereken üretim işi

1. Kanıt kaydını immutable ve kökeni doğrulanabilir yap. Bir knowledge JSON'undaki `level`/`origin` alanını değiştirmek statik kanıtı gerçek host/LIVE kanıtına dönüştürmemeli. Salt hash eşitliğinin neyi doğruladığını açık tut; dosya içeriği, kayıt manifesti ve kaynak attestation sınırlarını ayır. Anahtar/cookie veya kişisel veri gerektirmeyen test fixture'ları kullan. Yerel aynı kullanıcı hesabının tamamen ele geçirilmesine karşı OS güvenliği sağladığını iddia etme.
2. `observation`, `hypothesis` ve `verified_procedure` ayrı kalmalı. Aynı evidence_id'yi iki kez yazmak iki bağımsız doğrulama sayılmamalı. Çelişki, başarısız success-check, eski sürüm veya doğrulanamayan kayıt güvenini düşürmeli; başarı sayacı kendi kendine artmamalı.
3. Kaynak dosya kimliği, içerik SHA, araç/şema/prosedür sürümü, zaman ve kanıt dosyası değiştiğinde doğru invalidation. Değişiklik aynı boyut ve timestamp ile yapılsa da hash karşılaştırması çalışmalı. JSON bozulması, NaN, aşırı büyük/derin alanlar, eksik manifest veya path traversal cache miss/typed failure olmalı; uygulama çöküşü veya yanlış hit üretmemeli.
4. Kalıcı prosedür verisi tipli ve sınırlandırılmış olsun. Önkoşul, geçerli hedef sürümü, gerekli güncel grant, adım kimliği ve başarının nasıl ölçüleceği kaydedilsin. Prosedür metni code/eval/shell olarak yürütülmesin. Host/Broker'ın yeni görev izni ve gözlem kontrolü olmadan bellek kaydı eylem başlatmasın. Bu alanda yalnız veri ve doğrulama/gating uygulanacak; gerçek UI kontrolü Codex'te.
5. Görev sonrası öğrenme gerçekten sonraki görev bağlamına ulaşsın. ApplicationLearning'in legacy cache-hit yolunda yeni investigation bilgisinin kaybolmasını incele. Sadece statik metadata biriktiren liste yerine kanıt/prosedür/başarısız yöntem bağlamı uygun sınırlı biçimde sunulsun; ham log, mutlak kullanıcı yolu, kopyalanmış kod, sır veya geniş ekran metni otomatik paylaşılmasın. Görev soruları arasında ilgili bilginin tekrar kullanımını güvenli ve ölçülebilir şekilde tasarla; alakasız soruya kesin cevap gibi taşıma.
6. Bellek büyümesi/IO maliyeti ölçülebilir ve sınırlı olsun. Cache hit'leri eski kanıt zincirini sonsuz kopyalamasın. Tekrarlanan publish/idempotency, iki süreçte aynı kayda yazma, crash sonrası yarım yazma ve iptal yarışı için güvenilir kalıcılık. Silme/taşıma/otomatik retention temizliği ile kullanıcı verisine dokunma; limit dolduğunda açık durum ver.
7. Ağır hash/IO ve model çağrısını UI lock içinde yapma. Mevcut prepare/commit yayın sınırına ve job.cancel fence'ine uy; session/GUI'ye gereken küçük bağ değişikliğini integration request olarak teslim et. Başarısız veya iptal edilmiş bir analiz başarılı prosedür haline gelmemeli.
8. Confidence veya öğrenme kalitesini modelin kendi övgüsünden üretme. Geçerlilik, başarı/başarısızlık kanıtı, kullanım/versiyon koşulu, çelişki ve tekrar doğrulamadan türetilen açıklanabilir bir kalite çıktısı ver. Yeni genel agent/task framework kurma.

## Kabul ve testlerin

Gerçek dosya ve kalıcı JSON ile positive/negative round trip; yeni Python sürecinde load; başka süreçte lock/yarış; bozuk ve değiştirilmiş kanıt reddi; cancellation sırasında hiçbir yanlış memory commit olmaması; duplicate proof'un reddi; başarısız doğrulama sonrası eski prosedürün seçilmemesi; kaydı okumanın scope/grant/task restore etmemesi; bounded model context ve eski API uyumluluğu. Mock başarıyı LIVE diye yazma. Gerçek UI veya uygulama çalıştırma bu görevin kabul şartı değil; SOURCE/STATIC ve gerçek yerel kalıcılık testlerini açık ayır.

Mevcut hedef testleri: python -X utf8 -B scripts/run_safe_tests.py tests.test_investigation_evidence tests.test_rea_learning. İlgili tüketici gateway/session testlerini read-only çalıştır; değiştirme. Son tam safe suite'i de çalıştır, engel varsa komut/hata/build ile raporla. Baseline'daki bilinen eksikleri saklama ve tüm testleri skip yaparak yeşil üretme.

Kodun, geriye uyumlu şema/API değişikliklerin, test/fixture'ların ve docs/rea-system/CLAUDE_MEMORY_REPORT.md tek teslimde olsun. Ortak base/commit ve yalnız sahiplik alanı için bundle/patch; başkalarının commit'lerini kendi işin olarak paketleme. .env, oturum, konuşma, private test kullanıcı profili ve binary artifact'ları source bundle'a ekleme. Çalışan EXE'yi güncelleme, public push/release yapma, ASTER/C:/WarbandIsland veya kullanıcı kayıtlarına dokunma. Ağır ve kritik üretim alanın bu; yalnız “tasarım önerileri” ile teslim etme.
