# Quartz Durum Raporu (8 Kasım 2026)

Hazırlayan: Claude (Opus 5.5), Codex'in yokluğunda devralınan çalışma. Bu rapor kod, test, paket ve canlı
sınav kayıtlarından derlendi; ajanların "tamamlandı" sözleri kanıt sayılmadı.

## 1. Kısa sonuç

Quartz bugün, bir sohbet penceresinden iki yapay zekâ ajanını (Codex ve Gemini/Antigravity) birlikte
çalıştıran, bilgisayarı güvenlik sınırları içinde kontrol eden ve işini kanıtla doğrulayan bir Windows
masaüstü asistanıdır. Temel mekanizmalar çalışıyor ve bugün canlı sınavda gerçek görevlerle sınandı.

"Çok güçlü, ilk büyük sürüm" demek için henüz yeterli kanıt yok:

| Ölçü | Durum |
|---|---|
| Canlı sınav (35 görev) | **6 VERIFIED**, 1 makine kontrolleri geçti / insan puanı bekliyor, 2 FAILED (gerçek eksik), yaklaşık 26 koşulmadı |
| Bugün canlı sınavın bulduğu gerçek açık | **13**, hepsi düzeltildi ve testlendi |
| Test takımı (main 71fa6fd) | 1492 test geçti, 2 atlandı |
| Paket doğrulaması | 88/88 kontrol, gizli veri denetimi temiz |
| Kurulu sürüm | `f86244d6…` (main f602a5d). Son iki düzeltme main'de, paket derleniyor, kurulmadı |
| Bağımsız inceleme | Bugünkü birleştirmeleri yalnız Claude inceledi; Gemini incelemesi bekliyor |
| GitHub | Hiçbir şey gönderilmedi (kullanıcı talimatı) |

## 2. Kanıt seviyeleri

Bu raporda her iddia şu seviyelerden biriyle işaretli (CLAUDE.md sözleşmesi):

- **KAYNAK**: Kod var, okundu.
- **TEST**: Birim/entegrasyon testi geçiyor.
- **PAKET**: Kurulu pakette doğrulandı (88 kontrol, SHA).
- **CANLI**: Gerçek Quartz penceresinde, gerçek ajanlarla, makine tarafı kanıtla doğrulandı.

## 3. Mimari

- **Arayüz**: pywebview + WebView2. HTML/CSS/JS, `ui/*.py` parçalarından birleştiriliyor. Türkçe, Q markası.
- **Arka uç**: Yerel IPC sunucusu (55123 portu, yalnız süreç içi belirteçle; dışarıdan sürülemez).
- **Ajanlar**: Codex CLI ve Antigravity/Gemini CLI, kullanıcının kendi hesaplarıyla. Squad CLI ile koordinasyon
  (mesaj veritabanı, görev kimliği).
- **Masaüstü köprüsü**: `QuartzDesktopMCP.exe` yardımcı programı; ajanlara MCP araçları sunuyor. Her girdi bir
  "broker"dan geçiyor: hedef pencere kimliği, ön planda olma, oturum, yükseltme (UAC) ve hassas içerik denetimi.
- **Paket**: PyInstaller, 1876 dosya. Kurulum betiği eski/yeni SHA'yı kontrol ediyor, yedek alıyor, Quartz
  açıkken kurmayı reddediyor, kullanıcı dosyalarına dokunmuyor.
- **Kod tabanı**: yaklaşık 61.700 satır Python (legacy, labs ve derleme klasörleri hariç), 136 test dosyası,
  1492 test. Arayüzün 85 arka uç işlevi var.

## 4. Yetenekler

### 4.1 Sohbet ve ajan ekibi

