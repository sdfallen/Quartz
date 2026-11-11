# Dalga 2 — tam regresyon düzeltmeleri ve boşta ölçüm

## Yeni gerçek bulgu

Grup değerlendirmesinde metin üretildikten sonra Squad send hatası olunca
mesaj failed olmasına rağmen katılımcı sonucu completed kalabiliyordu. Yeni
test `test_failed_second_round_squad_delivery_is_not_a_completed_group`,
önce completed != partial ile başarısız oldu. Her iki turdaki exception yolu
katılımcı sonucunu da failed yapar; tek diğer yanıtla sonuç partial olur.
Komut: `python -X utf8 -B scripts/run_safe_tests.py tests.test_group_partial_outcome`.
İlk çıktı: 3 test / failure1. Sonraki hedefli regresyon: 61 test / skip0 PASS.

İlk tam suite: 1391 test, 4 failure, 2 skip. Dört failure'ın ikisi eski
manual-log sırasında grant koruma beklentisi; biri yeni partial yerine failed
beklentisi; biri explicit ikinci-tur sonucunu dönmeyen eski MagicMock fixture'ı.
Beklentiler yeni kullanıcı sözleşmesiyle hizalandı. Full auto-approved log
isteğinde grant koruma testi ayrıca tutuldu; manuel istek revoke + yeni token
testine döndü. Başarısız loglar korunur, ilk tam suite PASS olarak sunulmaz.

İki yeni test modülünde import edilen mevcut TestCase sınıfı discovery sırasında
gereksiz tekrar koşuluyordu; module alias'a dönüldü. Eski kayıtlı test sayıları
o koşuların gerçek sayılarıdır; nihai suite gereksiz tekrarları içermez.

Son küçük güvenilirlik kontrolleri: Stop paused checkpoint'i terminal durumla
günceller; restart durdurulmuş işi bekleyen onay gibi göstermez. Runtime exit
readback hatası başarı değil unconfirmed'dır. Katılımcı status okuma hatası
Stop'un yerel revoke aşamasını engellemez. İlgili hedefli koşu: 24 / skip0 PASS.

## Gerçek 600 saniyelik önce/sonra

| Ölçüm | Önce | Sonra |
|---|---:|---:|
| Kaynak | `577c264` | `99e82d0` |
| Gerçek süre | 600.000 s | 600.001 s |
| status/poll turu | 592 | 591 |
| Squad süreç açılışı | 140 | 12 |
| Codex probe açılışı | 4 | 4 |
| Antigravity probe açılışı | 6 | 6 |
| Toplam süreç açılışı | 150 | 22 |
| Model start girişimi | 0 | 0 |

Toplam açılışta %85,3; Squad açılışında %91,4 azalma. Bunlar süreç **başlatma**
sayılarıdır; aynı anda yaşayan süreç sayısı, CPU, RAM veya FPS değildir.
Gerçek readonly CLI/Squad sorguları, disposable owned proje, headless aynı
AgentChat status/poll yolu, bir saniye aralık ve capture-off kullanıldı.
Provider start metotları fail-closed yasaklandı. Kişisel veri/komut içeriği
yerine yalnız executable basename ve sayaç tutuldu. Gerçek ana sohbet GUI'si
açılmadı; paketli cost-01 kabulü açık.

Gemini'nin önceki 170 ölçümü başka koşuldadır; bu ölçümdeki 150 yerine
kullanılmadı. İlk ön koşu 600 s sonunda yanlış cleanup metodu nedeniyle JSON
yazamadı; geçersiz sayılıp betik düzeltilerek temiz 600 s yeniden koşuldu.
Başarılı ölçümler farklı, sabit kaynak worktree'lerinde sırayla yapıldı.
Özel `idle-before.json` ve `idle-after.json` kaynak/hash/süre detaylarını taşır.
Sonraki oracle/grup düzeltmeleri cache fonksiyonlarını değiştirmez; nihai
teslimde AST hash eşliği ayrıca kaydedilir. Ölçümü yeni paket kabulüne genelleme.

Ham çıktılar/evidence Git'e eklenmez. BUILT / LIVE GUI yok; dağıtım yapılmadı.

Metrik hassasiyeti: collector Popen constructor girişini sayar; başarılı süreç
oluşumu ile failed spawn ayrımı yapılmadı. Yukarıdaki “açılış” sayıları tam
olarak Popen başlatma çağrılarıdır; process identity census veya tümünün başarıyla
başladığı iddiası değildir. Sayaç/göreli azalma gerçek çağrı yolundan ölçüldü.
