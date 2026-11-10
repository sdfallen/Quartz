# Claude incelemesi — S4 Squad öz-onarımı (Gemini, `64e7fde`)

İncelenen: `antigravity/wave0-wave1-analysis-20261105` `64e7fde` (main `04ec053` üstünde tek commit).
Gemini'nin hedefli testleri: `tests.test_squad_adapter tests.test_environment_health` → `Ran 22 tests`, OK.

**Karar: REDDEDİLDİ — bir P1 (veri kaybı).** Kök neden analizi (A/B/C) iyi ve kanıtlı; gizli öznitelik
ve kök dosya geri yükleme fikirleri doğru. Silme yolu daraltılmadan main'e alınmamalı.

## P1 — sağlam ama meşgul bir veritabanı "bozuk" sayılıp siliniyor

`_is_db_corrupt()` her `sqlite3.DatabaseError`'da `True` dönüyor. `OperationalError` ("database is locked",
"unable to open database file") bunun alt sınıfı. Başka bir Squad süreci (ajanların `squad send`'i, Quartz'ın
kendi yazımı) o anda yazıyorsa 0,5 sn içinde kilit alınamıyor → "bozuk" → `status()` `_repair_workspace()`
çağırıyor → `messages.db`, `-wal`, `-shm` siliniyor.

`status()` salt okunur bir tanı çağrısı; `multi_agent_service` (3 yer) ve `natural_desktop` bunu sohbet
durumu yoklamasından düzenli çağırıyor. `_DB_LOCK` yalnız süreç içi; dış `squad.exe` süreçlerini dışlamıyor.

Yeniden üretim (`64e7fde`, geçici klasör, 500 mesajlık sağlam DB):

```
healthy, unlocked            -> _is_db_corrupt False
healthy, writer holds lock   -> _is_db_corrupt True
lock released after the check (short-lived squad process exits), then status():
messages.db exists after status(): False
```

Windows'ta yazıcı dosyayı açık tuttuğu sürece silme başarısız oluyor (OSError yutuluyor); ama Squad CLI kısa
ömürlü, kilit kontrol ile silme arasında bırakılınca bütün mesaj geçmişi gidiyor. Ayrıca `_run()` stderr'de
`"no such table"` görünce de onarıma gidiyor; bu bozulma değil, şema/sürüm farkı olabilir.

## İstek (Gemini)

1. Bozukluk yalnız olumlu kanıtla: başlık `SQLite format 3\0` değil **veya** `quick_check` sonucu `ok` değil.
   `OperationalError` (kilitli/meşgul/açılamıyor) → "bilinmiyor", asla bozuk değil. `"no such table"` listeden çıksın.
2. Silme yok: bozuk dosyayı `messages.db.corrupt-<zaman>` olarak taşı (karantina), geri alınabilir kalsın.
3. Onarım `status()`/`initialized`/sağlık yoklamasından yapılmasın; yalnız görev başlatma veya
   `initialize()` gibi açık bir yazma yolunda ve dış süreç yokken (ör. dosya açılabiliyorsa) yapılsın.
4. Negatif testler: (a) başka bağlantı `BEGIN EXCLUSIVE` tutarken `_is_db_corrupt` False/bilinmiyor;
   (b) kontrol ile onarım arasında kilit bırakılsa bile `status()` sonrası DB duruyor; (c) bozuk dosya karantinada.

## Küçük notlar

- P2: `_restore_root_files` init'ten önceki anlık görüntüyü init sonrası geri yazıyor; init sürerken
  kullanıcı/ajan bu dört dosyayı değiştirirse değişiklik geri alınır. Pencere kısa, ama not edilmeli.
- P3: `.git/info/exclude`'a `.squad/` eklemek ve `.squad`'ı gizlemek kullanıcı projesinde kalıcı değişiklik;
  makul, ama Quartz'ın "projeye ne yazdı" kanıtında görünmeli.
- `notion` modu ve `_run_subprocess` TypeError düzeltmeleri (P3 notlarım): kabul.

## Kanıt seviyesi

SOURCE + yerel yeniden üretim. Paket/canlı değerlendirilmedi. Bu commit main'deki paket (`4944f6a`) içinde değil.
