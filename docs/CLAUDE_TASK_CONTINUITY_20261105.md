# Görev sürekliliği: Durdur'a kadar çalışma (5 Kasım 2026)

Dal: `claude/task-continuity-20261105`, taban `92751a3` (yerel `main`).
Kullanıcı isteği: ana sohbetteki görev, kullanıcı Durdur'a basana kadar sürsün.

## Kaldırılan sınırlar (ana sohbet görevi)

- Görev süresi: normalde 15 dakika, ASTER profilinde 30 dakika. `expires_at` artık `None`.
- Oturum süresi: 30 dakikalık giriş kiralaması artık görev canlıyken `_watch` tarafından yenilenir.
- Eylem bütçesi: oturum başına 100 eylem sürekli oturumda uygulanmaz.
- Antigravity tur süresi: 15 dakikadan 1440 dakikaya çıktı. Bu kod yolunda Codex'e süre verilmiyor.

## Korunanlar

- Durdur, UAC, taze gözlem, pencere kimliği, tek operatör ve kilit ekranı denetimleri değişmedi.
- Bearer yine kısa ömürlüdür: sahibi yenilemezse en geç 30 dakikada düşer. `renew()` bitmiş oturumu
  canlandırmaz ve yeni yetki vermez.
- Warband oyun penceresi sınırlı, süreksiz oturumda kalır (30 dakika, 100 eylem). Süre artık görev
  başlangıcından değil, oturum izninden sayılır.
- Kullanıcının süre seçtiği onaylı pencere/log görevi (`chat_coordination`, 30–900 saniye) değişmedi.

## Yeni takılma denetimi

- `desktop_act`: aynı eylem aynı ekranda 8 kez çalışır, sonraki 3 deneme girdi göndermeden reddedilir,
  12. denemede görev `blocked: stalled` ile biter. `wait` sayılmaz ve seriyi bozmaz.
- `jarvis_*` girdileri: ekran karşılaştırması olmadığı için sınır gevşektir; 40 özdeş çağrı çalışır,
  sonrakiler reddedilir, 45. çağrıda görev durdurulmak üzere işaretlenir. Metin saklanmaz, yalnız özet tutulur.

## Bilerek kalan sınırlar

- Yanıtsız izin kartı 10 dakikada görevi bitirir (`permission expired`). Ayrı bir ürün kararı gerektirir.
- Tek bir Antigravity turu 24 saatte zaman aşımına uğrar.
- Ajan turunu bitirince görev biter. Hedef pencere kapanır veya süreci değişirse oturum kapanır.
- Yalnız `wait` veya salt okunur çağrılarla dönen ajan denetime takılmaz: girdi göndermez ama kota harcar.

## Integration request

`core/natural_desktop.py`, `core/task_outcome.py`, `tests/test_natural_desktop.py` Codex sahipliğindedir;
`core/desktop_broker.py` ve testi manifestte sahipsizdir. Kullanıcının isteğiyle bu dalda değişti, birleştirmeden
önce Codex incelemesi gerekir.

## Kanıt

Seviye TESTED; BUILT ve LIVE VERIFIED değil. Sayılar teslim mesajında yazılır. Gerçek CLI'nin `--print-timeout 1440m`
değerini kabul ettiği ve uzun gerçek görev henüz denenmedi.
