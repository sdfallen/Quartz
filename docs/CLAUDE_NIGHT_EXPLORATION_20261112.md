# Gece keşfi: Quartz ajanları nerede daraltıyor? — 12 Kasım 2026

Kullanıcı isteği (11 Kas gece): "Neler yapabileceğimizi keşfet. Gece GPT ve Antigravity ile iletişime geçebilirsin."
Push, main'e birleştirme ve paket kurulumu yapılmadı. Taban: main `7f4d31f`.

## Varılan çerçeve

Codex CLI ve Antigravity (agy 1.5.6) kod okuma, yazma, test ve yeniden denemeyi zaten yapıyor. Quartz bunları
yeniden icat etmemeli; ajanlara geniş alan verip yalnız ajanların yapamadığını eklemeli (masaüstü, ajanlar arası iş
bölümü, güvenlik çerçevesi, ortak hafıza). Bu yüzden gece önce **gereksiz daraltmalar** arandı.

## Kısıt envanteri (koddan; Codex ve Gemini sahip görüşüyle)

| Kod | Bulgu | Karar |
|---|---|---|
| K1 | `message_intent` yalnız emir fiilini "görev" sayıyor; 13 günlük sorudan 12'si "sohbet". Sohbet turu boş geçici klasörde, araçsız çalışıyor: ajan projeyi göremiyor. | **En büyük daralma.** Prototiplendi (aşağıda). |
| K2 | Masaüstü ve korumalı yollarda Codex'in kabuk, web, görüntü, alt ajan, hafıza, MCP özellikleri kapalı. | Gözlemci için doğru; masaüstünde görüntü/okuma açılabilir (Gemini). Açık iş. |
| K3 | Antigravity sabit 10 dk (CLI varsayılanı 0 = bitene kadar). Kapı 4'te iş yarıda kesildi. | Göreve göre süre (Codex) vs kaldır (Gemini). Kullanıcı kararı. |
| K4 | Antigravity'de proje içi yazma yok; yazma = tam erişim. | **Doğru, korunmalı.** Canlı uyarı: "terminal sandbox bu makinede yok"; yerleşik yazma araçları sandbox'tan etkilenmiyor (Gemini de kabul etti). |
| K5 | Geçmiş: son 8 (oturumla 4) mesaj, mesaj başına 1500 karakter. | Seçici bağlam aktarımı (Codex) / sınırı büyüt (Gemini). Açık iş. |
| K6 | Birlikte modu 2 tur; araçsız sohbette 1 tur. | Varsayılan makul; derin incelemeye ek tur. |
| K7 | Yetenek yönlendirmesi tamamen regex. | Öneri katmanı; yetki kararı deterministik kalmalı. K1 düzelince zararı büyük ölçüde azalır. |
| D1 | Emir fiilsiz tek soru, ajanın sıcak oturumunu koparıyor. | Açık iş. |
| D2 | Birlikte modunda ajanlara "araç çağırma" deniyor; 2. turda birbirlerini dosyayla doğrulayamıyorlar. | Açık iş — proje okuma yolunun doğal devamı. |
| D3 | Antigravity istemi komut satırından: ~32 KB üstü Windows'ta başlatılamaz. | Açık iş (stdin/stream-json). |
| D4 | Masaüstü kancası Antigravity'nin MCP şema dosyasını okumayı engelliyor olabilir. | **Doğrulanmadı;** canlı sınavlarda masaüstü operatörü çalıştı. |
| P | İstemler "asla 'yetkim yok' deme, Tam Yetki kalıcı" diyordu. | **Zararlı (kanıtlandı, aşağıda).** Kaldırıldı. |

## Prototip: proje sorularına salt okunur okuma yolu

Dal `claude/project-read-20261112` (`6b8bcba` → `e29c38d`).

- Soru algısı: sohbet sayılan + proje/kod bağlamı (veya seçili projenin adıyla ilgili soru). Kavram soruları, selam,
  "dosyalara bakmadan", canlı ekran, yerel klasörler ve URL hariç.
- **Codex:** geçici klasörde, kabuk dahil bütün yerleşik araçlar kapalı; proje yalnız Quartz'ın çalıştırma başına
  eklenen `quartz_project` MCP sunucusundan (`list/read/search`) okunuyor. Kök, gizli dosyalar, junction, ikili dosya ve
  sonuç boyutu Quartz'ta zorlanıyor.
- **Antigravity:** geçici klasör + `--add-dir <proje>` + PreToolUse okuma koruması: yalnız açık yollu
  `read_file/view_file/list_dir`, proje içinde, gizli dosyasız. Gemini CLI arka ucunda kapalı.
