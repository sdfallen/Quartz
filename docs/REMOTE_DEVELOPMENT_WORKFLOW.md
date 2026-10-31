# Quartz uzak geliştirme ve yerel kabul akışı

1. `main` ve `CLAUDE.md` ile sahiplik manifestini oku. Koordinasyon baseline'ından
   kendi branch'ini ayrı clone/worktree'de oluştur.
2. Yalnız sahibi olduğun dosyalarda çalış. Diğer alanlarda bulguyu ve minimum
   integration request'i raporla. Sahiplik listesi açık izindir; genel yetki değildir.
3. Göreve başlamadan commit/checkpoint al. Kullanıcı verisi veya runtime klasörünü
   Git'e taşıma. Değişiklikler küçük ve incelenebilir olmalı.
4. Hedefli test, tam güvenli regresyon, Python/JS ve yayın denetimlerini çalıştır.
   Ortamın çalıştıramadığı kontrolü NOT TESTED olarak yaz.
5. Kendi branch'ini gönderip PR aç. PR; problem, değişen dosyalar, sözleşmeler,
   gerçek test sonucu ve canlı kabul ihtiyacını içermeli. `main`e doğrudan yazma.
6. Codex değişiklikleri inceler. Çakışan API/paketleme ihtiyaçları sahiplerle
   koordine edilir. Her PR için bağımsız inceleme ve geçerli CI sonucu aranır.
7. Birleştirilmiş kaynakta tam testler çalıştırılır. Staging paket oluşturulur;
   mevcut kurulu uygulama ve kişisel dosyalar bu aşamada değişmez.
8. Yerel dağıtım gerekliyse aktif kullanıcı görevleri kontrol edilir; kullanıcı
   verisi hash manifesti, geri alınabilir yedek ve paket doğrulaması hazırlanır.
   Kurulu uygulama güncellemesi kaynak PR kabulünden ayrı bir adımdır.
9. Gerçek Windows'ta etki alanına uygun gözlem/eylem/yeniden gözlem kabulü yapılır.
   Kullanıcı oturumu ve UAC gibi gerekli insan aşamaları ayrıca belirtilir.

## Kanıt seviyeleri

| Seviye | Ne kanıtlar? |
|---|---|
| SOURCE/STATIC | Kaynak ve sözleşme incelemesi |
| TESTED | Adı/komutu ve sonucu kayıtlı test |
| BUILT | Belirtilen SHA'dan gerçekten oluşturulmuş paket |
| LIVE VERIFIED | Belirtilen paket, oturum ve uygulamada gözlenen gerçek sonuç |

CI yeşili yalnız koşulan job'ın kapsamını doğrular. Testlerin çalıştırılma adedi
dinamiktir. Erişilebilirlik verisi görsel QA'nın, model yanıtı sonuç kanıtının
yerine geçmez.

## PR teslimi

- İncelenen baseline SHA ve son commit.
- Değiştirilen sahipli dosyalar.
- Test komutları ve gerçek sonuçları.
- Güvenlik, kullanıcı verisi, kaynak/paket etkisi.
- Integration request ve uygulanmadan önceki engeller.
- NOT TESTED / BLOCKED alanları ve yerel kabul adımları.

Özel güvenlik bulguları public PR'a ayrıntılı exploit veya gerçek veriyle yazılmaz;
`SECURITY.md` izlenir. ASTER resmen rafa kaldırılmıştır.