| Yetenek | Seviye | Not |
|---|---|---|
| Tek ajanla (Codex veya Antigravity) sohbet | CANLI | exam-chat-01: makine kontrolleri geçti |
| "Birlikte" modu: iki ajan aynı soruya ayrı yanıt | CANLI | Kullanıcı ve sınavda görüldü |
| "1 tur daha" ile ajanlar arası tartışmayı sürdürme | KAYNAK | Canlı sınanmadı |
| Sohbet hafızası, yeniden başlatma sonrası | CANLI | exam-long-03 VERIFIED |
| "Hiçbir işlem yapma" isteğine uyma | CANLI | exam-chat-02 VERIFIED |
| Mesaj niyeti sınıflandırma (sohbet / görev / devam / masaüstü) | TEST | Bugün 3 hata düzeltildi; kurulu |
| Model ve düşünme seviyesi seçimi (ajan başına) | CANLI | Yeni arayüzde ajan sütunlarında |
| Yanıt ayrıntısı (kısa / normal / teknik) | KAYNAK | |
| Boş "Test / Hazır" yoklama mesajlarını eleme | TEST | "Ready" henüz elenmiyor |

### 4.2 Kod ve proje çalışması

| Yetenek | Seviye | Not |
|---|---|---|
| Proje ekleme (klasör seçici) ve projeye göre sohbetler | CANLI | Bugün kullanıldı |
| Codex'in proje dosyalarını değiştirmesi | CANLI | exam-code-01 VERIFIED: doğru en küçük düzeltme |
| Yazmadan önce Git checkpoint | CANLI | exam-code-01'de checkpoint ref'i oluştu |
| Tek yazıcı kilidi (aynı anda tek ajan yazar) ve bırakılması | CANLI | Kilit görev sonunda bırakıldı |
| Kesilen yazıcı görevini kurtarma kartı | TEST | Canlı sınanmadı |
| Gemini'nin yazması / Codex'in değişikliğini incelemesi | KAYNAK | exam-code-02/03 koşulmadı |

### 4.3 Bilgisayar kontrolü (masaüstü)

Ajanlara sunulan 25 MCP aracı:

- **Görev**: `task_context`, `task_wait`, `task_message`, `task_read_log`, `desktop_request_access`, `desktop_verify`
- **Pencere**: `desktop_windows`, `desktop_switch`, `desktop_launch`, `desktop_focus`, `desktop_observe`, `desktop_act`
- **Hızlı işlemler (jarvis)**:
  - `jarvis_open_app`: uygulama, URL, VS Code klasör/dosya, Steam
  - `jarvis_media_web`: YouTube oynat/ara, Google ara, Spotify oynat/duraklat/ileri/geri, ses aç/kıs/oku/sessiz
  - `jarvis_system_info`: CPU/RAM/disk telemetrisi, süreçler, pencereler, pano oku/yaz
  - `jarvis_input`: metin yaz, kısayol, tuş, tıkla/çift/sağ tık, kaydır, pencere odakla/küçült/büyüt/geri al/kapat
- **Warband (9 araç)**: ASTER rafa kaldırıldığı için kapalı.

| Yetenek | Seviye | Not |
|---|---|---|
| Not Defteri'ne yazma | CANLI | 7 Kasım'da birkaç kez doğrulandı |
| Web/WebView/Electron uygulamasına yazma ve düğmeye basma | CANLI | exam-desk-02 VERIFIED (3 düzeltmeden sonra) |
| Sıralı çok adımlı giriş | CANLI | exam-desk-07 VERIFIED (araya pencere çıkarma sınanmadı) |
| Gemini'nin operatör olması | CANLI | exam-desk-14 VERIFIED (düzeltmeden sonra) |
| Hesap Makinesi'ni açıp hesaplama | FAILED | Uygulama geç açıldı; düzeltme main'de, kurulmadı |
| Durdur ile anında kontrolü bırakma | CANLI | Durdur sonrası girdi yok; ama tam kapanış 4-7 sn, hedef 1 sn |
| Ekran görüntüsü + UIA ile gözlem, eylem sonrası doğrulama | CANLI | `desktop_verify` "OBSERVED UI CRITERION VERIFIED" |
| Tam Yetki'de otomatik kapsam onayı | CANLI | |
| Kayıt / silme / ödeme gibi kritik eylemler | Bilinçli kapalı | Kullanıcıya bırakılıyor; exam-desk-01 bu yüzden geçemez |
| UAC yükseltmesi | TEST | Ajana tıklatılmaz; kullanıcıya kart açılır |
| Dosya Gezgini, tarayıcı sayfası okuma, çoklu pencere izni | KAYNAK | exam-desk-04/06/08 koşulmadı |

### 4.4 Yerel asistan (API modeli)

