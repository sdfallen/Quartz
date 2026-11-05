# Dalga 2 — Türkçe anlama

Claude'un önceden etiketlenmiş 78 satırı değiştirilmeden test fixture'ına
alındı. Başlangıç: 70/78; son: 78/78. Sohbetten desktop'a kritik yanlış
yönlendirme: 1 → 0. Bu seed-set sonucu, sınırsız doğal dil doğruluğu değildir.

Genel kurallar: niteliksiz son “ama/fakat/ancak … gerek yok/vazgeçtim/boşver”
isteği geri çeker; farklı nesneye bağlı istisna önceki eylemi iptal etmez.
Eylem eşleştirmesi Türkçe klavye karakterlerini katlayabilir. Uygulama adları
tek tek eklenmez; isim + nesne eki + aç/başlat/kapat yapısı kullanılır. Pencere
büyüt/küçült ve onayla devam kalıpları desteklenir. Hiçbiri yetki vermez.

Eksik sekiz örnek: c23, t10, t11, d09, d10, d11, d18, k04. Tutulan ek negatif
örnekler, açıklama soruları ve başka nesneye bağlı olumsuzluk testtedir.

Komut: `python -X utf8 -B scripts/run_safe_tests.py tests.test_wave2_intent_corpus
tests.test_message_intent tests.test_desktop_task_ui`.
TESTED: 36 test / 0 skip PASS; corpus testinin içinde 78 ayrı alt vaka.
İlk ek karşı örnek Krita'yı için kaynaştırma eki eksiğini buldu; düzeltilip
yeniden koşuldu. BUILT / LIVE: yok. Kullanıcı sohbeti/ekran kanıtı depoya konmadı.
