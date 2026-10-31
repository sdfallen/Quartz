# Quartz paralel görev ve dosya sahipliği

Karar: 31 Ekim 2026. Başlangıç kaynak referansı: `cba9972`.
Bu dosyayı ekleyen koordinasyon commit'i ortak başlangıç baseline'ıdır.
`git log --all -- CLAUDE.md docs/PARALLEL_OWNERSHIP.md` ile bulunabilir.

| Ajan / kullanıcının model seçimi | Branch | Görev |
|---|---|---|
| Codex / 6.1 Sol | `codex/orchestration-kernel` | Görev yaşam döngüsü, devam, kilit, checkpoint, entegrasyon |
| Claude / 5.5 Opus | `claude/frontend-architecture` | GUI ayrıştırma ve frontend sözleşmeleri |
| Antigravity / 3.8 Flash High | `antigravity/runtime-efficiency` | Süreç, CPU/RAM, polling ve log maliyeti |
| Notion Kimi / K3 | `kimi/remote-quality-audit` | GitHub kaynak/dağıtım denetimi ve bağımsız test |

Model adları kullanıcının görevlendirmesidir; bu belge dış ajan oturumu başlatmaz
ve sağlayıcıdaki model erişimini doğrulamaz.

## Codex sahipliği

1 Kasım modern arayüz teslimi sonrası entegrasyon: kullanıcının ve Claude'un
integration request'i doğrultusunda `gui.py`, `main.py`, `core/notion_*.py`,
ilgili frontend/Notion testleri ve paket spec'i Codex tarafından birleştirilir.
Claude'un tema/animasyon tasarımı korunur. Antigravity performans dalı bu
entegrasyona dahil değildir; mevcut inceleme bulguları ayrı kalır.

1 Kasım entegrasyon kapsamı: yeni `core/notion_*.py`,
`scripts/notion_agent.py`, `tests/test_notion_*.py` ve
`docs/CODEX_NOTION_*.md` Codex'e aittir. Mevcut Codex sahipliğindeki
sohbet/servis dosyalarına isteğe bağlı Notion adaptörü eklenebilir.
`gui.py` ve kurulum ekranı değişiklikleri bu kapsamda değildir;
frontend sahibine integration request ile devredilir.

- `core/agent_chat.py`, `core/multi_agent_service.py`, `core/natural_desktop.py`
- `core/run_evidence_store.py`, `core/writer_journal.py`, `core/workspace_checkpoint.py`
- `tests/test_agent_chat.py`, `tests/test_multi_agent_service.py`, `tests/test_natural_desktop.py`
- `tests/test_agent_permissions.py`, `tests/test_writer_recovery.py`, `tests/test_workspace_checkpoint.py`
- Yeni `tests/test_orchestration_*.py`
- `CLAUDE.md`, bu manifest, `docs/REMOTE_DEVELOPMENT_WORKFLOW.md`
- `docs/QUARTZ_CLAUDE_PROJECT_BRIEF_20261031.md`, yeni `docs/CODEX_ORCHESTRATION_*.md`

Paketleme/CI/kurulum dosyaları yalnız PR'lar bittiğinde ve sahiplerle koordine
edilen entegrasyon aşamasında Codex tarafından güncellenebilir.

## Claude sahipliği

- `gui.py`, yeni `ui/` dosyaları, yeni `core/ui_*.py`
- `tests/test_gui_*.py`, `tests/test_chat_keyboard.py`, `tests/test_chat_task_entry.py`
- `tests/test_diagnostics_poll.py`, `tests/test_elevation_ui.py`
- `tests/test_permission_continuation_ui.py`, `tests/test_permission_selection.py`
- `tests/test_response_style.py`, `tests/test_self_diagnostics_ui.py`
- Yeni `docs/CLAUDE_FRONTEND_*.md`

Pywebview API adları/payload'lar korunur. Paket spec değişimi gerekiyorsa Codex'e
integration request verilir; PR bu entegrasyon yapılmadan paket-kabul edilmiş sayılmaz.

## Antigravity sahipliği

- `core/low_spec_optimizer.py`, `core/async_snapshot.py`, `core/process_tree.py`
- `tests/test_low_spec_optimization.py`, `tests/test_process_tree.py`
- Yeni `tests/test_runtime_efficiency_*.py`, `scripts/measure_runtime_efficiency_*.py`
- Yeni `docs/ANTIGRAVITY_PERFORMANCE_*.md`

GUI veya kurulum dosyası gerekiyorsa integration request kaydet.

## Kimi sahipliği

- `docs/kimi/`, `tests/kimi_remote/`, `scripts/kimi_remote/`
- Üretim dosyaları salt okunur. Her bulgu incelenen SHA ve sorumlu ajanla sunulur.
- Notion bağlantısında yazma/PR yetkisi yoksa Markdown teslim edilir; yapılmamış
  GitHub eylemi tamamlanmış gösterilmez.

## Ortak kurallar

- Her ajan ayrı clone/worktree kullanır; aynı klasörde branch değiştirerek çalışmaz.
- Yukarıda sahiplenilmeyen tüm dosyalar bu çalışma sırasında salt okunurdur.
- Kapsam genişlemesi manifesti yöneten Codex ile koordine edilir.
- Başka ajanın branch'ini birleştirme; PR'ı Codex inceleyip entegre eder.
- Yeniden kullanılacak API değişiklikleri önce PR'da sözleşme olarak belirtilir.
- ASTER/Warband, kullanıcı verileri ve yerel dağıtım paralel çalışma dışında kalır.
- Uzak testler ve gerçek Windows kabulü ayrı raporlanır.