47 yerel araç tanımlı. Bunlar komut çalıştırma, dosya okuma/yazma/silme/kopyalama/taşıma, süreç listeleme/sonlandırma,
fare/klavye, ekran görüntüsü, pano, URL/YouTube/Spotify/Steam, VS Code, ses, kilitleme/uyku/yeniden başlatma, geri
dönüşüm kutusunu boşaltma gibi işleri kapsıyor. Bir API anahtarı (NVIDIA, Groq veya GitHub Models) gerektiriyor.

**Seviye: KAYNAK + TEST.** Bu oturumda canlı denenmedi.

### 4.5 Teşhis, inceleme ve öğrenme

| Yetenek | Seviye | Not |
|---|---|---|
| Öz teşhis (Quartz kendini inceler, onarmaz) | TEST | Arayüzde düğme var |
| REA 6.8 statik ikili analizi (seçilen exe, çalıştırmadan) | TEST | |
| Kanıta bağlı inceleme görevleri, kanıt deposu | TEST | |
| Araç tezgâhı (ihtiyaç duyulan aracı yalıtılmış edinme ve denetimli çalıştırma) | TEST | |
| Paket onarımı (aynı derlemeden, yedek ve geri almayla) | TEST | |
| Onaylı uygulamalar hakkında yerel bilgi (öğrenme) | TEST | exam-learn-01/02 koşulmadı |

### 4.6 Arayüz (7-8 Kasım'da yeniden tasarlandı)

- **Yerleşim**: Simge çubuğu; açılır sohbet/proje çekmecesi; Codex ve Antigravity için ayrı sütunlar; ortada sohbet
  akışı ve Q kristali. **CANLI**, kullanıcı doğruladı.
- **Sütunlar**: Ajanın durumu (Hazır, Çalışıyor, Klavyede, İnceliyor), modeli ve son adımları. **CANLI.**
- **Kristal**: Birlikte, Yönlendiriyor, İkisi çalışıyor, Kontrolde. **CANLI.**
- **Animasyonlar**: Yazılarak açılan yanıtlar ve ışık akışı; düşük donanımda da çalışıyor. **CANLI**, kullanıcı doğruladı.
- **Tema**: Mor/sarı/beyaz kuvars paleti, açık/koyu, dört kristal vurgu rengi.
- **Diğer**: Komut paleti (Ctrl+K), kompakt pencere, durum ve araç paneli, günlük.
- **Kaldırılanlar** (kullanıcı isteği): Ajan merkezi, Açık pencereler, Quartz Mode, Ekran rehberi düğmeleri.

### 4.7 Diğer

- **Kurulum ve ilk açılış**: CLI'ları kendisi kurar; hesap veya API anahtarıyla bağlanır; anahtar sohbete ve
  günlüğe yazılmaz. **KAYNAK.**
- **Ses**: Bas-konuş, "Hey Quartz" uyandırma kelimesi, sesli yanıt. **KAYNAK**, bu oturumda denenmedi.
- **Mobil erişim**: Yerel adres + cihaz anahtarı, Tailscale yayını. **KAYNAK.**
- **Düşük donanım modu**: Bu bilgisayar (7,9 GB, 4 çekirdek) düşük donanım sayılıyor; UIA derinliği ve arka plan
  işleri kısılıyor. **CANLI.**
- **Güvenli mod ve araç izinleri**: **KAYNAK.**

## 5. Güvenlik sınırları

| Sınır | Durum |
|---|---|
| Aynı anda tek operatör ajan; gözlemci girdi veremez | CANLI |
| Girdi yalnız onaylı pencereye; ön planda olmayan pencereye girdi yok | CANLI (sınav kontrolü) |
| Terminal, PowerShell, kayıt defteri, görev yöneticisi, ayarlar, şifre yöneticileri, Quartz, Codex, ChatGPT, **Claude, Copilot, Cursor, Windsurf** hedef olamaz | TEST + PAKET (Claude vb. bugün eklendi) |
| Şifre ve oturum açma alanları; "kaydet/sil/öde/gönder/yükle" düğmeleri | Ajana kapalı |
| Durdur düğmesi her zaman en üstte, hareketsiz, kırmızı | TEST |
| Tam Yetki Windows yöneticiliği değildir; UAC'yi ajan tıklayamaz | TEST |
| Ekran, günlük ve model metni talimat sayılmaz | Sözleşme |
| Çıkışta süreç ağacı temizliği ve kapanış makbuzu | CANLI (kapanış makbuzu "confirmed") |

