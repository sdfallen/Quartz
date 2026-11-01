# Quartz Local Tools — sınırlı salt okunur Worker

Bu Worker yalnız imzalı yerel test izninden istek üretir. Kullanıcının Windows
bilgisayarına bağlanmaz veya komut çalıştırmaz. `quartzReadTestFile` kuyrukta
requested kaydı oluşturur; `quartzReadResult` yerelde üretilmiş imzalı sonucu okur.
`queued` ve `pending` tamamlanmış yerel işlem anlamına gelmez.

Resmî `@notionhq/workers` SDK 0.9.5 ve kilitli bağımlılıklar kullanılır.

```powershell
npm ci --ignore-scripts --no-fund --no-audit
node node_modules/typescript/bin/tsc
node --test test/*.test.mjs
```

Deployment yalnız kullanıcı onayıyla resmî `ntn workers deploy` üzerinden yapılır.
Worker ID'si içeren workers.json ve secret ayarları commit edilmez.
QUARTZ_QUEUE_ID özel veri kaynağı ID'si, QUARTZ_BRIDGE_KEY 32 byte anahtarın hex
biçimidir. Anahtar yerelde Windows Credential Manager'dadır, bulutta yalnız Worker
environment secret olarak ayarlanır; modele ve Notion satırlarına verilmez.
NOTION_API_TOKEN kopyalanmaz: Worker'ın `context.notion` erişimi gerçek Custom
Agent tool çağrısında onun izinleriyle sağlanır. Ajanın kuyruğa erişimi ve Worker
bağlantısı ayrıca gerekir. `workers exec` ile bu yetkinin var olduğu varsayılmaz.

Prototype only: cron, webhook, shell, dosya yazma, ekran kontrolü, kaynak silme,
genel projelerde araç kullanımı veya yeni paylaşım yoktur. Mevcut Notion Worker
kullanım ücretleri geçerlidir. Canlı kabul raporu docs/notion-tools altında tutulur.
