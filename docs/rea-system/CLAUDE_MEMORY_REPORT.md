# Claude — kanıt kökeni, doğrulanmış öğrenme ve hafıza bütünlüğü

Tarih: 2026-11-02. Sahip: Claude (Opus). Dal: `claude/rea-memory`.

- Ortak base: `e476c2fbd42c19f050d1a1e896959fe2e3ccd19d`
  (`codex/rea-memory-claude-20261102`). Tree `d1cfc94`, kullanıcının
  `quartz-rea-claude-memory` worktree index'iyle `git write-tree` üzerinden
  eşleşti. Eski `cbc303b` checkpoint'i bu implementasyonu içermez.
- Bu teslim: base üzerine tek commit (SHA teslim mesajında).
- Codex'in agent_chat WIP checkpoint'i alınmadı. Bu bir çalışan EXE dağıtımı değil.

Kanıt seviyesi: **SOURCE/STATIC + gerçek yerel kalıcılık testleri (Linux)**.
Gerçek UI/uygulama çalıştırma, paket kabulü ve BUILT/LIVE GUI bu görevin
kapsamı değildir. Linux sonucu Windows canlı kabulü değildir. Hiçbir ikili
çalıştırılmadı; derlenmiş/motor çözümleme, disassembly, injection veya araç
edinimi yapılmadı — bu görev yalnız yerel Python/JSON veri modeli, kanıt
kökeni ve doğrulama/gating'dir.

## Kapatılan boşluklar (CODEX_OWNED_HANDOFF.md 1–6) ve kanıt

### 1. Kanıt kökeni: salt hash promotion'ı engellemez
`EvidenceRepository.verify_record` artık artifact digest'ine ek olarak kaydın
`level`/`origin`/`kind`/`digest`/`bytes`/`target_fingerprint` alanlarını
**üretildiği oturumun manifest'i** ile karşılaştırıyor
(`evidence/<id>/manifest.json`). Taşınabilir knowledge JSON'da `level`'i
`LIVE`, `origin`'i `host-verification` yapmak digest'i bozmaz ama manifest hâlâ
`SOURCE` dediği için kayıt cache miss olur — statik kanıt prosedür doğrulayan
canlı kanıta yükseltilemez.
- Güven sınırı açık: artifact baytı digest ile; köken alanları oturum
  manifest'i ile; manifest tek oturumun attestation köküdür. Manifest'i de
  yeniden yazan tam yerel hesap ele geçirmesine karşı koruma iddia edilmez
  (handoff ve TEAM_CONTRACT bunu açıkça kapsam dışı bırakır).
- Test: `test_editing_knowledge_level_and_origin_does_not_promote`,
  `test_verify_record_rejects_mismatched_kind`, `test_missing_manifest_is_not_verifiable`.

### 2. Aynı evidence_id iki kez = iki bağımsız doğrulama değil
`validate_finding` artık `evidence_ids`/`counter_evidence_ids` içinde yinelenen
referansı reddediyor (`duplicate-evidence-link`). Böylece bir prosedür
`evidence_ids=[X, X]` ile iki LIVE host-verification kontrolünü geçemez;
bağımsızlık ayrı evidence id iledir.
- Test: `Independence.test_duplicate_evidence_ref_rejected`,
  `test_two_distinct_live_refs_accepted`; `learning.finding_quality` de
  bağımsız LIVE sayısını küme olarak hesaplar.

### 3. ApplicationLearning cache-hit yolunda context kaybı
Cache hit'te `ArtifactDiagnosticsService` yeniden çalışmadığı için `service`
None kalıyor ve taze rapora bağlı investigation context düşüyordu. Artık
`ApplicationLearning._cached_investigation_context`, aynı dosya için kalıcı
investigation hafızasından sınırlı, yol içermeyen context'i okuyup işe ekliyor.
Yeni `InvestigationMemory.context_for_target`, soru/araç anahtarından bağımsız,
hedefe özel, en güncel geçerli kaydın context'ini aynı doğrulama titizliğiyle
(manifest attestation + failed-outcome invalidation) döndürür.
- Eski API korunur: `investigation_root` verilmezse veya dizin yoksa davranış
  değişmez (no-op), context best-effort'tur.
