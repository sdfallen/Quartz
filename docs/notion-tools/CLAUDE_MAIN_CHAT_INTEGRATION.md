# Doğrulanmış Notion Worker köprüsü — ana sohbet entegrasyonu (Claude)

## Dal ve başlangıç

- **Dal:** `claude/notion-main-chat`.
- **Baseline:** `e9c3ae2` (`codex/notion-tools-integration`). Bu commit yalnız
  yerel depodaydı; ayrı bir clone'da Git nesneleri birebir kuruldu. Commit
  zinciri `4515712` (GitHub) → `9b87486` → … → `e9c3ae2`, toplam 10 commit.
  Entegrasyon worktree'sinin index'inden yazılan ağaç `e9c3ae2^{tree}` ile
  aynı (`b91ac3e`).
- **Git durumu:** Codex worktree'sinde `e9c3ae2` zamanından sonra değişmiş,
  Git'in takip ettiği dosya yok. Takip edilmeyenler: `node_modules`,
  `workers/.../dist`, Git dışı `workers.json`, `quartz_conversations.json`,
  `__pycache__`, `build/`. Hiçbiri silinmedi veya değiştirilmedi. Ortak
  checkout'ta dal değiştirilmedi; çalışma ayrı bir clone'da yapıldı.
- Depo kökünde `AGENTS.md` yok. `workers/quartz-local-tools/AGENTS.md` ise
  Notion iskeletinin genel dosyası; geçerli talimatlar `CLAUDE.md` ve
  `docs/notion-tools/*` olarak okundu.

## Kapsam

Yalnız onaylı, tek kullanımlık, salt okunur test projesi. Her onaylı görev
için yeni bir klasörde yeni bir `fixture.txt` oluşturulur. Genel dosya
taraması, shell, dosya yazma, ekran görüntüsü, Desktop Broker, REA veya Squad
erişimi **eklenmedi**. Taşıma katmanı (`core/notion_worker_bridge.py`: HMAC,
grant/request/result ayrımı, dosya kimliği ve hash, kalıcı SQLite makbuzu)
**değiştirilmedi**; aynen kullanılıyor.

## Değişen dosyalar ve sorumlulukları

| Dosya | Sorumluluk |
|---|---|
| `core/notion_worker_task.py` (yeni) | Sohbet turundan sürülen yaşam döngüsü: niyet tespiti, sohbet içi bekleyen onay, yerel manifest/scope, imzalı grant, tek gönderim, kuyruk izleme, sonuç bildirimi, doğrulama, Stop/timeout/kapanış, yeniden başlatmada eski grant'leri kapatma, `notion_tools` görünümü. CLI sürücüsünün mantığı servis olarak ayrıldı; CLI sürücüsü olduğu gibi kaldı. |
| `core/agent_chat.py` | Notion turu, niyet varsa **ve** araçlar hazırsa servise gider; yoksa bugünkü bulut sohbeti sürer. `cancel_active` önce yerel yetkiyi geri alır. `chat_status` ve `chat_poll` gerçek `notion_tools` döndürür. `decide_notion_tool` eklendi. |
| `core/multi_agent_service.py` | Servisi ihtiyaç anında oluşturan (lazy) `notion_tools`. Kapanışta önce yerel yetki geri alınır. |
| `main.py` | Kimliği doğrulanmış IPC eylemi `notion_tool_decide` (mevcut IPC auth). |
| `gui.py` | `Api.notion_tool_decide`; sohbet içi izin kartı (`syncNotionTools`); `chat_poll` sırasında da güncelleme (aktif tur sırasında kart görünür). |
| `ui/document.py` | Panel Stop ipucu mevcut İptal düğmesini tanıyor; yerel okumayı "Yürüten: Quartz yerel okuyucu · isteyen Notion" diye gösteriyor. |
| `ui/theme.py` | İzin kartına mevcut izin kartlarıyla aynı stil. |
| `scripts/notion_worker_acceptance.py` | Profil başına açık yönetici adımı: `--enable-main-chat` / `--disable-main-chat`. |
| `Quartz.spec` | Lazy import edilen `core.notion_worker_task`, `core.notion_worker_bridge` ve `win32cred` hiddenimports'a eklendi. |
| `tests/test_notion_main_chat_tools.py` (yeni) | 28 yaşam döngüsü, uygunluk, niyet ve bağlantı testi. |
| `tests/test_notion_review_wiring.py` | Yeni `syncNotionTools` yolu ve `chat_poll` bağlantısı için güncellendi. |

