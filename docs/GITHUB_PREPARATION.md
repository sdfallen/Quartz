# Quartz private repo hazırlığı — 24 Ekim 2026

Hedef: GitHub üzerinde `Quartz`, **private**.

## Koruma

Kaynak değiştirilmeden önce proje checkpoint'i alındı:
`C:/Users/LENAVO/.codex/backups/quartz-github-preparation-20261024/agent-1792871704-971cb30247204921a18ee928b78a88c8.zip`.

Önceki `master` ve checkpoint referansları yerelde korunuyor. Eski HEAD
geçmişinde `quartz_conversations.json` bulunduğundan bu geçmiş yayınlanmayacak.
Yeni başlangıç commit'i `4be5b5a` yalnız denetlenmiş güncel kaynak ağacını
içerir. Yayın dalı `codex/github-private-ready`; gönderim hedefi `HEAD:main`
olmalıdır. `--mirror` / `--all` kullanılmamalıdır.

Kullanıcı verileri, anahtarlar, `labs/`, ekran kayıtları, loglar, yerel
veritabanları ve EXE çıktıları Git dışında bırakıldı. Hiçbiri silinmedi.
Warband, kayıtlar ve çalışan Quartz paketi değiştirilmedi.

## Hazırlananlar

- README, boş `.env.example`, gözlenmiş bağımlılık sürümleri.
- Windows/Python 3.13 kaynak testi için GitHub Actions tanımı.
- Index ve gönderilecek dalın geçmişi için pasif yayın denetimi.
- Denetim için beş regresyon testi.
- Temiz klonda kişisel `.env` olmadan test bootstrap düzeltmesi.

İlk temiz klon testi eksik Vision API anahtarı yüzünden 26 import/test hatası
verdi; önceki yerel ortam bu bağımlılığı gizliyordu. Yalnız güvenli test
çalıştırıcı değiştirildi: gerçek `.env` yüklenmiyor, test istemcileri sahte
anahtarla kuruluyor. Bu düzeltme gerçek model kabulü değildir.

CI tanımı eklendi; uzak GitHub Actions koşusu henüz çalıştırılmadı. Yeni bir
Python ortamına bağımlılık kurma testi de henüz yapılmadı; temiz Git klonu
mevcut Python ortamıyla test ediliyor.

## Uzak repo durumu

Hazırlık sırasında GitHub CLI veya kayıtlı GitHub hesabı bulunmadı; GitHub
entegrasyonu henüz bağlı değildi. Uzak repo oluşturulmuş veya dosyalar
yüklenmiş sayılmaz. Hesap bağlantısından sonra özel repo oluşturulmalı,
yalnız yayın dalı gönderilmeli ve API ile görünürlük/commit doğrulanmalıdır.
