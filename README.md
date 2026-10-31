# Quartz

[![Quartz source checks](https://github.com/sdfallen/Quartz/actions/workflows/tests.yml/badge.svg)](https://github.com/sdfallen/Quartz/actions/workflows/tests.yml)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-4b8bbe)](#gereksinimler)
[![Python](https://img.shields.io/badge/Python-3.13-3776ab)](#geli%C5%9Ftirici-kurulumu)
[![License](https://img.shields.io/badge/license-source--available-lightgrey)](#lisans)

Quartz, Codex ve Antigravity CLI ajanlarını tek bir Windows masaüstü
uygulamasında birleştiren yerel bir geliştirme asistanıdır. Ana sohbet;
proje bağlamını, iki ajanlı Squad koordinasyonunu, görev kapsamlı masaüstü
araçlarını ve doğrulanabilir çalışma kanıtlarını ortak bir akışta tutar.

> **Geliştirme önizlemesi:** Bu depo kaynak geliştirme içindir. Hazır bir
> son kullanıcı sürümü veya destek garantisi sunmaz. Gerçek masaüstü ve oyun
> kabul testleri, kaynak testlerinden ayrı değerlendirilir.

## Neler sunuyor?

| Alan | Mevcut durum |
| --- | --- |
| Tek sohbetten görev ve normal konuşma | Var; mesaj niyeti araç kullanımından önce sınıflandırılır |
| Codex + Antigravity koordinasyonu | Var; roller Squad üzerinden paylaşılır, fare/klavye tek operatörde kalır |
| Masaüstü gözlemi ve kontrolü | Görev ve pencere kapsamlı izin, kimlik kontrolü, Stop ve taze gözlem korumalarıyla |
| Uygulama öğrenmesi | Onaylı EXE üzerinde REA destekli sınırlı statik inceleme ve yerel, hash bağlı bilgi deposu |
| Yönetici isteyen uygulamalar | WinError 740 için uygulamaya özel UAC isteği; Quartz kendiliğinden yükseltilmez |
| Öz teşhis ve kaynak onarımı | Salt okunur teşhis; onarım yalnız doğrulanmış referans, önizleme, kullanıcı onayı ve yedekle |
| Warband / ASTER | Universal Modder üzerinden ayrı ve korumalı adaptör; oyun varlıkları bu depoda değildir |

REA bulguları bir uygulamanın iç kodunu veya bütün çalışma biçimini öğrenmiş
olduğu anlamına gelmez. Statik dosya kanıtı, canlı ekran gözlemi ve gerçek
işlev testi ayrı kanıt düzeyleridir.

## Güvenlik modeli

- “Tam Yetki”, Windows yönetici tokenı değildir ve UAC sınırını kaldırmaz.
- Ekrandaki metinler güvenilir sistem talimatı sayılmaz.
- Pencere kimliği veya taze görüntü doğrulanamıyorsa koordinat tahmini yapılmaz.
- Yeni kapsam, korunan proje veya yönetici uygulaması gerektiğinde ayrı izin istenir.
- `.env`, CLI oturumları, sohbetler, yerel hafıza, ekran görüntüleri ve çalışma
  logları Git tarafından dışlanır.
- Warband kayıtları ve Universal Modder kurulumu bu repo tarafından taşınmaz.

Ayrıntılar için [güvenlik politikası](SECURITY.md) ve
[masaüstü operatörü sözleşmesi](DESKTOP_OPERATOR.md) okunmalıdır.

## Gereksinimler

- Windows 10/11 x64
- Python 3.13
- Geliştirici JavaScript kontrolleri için Node.js 22
- GUI için Microsoft Edge WebView2 Runtime
- Codex veya Antigravity ajanı için ilgili CLI hesabı

Codex Desktop veya Antigravity Desktop/IDE zorunlu değildir. İlk açılış
sihirbazı eksik CLI bağlantısını hazırlayabilir; resmî hesap girişini kullanıcı
tamamlar. API anahtarı yolu isteğe bağlıdır ve sağlayıcının ayrı API kota ve
ücretlendirmesine tabidir.

## Geliştirici kurulumu

```powershell
git clone https://github.com/sdfallen/Quartz.git
cd Quartz
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B scripts/check_gui_javascript.py
.\.venv\Scripts\python.exe -B scripts/run_safe_tests.py
.\.venv\Scripts\python.exe quartz_entry.py
```

Venv'i aktive etmek gerekmez. `.env` hesapla ilk kurulum için zorunlu değildir.
API anahtarı kullanılacaksa `.env.example` yerelde `.env` olarak kopyalanabilir;
gerçek anahtarları veya hesap dosyalarını commit etmeyin.

Daha ayrıntılı temiz makine akışı için
[ikinci bilgisayarda geliştirme rehberine](docs/SECOND_COMPUTER_DEVELOPMENT.md)
bakın.

## Doğrulama

```powershell
python -B scripts/audit_publish.py --history
python -B scripts/check_python_syntax.py
python -B scripts/check_gui_javascript.py
python -B scripts/run_safe_tests.py
```

31 Ekim 2026 tarihli yerel kaynak ağacında **661 regresyon testi** geçti ve
yayın denetimi bulgu üretmedi. GitHub Actions aynı güvenli testleri temiz bir
Windows ortamında tekrar çalıştırır. Testlerde model sağlayıcıları mock edilir;
başarı gerçek model hesabı, UAC, GUI veya oyun kabulü anlamına gelmez.

REA isteğe bağlıdır. Yerel kullanıcı klasörüne sabitlenmiş REA 6.8.0 kurulumu:

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_rea_tool.py
```

Bu komut global npm/PATH veya ajan kayıtlarını değiştirmez. REA olmadan normal
sohbet ve diğer ajan bağlantıları çalışmaya devam eder.

## Paketleme

```powershell
.\.venv\Scripts\python.exe -B build.py --require-brand
```

Derleme benzersiz bir staging dizininde yapılır ve mevcut `dist/` klasörünü
değiştirmez. Kişisel verisiz yeni bilgisayar paketi ayrıca hazırlanmalıdır:

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_distribution.py `
  "<staging>\dist\Quartz" "<boş-hedef>\Quartz"
```

`--deploy` yalnız kapalı yerel Quartz üzerinde test, paket eşleşmesi, veri hash
kontrolü ve geri alınabilir dizin değişimiyle kullanılmalıdır. Derlenmiş EXE ve
kişisel dağıtımlar Git'e eklenmez.

## Proje yapısı

- `gui.py` — ana sohbet, izin kartları ve WebView arayüzü
- `core/agent_chat.py`, `core/message_intent.py` — sohbet/görev ayrımı
- `core/natural_desktop.py`, `core/desktop_*` — görev kapsamlı bilgisayar kontrolü
- `core/application_knowledge.py`, `core/rea_adapter.py` — sınırlı uygulama öğrenmesi
- `core/elevation.py` — WinError 740 ve uygulamaya özel UAC akışı
- `core/warband_workspace.py` — korumalı Universal Modder adaptörü
- `tests/` — çevrimdışı kaynak regresyonları
- `docs/` — mimari kararlar, kabul kapsamları ve geçmiş teknik raporlar

## Katkı ve güvenlik bildirimi

Değişiklik göndermeden önce [CONTRIBUTING.md](CONTRIBUTING.md) içindeki test ve
gizlilik kontrollerini uygulayın. Bir güvenlik açığını public issue olarak
paylaşmadan önce [SECURITY.md](SECURITY.md) içindeki özel bildirim yolunu kullanın.

## Lisans

Bu proje için henüz bir açık kaynak lisansı seçilmemiştir. Kaynakların public
olarak görülebilmesi; kopyalama, değiştirme veya yeniden dağıtım izni vermez.
Ayrıntılar [LICENSE](LICENSE) dosyasındadır. `assets/bin/` içindeki Squad
yardımcısının MIT lisansı ve provenance kaydı kendisine aittir.
