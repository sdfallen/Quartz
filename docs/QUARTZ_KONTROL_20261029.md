# Quartz — Önceki inceleme sonrası kontrol

Tarih: 29 Ekim 2026. Önceki rapor: `QUARTZ_GENEL_INCELEME_RAPORU_20261028.md`.

## Sonuç

Önceki rapora yönelik gerçek düzeltmeler yapılmış ve mevcut pakete alınmış. Ancak **Q02 ve Q04 tamamen kapanmış değil**. Yeni regresyonların geçmesi, bu iki alanın normal uygulama çağrılarında doğru çalıştığı anlamına gelmiyor.

Bu oturumda üretim kodu veya paket değiştirilmedi. Yalnız kontrol raporu ve izole test kanıtları oluşturuldu. ASTER, oyun kayıtları ve gerçek hesap bilgileri üzerinde işlem yapılmadı.

## Tekrar çalıştırılan kontroller

| Kontrol | Sonuç | Sınır |
|---|---|---|
| `scripts/run_safe_tests.py` | **537 test PASS**, 135,610 saniye | İzole/mock testler; gerçek model veya GUI kabulü değil |
| Yayın denetimi, HEAD geçmişi dahil | **PASS**, bulgu 0 | 257 mevcut dosya, 286 geçmiş blob; bütün disk/ref'lerin taraması değil |
| Gömülü GUI JavaScript kontrolü | **PASS** | Sözdizimi kontrolü |
| Paket/kaynak doğrulayıcı | **PASS** | Doğrulayıcının kapsadığı modüller, helper, CSS ve marka dosyaları |
| Ek paketli scheduler karşılaştırması | **PASS** | `agents.scheduler_agent` bytecode sözleşmesi kaynakla eşleşiyor |
| Yeni hedefli artık-hata kontrolleri | **Üç bulgu yeniden üretildi** | Sahte servisler, geçici dosyalar; dış sağlayıcı isteği yok |
| Gerçek paketli sohbet → model → masaüstü görevi | **NOT TESTED** | Kontrol anında Quartz süreci bulunmadı; uygulama başlatılmadı |

EXE SHA-256: `fdfa0c9dd547d068237325f23662e0bd1f0f4c50d69517e0db0a06c5c07c97c6`.

Git HEAD hâlâ `fa8383d`; güncel düzeltmeler çalışma ağacında. Paket eşleşmesi bu çalışma ağacına göre kontrol edildi; yalnız Git HEAD'e göre değil.

## Q01–Q10 kapanış durumu

| Bulgu | Güncel değerlendirme |
|---|---|
| Q01 — yanlış sistem bilgisi fonksiyonları | **Düzeldi — SOURCE/TEST.** Gerçek controller adlarına bağlanmış; dispatcher testi var |
| Q02 — hazır durumunun fazla iyimserliği | **KISMEN.** Doğrulanmamış API anahtarı artık ayrılıyor; OAuth dosyası içeriği hâlâ gerçek hesap doğrulaması yerine kullanılabiliyor |
| Q03 — onboarding rollback/bozuk hafıza | **Düzeldi — SOURCE/TEST.** Hatalı kökte `.env` geri alınıyor; bozuk JSON korunup sidecar kullanılıyor |
| Q04 — hesap/backend seçimi | **KISMEN.** Giriş alt sürecinden API anahtarları çıkarılmış ve tercih yazılıyor; normal runtime seçimi ve sonraki görev ortamı tercihi tam uygulamıyor |
| Q05 — mevcut CLI sağlık testi | **Düzeldi — SOURCE/TEST.** Yeniden kullanım öncesi sürüm probe'u var |
| Q06 — host timeout | **Kaynak düzeltmesi mevcut.** `process.wait(timeout=...)`, timeout halinde süreç ağacı durdurma ve başarısız sonuç var; canlı asılı sağlayıcı deneyi yapılmadı |
| Q07 — Gemini araç sonucu | **Düzeldi — SOURCE/TEST.** `tool_result`, ortak DONE/ERROR olayına çevriliyor; parser Gemini komut/dosya adlarını da tanıyor |
| Q08 — ham Jarvis argümanı/pano kaydı | **İncelenen Jarvis yolu düzeldi — SOURCE/TEST.** Metin ve pano sonucu maskeleniyor; bütün diğer log kanallarına ilişkin genel gizlilik kabulü yapılmadı |
| Q09 — günlük zamanlayıcı | **Düzeldi — SOURCE/TEST.** Tarih içeren çalışma kimliği var; aynı gün çift çalışmama/ertesi gün çalışma testi geçiyor. Kalıcı görev deposu ayrı eksik |
| Q10 — Squad publication kuralı | **Düzeldi — TEST.** Dar dosya yolu, lisans/provenans ve hash kontrolüyle istisna var; değiştirilmiş binary reddediliyor |

