# SpeS Android uygulaması

Telefonundan SpeS ekibini (Fatum, Fides, Eos) izlemek ve yönlendirmek için yerel
Android uygulaması. Google/Firebase kullanmaz: telefon yalnız **Tailscale**
üzerinden kendi bilgisayarındaki SpeS'e bağlanır; model sağlayıcılarına bilgisayar bağlanır.

## Neler yapar
- Ekip sohbetini gösterir; mesaj gönderir. Telefondan başlayan işler **yalnız
  okuma** yetkisiyle çalışır, projeye yazma için bilgisayar gerekir.
- **Dur** düğmesi her zaman görünür; çalışan işi durdurur.
- Arka planda dinler: yeni ekip mesajı ve "iş bitti" bildirimi.
- **Acil uyarı (arama):** Bir iş başarısız olursa zil çalar, titrer ve kilit
  ekranında tam ekran açılır (Dur / Konuş / Sustur). 45 saniye sonra kendiliğinden susar.
- **Sesli mod:** "Konuş" ya da sohbetteki "Ses" düğmesi. Ses tanıma ve konuşma Android'in
  kendisi. "Dur", "durum", "tekrar dene" telefonda işlenir. Diğer sorular önce bilgisayara
  gider: bilgisayar ekibin görünen durumundan ~1 saniyede kısa bir cevap üretir (NVIDIA'nın
  barındırdığı Nemotron Bolt modeli) ya da soruyu ekibe iletir ve "Ekibe soruyorum" der.
  NVIDIA'ya yalnız ekip durumu ve son mesajların kısaltılmış metni gider; kod, dosya,
  hafıza, yol ve gizli değerler gitmez. İş isteği ve risk/güvenlik soruları her zaman ekibe gider.
- **Hafıza:** Ayarlar'da ajanların hatırladıkları görünür; her satır silinebilir.

## Kurulum (bir kez)
1. Bilgisayarda Tailscale yayınını aç (tailnet içi, internete açık değil):
   `tailscale serve --bg http://127.0.0.1:8765`
2. APK'yı telefona kopyala ve aç; "bilinmeyen kaynaklara izin ver" sorusuna izin ver.
3. Uygulamada Tailscale adresini yaz (ör. `bilgisayar.tailnet.ts.net`).
4. Bilgisayarda SpeS → Durum ve araçlar → Araçlar → **Mobil erişim**. Kartta görünen
   6 haneli **eşleştirme kodunu** telefona yaz. Kod 5 dakika geçerli, tek kullanımlık;
   5 yanlış denemede iptal olur.
5. Bildirim iznine izin ver. Android 14+ için Ayarlar ekranındaki
   "Tam ekran uyarıya izin ver" düğmesiyle acil uyarıyı aç; "Acil uyarıyı dene" ile dene.

## Güvenlik
- Cihaz anahtarı yalnız `Authorization` başlığında gider; adreste görünmez, yedeğe girmez.
- Yalnız HTTPS (Tailscale Serve); düz HTTP kapalı.
- Telefona kod, şifre veya anahtar gönderilmez; yalnız kısa ekip mesajları.
- APK imza anahtarı yalnız bilgisayarda (`%USERPROFILE%\.spes-dev\signing`) durur, depoya girmez.

## Derleme
Araçlar `%USERPROFILE%\.spes-dev` içindedir (JDK 17, Android SDK, Gradle):

`python -B scripts/build_android_apk.py`

Çıktı: `%USERPROFILE%\.spes-dev\out\SpeS-<sürüm>.apk`. Güncellemeler aynı anahtarla
imzalandığı için telefondaki uygulamanın üstüne kurulur.
