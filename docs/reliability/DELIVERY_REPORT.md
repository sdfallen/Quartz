# Quartz güvenilirlik çekirdeği — teslim raporu

Tarih: 25 Ekim 2026. Yerel dal: `codex/reliability-kernel-20261025`.
Başlangıç: `36a2d9ea8a8abdd744195fa84ff8eec61b3f7444`.

## Uygulanan mimari

Ana sohbet aynı giriş noktası olarak kaldı. Yeni büyük bir framework yerine
mevcut sorumlulukların arasına üç küçük, test edilebilir sınır eklendi:

```text
Ana sohbet / UI
  -> AgentChat: tur kimliği, sahiplik ve iptal
      -> MultiAgentService: izin, checkpoint, tek yazıcı, runtime
      -> NaturalDesktopTask: görev kapsamı ve yaşam döngüsü
          -> Desktop Broker: tek ve kimliği doğrulanmış input otoritesi
  <- AsyncSnapshot: tek arka plan diagnostik, beklemeyen durum okuması
  <- Source verification: çalıştırmadan sınırlı Python AST kanıtı
  <- Task outcome: yürütme / kanıt / cleanup ayrı sonuçlar
```

Snapshot ve kanıt katmanı izin vermez; modelin "tamamlandı" metni hedef kabulü
sayılmaz. UI/Squad/provider durumları önbellekten sunulurken görevin gerçek
dispatch ve broker yetki kontrolleri yerinde kalır.

## Somut düzeltmeler

- Yavaş CLI/Squad kontrolleri UI durum okumasını tutmuyor. Aynı anda yalnız bir
  refresh; eski proje sonucunun yeni projeye yazılması engellendi.
- UI chat polling üst üste istek üretmiyor. Model keşfi beklerken kayıtlı model
  ve reasoning seçimi geçici varsayılanlarla değiştirilmiyor.
- İptal sırasında yeni görev başlatılamıyor. Geç eski callback yeni turun
  metnini, oturumunu, ilerlemesini veya terminal durumunu değiştiremiyor.
- Aynı pencere kimlikleri için yalnız log ekleme izni mevcut input lease'ini
  iptal etmiyor; onay süresini uzatmıyor ve yeni logu onaysız okumuyor.
- Stop önce yetkiyi kapatıyor; runtime, broker, geçici dosya, HTTP ve Squad
  cleanup adımları birbirinden bağımsız denenip hatalar kaydediliyor.
- HTTP istemcisi header/body aşamasında koparsa kapanış zinciri bozulmuyor.
- Yazıcı sonrası pasif Python syntax kontrolü, kapsam ve SHA ile ayrı kanıt
  oluşturuyor. Projenin kodu import edilmiyor veya testleri yürütülmüyor.
- Salt-okunur retry sonrası mesajın run kimliği gerçek ikinci run ile eşleşiyor.
- Ana durdurma metni Türkçe; ham teknik neden açılır ayrıntılarda korunuyor.

## Doğrulama sınırları

Son dağıtım kapısında **416 test: 411 PASS + 5 expectedFailure**, beklenmeyen
failure/error sıfır (51.180 s). Testlerin çoğu izole mock/fixture kapsamındadır.
`check_gui_javascript.py`, `git diff --check` ve secret/history audit PASS.
Audit 226 mevcut dosya / 210 history blob üzerinde bulgu üretmedi; daha sonra
eklenen final dokümanlar için sayı artabilir.

Paket kaynak kodu, yardımcı EXE/schema, CSS ve Q ikon kontrollerinin tamamı PASS.
Kurulu EXE SHA256:
`368ac674a87ed99d8846d77cc74b5254c4073be5cce5c61bca918001a86ac255`.
Dağıtım alındısı:
`C:/Users/LENAVO/.codex/backups/quartz-reliability-package-20261025/deployment-receipt.json`.
Eski dağıtım:
`C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261025-015746`.
Helper gerçek JSON-RPC initialize/tools-list ve tokensiz access reddini geçti.
Bu kapı gerçek klavye/fare veya masaüstü görevi kabulü değildir.

Gerçek iki sağlayıcılı host sohbet testi:
`labs/reliability-live-20261025-014707/result.json`.
Codex `gpt-6-luna/low`, Antigravity `gemini-3.8-flash-high/high` ayrı gerçek
run'larda yanıt verdi. Her iki run'da araç/komut/değişen dosya sayısı sıfır.
Bu test ana sohbet **servisi** üzerinden yapıldı; paketli GUI'ye yazılmış görev
veya eşzamanlı Squad masaüstü kabulü değildir. İlk host status ~1.96 ms,
en uzun örneklenen poll ~6.78 ms; genel açılış/FPS/CPU kazanımı değildir.