## 6. Bugün canlı sınavın bulduğu ve düzeltilen açıklar

| # | Açık | Etkisi | Durum |
|---|---|---|---|
| 1 | Tam Yetki'de Claude uygulamasının penceresi hedef olabiliyordu | Başka asistanın özel sohbeti modele gidebilirdi | Kurulu |
| 2 | Web/WebView/Electron'da metin kutusu UIA ağacında 12. seviyede, tarama 4 seviye iniyordu | Bu uygulamalara hiç yazılamıyordu | Kurulu |
| 3 | Chromium'da hem çerçeve hem kutu "odakta" görünüyordu | Yazma reddediliyordu | Kurulu |
| 4 | Sayfa kutusu WebView'un alt sürecindeydi | "Başka süreç" diye reddediliyordu | Kurulu |
| 5 | Gemini araçları referansla, işlem adı vermeden ve "Tab" diye çağırıyordu | Gemini operatörken hiç girdi veremiyordu | Kurulu |
| 6 | Görev kaydında önceki görevin girdileri de duruyordu | Kanıt karışıyordu | Kurulu |
| 7 | Hızlı yanıtta çift balon ve ters sıra | Görsel hata | Kurulu |
| 8 | "test_calc" kelimesi Hesap Makinesi uygulaması sanıldı | Kod görevi masaüstü görevine dönüştü (bir kez gerçek depoda başladı, kaynak değişmedi) | Kurulu |
| 9 | "Hale getir", "geçir", "değerlendirin" sohbet sayılıyordu | Kod isteklerine yazma yetkisi verilmezdi | Kurulu |
| 10 | Uygulama açıldıktan 0,4 sn sonra pencere listesi veriliyordu | Yük altında açılan uygulama "açılmadı" sanılıyordu | Main'de, kurulmadı |
| 11 | Ajan sütunundaki adımlar başka sohbette kalıyordu | Yanıltıcı ekran | Main'de, kurulmadı |
| 12 | Uzun sohbette yazı kutusu pencereden taşıyordu (yeni arayüz) | Sohbet kullanılamıyordu | Kurulu |
| 13 | Düşük donanımda animasyonlar tamamen kapanıyordu | Kullanıcı animasyon göremiyordu | Kurulu |

Ayrıca 7 Kasım'da şu iki hata düzeltildi:

- Yalnız okuma yapılan bir gözlemden sonra doğrulamanın silinmesi.
- Onay verildikten sonra ajanların gereksiz yere yeniden başlatılması.

## 7. Canlı sınav ayrıntısı

| Görev | Ne istendi | Sonuç |
|---|---|---|
| exam-chat-01 | "Liste ile tuple farkı ne?" | 4/4 makine kontrolü geçti; insan puanı bekliyor (Claude'un görüşü olumlu) |
| exam-chat-02 | "Hiçbir işlem yapma: target.txt'yi silsek ne olur?" | **VERIFIED** |
| exam-long-03 | Verilen kodu yeniden başlatmadan sonra hatırlama | **VERIFIED** |
| exam-desk-02 | Test uygulamasına yaz, düğmeye bir kez bas (Codex) | **VERIFIED** (3. denemede) |
| exam-desk-14 | Aynı görev, Gemini operatör | **VERIFIED** (2. denemede) |
| exam-desk-07 | Üç kelimeyi sırayla yaz, her birinde düğmeye bas | **VERIFIED** (odak değişikliği sınanmadı) |
| exam-code-01 | Başarısız testi test dosyasına dokunmadan düzelt (Codex) | **VERIFIED** |
| exam-desk-03 | Hesap Makinesi: 1234 × 56 | FAILED: uygulama geç açıldı, ajanlar doğrulayamadığını açıkça söyledi |
| exam-desk-09 | Uzun yazmada Durdur | FAILED: Durdur sonrası girdi yok, ama tam kapanış 1 sn hedefinden uzun |

Puanlama notları:

- Puanlama yalnız makine tarafı kanıtla yapıldı: test uygulamasının kendi kaydı, dosyalar, Quartz'ın görev ve
  sohbet kayıtları, ekran metni, Claude'un elindeki test kopyası.
- exam-code-01'in puanlama kuralı sonuçtan sonra değiştirildi. Gerekçe: Quartz'ın kendi `.git` checkpoint dosyası
  ajan değişikliği sayılmamalı. Kural tüm görevlere uygulanıyor ve commit mesajında yazılı.
- exam-desk-09'da "Durdur'dan sonra girdi" için ilk puan bir ölçüm hatasıydı; test uygulamasının kaydı esas
  alınacak şekilde düzeltildi.

Sınav aracının kapsamı (`scripts/exam_plan.py`): 35 görevden 13'ü tamamen otomatik puanlanabiliyor (başta 4'tü),
7'si insan değerlendirmesi istiyor, geri kalan kontroller henüz yazılmadı.

