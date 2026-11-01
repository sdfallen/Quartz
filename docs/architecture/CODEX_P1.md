# Codex P1 — kimlik ve sonuç yayınlama sınırı

Baseline: 047fa6e. P0 sahipliği geçerlidir; Claude/Antigravity dosyaları salt
okunur. Bu dilim yeni bir görev motoru veya runtime protokolü kurmaz.

## Mevcut bağlama haritası

| Giriş / bileşen | Kimlikler | Asıl sahip | Yan etki / kayıt | Stop |
|---|---|---|---|---|
| AgentChatService.send_message | conversation_id, turn_id, user/assistant message_id | _active_turn | ConversationStore mesajları | cancel_active önce yerel yayın fence'i koyar |
| _execute_codex_bubble / _execute_antigravity_bubble | message_id → run_id; provider session/thread_id | run durumu runtime; sohbetin sahibi AgentChatService | _publish_run_update üzerinden session/metin kaydı | run_id'ler MultiAgentService.cancel'a gider |
| MultiAgentService.dispatch / _start_writer | run_id, project canonical key, writer claim | service / WriterJournal | checkpoint, dosya diff'i, evidence | watcher gerçek runtime terminal sonucunu raporlar |
| Birlikte | turn/message listesi, Squad task_id, provider run_id'ler | AgentChatService, Squad taşıma | iki mesaj ve ortak proje bağlamı | bilinen run_id listesine iptal; tek writer korunur |
| NaturalDesktopTask | job/pending request/scope generation, operator/observer run | mevcut görev nesnesi ve broker | özel task kanalı, scope, taze gözlem ve evidence | yerel yetki önce kesilir; cleanup raporu ayrı |
| Kalıcı kayıt | conversation/session + evidence + writer journal | ilgili store | atomik JSON; geçmiş kayıt yetkiyi diriltmez | restart recovery, yeni grant değil |

Task/run/session aynı kimlik değildir. Mevcut turn_id ilk dilimde sohbet
sahiplik referansıdır; eski kayıtlara yeni task_id zorla yazılmayacak.

## İlk sınır incelemesi

_publish_run_update yerel iptal fence'i ile kalıcı kaydı aynı kilit altında
yapıyor. Ancak parametre conversation_id'sinin aktif turun conversation_id'si
olduğunu kontrol etmiyor. Aktif message_id ile yanlış conversation_id
verildiğinde session kaydı, mesaj bulunamadan önce farklı sohbete yazılabilir.
Bu public saldırı kanıtı değil; iç korelasyon sınırındaki eksik kontroldür.
Geçici gerçek ConversationStore üzerinde regresyonla sınırlandırılacak.

### Yeniden üretim ve düzeltme

Baseline üzerinde 3 hedefli testten biri başarısız oldu. Ayrı yeniden
üretimde gerçek geçici ConversationStore ile iki durum birlikte gözlendi:
`publication_reported_success=true` ve
`wrong_conversation_session_written=true`. Canlı CLI veya kullanıcı
sohbet dosyası kullanılmadı. Kamuya açık istismar veya normal oynanışta
gözlenmiş veri kaybı iddiası yok.

Düzeltme: aynı mevcut kilit/fence içinde, session veya message kaydı
yapılmadan önce aktif turun conversation_id'si ile cid eşleşmesi zorunlu.
Başka sohbete sonuç False döner; ne session ne mesaj değiştirilir. Sahipli
akış ve Stop sonrası yayın reddi korunur. Yeni motor, grant veya UI alanı yok.

Öncesi checkpoint: codex/checkpoint-p1-identity-before-20261101; source
dosya yedeği Codex backups/quartz-pyramid-p1-20261101/agent_chat.before.py.
Kanıtlar aynı klasörde identity-before.log, identity-reproduction.json ve
identity-after.log. İlk hedefli regresyon grubu: 64 test OK.

## Diğer ajanlara entegrasyon notu

- Claude: bu dilim pywebview API/payload veya GUI değişikliği istemiyor.
  _publish_run_update dönüşündeki False, eski/yanlış sahipli yayın reddidir;
  UI aynı sonucu tekrar göndererek yeniden canlandırmamalı.
- Antigravity: runtime stop/cancel tablosunda çağrıdan dönüş ile child'ın
  gerçekten çıkması arasındaki farkı belirt. Hangi alanla bunun kanıtlandığını
  veya UNKNOWN kaldığını raporla. Sadece orchestration arayüzünü kolaylaştırmak
  için iptal sonucunu terminal gibi sunma. Yeni alan gerekiyorsa önce öner;
  bu Codex dilimi runtime dosyalarını değiştirmiyor.
- Eski provider session/thread kimlikleri ve store şeması aynı. Kaynak
  düzeltmesi kurulu EXE'ye henüz dağıtılmadı; BUILT/LIVE NOT TESTED.

## Kapanış — bu küçük dilim

Hedefli grup 64 test OK. Tam Windows güvenli suite 844 case, hata yok,
12 standalone helper önkoşulu skip; bu worktree'de helper yeniden
derlenmedi. Son kaynak syntax kontrolü 235 Python dosyası OK; staged
yayın/history denetimi PASS, bulgu yok. Testler geçici dosyalar ve mocked
provider ile çalıştı. Tam rapor safe-suite.log içindedir.

SOURCE/TESTED doğrulandı. BUILT ve LIVE NOT TESTED. Kullanıcı uygulaması,
hesapları, kurulu EXE, sohbet dosyaları, Claude ve Antigravity sahipliği
değişmedi. Geri alma, bu dilimin tek commit'ini revert etmektir; checkpoint
ve source before yedeği yukarıdadır. P1'in geri kalanı ve P2–P4 tamamlanmadı.

## Sonraki bağımsız sınır

cancel_active/cancel_collaboration bazı iptal hatalarını yalnız logluyor;
UI yerel iptal ile süreç exit doğrulamasını aynı kabul etmemeli. Runtime
cancel sözleşmesinin kesin durum/exit alanları Antigravity tablosuyla
hizalanmadan yeni terminal durum veya otomatik yeniden başlatma eklenmez.
Bu dilimde shutdown ve process sahipliği kodu değiştirilmez.