Son retry kimliği düzeltmesi ve dağıtımdan sonra gerçek host testi tekrarlandı:
`labs/reliability-live-20261025-020006/result.json`. Aynı iki sağlayıcı VERIFIED,
araç olayları sıfır. İlk host status ~0.99 ms. Bu ikinci koşu da GUI değil,
izole ve salt sohbet kapsamındadır; aynı-son-kaynak denetimini tamamlar.

Antigravity incelemesindeki 5 expectedFailure aynen korundu. Bunların kapsamı
ve kabul edilmeyen önerilerin gerekçesi `REVIEW_DECISIONS.md` içinde. Bunlar
416 testin tamamı geçti biçiminde sunulmayacak.

### Gerçek paketli uygulama

01:57:52'de kurulu EXE başlatıldı (gözlem anındaki PID 9928; gelecekte geçerli
varsayılmayacak). Erişilebilirlik ağacı Quartz ana sohbetini, Q grafik öğesini,
önceki proje/sohbeti ve kayıtlı `gpt-6-sol/medium` ile
`gemini-3.8-flash-high/high` seçimlerini gösterdi. UI'de Squad kontrolü arka
planda sürerken sohbet metni okunabildi. Bu **UIA gözlemi**, görsel QA değildir.

Gerçek screenshot iki kontrollü denemede başarısız oldu:
`FrameArrived timed out: timed out waiting on channel`, ardından pencere bağı
yenilenerek `window capture timed out: timed out waiting on channel`.
Kör tıklama yapılmadı; ana sohbetten yeni sentetik mesaj gönderilmedi ve hiçbir
izin kartı onaylanmadı. **Paketli GUI görsel/desktop görev kabulü = BLOCKED**.
Saf host sohbet testi bunun yerine GUI kabulü olarak gösterilmedi. Quartz bu
kontrolden sonra yeni görev başlatılmadan açık kaldı; diğer pencerelere dokunulmadı.

Dağıtım anında kopyalanan bütün üst-seviye veri dosyaları hash eşitliğini geçti.
Açılış sonrasında `.env`, sohbet, hafıza, proje ve mobile access dosyaları hâlâ
eşit. Açılış loglarının değişmesi normaldir; aktif `assistant.log` kilitli olduğu
için yeniden hash alınamadı ve değişmedi iddiasında bulunulmadı. Kök dizindeki
üç korunan kullanıcı dosyasının hash'leri de başlangıç alındısıyla aynı.

## Açık işler / bu teslimin iddia etmedikleri

1. Kibar Türkçe ve İngilizce komutların niyet kapsamı için ayrı pozitif/negatif
   corpus gerekli. Sohbeti yanlışlıkla eyleme dönüştürmemek için kurallar bu
   dilimde genişletilmedi.
2. Çökme sonrası kalıcı task journal/recovery ve restart boyunca host kanıt
   saklama henüz yok. Mevcut source receipt servis belleğinde; yeniden açılışta
   bağımsız doğrulama kanıtı yok olarak kalır, sahte PASS gösterilmez.
3. Agent bazlı ayrıntılı progress görünümü ek kalite işi. Mesaj balonları zaten
   ayrı listelenir; yeni registry veya ikinci görev motoru kurulmadı.
4. Bilinmeyen proje test komutlarını otomatik yürütme eklenmedi. AST kontrolü
   yalnız listelenen en fazla 200 değişiklikteki uygun Python dosyalarını kapsar.
5. Legacy/Desktop/Natural akışları bir kerede birleştirilmedi. Bir sonraki adım
   ortak veri sözleşmesiyle kontrollü adaptör azaltma olabilir; yetki bypass'ı
   veya task singleton'ı yeniden canlandırma değildir.

## Koruma

Başlangıç checkpoint'i `CORE_PLAN.md` içinde. Paket staging ve alındı dizini:
`C:/Users/LENAVO/.codex/backups/quartz-reliability-package-20261025/`.
Eski dağıtım silinmez; ayrı kurtarılabilir dizine taşınır. Kullanıcı sohbeti,
model ayarları, Q ikonları ve yerel veriler korunur. Antigravity'nin teslim
alanına yazılmadı. ASTER/Warband, kayıtlar, sistem ayarları ve Overlay kapsam
dışı tutuldu. Bu geliştirmeler GitHub'a push edilmedi.
