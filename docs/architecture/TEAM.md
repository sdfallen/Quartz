# Üç ajan — mimari geçiş görevleri

Ortak başlangıç: codex/architecture-pyramid-20261101 dalının P0 teslim
commit'i. Kaynak davranışı baseline e2ce872 ile aynı; yalnız plan/envanter
değişir. Dış ajan kendi worktree/clone'unda çalışır. Aynı ana checkout'ta
dal değiştirmek, başka ajanın commit'ini üzerine yazmak veya çalışan EXE'yi
değiştirmek yok. Üç alan eşit sorumluluk taşır; satır sayısı eşitliği hedef değil.

| Sahip | Alan | Yazabileceği dosyalar |
|---|---|---|
| Codex | Uygulama sözleşmeleri, korelasyon, yaşam döngüsü, entegrasyon | core/agent_chat.py, multi_agent_service.py, natural_desktop.py, chat_coordination.py, task_outcome.py, run_evidence_store.py, writer_journal.py; main.py/quartz_entry.py yalnız entegrasyonda; ilgili backend testleri; docs/architecture/* |
| Claude | Sunum sınırı ve frontend ayrıştırma | gui.py, ui/*, assets/workspace.css; test_gui_*, frontend/keyboard/render testleri; docs/CLAUDE_* |
| Antigravity | Provider/runtime ve süreç maliyeti | core/codex_runtime.py, antigravity_runtime.py, gemini_runtime.py, process_tree.py, async_snapshot.py, low_spec_optimizer.py; ilgili runtime/process/low-spec testleri; docs/ANTIGRAVITY_* |

Diğer üretim dosyaları ilk dilimde salt okunur. cli_installer, onboarding,
hesap/secret saklama, legacy assistant, Desktop Broker/native, checkpoint,
paket spec/CI ve güvenlik ilkelerini izinsiz geniş kapsamda değiştirme.
Gerçek bağımlılık çıkarsa integration request kaydet: neden, çağrı noktası,
önerilen küçük sözleşme, sahibinin yapacağı değişiklik ve test.

## Ortak P1 ön teslimi

Her sahip kod değiştirmeden kısa bir bağlama tablosu çıkarır:
giriş çağrısı, task/run/session kimliği, state'in sahibi, side effect sahibi,
Stop sahibi, kalıcı kayıt ve hata/kanıt çıkışı. Aynı bilgi iki yerde
otoriteyse bunu bulgu olarak belirt; varsayımla birini silme.

Kayıtlar ortak PYRAMID.md sözleşmesiyle hizalanır. İlk uygulama tek akışta
yapılır; source/test/live kabulü olmayan geniş rewrite başlatılmaz.

## Teslim kapısı

1. Commit SHA + ortak baseline + yalnız sahip olunan dosyaların diff'i.
2. Gerçek bulgu, küçük değişiklik ve geri alma adımı.
3. Hedefli test; uygun tam Windows suite; skip ve platform sınırlamaları.
4. Paket ve canlı kabul ayrı. Linux mock test Windows GUI kabulü değildir.
5. Modelin tamamlandım demesi hedef doğrulaması değildir.
6. Kod çalıştırma, observer/read-only kısıtları ve input safety korunur.
7. Kaynak/scope/Stop/özgün kullanıcı verilerinde regresyon olursa birleşim durur.

Son birleştirme ve dağıtım yalnız Codex'te. Her ajan bağımsız şekilde paket
dağıtmaz. Notion Worker/model/UI işi ve ASTER bu kapsamın dışındadır.

## İlk güvenilir dikey akış

Normal sohbet → kullanıcıdan gerçek geliştirme görevi → doğru provider/rol
→ checkpoint/tek yazıcı → çalışma ve kanıt → aynı sohbetten ek talimat
→ Stop/cleanup → uygulamayı yeniden açma. Masaüstü dalı mevcut broker ve
native kullanıcı onayı üzerinden ayrıca bağlanır. Kullanıcıya ikinci bir
görev merkezi veya yeni kontrol modu sunulmaz.
