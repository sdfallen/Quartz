# Tam Yetki korunarak çalışma doğruluğu düzeltmeleri

26 Ekim 2026. Kullanıcı Tam Yetki varsayılanını ve otomatik kapsam onayını
bilinçli olarak seçti. Bu çalışma bu politikayı değiştirmez; önceki incelemedeki
yetki varsayılanına ilişkin öneri kullanıcı tercihiyle kapsam dışına alınmıştır.

## Düzeltilenler

1. **Hedef doğruluğu:** Jarvis girdisinde pencere eşleşmesi tam bir adet olmalı.
   Bulunamayan/belirsiz hedefte girdi yok. Açık hedef verilmezse gerçek foreground
   HWND kullanılır; hedef tahmin edilmez. Native session, süreç kimliği, geometri
   ve foreground girdiden hemen önce denetlenir. Tıklama hedef rect içinde kalır.
2. **Görev sınırı:** Devam eden çağrı/temizlik/eski watcher bitmeden ikinci görev
   başlayamaz. Eski çağrı kendi job nesnesine bağlıdır. Stop sonrasında gelen sonuç
   yeni göreve veya doğrulamasına yazılmaz; eski kanıtta `interrupted_calls` olarak
   tutulur. Yeni eylemler kapalıyken UI `Görev durduruluyor` gösterir.
3. **Denetleyici uyumu:** `hotkey` tek chord string'i alır. `type_and_enter`
   Unicode metni panoyla aktarır; Enter ayrı seçenektir. Eski çağrılar varsayılan
   olarak Enter davranışını korur. Her gerçek tuş/paste öncesi iptal/hedef guard'ı
   yeniden çalışır. Controller çağrısı tek başına sonuç kabulü oluşturmaz.
4. **Gerçekte olmayan profil:** MCP'deki coding/gaming/study/night/chill iddiası
   kaldırıldı. Bunların mevcut `quartz_mode()` Windows güç planıyla eşleştirilmesi
   doğru değildi. Eski istemci bu action'ı gönderirse açıklayıcı hata alır. Legacy
   manuel Quartz Mode fonksiyonu silinmedi; bu görevde güç planı çalıştırılmadı.
5. **Sohbet ayrımı:** `Spotify'daki oynat tuşu ne işe yarıyor?`, `Set theory
   hakkında ne düşünüyorsun?`, `Bunu yap demek kolay mı?` sohbet olarak kalır.
   Ayrı cümledeki gerçek emir ve `Set the volume to 20` görev olarak korunur.
6. **F-06:** Etkin görevsiz `Devam et` veya `Durdur` Quartz tarafından Türkçe
   durum mesajıyla karşılanır; eski işlem tekrarlanmaz ve yeni model/izin açılmaz.

`jarvis_system_info` clipboard yazma da içerdiğinden MCP read-only annotation'ı
düzeltildi. Bu, kullanıcı Tam Yetki politikasını veya grant akışını değiştirmez.

## Kontroller

- İlk hedefli koşuda bir test fixture'ı yanlış bound method'u patch'lediği için
  belirsiz hedef testi başarısız oldu; test doğru `desktop.windows` nesnesini
  patch'leyecek şekilde düzeltildi. Üretim eşleştirme koşulu gevşetilmedi.
- 9 yeni regresyon testi geçti. Gerçek controller fonksiyon gövdeleri AST'den
  alınarak sahte klavye/pano ile çalıştırıldı; gerçek masaüstü girdisi yok.
- İlk tam koşu: **476/476 OK**. Küçük kanıt kaydı/annotation değişikliğinden sonra
  ilgili **17/17 OK**. Gömülü JavaScript parse exit 0.
- Paket doğrulayıcıya `advanced_controller` kod imzası da eklendi; böylece yeni
  text/hotkey adaptörlerinin EXE içinde güncel olması kontrol edilir.
- Kaynak karşılaştırması başlangıç checkpoint'ine karşı yapıldı. Kullanıcının
  önceden yaptığı 13 dosyalık değişiklik korunuyor; bu çalışmaya ait düzeltmeler
  bunların üzerine dar kapsamla eklendi. Kullanıcı değişiklikleri ayrı bir commit
  altında bize aitmiş gibi topluca kaydedilmedi.

Canlı CLI/MCP taşıma, derleme, paketli GUI ve teslim sonuçları aşağıdaki teslim
makbuzlarında ayrı izlenir. Birim testleri gerçek Windows girdi kabulü değildir.

## Koruma

Başlangıç kaynak checkpoint'i:
`C:\Users\LENAVO\.codex\backups\quartz-full-mode-fixes-20261026\agent-1793044131-3bb5060c3a194ad78a30c99a81d9ef33.zip`

Paket ve eski MCP helper yedeği:
`C:\Users\LENAVO\.codex\backups\quartz-full-fixes-package-20261026`

Tam Yetki, otomatik onay, kayıtlı modeller, sohbetler, Q ikonu, Squad ve mevcut
Universal Modder sınırı korunur. ASTER/Warband kaynakları ve korunan kayıtlar
değiştirilmez. Registry, sürücü, Overlay, güvenlik ve güç planı işlemi yapılmaz.

## Teslim sonucu

- Son kurulum öncesi regresyon: **476/476 OK**, beklenen başarısızlık yok.
- Gerçek CLI/MCP/Squad bağlantısı: **VERIFIED**; Codex ve Antigravity completed.
  Kanıt: `labs/natural-gateway-20261026-230016/transport-result.json`. Bu, izole
  host deposu ve penceresiz backend ile gerçek modellerin taşıma testidir; Windows
  girdi kabulü değildir.
- Kaynak/paket, helper şeması, `advanced_controller`, CSS ve Q ikonları eşleşti.
- Yeni EXE SHA256: `8c2139d340bcd425a04e6ca6991820a88d7759eff2222a1aa7d5dfd61b9b7121`.
- Eski dağıtım yedeği: `C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261026-230556`.
- Kurulumda 34 veri dosyası byte-identical. Kullanıcının Full policy, model,
  Native controller ve diğer değiştirmediğimiz kaynakları başlangıç checkpoint'i
  ile eşleşiyor (`user-policy-preserved.json`).
- Quartz önceden kapalıydı. Yeni EXE normal açıldı; UIA'da çevrimiçi durum,
  **Tam Yetki**, kayıtlı modeller ve ana sohbet görüldü.
- Görsel/girdi kabulü: **BLOCKED**. İki capture denemesi `window capture timed out`,
  gözlenen sohbet alanına tek click denemesi `coordinate input geometry is unavailable`
  verdi. Rastgele koordinat veya farklı kontrol kanalı kullanılmadı.

Sonraki canlı kontrol: açık test uygulamasında metin girişi (Enter kapalı/açık),
Ctrl+C gibi kısayol, bulunamayan hedefin güvenli reddi ve Durdur sonrasında ikinci
görev. Şu an bu maddeler fonksiyon/izole regresyon düzeyinde VERIFIED; gerçek
Windows etkileşimi olarak doğrulanmış sayılmıyor.
