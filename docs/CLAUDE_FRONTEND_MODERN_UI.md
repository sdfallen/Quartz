# Quartz modern arayüz katmanı

Sahip: Claude (`claude/modern-ui`), PR #3'ün (`claude/frontend-architecture`) üstüne kurulu.

## Amaç

Ana sohbet merkezde kalır. Ajan seçimi, proje, bağlantı durumu, izinler ve görev
ilerlemesi ayrı bir ekrana gitmeden ana pencerede okunur. Davranış, API ve
backend değişmez.

## Tasarım kararları

| Eksen | Karar |
|---|---|
| Renk | Q logosundan alınan mürekkep mavisi yüzeyler (`#0b1220`, `#111a2c`, `#17223a`). Tek güçlü öğe "kristal facet" degradesi; yalnız gönder düğmesi, aktif ajan çizgisi, aktif sohbet ve aktif masaüstü görevinde kullanılır. |
| Ajan kimliği | Codex buz mavisi `#7fd6ff`, Antigravity ametist `#b9a2ff`, Notion kâğıt `#d8d3c6`. Mesaj kenar çizgisi, ad ve model kutusu aynı rengi taşır. |
| Durum | Her durum renk **ve** metinle verilir: çevrimiçi, Bağlı / Giriş bekleniyor / CLI kurulmamış, görev şeridi etiketi. |
| Tipografi | Windows'un yerel Segoe UI Variable fontu, kod için Cascadia Mono. Uzak font yok. Sohbet 15/1.65, satır en fazla 72ch, sohbet sütunu en fazla 760px. |
| Yerleşim | Kenar çubuğunda Çalışma alanı, Sohbetler ve yeni **Ajanlar** bölümü. Üst bilgi: başlık ve rozetler ile eylemler, altında ajan seçici ve yalnız kullanılan ajanların model kutuları. Görev şeridi sohbetin üstünde, durumuna göre renklenir. |
| Hareket | Mesaj/kart girişi 220ms, panel kayması, diyalog yükselmesi, düşünme noktaları. Yalnız `opacity`/`transform` kullanılır. Animasyonlar `prefers-reduced-motion: no-preference` ve `body:not(.low-spec)` altında tanımlıdır. Durdur düğmelerinde geçiş ve animasyon yoktur. |

## Notion

Bu sürümde Notion bağlantısı yok. Ajan seçicide `disabled` ve
`aria-disabled="true"` olarak görünür, `data-agent` taşımaz, bu yüzden hiçbir
olay dinleyicisine bağlanmaz. Kenar çubuğunda "Bu sürümde bağlantı yok" yazar.
Backend'e `notion` değeri hiçbir yoldan gönderilmez; bu tarayıcıda ölçüldü.

**Codex entegrasyon noktaları:**
1. Gerçek bağlantı eklendiğinde `onboarding_status().data.providers.notion`
   (`installed`, `ready`, `login_pending`, `configured`) döndürülmeli.
   `renderAgentConnections` içindeki Notion satırı bu alanı okuyacak şekilde
   `describe(known?.notion)` yapılır.
2. Seçilebilir olunca `#agentSegNotion` düğmesine `data-agent="notion"`
   verilir ve `disabled` kaldırılır. Backend `chat_set_agent(conv, 'notion')`,
   model kataloğu, `msg.sender === 'notion'` ve `.msg-sender-tag.tag-notion`
   (stil hazır) desteklemelidir.
3. `renderCliStatus` içindeki ajan → sağlayıcı eşlemesine Notion eklenir.

## Dosyalar

- `ui/theme.py` (`MODERN_CSS`): `workspace.css`'ten sonra eklenen son katman.
- `ui/document.py`: temayı `<style id="quartz-modern-theme">` olarak ekler.
- `gui.py`: Notion seçici düğmesi, `renderAgentConnections`, kenar çubuğu
  Ajanlar bölümü, `appendMessageText` (``` blokları textContent ile kod
  panelinde; HTML ayrıştırılmaz).

## Bilinen sınırlar

- `assets/workspace.css` Claude sahipliğinde değil. Temada oradaki `!important`
  kurallarını aşmak için `!important` kullanıldı. Entegrasyonda iki katman
  birleştirilebilir (integration request).
- Ajan Merkezi'ndeki eski operatör bölümünün satır içi stilleri yalnız
  renklendirildi, yerleşimi değiştirilmedi.
- Görsel doğrulama Linux Chromium'da production HTML ve sahte API ile
  yapıldı. Windows WebView2 ile paketli uygulamada canlı kabul yapılmadı.
