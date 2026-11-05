# Dalga 2 arayüzü: sonuç rozetleri ve duraklatılmış izin kartı (6 Kasım 2026)

Dal: `claude/wave2-ui-20261106`, taban `main` `abbeeb7`. Karşıladığı talepler: `IR-CLAUDE-OUTCOME-02`,
`IR-CLAUDE-ORACLE-01`, `IR-CLAUDE-APPROVAL-PAUSE-01` (madde 1, 2, 3 ve 5). Tasarım: `CLAUDE_FRONTEND_STATUS_DISPLAY_20261105.md`.
Durum: **Gemini incelemesi bekliyor.** Geçici devir kuralı gereği Claude bu dalı kendisi `main`'e almaz.

## Değişenler

| Dosya | Değişiklik |
|---|---|
| `ui/js_messages.py` `agentMessageView` | `partial` ve `goal_verdict=PARTIAL`: "Kısmi — istenen ajanlardan biri tamamlayamadı", varsa `participants`'tan başarısız ajan adı. `blocked`: "Engellendi; nedeni ayrıntılarda" (eskiden "Henüz doğrulanmadı"). `awaiting_approval`: "Onay bekleniyor — görev duraklatıldı". Yalnız `goal_verdict=VERIFIED` + `goal_evidence.level=HOST POSTCONDITION` + boş olmayan `checks` "Önceden bildirilen N hedef koşulu dosyadan doğrulandı; kullanıcı kabulü ayrı." gösterir. Yazma izinli turların mevcut kaynak kontrolü metni korunur. Salt okunur inceleme ve masaüstü görevi mesajları: "Yürütme bitti, hedef henüz doğrulanmadı." Sade sohbet yanıtına rozet yok. `outcome` teknik ayrıntılara eklendi. |
| `ui/js_messages.py` `renderTasks` | Yerel asistan görev kartından `✓` kaldırıldı; durum adları Türkçe (bilinmeyen: "durum bilinmiyor"). |
| `ui/js_desktop.py` `pollNaturalTask` | Kart anahtarı istek kimliği + süre dolumu + temizlik durumundan oluşur; biri değişince kart yeniden çizilir. Duraklatılmış görevde "Görev duraklatıldı…" notu. `pause.cleanup_confirmed=false` iken Onay devre dışı ve açıklamalı; başarısız onay denemesi düğmeyi yeniden açmaz. Süresi dolan kartta Onay gizli ve devre dışı; "Yeniden onay hazırla" `natural_refresh_permission(eski_id, sohbet, true)` çağırır, yeni kart ayrıca onaylanır. Tam Yetki engelli veya süresi dolmuş kartı otomatik onaylamaz. |
| `gui.py` | `natural_refresh_permission(request_id, conversation_id, confirmed=False)` köprüsü; yalnız `confirmed is True` geçirir. Model araçlarına (`desktop_mcp.TOOLS`) eklenmedi. |
| `assets/workspace.css` | `.coordination-card .pause-note`; renk yanında metin taşır. |
| `tests/test_gui_wave2_status.py` | 12 yeni test (rozet tablosu, sahte "VERIFIED" model metni, kart durumları, Tam Yetki, yeniden onay, köprü). |
| `tests/test_desktop_broker.py` | 2 yeni test: duraklatma eski bearer/snapshot/lease'i kapatır; devam yeni kimlik doğrulaması ve yeni gözlem ister, eski bearer yenilenemez. Broker kodu değişmedi. |

## Kontroller

| Komut | Sonuç |
|---|---|
| `python -B scripts/run_safe_tests.py tests.test_gui_wave2_status` | 12 test OK |
| Aynı testler UI değişikliği geri alınmış halde | 11 başarısız, 1 geçti (model araç listesi koruması değişiklikten bağımsız) |
| `python -B scripts/run_safe_tests.py tests.test_desktop_broker` | 49 test OK |
| `python -B scripts/run_safe_tests.py` (tam) | 1388 test, 2 atlandı, OK |
| `python -B scripts/check_python_syntax.py` | 326 dosya OK |
| `python -B scripts/check_gui_javascript.py` | exit 0 |
| `python -B scripts/audit_publish.py --staged --history` | PASS, bulgu yok |

## Yapılmayanlar

- `paused_contexts` için yeniden açılışta gösterim (talep madde 4) yapılmadı: backend yalnız salt okunur bağlam veriyor ve
  devam yolu yok; kullanıcıya düğmesiz bir bilgi kartı göstermek ayrı bir tasarım kararı.
- Grup sonucunun mesajlara `participants` ile taşınması (Gemini C-W2-2) backend işidir; alan gelmezse rozet ajan adını yazmaz.
- Canlı kabul (talep madde 6): bekleyen kart, uzun bekleme, süre dolumu ve yeniden onay, Durdur yarışı, UAC, pencere kimliği
  değişimi, dar pencere. Bu oturumda Quartz açılmadı, paket derlenmedi. Seviye SOURCE + TESTED.
