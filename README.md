<p align="center"><img src="assets/branding/spes-mark.png" width="96" alt="SpeS logosu: ufuktan doğan güneş"></p>

# SpeS Workspace

[![SpeS source checks](https://github.com/sdfallen/Quartz/actions/workflows/tests.yml/badge.svg)](https://github.com/sdfallen/Quartz/actions/workflows/tests.yml)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-4b8bbe)](#gereksinimler)
[![Python](https://img.shields.io/badge/Python-3.13-3776ab)](#geli%C5%9Ftirici-kurulumu)
[![License](https://img.shields.io/badge/license-source--available-lightgrey)](#lisans)

**SpeS**, Claude Code, Codex ve Antigravity CLI ajanlarını tek bir Windows
masaüstü uygulamasında, tek bir sohbetten birlikte çalıştıran yerel bir
geliştirme asistanıdır. Adı Latince *spes* (umut) kelimesinden gelir; eski adı
**Quartz**'tı. Sakin, odaklı bir çalışma masası olarak tasarlanmıştır: tek ana
sohbet, ekip şeridi ve sağda sekmeli bir iş paneli.

> **Geliştirme önizlemesi:** Bu depo kaynak geliştirme içindir. Hazır bir
> son kullanıcı sürümü veya destek garantisi sunmaz. Gerçek masaüstü kabul
> testleri, kaynak testlerinden ayrı değerlendirilir.

## Ekip

| Ad | Ajan | Rol |
| --- | --- | --- |
| **Fatum** | Claude Code CLI | Ana geliştirici ve lider: planı yazar, kararı verir, işi kuran tek yazıcıdır |
| **Fides** | Codex CLI | Güvenilir denetçi: kabul kontrollerini belirler, bitişi kanıtla denetler |
| **Eos** | Antigravity CLI | Erken gören: riskleri ve gözden kaçan alternatifleri ortaya koyar |

Adlar yalnızca bir üslup ve bakış açısıdır; hiçbir yetki vermez.

## Neler sunuyor?

| Alan | Mevcut durum |
| --- | --- |
| Tek sohbetten görev ve normal konuşma | Mesaj niyeti araç kullanımından önce sınıflandırılır |
| **Birlikte** (ekip modu) | Plan → paralel eleştiri → karar → inşa (tek yazıcı) → salt okunur kontrol → kapanış |
| Tek ajanla çalışma | Ekip şeridinden Fatum, Fides veya Eos tek başına seçilebilir; model ve çaba ayarı kartın yanında |
| İş paneli | **Önizleme**: bu bilgisayarda çalışan web uygulamasını (yalnız localhost) gösterir. **Değişiklikler** ve **Kontroller**: yalnız SpeS'in kendi gözlediği kanıt (`host_evidence`); ajanın "değiştirdim" demesi listeye girmez |
| Limit göstergesi | Ajanların 5 saatlik ve haftalık kullanım oranları (CLI veriyorsa) |
| Proje sınırı | Ajanlar seçilen proje klasörüyle sınırlı çalışır |
| Masaüstü gözlemi ve kontrolü | Görev ve pencere kapsamlı izin, kimlik kontrolü, Stop ve taze gözlem korumalarıyla |
| Uygulama öğrenmesi | Onaylı EXE üzerinde REA destekli sınırlı statik inceleme ve yerel, hash bağlı bilgi deposu |
| Yönetici isteyen uygulamalar | WinError 740 için uygulamaya özel UAC isteği; SpeS kendiliğinden yükseltilmez |
| Öz teşhis ve kaynak onarımı | Salt okunur teşhis; onarım yalnız doğrulanmış referans, önizleme, kullanıcı onayı ve yedekle |
| Görünüm | Koyu (varsayılan), açık ve sistem teması; dört vurgu rengi (umut yeşili, şafak pembesi, lavanta, kül) |

Warband / ASTER çalışması resmen rafa kaldırılmıştır; eski adaptör kodu yalnız
tarihsel olarak durur ve yeni görev başlatmaz.

REA bulguları bir uygulamanın iç kodunu veya bütün çalışma biçimini öğrenmiş
olduğu anlamına gelmez. Statik dosya kanıtı, canlı ekran gözlemi ve gerçek
işlev testi ayrı kanıt düzeyleridir.

## Ad değişikliği hakkında

Kullanıcıya görünen her yer (pencere başlığı, logo, arayüz, ajan adları,
kurulum etiketleri) SpeS'tir. Kayıtlı veriyi kaybetmemek için bazı teknik adlar
bilerek korunmuştur: `Quartz.exe` ve `dist/Quartz` paket yolu,
`%LOCALAPPDATA%\Quartz` veri klasörü, `quartz_*.json` veri dosyaları, `QUARTZ_*`
ortam değişkenleri ve bu GitHub deposunun adı. Bunlar ayrı, geri alınabilir bir
taşıma adımıyla değiştirilecektir.

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
.\.venv\Scripts\python.exe quartz_entry.py   # SpeS'i başlatır
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

Güvenli test paketi her PR'da GitHub Actions üzerinde temiz bir Windows
ortamında yeniden çalışır; çalıştırılan test sayısı koşu çıktısında yazar. Testlerde model sağlayıcıları mock edilir;
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
  "<staging>\dist\Quartz" "<boş-hedef>\SpeS"
```

`--deploy` yalnız kapalı yerel SpeS üzerinde test, paket eşleşmesi, veri hash
kontrolü ve geri alınabilir dizin değişimiyle kullanılmalıdır. Derlenmiş EXE ve
kişisel dağıtımlar Git'e eklenmez.

## Proje yapısı

- `gui.py`, `ui/` — ana sohbet, ekip şeridi, iş paneli ve WebView arayüzü
- `ui/styles.py`, `assets/workspace.css` — SpeS tasarım belirteçleri ve bileşen stilleri
- `scripts/build_brand_assets.py` — logo geometrisi: SVG, PNG ve ICO tek kaynaktan
- `core/team_turn.py`, `core/agent_character.py` — Birlikte ekip turu ve ajan kişilikleri
- `core/claude_runtime.py`, `core/codex_runtime.py`, `core/antigravity_runtime.py` — CLI ajan bağlantıları
- `core/agent_chat.py`, `core/message_intent.py` — sohbet/görev ayrımı
- `core/natural_desktop.py`, `core/desktop_*` — görev kapsamlı bilgisayar kontrolü
- `core/application_knowledge.py`, `core/rea_adapter.py` — sınırlı uygulama öğrenmesi
- `core/elevation.py` — WinError 740 ve uygulamaya özel UAC akışı
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
