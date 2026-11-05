# P1-1 backend / IR-CLAUDE-APPROVAL-PAUSE-01

Uygulama: `NaturalDesktopTask`, mevcut broker otoritesi korunur. Başka bir
görev motoru/yetki deposu eklenmez. `APPROVAL_PAUSE_DESIGN_20261105.md` artık
başlangıç tasarımıdır; bu not uygulanmış backend kapsamını açıklar.

## Durum ve süreç sözleşmesi

- Gerçek manuel scope/log/UAC kartı → `job.status=awaiting_approval`, `job.pause`
  var. Eski broker token/snapshot revoke; `connection/latest=None`. Önceden
  onaylı pencereye de yeni girdi yok. Full sıradan auto-approve korunur.
- Watcher paused iken lease yenilemez, yeni model turu başlatmaz. Sahip olduğu
  CLI'leri cancel/drain eder. Namespace `(provider, run_id)` ile ayrılır.
  `cancelled` tek başına exit kanıtı değildir: gerçek PID varsa runtime'ın
  `process_exit_confirmed=True`, `cleanup_pending=False` okuması gerekir.
- İzin 600 saniyede eskir; görev terminal olmaz. Önceki limitler büyütülmez.
  Onay süresini uzatmak için model veya polling yetki veremez.
- Geçerli onay task/conversation/request/generation ve fresh identity'ye bağlı.
  Cleanup belirsizse onay tüketilmez, grant yok. Devam yeni broker session ve
  taze observation gerektirir. Eski callback ve token geçersizdir.
- Duraklamada yalnız context/wait/mesaj ve önceden izinli log okuması açık;
  refocus yapan observe dahil desktop ve Jarvis girdi yolları kapalı. Bilinen
  UAC isteğine tekrar launch çağrısı yalnız mevcut isteğin durumunu döndürebilir.
- Kısa native girişler `_effect` ile sınırda serileştirilir. Ağ/uygulama araması
  yapabilen composite controller çağrısı `_controller` ile Stop kilidini tutmaz.
  Aynı anda yalnız bir kontrol çağrısı kabul edilir; o çağrı sürerken yeni
  manuel scope kartı açılmaz, task_wait ile tekrar istenir. Böylece eski uzun
  çağrının yeni kart beklerken devam etmesi önlenir. UAC exception yolunda normal
  launch zaten sonuçlanmıştır; yalnız kullanıcı kartı açılır.
  Sınırdan önce kabul edilmiş native etki geri alınmış sayılmaz ve tekrar
  oynatılmaz. Stop bu çağrının sonucunu doğrulanmış saymaz; inflight receipt
  ayrı kalır. Gerçek GUI Stop gecikmesi henüz ölçülmedi.
- UAC otomasyonu yok. Kullanıcının tek launch onayı Windows yanıtını bekler;
  otomatik yönetici kontrolü sağlamaz. Erken expiry yeni kartı engellemez.
- `task-state.json` atomik, yalnız küçük kimlik/durum metadata'sı; token,
  ekran, hedef EXE veya log içeriği içermez. `paused_contexts()` restart sonrası
  salt okunur bağlam verir; hiçbir grant/model/process otomatik canlanmaz.

## Claude'un yapacağı entegrasyon

1. `gui.py`, izin JS'i: `awaiting_approval` ve `pause.reason` göster. “Onay
   bekleniyor — görev duraklatıldı”; expired ise “Devam için yeni onay gerekli”.
   Durdur her zaman erişilebilir; bu durum başarı/hata rozeti değildir.
2. `pause.cleanup_confirmed` gelene kadar Onay'ı devre dışı göster; erken callback
   backend'de de reddedilir. Yanlış sohbet kartını aktif göreve taşımama.
3. Expired kartın “Yeniden onay hazırla” düğmesi güvenilir kullanıcı olayıyla
   `refresh_permission(old_request_id, conversation_id, confirmed=True)` çağırır.
   Bu **onay vermez**: yeni request/generation döner; kullanıcı yeni kartı ayrıca
   onaylar. Eski karta otomatik retry yok. `natural_approve` mevcut kimlik
   bağlarını ve explicit true şartını korur. Refresh model aracına eklenmez.
4. Restart için `paused_contexts` yalnız kesilmiş görevin bağlamını sunar; yeni
   seçim/onay yapılmadan resume yok. Bugünkü backend işi otomatik restart değildir.
5. Broker sahibi: mevcut `stop` token/snapshot'ı kaldırır, `grant` fresh
   identity/input-session kontrolü yapar; R1 owner-token renewal değişmedi.
   Bu sınırın direct broker ve GUI geçiş testlerini ekle. Broker dosyası bu
   teslimde değiştirilmedi; yeni bir broker permission katmanı gerekmiyor.
6. Canlı tek-operatör kabul: bekleyen kart, uzun bekleme, expired reissue,
   Stop yarışı, UAC, HWND/PID değişimi, dar UI. Paket kurulmadı/GUI açılmadı.

## Test ve değişen beklentiler

Yeni AP testleri: iki saat fake clock'ta terminal olmama, eski token/input ret,
yeni kart/generation/fresh observation, yanlış identity/chat, iki sağlayıcının
aynı run ID'si, belirsiz process cleanup, Stop/replay, private restart bağlamı,
full auto-approve ve deterministik controller/pause bariyeri.

Eski testlerde log kartı beklerken eski grant'in aktif kalması beklentisi,
kullanıcının yeni pause kararı gereği kaldırıldı. Erken onay artık CLI drain'i
bekler; yeni test late eski-exit olayının yeni run'ı bitirmediğini kontrol eder.
Diğer stale/duplicate/Stop/UAC testleri korunmuştur.

Hedefli komut: `python -X utf8 -B scripts/run_safe_tests.py
tests.test_group_partial_outcome tests.test_approval_pause tests.test_natural_desktop
tests.test_permission_continuation_ui tests.test_elevation tests.test_jarvis_regressions
tests.test_agent_chat tests.test_multi_agent_service`: 97 test, 0 skip, PASS.
Son küçük summary/UAC-expiry değişiklikleri final tam suite'te yeniden koşulacak.

Son bağımsız test uzun controller'ın görev kilidini tuttuğunda Stop'un
beklediğini üretti (tek test FAIL). Yukarıdaki composite/primitive ayrımıyla
70 testlik ilgili suite PASS oldu; son tam suite bunu yeniden kapsar. Claude'un
canlı kabulünde ağ bekleyen bir controller sırasında Stop ve manuel scope
isteği de denenmeli. Mevcut controller içindeki önceden kabul edilmiş etkiler
iptal edilmiş gibi gösterilmez; yeni native callback gerekiyorsa input_guard
mevcut broker/Native sınırına bağlanır, yeni bir permission otoritesi kurulmaz.

P0-2 ek kontrolünde ikinci grup turunun ve “devam” turunun ajan hataları da
partial'a bağlandı; NaturalDesktop seçilen ama kullanılamayan ajanı partial
olarak kaydeder. Squad lifecycle completion metni hedef verdict'ini ayrı yazar.
SOURCE/TESTED kapsamıdır; UI, BUILT ve LIVE VERIFIED kabulü değildir.
