# Integration request — kullanıcı onaylı onarım planı girişi (10 Kasım 2026)

Kullanıcı kararı (bu sohbette, kendi yazısıyla): "Evet, yapılsın". Soru: "Kapı 3 için onaylı bir onarım
başlatma girişi yapılsın mı?" Amaç: paketli Quartz'ta canlı kapı 3'ü yürütebilmek.

Sahiplik: arka uç (`core/agent_chat.py`, `main.py` IPC) **Codex**; köprü ve arayüz (`gui.py`, `ui/`)
**Claude**. Codex sözleşmeyi değiştirebilir; değişikliği teslim dosyasında yazsın, arayüz uyar.

## İlke

Test dosyaları, beklenen sayı ve Python yolu modelden değil **kullanıcıdan** gelir. Önizleme yalnız
okur ve hash'ler, hiçbir proje kodu çalıştırmaz. Kayıt açık onay ister, çalışan tur varken reddedilir,
tek kullanımlıktır ve sohbet/proje/sağlayıcı/modele bağlıdır (mevcut kurallar). MCP/model aracı yok;
yalnız GUI IPC.

## IPC eylemleri (Codex)

1. `repair_plan_preview` — `data`:
   `{conversation_id, provider, test_files: [str], support_files: [str], expected_tests: int,
     python_executable: str|null, max_repairs: int}`
   Başarı `data`:
   `{preview_id, conversation_id, project_id, project_path, provider, model,
     files: [{path, role: 'test'|'support', sha256}], expected_tests, python_executable,
     python_candidates: [str], max_repairs, warnings: [str]}`
   - `python_candidates`: algılanan mutlak Python yolları (WindowsApps takma adı en sona, uyarıyla).
     Dondurulmuş EXE'de `python_executable` boşsa ve aday varsa ilkini önerir ama kaydetmez.
   - Hata: `{status: 'error', data: '<Türkçe kullanıcı mesajı>'}` (yol, sayı, korumalı proje vb.).
   - `preview_id` 10 dk geçerli, tek kullanımlık.
2. `repair_plan_register` — `data: {preview_id, confirm: true}`
   Hash'ler, model ve ayarlar önizlemeden beri aynıysa ve çalışan tur yoksa
   `register_host_unittest_plan` çağrılır. `confirm` gerçek `true` değilse reddet.
   Başarı `data`: `repair_plan` özeti (aşağıda).
3. `repair_plan_clear` — `data: {conversation_id}`; çalışan tur yoksa bekleyen planı ve adaptörü kaldırır.
4. `chat_status` → `data.repair_plan` (etkin sohbet için):
   `null | {status: 'ready'|'running', provider, files_count, support_count, expected_tests,
            max_repairs, registered_at}`
   Plan tüketilince `null`; sonuç mesaj metadata'sında (`repair_cycle`, `code_review`) kalır.

## Arayüz (Claude)

- Besteci yanında "Onarım planı" düğmesi → panel: test dosyaları (satır başına bir, proje köküne
  göre), destek dosyaları, beklenen test sayısı, Python yolu (adaylardan seçim), en çok onarım (1–3),
  ajan seçimi (Codex/Antigravity).
- "Önizle" → dosya/rol/kısa hash tablosu ve uyarılar; "Onayla ve kaydet" yalnız geçerli önizlemeden sonra.
- Kayıtlı plan: besteci üstünde çip "Onarım planı hazır — N test · M dosya · en çok K onarım · ajan X"
  + "Kaldır". Çalışırken "Onarım döngüsü çalışıyor".
- Sunucu metni hiçbir zaman HTML olarak eklenmez (`textContent`).

## Kabul

Arka uç: önizleme kod çalıştırmaz (test), değişen dosya/model kaydı reddeder, çalışan turda kayıt/temizlik
reddedilir, `confirm` zorunlu, preview tek kullanımlık ve süreli. Arayüz: Node DOM testleri.
Sonra tek paket (kullanıcı onayıyla) ve Claude operatörlüğünde canlı kapı 3.
