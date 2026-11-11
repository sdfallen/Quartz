# Masaüstü eylem adları: canlı hata ve düzeltme (6 Kasım 2026)

Dal: `claude/desktop-act-alias-20261106`, commit `e9def44`, taban `main` `574f5ff`.

## Canlı bulgu

Kurulu paket `574f5ff` (`Quartz.exe` `94ebc627…`), görev `b873df4cf82746019528c8dbe9d4f032`:
"Not Defteri'ni aç ve 'deneme' yaz", operatör Gemini (`gemini-3.8-flash-high`), gözlemci Codex.

- Not Defteri açıldı, kart onaylandı, `desktop_focus` ve `desktop_observe` başarılı.
- `desktop_act` önce `action="type"`, sonra `action="input"` ile çağrıldı; ikisi de `Unsupported action` ile reddedildi
  (araç şemasındaki enum: `click, text, key, hold, ui`). Hata geçerli adları söylemiyordu; model yeniden denemedi,
  görev kullanıcı Durdur'a basana kadar bekledi (`cancelled`, `NOT VERIFIED`, temizlik `completed`).
- Koşuda `unauthorized_readonly_write` yok. R2 için ikinci canlı deneme (yazma izinsiz proje incelemesi) yapılmadı.

## Değişiklik

| Dosya | Değişiklik |
|---|---|
| `core/desktop_broker.py` | `ACT_ALIASES` ve `_canonical_act`: `type/input/type_text/write → text`, `press/key_press/keypress → key`. Snapshot kimliği ve bayatlık kontrolünden sonra, tekrar korumasından ve denetim kaydından önce uygulanır. Bilinmeyen adlar değişmeden geçer. |
| `core/desktop_native.py` | Bilinmeyen eylem hatası geçerli eylemleri ve yazma yolunu söyler. Yalnız modelin gönderdiği adı (en çok 40 karakter) yansıtır, ekran içeriği içermez. |
| `tests/test_desktop_broker.py` | 2 yeni test: eşanlamlılar korumalı `text` eylemine ulaşır ve kayıtta `text` görünür; takma ad snapshot kontrolünü atlatmaz. İlki düzeltme geri alınınca başarısız olur. |

## Kontroller

| Komut | Sonuç |
|---|---|
| `python -B scripts/run_safe_tests.py tests.test_desktop_broker` | 51 test OK |
| Aynı testler broker değişikliği geri alınmış | 1 başarısız |
| `python -B scripts/run_safe_tests.py` (tam) | 1405 test, 2 atlandı, OK |
| `python -B scripts/audit_publish.py --history` | bulgu yok |

## İnceleme istisnası

Geçici devir kuralına göre Claude'un üretim kodunu Gemini inceler. Kullanıcı bu değişiklik için "sen hallet" dedi;
Gemini incelemesi beklenmeden Claude öz incelemesiyle `main`'e alındı. Gemini sonradan inceleyebilir; bulgu çıkarsa
ayrı düzeltme yapılır.

## Düzeltilmeyen gözlemler

- Görev kaydında proje `aster-warband` (rafa kaldırılmış, `protected`) görünüyor ve temizlikte `warband` adımı var.
  Masaüstü görevinin neden bu projeye bağlandığı incelenmeli.
- Gözlemci Codex, `task_context` ile `task_message` yanıtlarında farklı görev kimlikleri gördüğünü ve operatör
  mesajlarını alamadığını bildirdi.
- `task-state.json` iptalden sonra `running` olarak kaldı; `paused_contexts` yalnız `awaiting_approval` okuduğu için
  şu an etkisiz.
