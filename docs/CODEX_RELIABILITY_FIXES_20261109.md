# Güvenilirlik düzeltmeleri — 9 Kasım 2026

Dal: codex/reliability-fixes-20261109. Üretim kaynak son commit: 86e806f.

Commitler: f5b7f1c (alt-adım görev devamı, Stop kanıtı), 6bf60dd (runtime kanıt aktarımı ve eski metadata), 86e806f (proje kaldırma rollback, reviewer kanıtı).

Metin eşleşmesi artık kalan görevleri bırakma talimatı üretmiyor. Completed özeti yalnız gözlenen metni bildiriyor. Stop receipt açıkça onaylanmadıkça sınav geçmiyor. Komut kayıtları yapılandırılmış ve eski metadata biçimlerinde okunuyor; bozuk biçim başarı üretmiyor. Runtime command_results, unauthorized_write_detected, unauthorized_files_changed ve error_events mevcutsa kopyalanıyor; eksik gözlem için varsayılan başarı üretilmiyor. Writer receipt ve iki sağlayıcının sohbet güncellemelerine bağlantı eklendi.

Reviewer için açık unauthorized_write_detected=false kanıtı gerekiyor; eksik receipt başarılı sayılmıyor. Proje kaydı yazma hatasında registry belleği ve sohbet kaydı geri alınıyor. Disposable fixture yeniden yükleme testi özgün sohbetin korunduğunu doğruluyor. Bu iki dosyalı işlem ani süreç/elektrik kesintisine karşı atomik değildir; rollback yazması da başarısız olursa hata yayılır, mevcut sohbet kurtarma kopyası kalır.

## Doğrulama

- 37 hedefli test: PASS.
- Önceki dilimde 31 oracle/görev ve 25 sohbet/servis testi: PASS.
- Sabit 86e806f üzerinde tam güvenli suite: 1576 vaka, 1574 başarılı, 2 atlandı, 219.928 saniye. Fixture sınıfı importundan gelen tekrar keşif dahil gerçek runner sayısıdır; benzersiz senaryo sayısı değildir.
- Python syntax: 339 dosya OK. Embedded JS exit0. Yayın denetimi PASS, bulgu0.
- İlk tam koşu eski test beklentisini belleğe aldığı için tek failure içeriyordu. Güncel commit üzerinde yeniden tam koşu temiz; önceki log silinmedi.
- Loglar bu worktree'nin ignored build/ klasöründe: final-focused.log, final-full-suite.log, final-full-suite-confirmed.log.

SOURCE / TESTED tamamlandı. Yeni BUILT / LIVE VERIFIED yok. Main'e birleştirme, paket kurma ve GitHub gönderimi yapılmadı. Kurulu uygulama bu düzeltmeleri henüz içermiyor. İlgili gerçek paketli görev ve hata-kabul testi sonraki dağıtım kapısıdır.