## Kullanıcının ana sohbetten izleyeceği akış

1. Notion seçilir ve normal bir mesaj yazılır, örneğin "Test projesindeki
   dosyayı incele". Niyet tespiti bilerek muhafazakâr: test projesi veya
   dosyası (ya da `fixture`) ile okuma/inceleme fiili birlikte geçmeli. Başka
   her şey bugünkü bulut sohbetidir.
2. Araçlar `ready` ise Quartz turu başlatır. Sohbete "izin istiyor" mesajı
   düşer. Görev şeridinin altında Notion paneli "İzin bekleniyor" gösterir,
   sohbette izin kartı açılır: kapsam, okumayı Quartz'ın yaptığı, yazma,
   terminal ve masaüstü erişimi olmadığı yazar.
3. **Bu görev için izin ver** basılınca:
   - Notion oturumu, gerekiyorsa sahipli yeni oturum olarak açılır.
   - Yerel manifest ve scope, tek kullanımlık fixture ve imzalı grant
     oluşturulur.
   - Kullanıcının mesajı ve grant/request kimlikleri Notion'a **bir kez**
     gönderilir.
4. Panel "Yürütülüyor · Yürüten: Quartz yerel okuyucu · isteyen Notion".
   İmzalı istek gelir, `ReadOnlyWorkerBridge` gerçek dosyayı okur, imzalı
   sonucu kuyruğa yazar.
5. "Sonuç doğrulanıyor". Notion'a `quartzReadResult` bildirimi gider. Ajan
   yanıtında dosyadaki rastgele kanıt **ve** SHA-256 geçerse "Tamamlandı ve
   doğrulandı". Geçmezse "dosya okundu, ajan yanıtı doğrulanmadı". Yanıt aynı
   sohbet mesajına yazılır, oturum aynı sohbette saklanır.
6. İptal düğmesi bütün tur boyunca görünür ve kullanılabilir.

## İzin ve Stop yaşam döngüsü

- **Onay** tek kullanımlıktır ve şunlara bağlıdır: güncel pending ID, sohbet,
  süre (120 sn) ve turun hâlâ çalışıyor olması. `confirmed=true` zorunludur.
  Eski ID, yanlış sohbet, ikinci karar, süresi dolmuş onay, durdurulmuş veya
  bitmiş tur onayı reddedilir.
- **Tam Yetki** bu kartı otomatik onaylamaz. Kart `natural_approve` yolunu
  kullanmaz.
- **Ret, timeout ve kapanış** onaydan önce olursa Notion'a istek gitmez ve
  fixture oluşmaz.
- **Stop** (İptal, pencere kapanışı, uygulama kapanışı):
  - Önce yerel yetki geri alınır (`stop_all` → bridge stop, `.stopped`).
  - İşlem sırasında gelen sonuç yayımlanmaz.
  - Ardından uzak oturum için iptal istenir.
  - Mesaj bunları ayrı söyler: "Yerel işlem durduruldu … Notion oturumunun
    durduğu doğrulandı / doğrulanamadı / Notion tarafında çalışan işlem yoktu".
- **Belirsiz gönderim:** `request_submitted` ağ çağrısından önce kaydedilir.
  Bağlantı kopması veya timeout'ta istek tekrarlanmaz.
- **Notion tarafı onay (`requires_action`):** otomatik onaylanmaz; görev
  "engellendi" olarak kapanır ve uzak iptal istenir.
- **Yeniden başlatma:** servis kurulurken bitmemiş fixture manifest'leri
  `.stopped` + `expired` yapılır; eski grant hiçbir zaman otomatik etkinleşmez.
