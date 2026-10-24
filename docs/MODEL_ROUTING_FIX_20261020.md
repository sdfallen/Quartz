# Agent Center model aktarımı düzeltmesi — 20 Ekim 2026

## Teslim

Kaynak düzeltildi, EXE üretildi ve kullanıcının açık yeniden başlatma izniyle
`dist/Quartz/Quartz.exe` güncellendi. Yeni Quartz PID12108 olarak açıldı.

EXE SHA256: `2E4AEEB69B071F2389667C4E7A44653127289D1E187528CC53C9C53E695586D7`.

## Değişiklik

- GUI, Agent Center çağrısında iki model/düşünme seçiminin anlık kopyasını
  gönderir. Tek ajan çağrıları da seçili model/effort ile başlar.
- Eski/API istemcisi bu alanları göndermezse backend ilgili sohbetin kayıtlı
  model seçimini okur; CLI kullanıcı varsayılanına bırakmaz.
- Eksik/geçersiz açık seçim hata verir. Collaboration iki seçimi de doğrular ve
  görev başında kopyalar; analiz/sentez aynı Codex seçimini, review ve varsa
  güvenli permission-retry aynı Antigravity seçimini kullanır.
- Provider kota hatasında model değiştirilmez, yetki yükseltilmez, permission
  fallback denenmez. Error alanı provider, istenen model, effort, aşama ve gerçek
  runtime hata nedenini taşır; bütün hesabın kotası tükenmiş gibi genellenmez.
- Agent Center çalışma satırlarına istenen model/effort ve collaboration seçim
  özeti eklendi. Bunlar backend model alias'ı çözümlemesi değil, gerçek gönderilen
  CLI seçimleridir.
- İlk Codex prompt'u yalnız ilk analiz rolüne sınırlandı; gerçek reviewer'ı ve
  sonraki aşamaları host'un başlatacağı açıklandı. Son sentez bağımsız okuma
  yoksa bu sınırlamayı korur. Bu prompt koruması tek başına başarı kanıtı değildir.

CLI seçimini açık aktarma yolu [resmî CLI seçenekleri](https://learn.chatgpt.com/docs/cli/reference)
ve [ayar önceliği](https://learn.chatgpt.com/docs/developer-settings) doğrulamasıyla
uyumlu tutuldu. Global Codex/Antigravity hesap veya model ayarı değiştirilmedi.

## Doğrulama

| Katman | Sonuç / kanıt |
|---|---|
| SOURCE/STATIC | 189 test PASS,15.638s; `scripts/run_safe_tests.py`; gerçek model testi değil |
| Güvenli test belleği | Kaynak kökü quartz_memory.json hash'i test öncesi/sonrası aynı |
| CLI argüman testleri | Codex -m ve model_reasoning_effort; Antigravity --model/--effort; izinler korunuyor |
| GUI JS sözdizimi | UTF-8 stdin ile node --check PASS |
| BUILT | PyInstaller başarı; yedi kritik PYZ code object güncel kaynak derlemesine eşit |
| GUI canlı erişilebilirlik | Yeni süreçte GPT-6-Luna/low, Gemini3.8FlashLow/low, Salt Okunur görüldü |
| AUTONOMOUS LIVE | Üç gerçek aşama completed, yaklaşık66.4s; aşağıdaki kayıt |

İlk JS kontrol yardımcı aracı Windows cp1254 Unicode hatasında takıldı; bu bir
uygulama JS hatası değildi. Yalnız kimliği doğrulanan kendi node --check çocuğu
sonlandırıldı, UTF-8 ile tekrar kontrol0 oldu. İlk GUI close tıklaması geometry
hatası verdi; yeni gözlem/aktivasyon ardından Alt+F4 ile normal kapandı. Eski
Quartz PID17344'ün gerçekten sonlandığı dağıtımdan önce CIM ile doğrulandı.

## Gerçek yeni EXE testi

Collaboration `bf5a2697f46743b4aa39a7715023f7f4`, izole ASTER test kopyası.
API isteğinde models alanı özellikle gönderilmedi: kayıtlı sohbet seçimine
fallback ve yeni backend yolu doğrulandı.

1. Codex `5514ca616cd34e12ab36f8215d902695`: **gpt-6-luna/low**, completed;
   gerçek salt-okunur komutla parley_contract.py incelendi.
2. Gemini `a2e9269d844643278b9cf6baa944de00`: **gemini-3.8-flash-low/low**,
   completed; gerçek read_file ACTIVE→DONE, parley_contract.py/StartLine50/
   EndLine75. Yalnız önceki raporu tekrarlamak yerine bağımsız kaynak okuması
   host araç kaydıyla doğrulandı.
3. Codex `de7464a6c3fc4b19b48fae1f55804965`: **gpt-6-luna/low**, completed;
   gerçek Gemini raporundan son sentez üretildi. Üç run'da files_changed boş.

Bu çağrıda429 oluşmadı. Önceki varsayılan çağrının hangi model/hesap kotasına
takıldığı geriye dönük kesinleşmiş veya o kota sıfırlanmış sayılmıyor.

Ham kabul kaydı: `labs/warband-review-20261020/model-routing-fix-live.json`.
Bu kaynak inceleme kabulüdür; Warband build'i, oyun testi veya üretim moduna
yazma yetkisi değildir. Gate B'nin durumu değiştirilmedi.

## Yedek ve koruma

- Önceki kirli kaynak/test kopyaları:
  `C:\Users\LENAVO\.codex\backups\quartz-model-routing-20261020-151039`.
- Eski dağıtım tamamıyla korunuyor:
  `C:\Users\LENAVO\.codex\backups\quartz-before-model-routing-20261020-152200`.
- Build/test/deployment/closing kayıtları:
  `C:\Users\LENAVO\.codex\backups\quartz-model-package-20261020-151623`.
- Taşınan6kullanıcı dosyası başlatmadan önce hash-eşit. Çalışan uygulamanın
  assistant.log dosyası kilitli olduğu için son hash'i okunamadı; diff0 sayılmadı.
  quartz_entry.log normal başlangıç/çıkış nedeniyle değişti.
- Önceki izole testin registry seçimi test kopyasında kalmıştı; asıl legacy
  Squad Pilot sohbeti ve gerçek squad-pilot proje seçimi geri bırakıldı.
  quartz_projects.json değişimi bu seçim temizliğidir; liste karşılaştırması
  ayrıca closing-integrity.json içinde kayıtlıdır.
- Kaynak kökündeki8kullanıcı dosyası hash fark0; seçili18orijinal Warband dosyası
  fark0;9save fark0; oyun süreç0; shared battle_size3.9167. Yeni lease/save yok.
- .env/histories silinmedi; mevcut dirty değişiklikler resetlenmedi. Registry,
  güvenlik, Overlay, sürücü, global model/hesap, Native ve save izni değişmedi.

Değişen üretim kaynakları: core/agent_chat.py, core/multi_agent_service.py,
main.py, gui.py. Testler: yeni test_model_routing.py ve mevcut üç test dosyası.
Gerçek provider limitleri uygulama tarafından kaldırılamaz; bu düzeltme doğru
seçimi aktarır ve hata kapsamını doğru görünür kılar.
