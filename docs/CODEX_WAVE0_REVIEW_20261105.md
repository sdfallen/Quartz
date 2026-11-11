# Dalga 0 bağımsız inceleme — 5 Kasım 2026

İnceleyen: Codex. Kendi worktree/dalı: `quartz-wave0-20261105`,
`codex/wave0-review-20261105`. Ortak checkout kirli (`CLAUDE.md`, kullanıcı
teslimleri); dalı değiştirilmedi veya resetlenmedi. Paket kurulmadı, uygulama
açılmadı, gerçek sağlayıcı/masaüstü kabulü çalıştırılmadı, GitHub'a gönderilmedi.

## Karar

| Teslim | Karar | Kanıt sınırı |
|---|---|---|
| `92751a3` UI + Antigravity polish | ACCEPT — SOURCE/TESTED | Güvenlik kararları backend'de kalıyor; GUI/package LIVE kabulü bu inceleme değil |
| `643b51f` task continuity | REJECT — R1 kapanana kadar main'e alınmaz | Pozitif testler geçse de yenileme sahibi bağlı değil |

Kurulu EXE `d3e534ae69f171d83df72225743d0e6530701cd256aaea84f4744f1cfe7b815b`.
643b51f dağıtım makbuzuyla SHA eşleşiyor. 16 ilgili paket modülünün bytecode'u
kaynakla eşleşiyor. Bu pasif arşiv incelemesidir, BUILT/LIVE testi değildir.
Kurulu paket de R1'i içeriyor; kullanıcı yasağı gereği değiştirilmedi.

## R1 — P2: Eski sahip yeni operatörün kiralamasını yenileyebiliyor

- `643b51f:core/desktop_broker.py:137–144`: `renew()` hangi oturum/sahip için
  çağrıldığını almıyor; mevcut continuous session'ın süresini yeniliyor.
- `643b51f:core/natural_desktop.py:1118–1119`: watchdog yalnız `self.connection`
  varlığını kontrol ediyor, o bağlantının token/session kimliğini geçirmiyor.
- Tekrar: A'nın 30 saniyelik oturumu biter; B yeni 30 saniyelik oturum alır;
  A'nın elde tuttuğu heartbeat callback'i çalışır. Beklenen `False`, gerçek
  `True`; B'nin expiry değeri **61 → 1831**. İki token farklı. Bu dış saldırı
  veya gerçek masaüstü ele geçirme kanıtı değil, yerel sahiplik sözleşmesi kusuru.
- Komut: `python -X utf8 -B <kanıt>/renewal_owner_probe.py
  C:\Users\LENAVO\.codex\worktrees\quartz-task-continuity-20261105`.
  Gerçek çıktı: `{"expected": false, "actual": true, "before": 61, "after": 1831}`;
  ardından `AssertionError: Stale owner renewed the replacement session` (exit1).
- Kanıt: `renewal-owner-assertion.log`, `renewal-owner-reproduction.json`.

### Integration request — Claude (desktop broker sahibi)

`renew` çağrısını onayla üretilen mevcut token/session kimliğine bağla; eşleşme
yoksa expiry değiştirmeden reddet. NaturalDesktopTask yalnız kendi connection
kimliğini geçirsin (Codex dosyası için bu dar çağrı değişimi koordine edilmeli).
Testler: expired A → B → stale A yenileyemez; B kendi kiralamasını yenileyebilir;
Stop sonrası yenileme yok; bounded session'a continuous yetki verilemez; kimlik,
taze snapshot ve UAC guard'ları korunur. Dosya sahibi atlanarak üretim yaması
yapılmadı. Düzeltme sonrası yeniden bağımsız inceleme gerekir.

## Diğer bulgular / korunan sınırlar

- `643b51f:core/desktop_broker.py:166–177`: Stop session'ı cleanup beklemeden
  temizliyor. `:186+` kimlik/kilit denetimi; `:331–340` snapshot tüketimi ve
  15 saniye tazelik korunuyor. Continuous yalnız 100 eylem sayacını kaldırıyor.
- `643b51f:core/natural_desktop.py:639–658`: 740/UAC istek kimliği ve generation
  denetimi var. İzin kartının 10 dakikada bitmesi bilinen açık ürün davranışı;
  planın Dalga 2 duraklatma kararı burada uygulanmadı.
