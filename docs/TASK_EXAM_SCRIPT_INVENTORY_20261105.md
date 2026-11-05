# Kabul betikleri — Dalga 0 envanteri

Seviye: SOURCE/STATIC. Sözdizimi derlenebilir olması, betiğin gerçek ortamda çalıştığını kanıtlamaz. Gerçek hesap/masaüstü betikleri bu incelemede çalıştırılmadı. Kullanıcının güncel görevi koşucuyu Codex alanına verir; eski plandaki Gemini ataması bu dilim için geçerli değildir.

| Betik | Sınıf | Çalıştırma | Not |
|---|---|---|---|
| `scripts/accept_cli_clean_install.py` | REQUIRES_NETWORK_INSTALL | NOT TESTED | Real isolated install acceptance; no credentials, user config or Desktop apps. |
| `scripts/accept_desktop_cancellation.py` | REQUIRES_ACCOUNT | NOT TESTED | Source integration: real CLI cancellation with an in-memory window fixture. |
| `scripts/accept_diagnostics_expansion.py` | REQUIRES_REVIEWED_FIXTURE | NOT TESTED | Real file/service acceptance on disposable copies; NOT packaged chat acceptance. |
| `scripts/accept_response_style.py` | REQUIRES_ACCOUNT | NOT TESTED | Read-only live chat/Squad acceptance in a new disposable project. |
| `scripts/accept_self_diagnostics.py` | REQUIRES_REVIEWED_FIXTURE | NOT TESTED | Real local IPC + optional REA acceptance on an explicitly selected package. |
| `scripts/coordination_acceptance.py` | REQUIRES_DESKTOP_AND_ACCOUNT | NOT TESTED | Real provider/Squad/native-window coordination, isolated from user projects. |
| `scripts/desktop_chat_acceptance.py` | REQUIRES_DESKTOP_AND_ACCOUNT | NOT TESTED | Real desktop + CLI/Squad through GUI-local prepare/status/stop APIs. |
| `scripts/desktop_mcp_acceptance.py` | REQUIRES_ACCOUNT | NOT TESTED | Live provider/tool-transport acceptance, with NO native desktop actions. |
| `scripts/desktop_native_acceptance.py` | REQUIRES_DESKTOP_AND_ACCOUNT | NOT TESTED | Product acceptance of the real CLI -> MCP -> native backend path. |
| `scripts/live_verify_agent_center.py` | REQUIRES_ACCOUNT | NOT TESTED | Harmless live verification for Quartz -> Squad -> Codex -> Squad. |
| `scripts/live_verify_dual_agents.py` | REQUIRES_ACCOUNT | NOT TESTED | Live, read-only Codex + Antigravity + Squad bridge verification. |
| `scripts/measure_runtime_efficiency_pyramid.py` | OFFLINE_MEASUREMENT | NOT TESTED | Measure full owned process-tree CPU and RAM for Quartz pyramid runtimes. |
| `scripts/multiwindow_acceptance.py` | REQUIRES_DESKTOP_AND_ACCOUNT | NOT TESTED | Real native broker + actual CLI/Squad multiwindow product self-test. |
| `scripts/multiwindow_safety_acceptance.py` | REQUIRES_DESKTOP | NOT TESTED | Owned real Windows lifecycle/launch acceptance through the packaged MCP. |
| `scripts/natural_desktop_e2e_acceptance.py` | REQUIRES_DESKTOP_AND_ACCOUNT | NOT TESTED | End-to-end natural desktop task acceptance verification. |
| `scripts/natural_gateway_acceptance.py` | REQUIRES_ACCOUNT | NOT TESTED | Real CLI/MCP/Squad transport check WITHOUT any native input or permission. |
| `scripts/notion_worker_acceptance.py` | LEGACY | NOT TESTED | Explicit, disposable read-only Worker acceptance. No normal-chat tools enabled. |
| `scripts/observer_guard_acceptance.py` | REQUIRES_ACCOUNT | NOT TESTED | Real AGY pre-tool deny acceptance in an isolated disposable workspace. |
| `scripts/rea_validation/workbench_acceptance.py` | REQUIRES_REVIEWED_FIXTURE | NOT TESTED | Explicit live acceptance: one pinned official tool, one generated local file. |
| `scripts/text_chat_acceptance.py` | REQUIRES_ACCOUNT | NOT TESTED | Real CLI text-only smoke; no game, project edits, GUI or user history. |
| `scripts/warband_adapter_acceptance.py` | LEGACY | NOT TESTED | Real project, read-only UM preparation/contracts/preservation acceptance. |
| `scripts/warband_agent_acceptance.py` | LEGACY | NOT TESTED | Real CLI/Squad + UM-owned game smoke. Host grants this explicit test scope. |
| `scripts/warband_squad_status_acceptance.py` | LEGACY | NOT TESTED | Actual isolated Squad task handshake; no model, game or ASTER write. |
| `scripts/workflow_acceptance.py` | REQUIRES_DESKTOP_AND_ACCOUNT | NOT TESTED | Owned real-UI A -> B -> A workflow; not packaged main-chat consent acceptance. |

## Yorumlama

- `LEGACY`: Warband/Notion kapsam dışı; çalıştırılmadı.
- Hesap gereken testin sahte pencere backend kullanması ücretsiz veya offline olduğu anlamına gelmez.
- Ağ/kurulum, paket/REA fixture ve yardımcı EXE gerektirenler ayrıca hazırlanmalıdır.
- Kaynakta 24 betikte sözdizimi hatası yok; bundan 24 çalışan test sonucu çıkarılmadı.
- `accept_response_style.py`, `accept_desktop_cancellation.py` ve ölçüm betiği çıktıdaki başarısızlıkları her dalda nonzero exit ile bildirmez. Salt exit0 kabul kanıtı değildir. Koşucu doğrulayıcı olmadan VERIFIED üretmez.
- Genel canlı betik adaptörleri bu dilimde kapalı: bazıları ROOT/labs içine ham sohbet/ekran yazar. Kanıtları dışarı yönlendiren adapter incelenmeden bayrak verilse de çalışmaz.
- `measure_runtime_efficiency_pyramid.py` yalnız sentetik süreç ölçer; gerçek Quartz FPS/boşta maliyet veya canlı sağlayıcı performansı değildir. Çalıştırıldığında ölçüm kanıtı özel klasörde tutulur.