- **Yeni görev:** yeni task_id, scope_ref, request_id, klasör, kanıt ve bridge.
  Önceki görev tamamlanınca `.stopped` olur. Aynı anda tek görev çalışır.

## Uygunluk (`availability`)

`ready` için hepsi gerekir:
- Bu profilde `worker-bridge.json`: `mode=readonly-fixture`, queue,
  credential_target ve runtime ile aynı workspace.
- Açık `main_chat: true`. Mevcut `enabled: false` kararı korunur ve
  `--enable-main-chat` bunu değiştirmez.
- Credential Manager anahtarı bu profilde okunabiliyor.
- Notion bağlantısı arka plan doğrulamasıyla `ready`.

Hiçbir profil verisi veya kimlik bilgisi profiller arasında kopyalanmaz.
CLI pilotunun geçmiş olması normal sohbeti hazır göstermez.

## Testler ve gerçek sonuçlar

Ortam: Linux konteyner, Python 3.13.18, Node 22.23.4, xvfb. **Windows değil.**

| Komut | Baseline `e9c3ae2` | Bu dal |
|---|---|---|
| `check_python_syntax.py` | — | 233 dosya OK |
| `check_gui_javascript.py` | — | exit 0 |
| `run_safe_tests.py` | 781 koştu: 2 fail, 19 error, 17 skip | 809 koştu: 2 fail, 19 error, 17 skip |
| `audit_publish.py --staged --history` | — | findings: [], secrets_printed: false |
| `git diff --cached --check` | — | temiz |
| `test_notion_main_chat_tools` art arda 25 koşu | — | 25/25 OK |

- Fail ve error kümesi baseline ile ad ad aynı (21 test). Hepsinin nedeni
  Windows'a özgü (`tkinter`, `os.startfile`, `msvcrt`, `pythoncom`). Codex'in
  Windows'taki 809 testi bu konteynerde 781 olarak koşuyor.
- Mock bulut ile kapsanan durumlar:
  - onay → gerçek okuma → doğrulama; kanıt modele önceden gönderilmiyor
  - kanıtsız "başardım" doğrulanmış sayılmıyor
  - ret, teyitsiz, yanlış sohbet, eski veya ikinci onay
  - bitmiş tura ve durdurulmuş tura geç onay
  - onay timeout'u
  - yürütme sırasında ve işleme anında Stop
  - uzakta işlem yokken Stop
  - istek timeout'u
  - bağlantı kopması
  - `requires_action`
  - imzasız tur
  - aynı request_id ile değişmiş zarf
  - tekrar gelen kuyruk satırı (yeniden okuma yok)
  - yeni görevde kapsamın taşınmaması
  - yabancı oturum
  - pencere kapanışı
  - yeniden başlatmada fence
  - tek görev sınırı ve sohbet kapsamı
  - uygunluk kapıları
  - niyet
  - sohbet bağlantısı
  - `--enable-main-chat` komutunun `enabled:false`'a saygısı
- **Tarayıcı (mock) kanıtı:** Linux Chromium, gerçek `gui._HTML` ve sahte
  pywebview API ile ölçüldü:
  - Kart göründü; tek tıkta `notion_tool_decide("p-77","c1",true,true)` gitti.
  - Düğmeler devre dışı kaldı, ikinci tıkta çağrı sayısı 1'de kaldı.
  - Tam Yetki açıkken otomatik karar 0.
  - Panel başlıkları: İzin bekleniyor, Yürütülüyor, Tamamlandı ve doğrulandı,
    İptal edildi.
  - Görüntüler ve JSON depoda değil, yerel teslim klasöründe. Bu bir LIVE
    kabul değildir.

## Paketli GUI kabulü

**BLOCKED.** Bu oturumun kullanıcının Windows bilgisayarında komut çalıştırma
(shell), paket derleme veya pencere gözlemleme yeteneği yok; yalnız dosya
okuma ve yazma köprüsü vardı, o da teslim sırasında koptu. Bu nedenle:
- izole profil
- `build.py`
- paketli EXE
- gerçek Worker çağrısı
- canlı Stop