## Yeniden üretilen açıklar

### 1. Normal factory kaydedilen Gemini tercihini okumuyor

Kaynak: `core/gemini_runtime.py:191–195`.

`google_runtime()` metadata'yı yalnız `base` açıkça verildiğinde okuyor. `core/multi_agent_service.py:45` ve `core/desktop_agents.py:131` normal çağrılarında `base` vermiyor.

İzole testte gerçek uygulama biçimindeki varsayılan çağrı kullanıldı; `app_root` geçici kullanıcı profiline bağlandı ve bu profilde `backend=gemini` kaydedildi. Beklenen Gemini iken mevcut eski backend seçildi; Gemini constructor çağrısı **0**.

Yeni regresyon testi `base=root` vererek çalıştığı için varsayılan çağrıdaki bu kusuru yakalamıyor.

### 2. Hesap seçimi görev alt sürecinde tekrar API'ye dönebiliyor

Kaynak: `core/gemini_runtime.py:93–100` çevresindeki `_process_options`.

Onboarding yalnız giriş penceresinin ortamından API anahtarını çıkarıyor. Sonraki görevde `cli_environment()` anahtarı yeniden getiriyor ve `_process_options` `selectedType=gemini-api-key` ayarlıyor; kaydedilmiş `method=account` tercihi burada okunmuyor.

Geçici profilde hesap yöntemi kayıtlı ve ortamda yalnız örnek API metni varken görev ortamında anahtar kaldı, seçilen kimlik doğrulama tipi **gemini-api-key** oldu. Gerçek anahtar/hesapla işlem yapılmadı.

### 3. OAuth dosyasının biçimi gerçek doğrulama sayılıyor

Kaynak: `core/onboarding.py:28–36`, `:93–105`; `core/gemini_runtime.py:51–66`.

Token alanının dolu olması `auth_verified` üretmeye yetiyor. Geçici OAuth dosyası yalnız örnek `access_token`, geçmiş `expiry_date=1` ve refresh token olmadan oluşturuldu. Sonuç:

```json
{"auth_verified": true, "verification_status": "verified", "ready": true}
```

Dış doğrulama yapılmadı. Bu örnek gerçek OAuth token'ının sağlayıcı tarafından reddedildiği bir canlı test değildir; **“verified” etiketinin yerel dosya içeriğine dayanarak verildiğinin** kanıtıdır.

## Sonraki dar müdahale

1. Varsayılan factory'de de mevcut uygulama kökünden metadata oku.
2. Seçilen yöntemi sonraki runtime ortamı ve CLI ayarına uygula; gerçek kullanıcı anahtarını silmeden görev alt sürecinden gerektiğinde çıkar.
3. OAuth varlığı/biçimi ile doğrulanmış hesap durumunu ayır; doğrulanmamış veya süresi geçmiş kaydı hazır göstermeme sözleşmesi koy.
4. Testleri `base` verilen yardımcı çağrıyla sınırlama; gerçek servislerin kullandığı varsayılan çağrıyı da kapsa.
5. Bundan sonra gerçek paketli ana sohbet kabulü yap. Bu rapor bu canlı kabulü tamamlanmış saymıyor.

Önceki rapordaki Q11–Q16 ürünleştirme başlıklarının tamamı yeniden kapatılmadı. Temiz Windows kurulumu, updater, mobil/ses eşdeğerliği ve genel proje kabulü hâlâ ayrı işlerdir.

## Kanıtlar

Proje kökü altındaki `labs/recheck-20261029/`:

- `regression.log` — 537 test.
- `publish-audit.json` — yayın denetimi PASS.
- `package-verification.json` — kaynak/paket ve ek scheduler kontrolü.
- `residual_probes.py` — gerçek hesaplara dokunmayan tekrar üretim kodu.
- `residual-probes.json` — üç açık için gerçek test çıktısı.

Genel hüküm: **Belirgin ilerleme var; “önceki bütün açıklar kapandı” demek henüz doğru değil.**
