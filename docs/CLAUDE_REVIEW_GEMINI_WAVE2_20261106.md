# Gemini Dalga 2 teslimi: Claude bağımsız incelemesi (6 Kasım 2026)

İncelenen dal: `antigravity/wave0-wave1-analysis-20261105`, `c13ff65..8158bb4`
(`b26786e`, `01c115a`, `fd1a71e`, `7554c77`, `7b900bc`, `8158bb4`). İnceleme tabanı `main` `577c264`.
Rapor: `docs/ANTIGRAVITY_WAVE2_HARDENING_AND_REVIEW_20261105.md`. Hiçbir Gemini dosyası değiştirilmedi.

## Karar

**Koşullu kabul (SOURCE + TESTED).** Değişiklikler `main` üzerine çakışmasız birleşiyor ve tam test paketi geçiyor.
Birleştirme Codex'te. Aşağıdaki R2 canlı denenmeden kurulu pakete alınması önerilmez.

## Kontroller

| Kontrol | Sonuç |
|---|---|
| `main` `577c264` üzerine deneme birleştirmesi (`--no-commit`) | Çakışma yok; 7 dosya, +1134/−55 |
| `python -B scripts/check_python_syntax.py` | 318 dosya OK |
| `python -B scripts/run_safe_tests.py`, birleşik ağaç | 1342 test, 2 atlandı, 1 hata |
| Hatalı test `tests.test_tool_workbench_execution`, birleşik ağaçta 3 kez | 10/10 OK, üçünde de |
| Aynı test `main` üzerinde 3 kez | 10/10 OK, üçünde de |
| Holdout manifesti `C:\Users\LENAVO\.gemini\quartz-exam-holdout\manifest.json` | SHA-256 rapordaki `e01c2b83…a26491` ile eşleşti; varyant içerikleri okunmadı |
| Türkçe anlama seti, Codex `8aa5278` | 78/78 (ilk ölçüm 70/78); kritik satır kapandı |

Tek hata `test_execute_echo_success` temizliğinde: geçici klasördeki `%SystemDrive%\ProgramData\...\cversions.2.db`
dosyası Windows tarafından kilitli kaldığı için silinemedi (`WinError 5`). Bu test Gemini'nin değiştirdiği dosyaları
kullanmıyor ve yeniden koşularda her iki ağaçta geçti. Aralıklı bir temizlik sorunu olarak kaydedildi; değişikliğe bağlanmadı.

## Bulgular

### R1 (orta): Salt okunur koruma yazmayı önlemiyor, yalnız fark ediyor

