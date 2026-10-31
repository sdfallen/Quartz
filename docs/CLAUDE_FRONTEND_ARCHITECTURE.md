# Quartz frontend mimarisi ve GUI ayrıştırma planı

Sahip: Claude (`claude/frontend-architecture`). Baseline: `59e3533`
(`codex/coordination-baseline-20261031`; ürün kaynağı `cba9972` ile aynı).

## 1. Başlangıç sınırı

`gui.py` (4.467 satır) tek dosyada beş katman taşıyordu:

| Katman | Konum (baseline) |
|---|---|
| IPC yardımcısı + `Api` pywebview köprüsü (77 public metot) | satır 28–893 |
| Doküman başı + temel tema CSS'i (~29,8 KB) | satır 894–1526 |
| HTML gövde işaretlemesi (~19,3 KB) | satır 1527–1842 |
| Uygulama JavaScript'i, tek script bloğu (~124 KB) | satır 1843–4414 |
| Asset enjeksiyonu (`workspace.css`, marka PNG) + `QuartzUI` bootstrap | satır 4421–4467 |

## 2. Bağlayıcı sözleşmeler

- **`gui._HTML`**: 21 test/betik birleşmiş dokümanı okuyor, çoğu Claude
  sahipliği dışında. Birçoğu JS'i işaret metinleriyle dilimleyip Node'da
  çalıştırıyor. Ad ve içerik korunur.
- **`scripts/check_gui_javascript.py`** (sahibi Claude değil) script bloklarını
  `gui.py`'nin **ham metninden** regex ile çekiyor. JS taşınırsa kontrol boş
  girdiyle geçer. `gui.py` yorumlarına da açılış script etiketi yazılmamalı,
  çünkü regex orada başlar.
- **`Quartz.spec`** (sahibi Claude değil) veri dosyalarını açık bir izin
  listesiyle paketler. `ui/` altındaki `.css/.js` dosyaları pakete girmez,
  Python modülleri ise `gui` import analizinden toplanır.
- **`Api` metot adları/payload'ları**: JS `window.pywebview.api.<ad>` ile çağırır.

## 3. Hedef sınır

```
gui.py            Api köprüsü + QuartzUI bootstrap + gövde/JS (_HTML_BODY) + _HTML
ui/document.py    build_document(): baş + tema + workspace.css + marka  [dilim 1 ✓]
ui/styles.py      BASE_CSS                                              [dilim 1 ✓]
ui/shell.py       HTML gövde işaretlemesi                               [dilim 2]
ui/app_js.py      uygulama JS'i, bölümlere ayrılmış                     [dilim 3]
core/ui_bridge.py Api yardımcıları                                      [dilim 5]
```

## 4. Dilim 1 (bu PR)

- Temel CSS, satır satır aynen `ui/styles.py` → `BASE_CSS` olarak taşındı.
- Doküman başı ve `_MEIPASS` farkında asset enjeksiyonu `ui/document.py` içine taşındı.
- `gui.py` yalnız gövdeyi ve JS'i (`_HTML_BODY`) tutuyor. `_HTML`, `_ASSET_ROOT`
  ve `_BRAND_MARK` adları korunuyor.
- Doküman byte'ı byte'ına aynı: SHA-256 `9cf9fc6d…c01d`, 193.008 karakter.
  Kaynak modda ve PyInstaller frozen stub'ında ölçüldü.
- Kalıcı sözleşme testleri: `tests/test_gui_frontend_boundary.py`.

## 5. Sonraki dilimler

| Dilim | İçerik | Ön koşul |
|---|---|---|
| 2 | HTML gövde → `ui/shell.py` | yok |
| 3 | JS → `ui/app_js.py` | `check_gui_javascript.py` `build_document()` çıktısını parse etmeli (integration request) |
| 4 | Gerçek `.css/.js` dosyaları | `Quartz.spec` datas + `verify_desktop_package.py`/`self_diagnostics` listeleri (integration request) |
| 5 | `Api` yardımcıları → `core/ui_bridge.py` | testlerin `gui.ipc_send` patch noktaları korunur |

## 6. Riskler

- **`ui` paket adı:** Gelecekte aynı adla bir pip paketi gelirse çakışabilir.
  Şu an bağımlılıklarda böyle bir paket yok.
- **Windows'a özgü testler:** Linux'ta koşmuyor. Paket ve WebView2 kabulü
  Windows'ta Codex entegrasyonunda yapılacak.
