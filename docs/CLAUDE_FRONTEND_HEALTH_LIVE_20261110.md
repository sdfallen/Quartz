# Claude canlı kontrol — sağlık kartı, kurulu paket `cb67194c…` (10 Kasım 2026)

Kurulu `dist\Quartz\Quartz.exe` SHA-256 `cb67194c7cd43640e6898c7235ac1c222e2cb6c862f6dd7159291715f4ecba24`
(paketle aynı). Proje `exam-code-03` (`.squad` yok), mod Birlikte.

## Bulgu (P1, düzeltildi: `claude/health-card-poll-20261110`)

Kart açılıştan sonra 2 dakikadan uzun süre hiç görünmedi. Neden: kartı yalnız `loadActiveConversation()`
çiziyor; o da açılışta, ilk kontrol henüz bitmemişken (yer tutucu, `age_seconds: null`) bir kez çalışıyor.
Düzenli yoklama (`ui/js_lifecycle.py`) aynı `chat_status` verisini alıyor ama kartı çizmiyordu. Sonuç:
kart ancak sohbet değiştirilince çıkıyor; "Yeniden kontrol et" de yeni sonucu göstermiyor.

Canlı kanıt: aynı sohbet yeniden seçilince kart hemen çıktı — "Görev başlatılamaz: 2 engel, 1 uyarı"
(Python Store takma adı uyarı; Squad bağlı değil; Antigravity CLI oturumu açık değil).
Arka uç kaynakta doğru: aynı yoklama döngüsü 2. okumada `blocked` döndürüyor (~1,5 sn).

Düzeltme: yoklama `environment_health` geldiğinde kartı çiziyor (2 satır). Kart aynı sonucu tekrar
çizmediği için açılan "Ayrıntılar" yoklamada kapanmıyor. Test `test_shell_and_bridge` düzeltmesiz
başarısız; kart testleri 7 test OK; sözdizimi 347 dosya OK; gömülü JS exit 0.

## Açık soru (Codex/Gemini)

Kart "Antigravity CLI oturumu açık değil" diyor, oysa yan panel Antigravity için "Hazır" / "Bağlı"
gösteriyor ve bu sohbette Antigravity tur #5'i yazmış. `environment_health` `ready`/`authenticated`
alanlarını `agent_chat` ham durumundan alıyor; panel başka bir sinyal kullanıyor olabilir. Yanlış engel
olabilir; doğrulanmadı.

## Kanıt seviyesi

Bulgu LIVE (kurulu paket). Düzeltme SOURCE/TESTED; paketlenmedi, canlı değil.
