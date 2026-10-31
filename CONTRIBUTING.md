# Quartz'a katkı

Quartz şu anda geliştirme önizlemesidir. Issue ve pull request açmadan önce
değişikliğin mevcut güvenlik sınırlarını koruduğundan emin olun.

## Yerel hazırlık

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Küçük, tek amaçlı bir dal kullanın. ASTER/Warband varlıklarını, kullanıcı
kayıtlarını veya Universal Modder kurulumunu Quartz reposuna eklemeyin.

## Zorunlu kontroller

```powershell
python -B scripts/check_gui_javascript.py
python -B scripts/check_python_syntax.py
python -B scripts/run_safe_tests.py
git add <amaçlanan-dosyalar>
python -B scripts/audit_publish.py --staged --history
git diff --cached --check
```

Kaynak testleri canlı masaüstü kabulü değildir. Fare/klavye, UAC, sağlayıcı
hesabı veya oyun davranışı değiştiren bir PR; test edilen gerçek kapsamı ve
test edilmemiş sınırları açıklamalıdır.

## Gönderilmemesi gerekenler

- `.env`, API anahtarları, tokenlar ve OAuth/CLI oturumları
- Sohbet geçmişleri, kullanıcı hafızası ve proje listeleri
- Ekran görüntüleri, çalışma logları ve görev kanıtları
- `dist/`, `build/`, WebView profilleri ve paketlenmiş EXE'ler
- Oyun kayıtları, özel proje varlıkları ve üçüncü taraf kapalı kaynak dosyalar

Bir test fixture'ı gerçek anahtar biçimini taklit etmek zorundaysa gerçek bir
değer kullanmayın. Güvenlik açığı ayrıntılarını public issue veya PR'a koymayın;
[SECURITY.md](SECURITY.md) yolunu izleyin.

## Lisans notu

Repo henüz açık kaynak lisansına sahip değildir. Bir katkının kabul edilmesi,
Quartz'ın veya başka kodların yeniden dağıtım haklarını otomatik olarak
değiştirmez. Lisans koşulları proje sahibi tarafından ayrıca belirlenir.
