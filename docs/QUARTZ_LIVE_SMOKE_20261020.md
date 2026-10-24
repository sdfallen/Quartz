# Quartz canlı duman testi — 20 Ekim 2026

## Test edilen sürüm

- Çalışan uygulama: `dist/Quartz/Quartz.exe`, PID 17344, başlangıç 13:18:11 +03:00.
- EXE SHA256: `A733BF5F0E6440AE12FEB30E2C039C180E23632BF1E6331B8F2B96FB130B4B7E`.
- Bu EXE önceki teslimdeki F243... hash'inden farklıdır; eski EXE olarak sunulmadı ve üzerine yeniden dağıtım yapılmadı.
- PYZ içindeki `core.agent_chat`, `core.multi_agent_service`, `core.codex_runtime`, `core.antigravity_runtime`, `core.workspace_checkpoint`, `main`, `gui`: mevcut kaynak derlemesiyle 7/7 code-object eşitliği.

## Sonuçlar

| Kontrol | Sonuç | Gerçek gözlem |
|---|---|---|
| Güvenli regresyon | PASS | `python -B scripts/run_safe_tests.py`: 176 test, 14.819 saniye, exit 0 |
| Test runner bellek izolasyonu | PASS | Kaynak kökü `quartz_memory.json` hash'i test öncesi/sonrası aynı |
| Backend | LIVE VERIFIED | Loopback IPC health=ok, doğru PID, iki CLI authenticated/ready |
| UI erişilebilirlik | VERIFIED | Quartz metin ağacı okunabildi; İşlem Yetkisi=Salt Okunur, ÇEVRİMİÇİ |
| Görsel ekran yakalama | BLOCKED | İlk FrameArrived ve yeniden gözlem/aktivasyon sonrası window capture zaman aşımı; görsel çizim kalitesi doğrulanmadı |
| Codex tekli | AUTONOMOUS LIVE VERIFIED | Mevcut GPT-6-Luna/low ile 12.13 saniyede tam `QUARTZ_TEST_OK`, completed, read-only |
| Antigravity tekli | AUTONOMOUS LIVE VERIFIED | Mevcut Gemini 3.8 Flash Low/low ile 10.09 saniyede tam `QUARTZ_TEST_OK`, completed, read-only |
| Birlikte | AUTONOMOUS LIVE VERIFIED | 28.59 saniye; iki ajan, iki tur, dört completed yanıt; hepsi `QUARTZ_GROUP_OK` ve read-only |
| Onaysız proje yazma isteği | LIVE VERIFIED | Backend error: açık kullanıcı onayı gerekli; görev başlatılmadı |
| Onaysız tam-yetki isteği | LIVE VERIFIED | Aynı ret; sohbet mesaj sayısı değişmedi |
| Whitespace kontrolü | PASS | `git diff --check`, exit 0; yalnız LF/CRLF uyarıları |

Canlı model istekleri araç çağırmadan, dosya/komut kullanmadan yalnız test belirtecini döndürmeyi istedi. Gerçek uygulamanın mevcut IPC → chat → yerel CLI → sonuç yolu kullanıldı; sahte model yanıtı üretilmedi. Testler GUI üzerinden Codex CLI otomasyonu yerine mevcut uygulama IPC arayüzünden gönderildi. Model seçimi değiştirilmedi.

## Koruma ve sınırlar

- Ayrı test sohbeti: `fc2e156e202b4fa18f201c58e4e5db0d`, başlık `Quartz - 20 Ekim canli duman testi`.
- Test mesajları bu sohbet içinde saklandı. Önceki aktif sohbet seçimi geri yüklendi; eski mesajlar düzenlenmedi/silinmedi.
- Onaysız yetki ret denemeleri aktif sohbetin mesaj sayısını değiştirmedi.
- Mevcut kullanıcı uygulaması kapatılmadı. Test sonu aktif görev completed; çalışan kullanıcı uygulaması açık bırakıldı.
- Uygulama normal sohbet/run kayıtları oluşturabilir. Antigravity inceleme modu OS düzeyinde mutlak salt-okunurluk garantisi değildir.
- Bu oturumda gerçek modelle proje dosyası yazma veya tam-yetki görevi çalıştırılmadı. Yazıcı kilidi/checkpoint/geri okuma testleri regresyon kapsamındadır; bu sonuçlar gerçek modelin dosya düzenleme kabulü yerine geçmez.
- Warband başlatılmadı veya mod/kayıt dosyaları değiştirilmedi. Registry, Overlay, sürücü, izin ya da model ayarları değiştirilmedi.
- Sonuç temel bağlantı, grup mesaj akışı ve onay kapısının canlı doğrulamasıdır; uzun süreli ortak geliştirme, sistem izolasyonu veya bütün proje iş akışlarının kabulü değildir.
