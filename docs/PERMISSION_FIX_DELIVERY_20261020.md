# Yetki/checkpoint teslimi — 20 Ekim 2026

## Sonuç

Kaynak düzeltmeleri tamamlandı ve yerel dağıtım güncellendi:
`dist/Quartz/Quartz.exe`.

EXE SHA256:
`F2437024CA6E8447702A8011EB0FF40033A9AA196416E6124FEA17D5367A86CE`.

| Kontrol | Sonuç | Kanıt/kapsam |
|---|---|---|
| Tam regresyon | PASS:176test | `python -B scripts/run_safe_tests.py`; gerçek model görevi değil |
| Yetki/ret/retry/kilit/checkpoint regresyonları | PASS | `tests/test_agent_permissions.py` ve runtime/checkpoint testleri |
| Gerçek geçici dosya değişimi ve geri okuma/geri yükleme | PASS | Tamamen disposable klasör, gerçek kullanıcı dosyası değil |
| Git dirty/untracked/deleted arşivi | PASS | Disposable Git repo; ana çalışma ağacı resetlenmedi |
| PyInstaller build | PASS | Ayrı dist/work dizini, eski dağıtımı silen build.py çalıştırılmadı |
| Paket kaynak eşitliği | PASS:7/7 | PYZ'deki agent_chat, multi_agent_service, codex_runtime, antigravity_runtime, workspace_checkpoint, main ve gui code object'leri güncel kaynak derlemesiyle eşit |
| Paket kullanıcı dosyaları | PASS:4/4hashaynı | Eski dağıtımdan yeniye taşınan kullanıcı dosyaları |
| Kaynak kökü kullanıcı dosyaları | 7/8hashaynı; hafızada oturum-tarihi yan etkisi | `.env`/konuşmalar dahil7dosya aynı; `quartz_memory.json` test importunda güncellendi, aşağıdaki notu oku |
| Gerçek Codex/Antigravity ajan görevi | NOT TESTED | Bu düzeltmede ücretli/canlı model görevi veya Warband testi başlatılmadı |
| Gerçek GUI etkileşimi | NOT TESTED | UI varsayılan/onay kaynak testleri var; kullanıcı oturumu devralınmadı |

## Kullanım

- Varsayılan **Salt Okunur**.
- **Proje Yetkisi**: Codex seçili proje sandbox'ında yazar; Antigravity tek başına
  proje-sınırlı yazmayı açık hata ile reddeder. Birlikte modunda Codex yazar,
  Antigravity sonrasında salt-okunur inceler.
- **Tam Yetki**: görev başındaki açık onayla ayrı full-access yolu. Bu mod
  bilgisayar yalıtımı veya tam sistem yedeği sağlamaz. Önce proje checkpoint'i
  gerekir; başka yazıcıyla çakışmaz.
- İzin reddi otomatik onay/yetki artışına dönüştürülmez. Başarısız yazmalı iş
  kendiliğinden tekrar çalıştırılmaz. Yeni bir görevde tekrar denemek kullanıcının
  yeni isteğidir; önceki yan etkileri otomatik geri alındı sayılmaz.

## Korunan yedekler

- Değişiklik öncesi kaynak/test/docs:
  `C:\Users\LENAVO\.codex\backups\quartz-permission-fix-20261020-101832.zip`.
- Önceki dağıtım TAMAMIYLA ve silinmeden:
  `C:\Users\LENAVO\.codex\backups\quartz-distribution-before-permissions-20261020-1037`.
- Build/test/deployment kayıtları:
  `C:\Users\LENAVO\.codex\backups\quartz-permission-package-20261020-1030`.
  Burada `build.log`, `regression-176.log`, `deployment-receipt.json` bulunur.
  İlk staging denemesinin çıktı biçiminde Select-Object/hashtable nedeniyle null
  alanlar göründü; gerçek JSON receipt yeniden okunup değerler doğrulandı.

Program Files kurulumu ve masaüstü kısayolları değiştirilmedi. Eski kurulumun
kısayolu otomatik olarak yeni EXE'yi açıyor varsayılmamalı; bu teslimin adresi
çalışma klasöründeki `dist/Quartz/Quartz.exe` dosyasıdır.

## Sınırlar

Son hash kontrolü, mevcut `assistant.py` importunun global `MemorySystem()`
oluşturduğunu ve bunun `_update_session()` → gecikmeli `_flush()` yoluyla kaynak
`quartz_memory.json` dosyasına oturum tarihi yazdığını yakaladı. Test assertion'ları
176/176 geçse de bu veri kontrolü BAŞARISIZ oldu; 8/8son-koruma PASS iddia edilmiyor.
Test runner artık discovery'den ÖNCE memory yollarını geçici klasöre yönlendirir,
sonunda timer'ı kapatır. Önceki tarih tahmin edilerek geri yazılmadı; kullanıcı
not/tercihleri eski bir dağıtım dosyasıyla körlemesine değiştirilmedi. Üretim
uygulamasının normal oturum-tarihi davranışı değiştirilmedi. Nihai yalıtılmış
koşuda176test12.837s'de geçti; o koşudan önceki/sonraki hafıza hash'i aynı:
`9D7F72719FC321914B3BA138CE688A51F29A95EA40EFDD83EF13E598C4D292F2`.
Son kayıtlar `regression-176-isolated-memory.log` ve `closing-integrity.json`.

Warband klasör kayıt koruması kaldırılmadı, oyun/mod/kayıt dosyaları değiştirilmedi.
Universal Modder/Warband'a özel çoklu-kök yedekleme ve lease kapanış profili ayrı
iştir. Yerel IPC kimlik doğrulaması ve üretim log rotasyonu bu kapsamda çözülmüş
sayılmaz. Tam yetki proje dışına erişebilir; proje checkpoint'i o dış değişiklikleri
geri alma garantisi değildir. Antigravity inceleme modu mutlak OS salt-okunur
yalıtımı olarak sunulmaz.

İzin ayrımı, [resmî Codex CLI izin sözleşmesi](https://learn.chatgpt.com/docs/cli/reference)
ile aynı read-only/workspace-write/full-access ayrımını korur; mevcut model veya
hesap ayarları değiştirilmedi.
