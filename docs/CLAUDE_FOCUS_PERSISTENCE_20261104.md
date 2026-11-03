# Odak değişiminde görevin sürmesi

Tarih: 4 Kasım 2026. Sahip: Claude. Taban: `4120f5e`. Kullanıcı isteği: pencere
değişimi veya kullanıcı müdahalesi görevi bitirmesin; görev İptal'e kadar sürsün.

## Gözlenen hata

Kanıt: `task-evidence/9e03d429…` ve `2b341d29…`, sonuç
`blocked: foreground changed (user takeover)`. Her iki Aseprite görevi seçili
`aster-warband` projesinde çalıştı. `persistent_control=not self.warband` bu
profilde odak kurtarmayı kapattığı için oyun dışı pencerede de görev durdu.

## Değişiklik

- `core/natural_desktop.py`: odak kurtarma yalnız Warband profilindeki oyun
  penceresinde kapalı. Devam talimatı yalnız Warband metninde kaldığı için genel
  talimata taşındı; "engeli raporla" ifadesi kaldırıldı.
- `core/desktop_broker.py`: kalıcı kontrolde başarısız `desktop_switch` görevi
  bitirmez; girdi göndermeden hata döner.
- `core/desktop_agents.py`: eski giriş yolunun talimatı aynı sözleşmeye geçti.

Warband oyun girdisi, Stop, kilit ekranı, süreç kimliği, taze gözlem ve UAC
sınırları değişmedi. Odak değişiminden sonra eski eylem tekrar uygulanmaz.

## Bilinçli olarak korunan sınırlar

Görev süresi (`expires_at`), oturum başına 100 eylem bütçesi, kapatılan veya
süreci değişen hedef pencere görevi hâlâ bitirir. Ajan kendi turunu bitirirse
görev de biter; talimat bunu odak nedeniyle yapmamasını söyler ama zorlamaz.

## Kanıt seviyesi

TESTED: yeni regresyonlar düzeltmesiz kodda başarısız, düzeltmeyle başarılı.
Gerçek Windows odak değişimi ve paketli sohbet kabulü bu belgede kanıtlanmaz.

## Codex entegrasyon kontrolü

4 Kasım 2026: `claude/focus-persist-20261104` (`19601a2`) dalı,
`codex/rea-chat-review-20261102` entegrasyon dalına fast-forward alındı.
Bu işlem `main` birleşmesi veya uzak repoya yayın değildir. Yeni paketler
`19601a2` ve sonrasındaki bu entegrasyon kaynağından üretilmeli; eski ana
çalışma klasöründen derleme odak düzeltmesini içermeyebilir.

Kurulu EXE SHA256:
`87fd63861d814f1ef5b6668b43bac1be14f20186b14217bf8a1b340f2a726df1`.
88 paket/kaynak kontrolü hatasız; önceki Stop (`b27f8ae`) ve öğrenme
(`05890c7`) düzeltmeleri ancestry içinde korunuyor. Hedefli broker, doğal
masaüstü, ajan ve Stop regresyonları: 89 test OK. Bu bağımsız incelemede
uygulama başlatılmadı veya kurulum değiştirilmedi; gerçek GUI kabulü yapılmadı.

Özel kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-final-integration-20261102`.
Kanıtlar: `focus-merge-targeted-20261104.log`,
`focus-installed-verification-20261104.json`.
Birleşme öncesi checkpoint: `before-focus-merge-4120f5e.bundle`.