- Context her zaman `instruction_authority:false`, `requires_current_grant:true`
  ve yol içermez; scope/grant/task restore etmez.
- Test: `CacheHitContext.test_cache_hit_recovers_investigation_context`,
  `test_absent_investigation_root_is_backward_compatible`.

### 4. Bozuk/forged tipler typed failure veya cache miss
`InvestigationMemory.prepare` artık `reusable_inventory`'yi yapısal doğruluyor:
yalnız `{status,message,evidence}`, `status=='PASS'`, coverage'da
`static_inventory`, `evidence.artifact_sha256==target.sha256` ve gerçek bir
`rea-full-artifact` digest'ine bağlı olmalı; `static_inventory` coverage'ı
envanter olmadan reddedilir. NaN/exotic/aşırı nesting zaten `bounded_json`
(allow_nan=False) ile typed failure. lookup'ın kayıt doğrulaması
`_load_valid_record`'a çıkarıldı; her defect None (cache miss) döndürür,
AttributeError/forged coverage sessiz promotion üretmez.
- Test: `ForgedInventory.test_inventory_without_coverage_is_rejected`,
  `test_nan_in_report_is_a_typed_failure`; mevcut
  `test_expired_and_malformed_record_is_cache_miss` korunur.

### 5. Statik gözlemle sınırlı kalmayan, açıklanabilir öğrenme
Yeni `core/investigation/learning.py` (saf, IO'suz):
- `finding_quality`: tier'ı **yalnız kanıt yapısından** türetir — bağımsız LIVE
  host-verification sayısı, reproducible bayrağı, counter-evidence, claim tipi.
  Modelin `confidence_basis` metni yalnız `stated_basis` olarak gösterilir,
  tier'ı **belirlemez**. Uydurma yüzde/skor yok; sıralı tier + sayım.
- `assess_record`: tier sayımları, invalidated claim'ler ve
  `has_reusable_procedure` (yapısal olarak doğrulanmış en az bir prosedür).
- `separate_by_type`: observation/hypothesis/verified_procedure ayrımı; hipotez
  yanıt olarak değil açık soru olarak etiketli döner; yanlış etiketlenmiş
  "verified_procedure" (tek LIVE) reusable listeye girmez.
- Test: `tests/test_learning_quality.py` (9 test), özellikle
  `test_model_confidence_text_never_sets_the_tier`,
  `test_no_numeric_confidence_percentage`,
  `test_mislabeled_procedure_is_not_reusable`.
- Çalışan fixture/demo: `labs/learning-evidence/demo_quality.py`.

### 6. Sınırlı büyüme ve idempotent kalıcılık
`InvestigationMemory.commit` artık aynı key için en güncel kaydın içerik
digest'ini (observed_at hariç) karşılaştırıp **aynı raporu yeniden yayınlamayı
dedupe ediyor**; tekrar publish dediğinde depo büyümüyor. Mevcut sınırlar
korunur: `MAX_RECORDS=200`, `MAX_RECORD_BYTES`, atomic publish, OS publication
lock, prepare/commit, TTL/hash/version/outcome invalidation,
`session.finish`'in cache-hit'te yalnız gerçek `rea-full-artifact`'ı taşıması
(büyüyen tarihsel zincir değil).
- Test: `Idempotency.test_identical_republish_is_deduped`,
  `test_concurrent_identical_commit_writes_once` (4 thread, tek dosya).

## Değiştirilen dosyalar (yalnız sahiplik alanım)

- `core/investigation/contracts.py` — yinelenen evidence referansı reddi.
- `core/investigation/evidence.py` — `verify_record` manifest attestation.
- `core/investigation/memory.py` — `reusable_inventory` doğrulama, idempotent
  commit dedupe, `_load_valid_record` refaktörü, `context_for_target`.
- `core/investigation/learning.py` — yeni; açıklanabilir kalite ve ayrıştırma.
- `core/application_knowledge.py` — cache-hit investigation context.
- `tests/test_learning_integrity.py`, `tests/test_learning_quality.py` — yeni.
- `labs/learning-evidence/demo_quality.py` — yeni çalışan fixture.
- `docs/rea-system/CLAUDE_MEMORY_REPORT.md` — bu rapor.

Facade imzaları ve JSONv1 şeması geriye uyumlu: yeni alan eklenmedi; yalnız
doğrulama sıkılaştırıldı ve iki yeni okuma yardımcısı (`context_for_target`,
`learning.*`) eklendi. session.py/gateway.py/planning.py, gui.py/main.py,
broker/process, paket spec/CI, run_safe_tests.py ve diğer sahiplerin testlerine
dokunulmadı.

## Testler (bu ortamda gerçekten koşulan — Linux, Python 3.13)

Komutlar repo kökünde; loglar teslim paketinde `logs/`.

| Komut | Sonuç |
|---|---|
| `python -X utf8 -B scripts/run_safe_tests.py tests.test_investigation_evidence tests.test_rea_learning tests.test_learning_integrity tests.test_learning_quality` | 58 test OK |
| `python -X utf8 -B scripts/run_safe_tests.py` (tam) | Sonra: 1000 test, 2 fail + 19 error, 17 skip. Base `e476c2f`: 980 test, aynı 2+19+17 |
| `python -B scripts/audit_publish.py --staged` | PASS, 0 bulgu, secrets_printed:false |
| `git diff --cached --check` | Temiz |
| `python -I labs/learning-evidence/demo_quality.py` | tier roll-up + bucket çıktısı |

Tam suite: başarısız/hatalı test kimlik listeleri base ile `diff` ile birebir
aynı (SAME-FAILURE-SET). Hepsi Linux ortamından: `pyautogui` gibi Windows
modülleri eksik, `codex.cmd`/`node.exe` yolları, UAC/native testleri. +20 test
bu teslimin yeni testleri. Bu sayı 1000 koşunun tamamının canlı olduğu anlamına
gelmez.

Mutasyon kontrolleri (geçici, geri alındı) — testlerin gerçekten koruduğunu
gösterir:
- Gap 2 reddini kaldır → `Independence` 1 fail.
- Gap 1 manifest attestation'ı kaldır → `ManifestAttestation` 3 fail.
- Gap 6 dedupe'u kaldır → `Idempotency` 2 fail.
- Gap 3 cache-hit context'i None yap → `CacheHitContext` 1 fail.

## Kalan açıklar / entegrasyon

- BUILT/LIVE GUI yok: gerçek REA, gerçek UI prosedürü ve paketli ana sohbet
  kabulü Codex entegrasyonundadır. `verified_procedure` tier'ı burada SOURCE
  fixture ile test edildi; gerçek host doğrulaması ayrı kanıttır.
- `context_for_target` hedefe özeldir, soruya özel değildir; application-
  knowledge katmanı zaten uygulama kapsamlıdır. Context açıkça historical ve
  grant'siz; alakasız soruya kesin yanıt olarak sunulmaz (tier yapısaldır).
- **IR-1 (Codex, session/gateway):** `learning.assess_record` /
  `separate_by_type`'ı investigator sunumuna bağlamak isterseniz, bunlar saf
  okuma fonksiyonlarıdır; gateway'in context üretimine ek alan gerekmez. Bağ
  noktasını birlikte netleştirelim (integration request, kod değil).
- **IR-2 (Codex, ArtifactDiagnostics):** Cache-hit context'i artık
  ApplicationLearning kendi okuyor. İsterseniz diagnostics raporu cache-hit'te
  de `investigation.context` döndürecek şekilde hizalanabilir; o dosya sizin
  alanınızda, dokunmadım.
- Linux'taki 21 base hatası Windows bağımlılıklarındandır, bu teslimle değişmez.

## Geri alma

Tek commit, şema/kullanıcı verisi değişmedi:
```
git revert <commit>
```
Ya da yeni `learning.py` ve iki yeni test dosyası ile `demo_quality.py` silinir;
`contracts.py`, `evidence.py`, `memory.py`, `application_knowledge.py` base
sürümüne döndürülür (`git checkout e476c2f -- <dosya>`). Facade adları ve
JSONv1 değişmediğinden tüketicilerde geri alma gerekmez.
