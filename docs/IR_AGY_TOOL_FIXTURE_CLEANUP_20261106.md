# IR-AGY-TOOL-CLEANUP-02 — mevcut Windows fixture temizliği

Son kaynak `d23fc0e` tam suite'inde tek hata:
`test_registered_search_worker.RegisteredSearchWorker.test_no_match_is_real_exit_one_with_empty_output_and_not_fabricated_matches`.
1367 vaka / error1 / skip2; gerçek arama exit1 ve boş çıktı assert'leri geçti,
sonra unittest TemporaryDirectory cleanup WinError5 verdi.

Yol: `<private-temp>/investigations/workspaces/tool-…/run_…/%SystemDrive%/ProgramData/Microsoft/Windows/Caches/cversions.2.db`.
Metadata denetimi: dosya 16384 byte, tüm bileşenler reparse=false/symlink=false,
çözülmüş yol hâlâ o testin özel Temp kökünde. Windows'un gerçek ProgramData'sı
üzerinde silme/izin müdahalesi yapılmadı. Artık klasör zorla kaldırılmadı.

Aynı test aynı kaynakta tek başına yeniden koşuldu: 1 test / PASS, 4.530 s.
Bu tekrar kalıcı kök neden teşhisi veya fix değildir. Önceki tam suite `e0f25e3`
1366 / skip2 PASS idi; yeni üretim değişikliği yalnız NaturalDesktop Stop
sınırındadır, Workbench ve registered worker dosyaları değiştirilmedi.

Hipotez: `core/tool_workbench/execution.py:58` `_sanitize_environment`, Windows
Store Python fixture'ının USERPROFILE/TEMP yönlendirmesi ve Windows cache
oluşumu etkileşebilir. SYSTEMDRIVE allowlist'te yok; **nedeni kanıtlanmadı**.
Kilit sahibini tahmin ederek süreç öldürme veya izin genişletme yapılmamalı.

Antigravity'den istek: özel fixture'da environment/oluşan dosya/cleanup receipt
izini incele. Değişiklik gerekiyorsa kendi dalında minimal fix + negatif
regresyon; Codex incelemeden main'e alınmayacak. Testi skip/ignore_errors ile
yeşile çevirme. Kalan workspace varsa cleanup confirmed iddiasını doğrula.

Kanıtlar özel Dalga 2 dizininde: `wave2-final-source-suite.log`,
`registered-search-recheck.log`. Tam suite tekrar sonucu final raporda ayrı
yazılacak; başarısız koşu silinmez. Bu dosya bir kaynak değişikliği veya LIVE
Quartz kusuru kabulü değildir.
