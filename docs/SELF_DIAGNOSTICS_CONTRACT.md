# Quartz öz teşhis — Codex / Antigravity sözleşmesi

30 Ekim 2026. Codex: backend/REA/paketleme. Antigravity: gui.py, CSS ve frontend testleri.

GUI API sarmalayıcıları `ipc_send(action, data)` ile aşağıdaki mevcut kimlik doğrulamalı backend eylemlerini kullanabilir:

- `diagnostics_start`, data: `{ "include_rea": true }` (isteğe bağlı; varsayılan true).
- `diagnostics_status`, data: `{ "job_id": "..." }` (boşsa son iş).
- `diagnostics_cancel`, data: `{ "job_id": "..." }`.

Standart yanıt: `{ "status": "ok", "data": JOB }`. Geçersiz parametrelerde `status:error` ve Türkçe `data` mesajı. Dış dosya/klasör veya komut argümanı kabul edilmez. Yalnız çalışan Quartz'ın kendi uygulama klasörü incelenir. Başlatma anında iş kuyruğa alınır; inceleme IPC/UI iş parçacığında çalışmaz. İkinci aktif iş aynı işi döndürür; tekrar çalıştırmaz. İptal, yalnız ilgili işin kendi alt sürecini durdurabilir.

JOB:

```json
{
  "schema_version": 1,
  "id": "job-id",
  "state": "running",
  "phase": "manifest",
  "progress": 25,
  "message": "Paket manifesti inceleniyor…",
  "checks": [
    {"id":"manifest", "status":"PASS", "title":"Paket manifesti", "message":"...", "evidence":{}}
  ],
  "verdict": "UNKNOWN",
  "limitations": [],
  "started_at": 0,
  "finished_at": null,
  "report_path": null,
  "rea_used": false
}
```

- `state`: `idle`, `running`, `completed`, `cancelled`, `failed`.
- `phase`: `queued`, `scope`, `resources`, `manifest`, `rea`, `report`, `done`.
- `checks[].status`: **PASS / FAIL / UNKNOWN / NOT_TESTED**.
- `verdict`: **PASS / FAIL / PARTIAL / UNKNOWN**. `completed` yalnız iş bitti demektir; başarı göstergesi için `verdict` de okunmalı. PARTIAL eksik kapsam demektir.
- `progress` gerçek aşama ilerlemesidir; zaman tahmini değildir. İptal/başarısızlık %100 başarı gibi gösterilmemeli.
- `checks[].evidence` güvenli özet veri; ham REA stdout/stderr veya uygulama logu değildir. Rapor içeriği HTML olarak işlenmemeli; metin olarak render edilmeli.
- `report_path` yerel özel teşhis raporu konumudur. Kullanıcı sohbetine ham dosya/log/anahtar basılmamalı.
- Başarılı paket kontrolü model erişimi, GUI işlevleri, güvenlik veya tüm uygulamanın hatasız olduğu anlamına gelmez.

Başlangıç kapsamı: kimlik/scope, gereken kaynak dosyaları, release-manifest.json ile sınırlı hash karşılaştırması, isteğe bağlı REA statik PyInstaller incelemesi. Otomatik onarım yok. Registry/hesap/uygulama ayarı değişikliği, hedef EXE çalıştırma, ASTER/Warband erişimi yok.

Kaynak modunda canlı paket yoksa paket kabulü NOT_TESTED kalır. REA kurulumu bu teşhis çağrısıyla kendiliğinden yapılmaz; eksik araç NOT_TESTED olur. Gerçek paket testi ayrı kontrollü fixture/CLI betiğiyle yürütülür.

## İsteğe bağlı yerel REA hazırlığı

`python -B scripts/prepare_rea_tool.py` REA 6.8.0'ı kullanıcıya özel `%LOCALAPPDATA%\Quartz\tools\rea` içine kurar. Uyumlu özel Node gerekirse resmî SHA-256 doğrulamalı taşınabilir Node kullanılır; sistem Node/PATH/agent yapılandırması değiştirilmez. npm kurulum scriptleri kapalı ve engine denetimi açıktır. Bu bakım işlemi normal teşhis başlatma eyleminin parçası değildir.

Hazır geliştirici ortamında `--prefix` ve `--node` ile izole hazırlık yapılabilir. Test operatörü için `QUARTZ_REA_SCRIPT` / `QUARTZ_REA_NODE` süreç ortamı da desteklenir. Bu yollar sohbet/IPC girdisinden alınmaz.

REA özeti `inspect-artifact ... --detail summary --evidence_output <özel-geçici-dosya> --json` ile alınır. Tam kanıt dosyası geçici çalışma klasöründe kalır ve temizlenir; kalıcı rapor yalnız doğrulanmış sayısal alanları, hedef/çıktı/kanıt hash'lerini taşır. Ham program metni veya REA stderr/stdout'u sohbet raporuna aktarılmaz.