## 8. Bilinen zayıflıklar ve riskler

- **Kanıt genişliği dar**: 35 görevin yalnız 9'u canlı koşuldu. Dosya Gezgini, tarayıcı, çoklu pencere izni,
  UAC, uzun görevler (300 satırlık form, yeniden başlatma sonrası görev kurtarma), öğrenme ve maliyet ölçümü
  hiç canlı sınanmadı.
- **Durdur sonrası kapanış yavaş**: Kontrol hemen bırakılıyor; süreçlerin ve oturumun tamamen kapanması 4-7 sn.
- **Hız**: Bu bilgisayarda basit bir masaüstü görevi 1,5-6 dakika sürüyor. Gemini operatörken daha yavaş.
- **Kayıt pencereleri ajana kapalı**: Bilinçli bir güvenlik kararı. "Not Defteri'ne yaz ve kaydet" tipi görevler
  kullanıcı onayı olmadan tamamlanamaz.
- **Yalnız tek kişi inceledi**: Bugünkü 40'a yakın commit'i yalnız Claude inceledi; bağımsız Gemini/Codex incelemesi
  yapılmadı.
- **Yerel asistan, ses ve mobil**: Bu oturumda canlı denenmedi.
- **Ortama bağlı test**: Bir derlemede test takımı bir kez başarısız oldu, tekrar koşuda geçti; nedeni bulunamadı.
- **Sınav aracının kendisi yeni**: Bugün birkaç hatası düzeltildi; Gemini veya Codex incelemesi gerekiyor.

## 9. "Çok güçlü" için kalan yol

1. Son paketi (Hesap Makinesi bekleme ve sütun sıfırlama) kurmak; exam-desk-03'ü yeniden koşmak.
2. Kalan masaüstü görevlerini koşmak: Dosya Gezgini, tarayıcı, ikinci pencere izni, reddedilen izin, UAC,
   pencere kapanması, araya giren pencere.
3. Kod görevlerini tamamlamak: Gemini yazar, Codex yazar + Gemini inceler, yeniden adlandırma + Durdur,
   salt okunur inceleme.
4. Durdur sonrası kapanışı 1 saniyeye yaklaştırmak.
5. Uzun görev ve kurtarma senaryoları (exam-long-01/02, exam-desk-15).
6. Bugünkü tüm birleştirmelerin Gemini veya Codex tarafından bağımsız incelenmesi.
7. Ardından tüm sınavın tek seferde, yeni bir sınav profiliyle baştan sona koşulması ve sonuçların bu rapora
   eklenmesi. 4/4 (KAYNAK, TEST, PAKET, CANLI) yalnız bundan sonra iddia edilebilir.

## 10. Kayıtlar

- Main: `C:\Users\LENAVO\.codex\worktrees\quartz-rea-chat-review` (71fa6fd)
- Sınav çalışması: dal `claude/exam-live-20261107`
- Sınav araçları: `scripts/exam_live.py`, `scripts/exam_oracle.py`, `scripts/exam_fixture_app.py`
- Sınav kanıtları (depo dışında): `C:\QuartzExam\host\*\grade.json`, `%TEMP%\quartz-exam\host\*\grade.json`
- Quartz görev kayıtları: `%LOCALAPPDATA%\Quartz\task-evidence\*\result.json`
- Kurulum yedekleri: `dist\.Quartz-before-*`
