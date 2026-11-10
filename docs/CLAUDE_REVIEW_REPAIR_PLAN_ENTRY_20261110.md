# Claude incelemesi + entegrasyon — onaylı onarım planı girişi (10 Kasım 2026)

## Codex arka ucu `76de570` — SOURCE/TESTED kabul

İncelenen: `core/repair_plan_entry.py`, `core/agent_chat.py`, `main.py` IPC (`c75c5fc..76de570`).

- Önizleme yalnız dosyaları okuyup hash'liyor (`HostUnittestAdapter` kurulumu `_manifest`), Python adayları
  `shutil.which` ve glob ile; hiçbir süreç başlatılmıyor. Korumalı/Warband proje reddi, tek ajan zorunlu.
- Kayıt: `confirm is True`, tek kullanımlık 10 dk `preview_id`, etkin sohbet/proje/kök/ajan/model,
  dosya hash'i ve Python `stat` yeniden denetleniyor; ikinci yakalama yarışı kapatılıyor. Çalışan tur,
  bekleyen worker/Stop ve doğrulanmamış temizlikte önizleme/kayıt/kaldırma reddediliyor.
- IPC alan beyaz listesi (`set(data) - permitted`), dış komut/zaman aşımı/kök kabul edilmiyor; MCP yok.
- `self._lock` `RLock`; `register_host_unittest_plan` iç içe kilitte kilitlenmez.
- P3: hata yolunda `confirm` denemesi kimliği tüketiyor (belgede; arayüz yeniden önizleme istiyor).
  WindowsApps takma adı aday listesinde sonda ve uyarılı; çalışabilirliği doğrulanmıyor (belgede).

## Claude arayüzü `9f4e0fa` + `5d07be0` — Codex incelemesi bekliyor

`gui.py` köprüsü (beyaz liste, tip denetimi), `ui/js_repair_plan.py` paneli ve çipi, `ui/shell.py`,
`assets/workspace.css`, yoklama ve sohbet yükleme bağlantıları. Sözleşme farkları uygulandı: ajan sohbetin
tek ajanından okunur (Birlikte'de engel), `model` nesnesi, `files_count` toplam, `clear` → `null`.
Kendi kodumu kabul etmiyorum.

## Entegrasyon `claude/repair-plan-integration-20261110` (`c204d84`)

`76de570` + Claude arayüzü, çakışmasız birleşim. Benim koşumlarım:
- Hedefli 6 modül (`test_repair_plan_entry`, `test_repair_plan_panel`, `test_host_test_runner`,
  `test_chat_repair`, `test_gui_frontend_boundary`, `test_environment_health_card`) → `Ran 75 tests`, OK.
- Tam `run_safe_tests.py` → `Ran 1682 tests`, OK (skipped=14; Codex'in ortamında 2 skip — ortam farkı).
- Python sözdizimi 365 dosya OK; gömülü JS exit 0.
- Not: arayüz dalında ilk tam koşuda 1 hata görüldü, yeniden koşuda tekrarlamadı; kaynağı belirlenmedi.

## Kanıt seviyesi

SOURCE + TESTED. BUILT ve LIVE yok. Sonraki: Codex arayüz incelemesi → kullanıcı onaylı tek paket →
Claude operatörlüğünde canlı kapı 3.
