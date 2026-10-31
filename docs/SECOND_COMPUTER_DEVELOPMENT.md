# Başka bir bilgisayarda Quartz geliştirmesine devam etme

Kaynak aktarımı: 31 Ekim 2026. Public kaynak deposu: `https://github.com/sdfallen/Quartz`.
Ana dal `main` güncel geliştirme kaynağıdır. Hazır kurulum dosyaları, kişisel
hesaplar, `.env`, sohbet geçmişleri ve test kayıtları bu kaynak aktarımına dahil değildir.

## 1. Klonlama ve geliştirici kurulumu

Windows x64,
Python 3.13 ve geliştirici JavaScript testleri için PATH üzerinde Node gerekir.
REA 6.8.0 için Node engine sınırları kaynakta `ReaAdapter.node_supported` ile
kontrol edilir; bu çalışma özel Node 26.13.0 ile doğrulanmıştır.

```powershell
git clone https://github.com/sdfallen/Quartz.git Quartz
cd Quartz
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B scripts/check_gui_javascript.py
.\.venv\Scripts\python.exe -B scripts/run_safe_tests.py
.\.venv\Scripts\python.exe quartz_entry.py
```

Venv'i aktive etmek zorunlu değildir; yukarıdaki açık interpreter yolları
PowerShell execution policy değişikliği gerektirmez. Testler gerçek model veya
masaüstü görevi çalıştırmaz; makinede guard/CLI olmayan bazı gerçek entegrasyon
testleri SKIPPED olabilir. Bu atlamalar başarı olarak yorumlanmamalıdır.

## 2. Yeni bilgisayarın hesapları

Codex Desktop ve Antigravity Desktop/IDE kurmayın; bu proje bunları gerektirmez.
İlk açılışta **Hesabımla bağlan** akışını kullanın. Quartz eksik CLI'yi hazırlayabilir;
ChatGPT/Google girişini resmî pencerede siz tamamlayın. Tek sağlayıcıyla başlanabilir.
API anahtarı ayrı, isteğe bağlı ve kendi API kotasına tabi yoldur.

Eski bilgisayarın `.codex/auth.json`, Google OAuth dosyaları, çerezleri veya `.env`
dosyasını Git'e eklemeyin. Yeni bilgisayarda kendi bağlantısını oluşturun.
WebView2 yoksa başlangıçtaki Microsoft runtime kurulum adımını tamamlayın.

Squad 0.7.6 yardımcısı `assets/bin/` altında lisansıyla bulunur. Yerel proje
yollarını Quartz içinden bu bilgisayara göre ekleyin; raporlardaki `C:\Users\LENAVO`
ve diğer eski yollar canlı yapılandırma talimatı değildir. ASTER varlıkları,
Warband kurulumu ve Universal Modder bu repoda bulunmaz; ayrıca yetkili kurulum gerekir.

## 3. REA'yı bu bilgisayarda hazırlama

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_rea_tool.py
```

REA 6.8.0 sabitlenmiştir. Kurulum kullanıcıya özel `%LOCALAPPDATA%\Quartz\tools\rea`
altındadır; özel Node gerekirse resmî kaynaktan hash doğrulamalı hazırlanır.
Global Node, PATH, CLI hesapları veya ajan MCP kayıtları değiştirilmez.
İnternet gerekir; Ghidra/Java bu statik PyInstaller dilimi için gerekli değildir.

Var olan uyumlu Node/npm için isteğe bağlı `--node C:\...\node.exe` kullanılabilir.
Eski bilgisayardaki `.codex/backups` yollarını yeni makineye sabitlemeyin.
İlk sürüm yalnız kendi Quartz paketini salt okunur inceler; otomatik onarım yapmaz.

## 4. Derleme ve paket teşhisi

```powershell
.\.venv\Scripts\python.exe -B build.py --require-brand
```

Komut güvenli testleri çalıştırır, Desktop MCP guard'ını ve Quartz'ı ayrı staging
klasörüne derler, sonra paket/kaynak eşleşmesini doğrular. Son satırdaki staging
yolunu kullanın. Mevcut çalışma dağıtımı `--deploy` verilmedikçe değiştirilmez.

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_distribution.py "<staging>\dist\Quartz" "<yeni-temiz-klasör>\Quartz"
```

Bu adım kişisel veri denetimi ve `release-manifest.json` oluşturur. Derlenmiş
temiz klasördeki Quartz'ı açıp `Öz teşhis başlat` yazın. `REA olmadan öz teşhis başlat`
ve `Öz teşhisi durdur` da desteklenir. Kaynak modunda Quartz.exe bulunmadığından
paket kontrolünün NOT_TESTED olması normaldir.

Uygun bakım ortamında gerçek backend/REA testi:

```powershell
.\.venv\Scripts\python.exe -B scripts/accept_self_diagnostics.py "<temiz-paket>\Quartz" "<özel-kanıt-klasörü>"
```

Bu CLI harness'i açıkça verilen kendi test paketini salt okunur inceler;
üretim IPC'si dış hedef kabul etmez. Sonuç, gerçek ana sohbet GUI kabulü değildir.

## 5. Kaldığımız nokta

- Codex tarafı: `core/self_diagnostics.py`, `core/rea_adapter.py`, IPC,
  `scripts/prepare_rea_tool.py`, test/paket güvenlik kontrolleri.
- Antigravity tarafı: `gui.py` sohbet kartı/GUI API, `assets/workspace.css`,
  `tests/test_self_diagnostics_ui.py`.
- Son yerel tam regresyon: 661 test PASS. Gerçek REA/IPC, manifest ve iptal kanıtları
  mevcut; teknik raporda kapsamları ayrı belirtilir.
- Açık kabul: aktif masaüstünde paketlenmiş ana sohbetten gönderim → gerçek kart
  ilerlemesi → sonuç ve iptal/yeni iş. Önceki ortamda görüntü yakalama ve tıklama
  geometrisi engellendi; bu kabul tamamlanmış sayılmıyor.
- Genel `Quartz'ı kontrol et` ifadesi için doğal yönlendirme, frontend tarafında
  dar bir sonraki kapsamdır. Şimdilik yukarıdaki doğrulanmış komutları kullanın.
- Yeni makinede resmî hesap girişleri ve gerçek model yanıtı ayrıca test edilmeli.
- Arayüz görsel kalitesi ve düşük donanım performansı kaynak testlerinden
  doğrulanmış sayılmaz. Ölçümleri/başarısızlıkları raporlayın.

## 6. Güvenli Git akışı

```powershell
git switch -c codex/next-work
```

Değişiklikten önce mevcut checkpoint mekanizmasını kullanın. `.env`, hesap
oturumları, sohbetler, ekran kayıtları, `node_modules`, `dist` ve `build`
commit edilmemelidir. GitHub'a göndermeden önce:

```powershell
.\.venv\Scripts\python.exe -B scripts/audit_publish.py --staged --history
git diff --cached --stat
```

Yerel checkpoint/eski `master` branch'leri kişisel geçmiş içerebilir; `--all`
veya `--mirror` ile göndermeyin. Kullanıcının oyun/proje kayıtlarına ve başka
uygulamalara bu kaynak aktarımından izin çıktığı varsayılmamalıdır.
