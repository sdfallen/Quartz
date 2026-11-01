# Notion Araç Entegrasyonu — Bağlantı Protokolü ve Taşıma Raporu

**Tarih:** 2026-11-01<br>
**Sorumlu Model / Rol:** Gemini 3.8 Flash / Antigravity (Taşıma Adaptörü ve Bağlantı Protokolü)<br>
**Koordinatör:** Codex<br>
**Kaynak Baseline:** `451571251a9425a1bf32e757dd92ac74d5c6913b`<br>
**Çalışma Dalı (Branch):** `antigravity/notion-tool-transport`<br>
**Durum:** Feasibility Teslimi + Taşıma Adaptörü ve Testleri<br>

---

## 1. Bağlantı Protokolü ve Fizibilite İncelemesi (Feasibility Analysis)

### 1.1 Resmî Notion API ve CLI Durumu (2026-03-11 Public Beta)
Notion Developer Platform ve resmî `ntn` CLI (v0.23.25) kaynakları taranmış ve aşağıdaki resmî durum tespit edilmiştir:

1. **Notion Custom Agents ve Session Yaşam Döngüsü:**
   - **Ana Endpoint:** `POST https://api.notion.com/v1/sessions` (Notion-Version: `2026-03-11`).
   - **Olay Sorgulama:** `POST https://api.notion.com/v1/sessions/{session_id}/events/query`.
   - **İptal / Durdurma:** `POST https://api.notion.com/v1/sessions/{session_id}/cancel`.
   - **Oturum Durumları:** `queued`, `in_progress`, `requires_action`, `completed`, `failed`, `canceled`, `terminated`.
   - **Belge Kaynakları:**
     - Notion Developer Reference: *Create or update a session* (`POST /v1/sessions`) — [https://developers.notion.com/reference/create-a-session](https://developers.notion.com/reference/create-a-session)
     - Notion Developer Reference: *Query session events* (`POST /v1/sessions/{session_id}/events/query`) — [https://developers.notion.com/reference/query-a-sessions-events](https://developers.notion.com/reference/query-a-sessions-events)

2. **Bulut Ajanının Yerel `stdio` / `localhost` MCP'ye Erişimi:**
   - **Durum:** **BLOCKED (Doğrudan bağlantı imkânsız).**
   - Notion Custom Agent tamamen Notion'ın bulut altyapısında çalışır.
   - Bulut ortamındaki bir Custom Agent'ın istemci makinesindeki yerel `stdio` MCP sürecine, Windows named pipe'ına veya `localhost` portlarına kendiliğinden erişmesi teknik olarak mümkün değildir.
   - Notion API'sinde OpenAI'ın `submit_tool_outputs` benzeri, istemcinin bir tool çağrısını alıp doğrudan API seviyesinde tool output olarak teslim ettiği ayrılmış bir endpoint bulunmamaktadır.

3. **`requires_action` Durumunun Gerçek Anlamı:**
   - **Önemli Bulgulama:** `requires_action` bir tool execution RPC durumu değil; bir **kullanıcı onay / insan müdahalesi (human-in-the-loop confirmation)** duraklamasıdır.
   - Notion arayüzünde ajan yan etkili bir eylem veya araç için onay istediğinde oturum `requires_action` durumuna geçer.
   - İstemci tarafından doğrulanmış bir araç sonucu dönülmeden salt `requires_action` durumunun görülmesi bir tool execution başarısı sayılamaz.

4. **Notion'ın Resmî Araç Genişletme Yolları:**
   - **Yol A — Notion Workers (`@notionhq/workers`):** Notion'ın kendi sunucularında çalışan TypeScript kod parçacıkları (`worker.tool(...)`). Doğrudan kullanıcının Windows masaüstüne, HWND'lerine veya yerel dosyalarına erişemez.
   - **Yol B — Uzak / Barındırılan MCP Sunucuları (Hosted Remote MCP):** Açık bir HTTPS URL'i üzerinden SSE / HTTP streaming ile bağlanan sunucular. Quartz'ın yerel, güvenli ve tünelsiz modeline aykırıdır (harici hosting, alan adı, tünel veya statik IP gerektirir).
   - **Yol C — İstemci Güdümlü Oturum Devamı (Client-Orchestrated Continuation):**
     - Quartz yerel oturumu başlatır ve olay akışını dinler.
     - Ajanın yapılandırılmış araç isteği veya `requires_action` ihtiyacı tespit edildiğinde, yerel Desktop Broker / Checkpoint / REA devreye girer.
     - Kullanıcı onayı ve yerel doğrulama tamamlandıktan sonra, elde edilen somut bulgu ve gözlem aynı `session_id`ye yeni bir oturum turu mesajı (`POST /v1/sessions` ile `{"session_id": "...", "message": ...}`) olarak iletilir.
     - Ajan bu taze gözlem ile akışını sürdürür.
     - **Bu yol tamamen yereldir, harici sunucu/ücret gerektirmez ve Quartz'ın tek operatör / taze gözlem sözleşmesini korur.**

---

## 2. Desteklenen Yol ve Taşıma Adaptörü Sözleşmesi

### 2.1 Yerel Taşıma Mimarisi (`core/notion_tool_transport.py`)

`core/notion_tool_transport.py`, `PLAN.md` içindeki ortak sözleşmeye tam uyumlu, bağımlılıkları enjekte edilebilen dar bir adaptördür:

```
[Notion İsteği / Olayı]
        │
        ▼
[NotionToolTransport (Doğrulama & Replay Koruması)]
        │ (schema_version, task_id, session_id, request_id, tool_name, arguments, scope_ref, deadline)
        ▼
[Enjekte Edilen Yerel Router (Codex / DesktopBroker / REA)]
        │
        ▼
[Yerel Sonuç (status, output, error, duration_ms, verification)]
        │
        ▼
[Taşıma Formatlayıcı -> Notion Devam Mesajı (session_id bağlı)]
```

### 2.2 Korunan Güvenlik Sınırları ve Savunmalar

1. **Yerel Komut Yürütmeme İlkesi:**
   - `NotionToolTransport` tek bir shell komutu, Win32 API veya dosya yazma eylemi yapmaz.
   - Yalnızca yapılandırılmış isteği doğrular, yönlendirir ve sonucu bağlar.
2. **Düz Metin / Kod Bloğu Enjeksiyon Koruması:**
   - Düz metin veya markdown kod blokları (````json ... ````) asla komut olarak yorumlanmaz.
   - Modelin ilettiği `scope_ref` yerel yetki sayılmaz; yetki her zaman yerel broker tarafından teyit edilir.
3. **Tekrar (Replay) ve Idempotency Koruması:**
   - Her `request_id` izlenir.
   - Tamamlanmış isteğin tekrarı durumunda yan etkili işlem tekrar yürütülmez; önbellekteki sonuç idempotently döner.
   - Halen yürütülmekte olan istekler için eşzamanlı çift çalıştırma engellenir.
   - Farklı `session_id` veya `task_id` ile gelen `request_id` replay girişimleri güvenlik hatası (`SessionMismatchError`) ile reddedilir.
4. **Zaman Aşımı (Deadline) ve İptal (Stop):**
   - Her istek için katı `deadline` uygulanır. Süresi dolan istekler yerel yönlendiriciye gönderilmez veya zaman aşımıyla sonlandırılır.
   - İptal (`cancel_request` / `cancel_session`) çağrısı yapıldığında yürütme durdurulur ve sonuç `"cancelled"` olarak işaretlenir.
5. **İkili Veri ve Ekran Görüntüsü Yük Sınırları (Payload Limits):**
   - Yanıtlardaki ikili veri / base64 ekran görüntüleri için 5 MB yük sınırı (`max_payload_bytes`) uygulanır.
   - Taşıma katmanı günlüklerinde (logs) asla API anahtarı, parola veya ham ekran verisi yazdırılmaz.

---

## 3. Kod Teslimi ve Değişen Dosyalar

Antigravity sahiplik manifestosuna uygun olarak yalnız şu dosyalar üretilmiştir:

1. `core/notion_tool_transport.py` (Yeni):
   - `NotionToolRequest`: Yapılandırılmış araç isteği veri modeli.
   - `NotionToolResult`: Standart araç sonucu veri modeli.
   - `NotionToolTransport`: Replay korumalı, oturum bağlı, zaman aşımlı ve iptal destekli taşıma adaptörü.
   - `format_continuation_message`: Doğrulanmış araç çıktısını Notion oturumuna dönecek güvenli devam mesajı formatlayıcısı.

2. `tests/test_notion_tool_transport.py` (Yeni):
   - Şema doğrulama, eksik alanlar, geçersiz UUID ve kötü niyetli veri testleri.
   - Oturum uyuşmazlığı ve replay/idempotency testleri.
   - Zaman aşımı (deadline) ve iptal (cancellation) testleri.
   - 5 MB yük sınırı aşımı ve ikili veri güvenliği testleri.
   - Yerel yönlendirici enjeksiyonu ve sonuç biçimlendirme testleri.

3. `scripts/probe_notion_tool_transport.py` (Yeni):
   - Salt okunur varsayılan ile çalışan doğrulama betiği.
   - Yerel CLI ve transport sözleşmesini canlı/simüle test eden probe.
   - Gerçek yan etki için açık `--allow-active-task` bayrağı gerektirir.

4. `docs/notion-tools/GEMINI_REPORT.md` (Yeni - bu belge).

---

## 4. Codex için Entegrasyon İstekleri (Integration Requests)

1. **`core/notion_runtime.py` Bağlantısı:**
   - `NotionRuntime._execute` döngüsünde `state == "requires_action"` veya ajanın structured tool çağrısı geldiğinde:
   - Mevcut doğrudan `return` (status="blocked") yerine, `NotionToolTransport` üzerinden yerel onay/yönlendirme tetiklenebilir.
   - Sonuç alındıktan sonra aynı `session_id` ile `POST /v1/sessions` yapılarak oturum kesintisiz devam ettirilebilir.
2. **Görüntü ve Ekran Kanıtı:**
   - Notion Custom Agent metin tabanlı yanıt verdiği için, yerel ekran görüntüsü doğrudan base64 metin olarak gönderilmek yerine, yerel Desktop Broker'ın doğruladığı yapılandırılmış UIA hiyerarşisi ve pencere durumu (`observed` / `verified`) olarak devam mesajına eklenmelidir.