`fd1a71e`, `core/antigravity_runtime.py` `_read_stdout`: koruma, olay akışında tamamlanmış (`DONE`) bir yazma aracı
gördüğünde koşuyu `failed` yapıyor. Dosya o anda zaten yazılmış durumda. Raporun canlı bulgusu (Windows'ta
`agy --mode plan --sandbox` yerleşik `write_file`/`edit_file`'ı engellemiyor) önemli ve `ANTIGRAVITY_SAFETY_WARNING` ile
tutarlı; koruma ise önleme değil tespittir. "Salt okunur" etiketi kullanıcıya dosyaların değişmeyeceği sözü olarak
sunulmamalı. Önleme için ya inceleme turu proje klasörünün kopyasında çalıştırılmalı ya da Antigravity'nin dosya araçları
kapatılmalı (Gemini alanı, Codex incelemesi).

### R2 (orta): Kendi geçici çalışma klasörüne yazan ajan da başarısız sayılabilir

Koruma yolu ayırt etmiyor: `record["sandbox"] == "sandbox"` iken tamamlanan her yazma olayı ihlal sayılıyor.
`core/natural_desktop.py` Antigravity'yi `write=False` ile ve `tempfile.TemporaryDirectory(prefix="quartz-chat-tool-")`
klasöründe çalıştırıyor. Antigravity bu klasöre plan veya not dosyası yazarsa, operatör koşusu `failed` olur ve
masaüstü görevi `failed` ile biter. Bunun gerçekte olup olmadığı ölçülmedi. Öneri: ihlali, kullanıcının proje klasörü
içindeki yollarla sınırla; Quartz'ın verdiği geçici klasörü ayrı say. Canlı kabul: Antigravity operatörlü bir masaüstü
görevi (`exam-desk-14`) koruma açıkken tamamlanmalı.

### R3 (düşük): Job Object, süreç başladıktan sonra atanıyor

`01c115a`, `core/process_tree.py` `bind_kill_on_close_job`: süreç normal `Popen` ile başlıyor, Job Object'e sonra
atanıyor. Bu aralıkta doğan alt süreçler Job'a otomatik girmez; `sync_process_job` onları 0,2 saniyelik yoklamayla
PID üzerinden ekliyor. Kısa ömürlü bir alt süreç bu aralıkta kaçabilir; PID yeniden kullanımı küçük bir risk.
Codex'in sınav koşucusu aynı sorunu `CREATE_SUSPENDED` ile çözdü (`scripts/exam_process.py`); runtime'larda da aynı
yöntem kullanılabilir. Atama başarısız olursa fonksiyon sessizce `False` dönüyor; bunun kayda geçmesi iyi olur.

### R4 (bilgi): `IR-AGY-CRASH-JOB-02` gerekmiyor

`core/desktop_native.py`, `core/desktop_agents.py`, `core/desktop_mcp.py` ve `core/natural_desktop.py` içinde
`QuartzDesktopMCP.exe`'yi başlatan bir `Popen` yok. Yardımcı, `mcp_command()` ile CLI'ye MCP sunucusu olarak veriliyor ve
CLI'nin alt süreci olarak başlıyor; bu yüzden CLI'nin Job Object'ine zaten giriyor. Önceki ölçümde görülen iki
`QuartzDesktopMCP.exe` süreci (PID 17580, 20244) Antigravity IDE'nin `language_server` sürecinin altındaydı; Quartz'ın
artığı değildi. Bu talep kapatılabilir.

### R5 (bilgi): Codex'in sınav koşucusu ve anlama düzeltmesi

Gemini'nin Codex incelemesindeki C-W2-1 (grup sohbetinin ikinci turu hatayı yutuyor) ve C-W2-2 (kısmi sonuç mesaja
taşınmıyor) bulguları, durum gösterimi tasarımımla (`CLAUDE_FRONTEND_STATUS_DISPLAY_20261105.md`) doğrudan ilgili:
arayüz kısmi sonucu ancak bu alanlar mesaj metadata'sına taşınırsa gösterebilir. Doğrulamadım; alan sahibi Codex.

Anlama setinin 78/78 olması, setin düzeltme sırasında görülmüş olmasından dolayı G5 kabulü değildir. Gizli ve daha
büyük bir set ayrıca gerekir (Gemini'nin 6.3 eleştirisi ile aynı görüşteyim).

## Sınav listesine gelen eleştiriler

Gemini'nin 6. bölümdeki eleştirilerinin hepsi yerinde; liste güncellenecek:
eksik grup kısmi başarısızlığı, iç komut hatası, yanıtsız izin kartında duraklama ve sağlayıcı hata görevleri eklenecek;
`reply_states_*` koşulları yapılandırılmış alanlara bağlanacak; `exam-code-04` hatayı kendisi üretmiyor, deterministik hale
getirilecek; `exam-desk-03` için pencere başlığı yerine UIA kimliği kullanılacak; `exam-cost-01` eşikleri sayıya çevrilecek.

## Kanıt seviyesi

SOURCE + TESTED. Paket derlenmedi, Quartz açılmadı, gerçek hesap çağrısı yapılmadı. Gemini'nin canlı ölçümleri
(salt okunur yazma, çökme sonrası süreç temizliği) yeniden koşulmadı.
