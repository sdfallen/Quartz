# Integration request — A-02: Stop, sahip olunan süreci sonlandırmıyor

Tarih: 3 Kasım 2026. Kaydeden: Claude. Sahip: Antigravity (`core/process_tree.py`).
Son birleştirme: Codex. İncelenen commit: `05890c7`
(`codex/rea-chat-review-20261102`). Bu dalda üretim kodu değişmedi.

Kanıt seviyesi: SOURCE + TESTED (mock). Gerçek süreçte AccessDenied üretilmedi;
BUILT veya LIVE VERIFIED değildir.

## Neden

`stop_process_tree` içinde `parent.children(recursive=True)` veya kök süreç
kimliği okuması `psutil.Error` verirse kod `False` döner, ama hiçbir süreci
sonlandırmaz. Eski yanlış başarı sonucu giderilmiş; A-02'nin Stop yarısı açıktır.

`wait_for_owned_cleanup`, kök süreç canlıyken yalnız bekler. `stop_process_tree`
yalnız kök çıktıktan sonra tekrar çağrılır. Bu nedenle keşif başarısız olursa
izleyici, süreç kendiliğinden çıkana kadar sürer.

Mock Popen ile ölçüm (gerçek süreç oluşturulmadı, izleyici 5 turda kesildi):

```json
{"stop_returned": false, "terminate_after_stop": 0, "watcher_ticks": 5,
 "watcher_returned": false, "children_rediscovery_calls": 1,
 "owned_terminate": 0, "owned_kill": 0}
```

## Çağrı noktaları

`core/process_tree.py` son `except (psutil.Error, OSError)` dalı. Etkilenen
çağıranlar:

- `core/codex_runtime.py`, `core/antigravity_runtime.py`: iptal ve zaman aşımı.
- `core/rea_adapter.py`: iptal, çıktı sınırı ve son tarih.
- `core/warband_workspace.py`: rafa kaldırılmış legacy kod; değiştirilmemeli.

## Önerilen küçük sözleşme

Keşif başarısız olsa da doğrulanmış Popen üzerinden kök süreç sonlandırılmaya
çalışılır. Alt süreçler bilinmediği için sonuç yine `False` kalır; ham PID
kabul edilmez.

```python
    except (psutil.Error, OSError):
        # Discovery/verification failure is uncertainty, not confirmed cleanup,
        # but the Popen handle still proves ownership of the root process.
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return False
```

Bu öneri yalnız `05890c7`'nin geçici kopyasında denendi:

- Aynı senaryoda `owned_terminate` 1, sonuç `False`. Mock süreç çıkmadığı için
  `owned_kill` de 1 oldu.
- `process_tree` kullanan 5 test modülü: 39 test, başarısız yok.

**Açık sınır:** Keşif reddedilirse torunlar envantere girmez ve bu düzeltme
onları sonlandırmaz. Kök çıktıktan sonra bilinen alt süreç kaydı yoksa izleyici
biter. Bu durumun bildirilmesi gerekip gerekmediği sahibin kararına bırakılır.

## Sahibin yapacağı değişiklik ve test

1. Yukarıdaki dalı veya eşdeğerini `core/process_tree.py` içine uygula.
2. `tests/test_process_tree.py` içine hedefli test ekle:
   - `children()` AccessDenied: terminate çağrılır, sonuç `False`.
   - `psutil.Process()` NoSuchProcess, kök Popen canlı: aynı beklenti.
   - terminate sonrası zaman aşımı: kill çağrılır, sonuç `False`.
   - terminate/kill `OSError`: istisna dışarı sızmaz.
3. Tam Windows suite'i çalıştır, gerçek test adedini teslimde yaz.

## Bu kayıtla birlikte eklenen rapor

`docs/CODEX_ORCHESTRATION_DELIVERY_REVIEW_20261101.md`, 1 Kasım tarihli
tarihsel kayıttır; içeriği değiştirilmedi. Bulgularının `05890c7` durumu:

| Bulgu | Durum | Dayanak |
|---|---|---|
| A-01 | Kapalı | Mock saat ve Event: takılı sorguda 1 deneme; proje değişiminde eski sonuç yeniyi ezmedi |
| A-02 | Kısmen açık | Bu belge |
| A-03 | Kapalı | Ham integer PID `AttributeError` verdi, terminate çağrılmadı |
| A-04 | Kapalı | Geçici dizinde 48 saat sınırından genç üç log silinmedi; boyut sınırı artık silme koşulu değil |
| A-05 | Eski iddia düştü | Eski ölçüm betikleri kaldırılmış; yeni betik değerlendirilmedi |
| A-06 | Kapalı (SOURCE) | `core/low_spec_optimizer.py`, `gui.py` ve `ui/` içinde profil sözlüğü bulunmadı |

Kurulu EXE, GitHub PR'ları ve canlı Stop davranışı bu kayıtta denetlenmedi.
