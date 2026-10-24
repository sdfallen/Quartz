# Quartz güvenilirlik çekirdeği — 25 Ekim 2026

## Hedef mimari

Ana sohbet görev giriş noktasıdır. UI gözlemler/komutlar gönderir; görev sahibi
durumu yönetir, runtime yalnız model sürecini, broker yalnız izinli OS girdisini,
kanıt katmanı yalnız gözlenen sonucu temsil eder. Birinin başarısı ötekini
otomatik başarılı yapmaz. Yeni bir plugin/registry/dağıtık framework kurulmaz.

Sınırlar:

1. **Hızlı okuma modeli:** UI durum okuması CLI/ağ beklemez; single-flight arka
   plan yenilemesi kullanır. Bilinmeyen, eski ve hatalı durumlar açık gösterilir.
2. **Tur sahipliği:** iptal ve geç callback aynı tur kimliğine bağlıdır. Terminal
   durum sonradan değiştirilmez; yeni tur eski cleanup sonucundan etkilenmez.
3. **Kesin kapanış:** token/izin iptali önce; her kaynak temizliği ayrı denenir.
   Bir hatalı runtime diğerlerinin kapanmasını veya kanıt kaydını atlatmaz.
4. **İki eksenli sonuç:** süreç tamamlandı bilgisi, hedef doğrulaması değildir.
   Görülen tek UI kriteri bütün görevin kabulü olarak sunulmaz.

## Bu dilimin kabulü

- Yavaş/başarısız durum kaynağı varken sohbet/geçmiş okunabilir.
- Aynı anda tekrarlanan poll tek arka plan kontrolü üretir.
- İptal sırasında ikinci tur başlatılamaz; iptal bittiğinde yeni tur mümkündür.
- Geç eski tur callback'i yeni turun ilerleme/terminal durumunu değiştiremez.
- Cleanup hatasında diğer kaynaklar kapatılır, durum ve hata kanıtı korunur.
- Mesaj ayrımı, yazma checkpoint'i, tek operatör, model seçimleri ve mevcut
  kullanıcı verileri korunur.
- SOURCE, BUILT ve LIVE sonuçları ayrı raporlanır.

## Çalışma paylaşımı

Codex üretim kodu ve `tests/test_reliability_*.py` alanını yönetir.
Antigravity yalnız `docs/reliability/antigravity/` ve
`tests/reliability_antigravity/` alanında bağımsız inceleme/test yapar.
Antigravity dosyaları incelenmeden değiştirilmeyecek veya commit'e alınmayacak.

## Koruma

Başlangıç checkpoint'i:
`C:/Users/LENAVO/.codex/backups/quartz-reliability-architecture-20261025/agent-1792881003-e8c562d728fa41d7aca0459e5647090f.zip`.
Başlangıç kaynak commit'i `36a2d9e`. ASTER/Warband ve kayıtlar kapsam dışı.
Çalışan Quartz görevi kontrol edilmeden kapatılmayacak. Paket değişikliği ayrı
staging ve veri hash denetiminden sonra yapılacak.
