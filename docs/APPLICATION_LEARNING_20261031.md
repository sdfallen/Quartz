# Uygulama bilgisi ve izin sonrası devam

## Davranış

Ana sohbetten verilen bir uygulama görevinde ajan mevcut masaüstü/MCP araçlarını kullanmaya devam eder. Tam pencere/süreç kapsamı onaylanınca, ilgili EXE'ler kullanıcı hesabında yerel ve salt okunur REA incelemesine otomatik alınır. Aynı EXE'yi kullanan birden fazla pencere tek incelemeye indirgenir. Tek iş parçacığı sırayla çalışır; her inceleme 512 MiB ve 180 saniye sınırındadır. Hedef çalıştırılmaz, komşu dosyalar taranmaz.

`ApplicationKnowledge` doğrulanmış bulguları `LOCALAPPDATA/Quartz/application-knowledge` altında atomik JSON kayıtlarıyla saklar. Anahtar normalize edilmiş tam dosya yolunun SHA-256 değeridir. EXE SHA-256, dosya kimliği/boyutu/zamanı, kaynak kontrol durumları, PE makine/bölüm bilgileri ve REA'nın sınırlı envanter sayımları kaydedilir. Bilinen sürümde tekrar kullanılır; dosya değişirse veya kayıt 30 günü aşarsa yeni inceleme gerekir. Bozuk/uygunsuz kayıt güvenilir bağlam sayılmaz. En çok 200 kayıt tutulur; sınır dolduğunda eski kayıtlar otomatik silinmez.

Bir sonraki görevde kayıt yeni bir servis nesnesinden yeniden okunur, dosya hash'i doğrulanır ve `task_context.application_knowledge` içinde iki ajana sunulur. Ajanın bu bilgiyi kullanması için talimat eklendi. Kaynak koddaki `.exe` yolları, model çıktıları, ekran metinleri, sohbetler, hesaplar, çerezler ve API anahtarları depoya aktarılmaz. Saklanan veri talimat veya izin değildir; yeni görevde yetki ve canlı gözlem tekrar gerekir.

Bu sürümde öğrenilen şey kanıtlı **statik dosya bilgisi**dir. REA'nın PE desteği kök dosya envanterini kapsar; uygulamanın tüm iç kodunu, web arayüzünü veya çalışma davranışını çözmüş sayılmaz. PyInstaller için önceki doğrulanmış özet desteği korunur. Bilinmeyen biçimler UNKNOWN kalır. Arayüz gezinme reçeteleri veya başarılı tıklama dizileri henüz kalıcı öğrenme kapsamına alınmadı. Model ağırlıkları veya Quartz kaynak kodu bu akışta değiştirilmez.

Warband EXE'leri bu genel öğrenme yoluna alınmaz; ASTER/Universal Modder akışı korunur. Steam gibi başka uygulamalar, seçili proje Warband olsa dahi kendi onaylanmış EXE kimlikleriyle öğrenilebilir.

## Devam hatası

Eski Steam görevi `4ac2794830074e69bbfc0614dfd49107` için kullanıcı gerçek onay düğmesine bastığını belirtti. Kayıtta ikinci başarılı grant/continuation bulunmaması, tıklamadığının kanıtı değildir. Eski koşunun tam canlı istisnası yakalanamadı.

Kaynakta iki hata yolu düzeltildi:

1. Onay köprüsü istisna verince düğmeler kalıcı devre dışı kalabiliyordu. Artık try/catch/finally ile hata gösterilir, çözümlenmemiş kart yeniden kullanılabilir ve başarılı cevap sonrası güncel görev tekrar okunur.
2. Onay sırasında CLI turu hâlâ çalışıp hemen ardından tamamlanırsa devam atlanabiliyordu. Onaylanan run kimliği izlenir; bu eski tur bittiğinde aynı görev ve MCP token'ıyla bir devam turu başlar. Önceden bitmiş tur senaryosu korunur. Yeniden oynatılmış tıklama/girdi yoktur.

Öğrenme sürerken turlar biterse görev, öğrenme sonucu hazır olana kadar bekler. Operatör yeni bilgiyi okumadıysa kontrollü devam turu açılır. Mevcut süre/Stop ve dört devam turu bütçesi korunur; sınırda sessiz başarı yerine açık hata verilir. Bu, sınırsız çalışma garantisi değildir.

## Kanıt ve kabul sınırı

Kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-app-learning-20261031`.

- `steam-learning.json`: gerçek Steam EXE (5823128 bayt), SHA-256 `f8a4ca44008c516eebecafaa4bc26772b2a6eb0fef8034bce56a3311e21ab705`, PE x64, 7 bölüm, REA kök envanteri PASS, çelişki0. İzole bilgi deposuna yazma ve yeni nesneden okuma başarılı. Steam çalıştırılmadı.
- `tests/test_application_knowledge.py`: kalıcılık, sonraki görevde yeniden taramadan kullanım, dosya değişiminde geçersizleştirme, süre aşımı, iptal/eksik kayıt reddi, serbest metin enjeksiyonu reddi, hash bağlama.
- `tests/test_natural_desktop.py`: onaydan önce ve hemen sonra biten tur varyantları. Kontrollü fixture sonucu; eski Steam hatasının bire bir canlı yeniden üretimi olarak sunulmaz.
- `tests/test_permission_continuation_ui.py`: köprü hatası sonrası düğme kurtarma, başarı sonrası görev durumunu yeniden okuma.
- Kaynak/DSL ve gerçek dosya/REA entegrasyonu, paketli ana sohbet üzerinden model+masaüstü canlı kabulüyle aynı düzey değildir. Tam otomatik Steam görevinin tamamlandığı iddia edilmez.

İlk 629 test PASS; iki ek hedefli testle birlikte derlemedeki güncel tam test ve paket sonucu `build.log` içindedir. Önceki kullanıcı verileri ve kaynak değişiklikleri korunur; GitHub yayını yapılmaz.