- İstemler turun gerçek erişimini söylüyor.
- İnceleme döngüsü:
  - v1 `6b8bcba` → Codex "değişiklik gerekli" (kabuk proje dışını/`.env`'i okuyabilir, MCP katmanı, kilit sızıntısı,
    arama sonucu filtresi) + Gemini "koşullu kabul" (Gemini CLI yolo kaçağı, göreli yol, yanlış pozitifler).
  - v2 `e29c38d` → Gemini KABUL; Codex yine "değişiklik" (etkin MCP kümesi kanıtlanmıyor; okuma sunucusunda
    kontrol/kullanım yarışı; kancada araca özgü alan; kayıt artığı; "okumadan" ifadesi).
  - v3 `fb9d489` → Codex başlatmadan önce `codex mcp list --json` ile etkin sunucuları doğruluyor (canlıda eklentiden
    gelen `node_repl` yakalandı ve kapatıldı); okumalar açılan tanıtıcının gerçek yolu üzerinden doğrulanıyor.
  - v3 → Codex yine "değişiklik" (ön kontrol exec oturumuna bağlı değil; tanıtıcı sonrası yeniden çözümleme ve
    ada bağlı listeleme; ön kontrolde Stop).
  - v4 `faf7053` → klasörler tanıtıcıdan listeleniyor (`GetFileInformationByHandleEx`); bilinmeyen durumlu MCP satırı
    ret; Stop ön kontrolde ve başlatmadan hemen önce denetleniyor. Test, tanıtıcı tutmanın bu Windows'ta yeniden
    adlandırmayı engellemediğini gösterdi; çözüm buna göre seçildi. Codex'in v4 incelemesi bekleniyor.
  - **Açık risk:** `codex mcp list` ön kontrolü ayrı süreçte; gerçek `exec` oturumuna bağlanmadı. Arada yapılandırma
    değişirse görülmez (pencere saniyeler; aynı bayraklar exec'e de veriliyor).
  - Testler ayrıca bir junction sızıntısını ve iki kilit sızıntısını yakaladı.

## Yan bulgu (main'de, bu dalda düzeltilmedi)

Main'deki "araçsız sohbet" ve gözlemci yolları Codex MCP sunucularını yalnız kullanıcı `config.toml` adlarından kapatıyor.
Bu makinede eklentiden gelen `node_repl` (ve özellik bayrağına bağlı `cua_repl`) bu döngünün dışında kalıyor. v3'teki
etkin küme doğrulaması bu yollara da uygulanmalı.

## Canlı deney (aynı 4–5 soru, main'in kopyasında; kopya her koşudan sonra temiz)

| Yol | Codex | Antigravity |
|---|---|---|
| **main (eski istem)** | Dürüst: "göremiyorum, yapıştır" (5/5 yanıtsız) | **Uydurdu:** README'yi okumadan yanlış özetledi; süre sınırı için var olmayan "WaitMsBeforeAsync 500–10000 ms" verdi; "tüm dosyalarına erişimim var" dedi |
| Dürüst istem, araçsız | "Göremiyorum, görev olarak iste" | Aynı — uydurma yok |
| **Proje okuma v2** | **4/4 doğru**, satır kanıtlı, 0 kabuk komutu, 15–48 sn | **4/4 doğru**, satır kanıtlı, 20–246 sn |

v1 (kabuklu Codex) aynı soruları 47–152 sn'de yanıtlıyordu; v2'nin Quartz araçları 3–4 kat hızlı.

## Kanıt seviyesi

- SOURCE/TESTED: tam takım Ran 1760, OK (skipped=2) (v4); `tests/test_project_read.py` 34 test.
- LIVE v3 kısa kontrol: Codex 2/2, 0 kabuk; Antigravity 2/2 (2 komut denemesi kancada reddedildi); kopya temiz.
- BUILT: derlenmiş yardımcı (okuma koruması 7/7, MCP sunucusu protokol duman testi).
- LIVE (geliştirme koşusu, paket değil): yukarıdaki A/B; Quartz GUI'den uçtan uca denenmedi.
- Kurulu paket değişmedi (`259fb177…`).

## Sabah kararları

1. Proje okuma v2'yi PR + CI ile main'e almak (iki ajanın v2 sahip incelemesi sonrası).
2. "Asla yetkim yok deme" istemlerinin kaldırılması (kanıtlı uydurma önleniyor; kullanıcı tercihi buydu, onay gerekli).
3. Sıradaki dilim: D2 (Birlikte modunda proje okuma), K3 (Antigravity süresi), D3 (32 KB).