**hiçbiri yapılmadı.** CLI pilotunun v7 kabulü bu entegrasyonun kabulü olarak
sunulmaz.

| Seviye | Durum |
|---|---|
| SOURCE/STATIC | ✅ |
| TESTED | ✅ Linux (yukarıda). Windows CI PR'da koşacak |
| BUILT | ❌ NOT BUILT |
| LIVE VERIFIED | ⛔ BLOCKED |

### Canlı kabul adımları (Codex)

1. Ayrı test paketi oluşturun: `build.py`, staging. Kurulu EXE'ye ve açık
   Quartz'a dokunmayın.
2. Paketli EXE'nin kendi profilinde (Store Python profiliyle karıştırmadan)
   Notion girişi, `worker-bridge.json` ve Credential Manager anahtarı mevcut
   mu, kontrol edin. Ardından **o profilde**
   `python -B scripts/notion_worker_acceptance.py --enable-main-chat`
   çalıştırın. Paket profili farklıysa aynı adım o profil için ayrıca ve
   açıkça yapılmalı.
3. İzole veri klasörüyle paketi açın, Notion'ı seçin, "Test projesindeki
   dosyayı incele" yazın.
4. Kartı **reddedin**: Notion'a istek ve fixture olmamalı.
5. Tekrar yazıp onaylayın. Worker run kaydında `quartzReadTestFile` ve
   `quartzReadResult` görülmeli; yanıtta kanıt ve SHA-256 manifest'le eşleşmeli;
   panel "Tamamlandı ve doğrulandı" göstermeli.
6. Yeni turda yürütme sırasında İptal'e basın: yerel `.stopped` oluşmalı,
   sonuç yayımlanmamalı, uzak durum ayrı yazılmalı.
7. Uygulamayı kapatıp yeniden açın: önceki fixture `expired` olmalı, kart
   kendiliğinden açılmamalı.
8. Korunan 9 kullanıcı/ayar dosyasının önce ve sonra hash karşılaştırması
   yapılmalı.

## Koruma diff'i

Bu görev boyunca kullanıcının bilgisayarına **hiçbir dosya yazılmadı**. Yalnız
Git nesneleri, worktree index'i, log ve belgeler salt okunur kopyalandı;
`.env`, token veya sohbet içeriği okunmadı. Kullanıcı dosyalarının
önce/sonra hash karşılaştırması **yapılamadı** (bağlantı koptu), bu yüzden
NOT TESTED. Testler yalnız geçici dizinlerde çalıştı.

## Bilinen eksikler

- LIVE ve BUILT yok (yukarıda).
- Niyet tespiti kural tabanlı ve dar; açık bir "test dosyası" isteği dışındaki
  ifadeler bulut sohbetinde kalır.
- Fixture her görevde Quartz tarafından üretilir ("onaylı disposable test
  projesi" yorumu). Kalıcı bir test klasörü istenirse ayrıca tanımlanmalı.
- Fixture klasörleri otomatik silinmez; retention ayrı bir karar.
- İlk turda Notion oturumu yoksa kısa bir oturum açma mesajı gönderilir (bir
  ek bulut turu).
- Uzak iptal doğrulaması mevcut `NotionRuntime` iptal yoluna dayanır;
  doğrulanamazsa öyle yazılır.

## Codex için minimum son entegrasyon

1. Bu dalı `codex/notion-tools-integration` üzerine alın. Baseline'dan sonra
   yalnız bir commit var.
2. Windows CI ve tam suite'i çalıştırın.
3. Yukarıdaki canlı kabul adımlarını izole paket ve profille yürütün.
4. Sonuçlara göre `--enable-main-chat`'i yalnız kullanıcı onayıyla, ilgili
   profilde açın.
5. Kurulu EXE güncellemesini ayrı ve geri alınabilir bir adım olarak yapın.

Geri alma: tek commit revert edilir. Yalnız `main_chat` anahtarı eklenmişse
`--disable-main-chat` çalıştırılır.