- `:1110+`: ajan tamamlanınca görev biter; sınırsız otomatik tur yeniden başlatma
  eklenmemiş. Yalnız salt okunur/wait döngüsü ve değişen ekran tekrarları guard'ı
  aşabilir; bu mekanizma genel kota veya ilerleme garantisi değildir.
- 1440m kod parametresi TESTED; gerçek CLI kabulü ve iki saatlik görev NOT TESTED.
  Kullanıcının Gemini'ye verdiği gerçek çağrı bu incelemede tekrarlanmadı.
- `92751a3:ui/js_workspace.py:16–31`: tercih kaydı hatası artık görünür.
  `ui/js_messages.py:218–238`: yeni biçimlendirme textContent tabanlı, link span
  olarak gösteriliyor; yeni keyfî HTML/URL yürütme yetkisi yok.
  `gui.py:928–938` yeni görünüm API'si allowlist/atomik kayıt kullanıyor.
  Pencere boyut API'leri görev/izin oluşturma yolu değil. Renk/DPI/gerçek Stop
  görünürlüğü SOURCE incelemesinden LIVE kabul edilmiş sayılmadı.

## Komutlar ve ölçümler

Özel kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-wave0-20261105`.

1. İlk hedefli komut yanlış `tests.test_task_outcome` adıyla çalıştı:
   145 vaka, 1 import error; operatör komut hatası, ürün kusuru değil (`targeted.log`).
2. Düzeltilmiş broker/natural/GUI/elevation/identity/runner seçimi:
   168 test OK (`targeted-final.log`).
3. Koşucu son hedefli paketi: 11 test OK (`runner-tests-final.log`).
4. İnceleme tabanı 643b51f + o sıradaki koşucu WIP tam suite:
   1322 test OK, skipped=2, 176.487s (`full-suite.log`).
   Bu koşu commit üstünde koşmuş gibi sunulmuyor; nihai koşucu ayrı tabana
   alınır ve aşağıdaki teslim kaydında yeniden test edilir.
5. Pasif kurulu arşiv karşılaştırması: 16/16 eşleşme (`installed-source-check.json`).

## Koşucu ve kapsam

`TASK_EXAM_RUNNER.md`, katalog ve envanter 24 scripti kapsar. Scriptler AST ile
okundu, gerçek hesap/masaüstü gerektirenler **NOT TESTED** bırakıldı. Bu nedenle
"çalışıyor" yalnız çalıştırılmış adaptör için kullanılabilir; sözdizimi geçerli
scriptleri canlı başarılı saymıyoruz. 4 legacy, 8 yalnız hesap, 6 masaüstü+hesap,
1 yalnız masaüstü, 1 ağ/kurulum, 3 özel fixture, 1 offline ölçüm var.

`accept_response_style.py:43–57`, `accept_desktop_cancellation.py:results` ve
`measure_runtime_efficiency_pyramid.py:134+` sonuçları tek başına process exit
ile görev kabulü sağlamaz. Koşucu oracle olmadan VERIFIED üretmez. Ham log ve
ekranlar repo'ya yazılmaz. Eski canlı scriptlerin ROOT/labs çıkışını ayıracak
adaptörler açık iştir; izin bayrağı tek başına onları çalıştırmaz.

Claude'un 30 görev listesi ve gerçek agent-step ölçümü henüz yok. Örnek smoke
yalnız koşucu altyapısıdır, %90 G1 veya %30 G6 başarısı iddiası değildir.

## Geri alma / main

`main` 92751a3'te bırakıldı; kullanıcı şartındaki "ikisi kabul edilirse" koşulu
sağlanmadı. Ortak checkout ve kurulu pakete geri alma uygulanmadı.
İlk bundle: `pre-wave0.bundle`. Koşucu teslimi reddedilen üretim commit'ini
taşımayan kendi commit'i olarak 92751a3 üzerine sunulur. Yalnız bu commit
geri alınabilir; kaynak/kanıt veya yedekler silinmez. Eski kurulu pakete dönme
ayrı kullanıcı kararıdır, bu görevde dağıtım yapılmaz.
