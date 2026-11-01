# Notion gecikmesi ve model sözleşmesi — Codex, 2026-11-01

Baseline: Claude ana sohbet teslimi d6174f6 (bundle'dan ayrı worktree'ye
alındı). Dal codex/notion-latency-models. Kullanıcının ana checkout'u, çalışan
Quartz EXE'si ve dış Claude teslimi değiştirilmedi. Pre-change checkpoint:
codex/checkpoint-notion-latency-before-20261101.

## Uygulanan

- Runtime yeni turda yalnız baseline sequence sonrasındaki olayları resmî
  sequence greater_than filtresiyle okur. İlk baseline okuması korunur;
  başka bir Notion istemcisinin mesajları yok sayılmasın diye varsayımsal
  session history cache veya yüksek-watermark eklenmedi. Mevcut tur içindeki
  olaylar yeniden okunabilir; güncellenen mesaj kaybolmaz.
- Signed sonuç hazır olduktan sonra worker task aynı kuyruğu sorgulayıp aynı
  sonucu tekrar PATCH etmez; bulut turunun tamamlanmasını bekler. HMAC,
  grant, TTL, durable idempotency, kimlik ve Stop kontrolleri değişmedi.
- Runtime ölçümleri: request_count/request_ms, submit_response_ms,
  first_text_ms, total_ms. Promptsuz/içeriksiz ölçümler sohbet metadata'sına
  taşınır. first_text_ms gözlenen ilk metindir, gerçek token üretim süresi
  değildir; request_ms hem CLI/ağ hem sunucu beklemesini kapsar.
- Bağlantı doğrulaması mevcut agent query yanıtından gerçek model bilgisini
  taşır: auto/pinned/unknown, id, label, selection_supported=false,
  managed_by=notion ve Türkçe gerekçe. Yeni model API'si icat edilmedi.

## Gerçek resmî sözleşme

- https://developers.notion.com/reference/notion-agent-apis/update-session.md
  mesaj şemasında model alanı yok; additionalProperties=false.
- https://developers.notion.com/reference/notion-agent-apis/query-session-events.md
  sequence filter destekliyor.
- https://developers.notion.com/reference/notion-agent-apis/retrieve-agent.md
  model auto veya pinned/id bildiriyor. pinned id null olabilir.
- Gerçek hesap agent query readback: model.mode=auto. Kaynak connection_status
  aynı bilgiyi model.label=Otomatik (Notion) olarak döndürdü.

Doğrudan Quartz'ta keyfî model değiştirme henüz desteklenmiş değildir. UI'da
gerçek ayar ve yönetim açıklaması gösterilecek; native Notion ayarındaki
değişiklik sonrası refresh yapılabilir. Kullanıcının istediği tam model
seçiminin yerine sadece etiket koyup tamamlandı denmeyecek.

## Testler

- Hedefli runtime/worker/latency: 45 test OK.
- Tam suite: 840 test, OK, 12 skip (bu yeni worktree'de standalone helper
  önkoşulu yok). Eski worktree'nin skip0 sonucu buraya aktarılmadı.
- Syntax: 234 Python dosyası OK.
- Gerçek kaynak Notion sohbeti: 17+26 sorusuna 43; completed.
  submit_response_ms=1500.53, first_text_ms=3204.62,
  total_ms=5839.27, request_ms=4824.43, request_count=4.
- Tek koşu; eşleştirilmiş before/after veya istatistiksel hız kazancı DEĞİL.
- Yeni Worker/GUI canlı kabulü bu görevde yapılmadı; paket oluşturulmadı.
- Yerel kanıt: Codex backups/quartz-notion-latency-20261101 içindeki
  source-chat-live.json, safe-tests.log, protection.json.
- Önceki pilotun 9 dosyalık koruma manifestine göre 8 aynı; paketli
  quartz_conversations.json farklı. Bu oturumun başlangıç snapshot'ı değildir,
  dolayısıyla değişimin bu oturumda oluştuğu veya nedeni iddia edilmez.
  Dosya geri alınmadı, içeriği rapora taşınmadı. Bizim kaynak çalışmamız ayrı
  worktree'dedir; mevcut kullanıcı sohbet dosyasına yazma yapılmadı.

## Claude teslim kapısı

CLAUDE_LATENCY_MODEL_PROMPT.md eşit sorumluluk ve dosya sahipliğini tanımlar.
Claude henüz bu oturumdan başlatılmadı; kullanıcı promptu kendi Claude
oturumuna iletecek. Frontend model alanı, kısmi cevap ve gecikme görünümü,
izin/Stop ve paketli UI testi onun sorumluluğudur. Son birleştirme ve
gerçek uygulama kabulü Codex'te. Yeni EXE dağıtılmadı.
