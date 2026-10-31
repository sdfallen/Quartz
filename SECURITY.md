# Güvenlik politikası

## Desteklenen sürüm

Quartz henüz kararlı bir sürüm yayımlamadı. Güvenlik düzeltmeleri yalnız
`main` dalının güncel kaynak ağacına uygulanır.

## Açık bildirme

Güvenlik açığına; API anahtarı, OAuth/CLI oturumu, yerel dosya erişimi,
masaüstü kontrolü, izin atlatma, UAC, WebView profili veya uzaktan komut
çalıştırma dahilse ayrıntıları public issue olarak paylaşmayın.

GitHub reposundaki **Security → Report a vulnerability** özel bildirim yolunu
kullanın. Private vulnerability reporting etkin değilse yalnız hassas olmayan
özetle bir issue açıp proje sahibinden özel iletişim kanalı isteyin. Gerçek
anahtar, parola, kullanıcı verisi veya çalışır exploit eklemeyin.

Raporda şunlar yararlıdır:

- Etkilenen commit ve Windows sürümü
- Beklenen ve gözlenen davranış
- En küçük tekrar üretme adımları
- Etkilenen veri/yetki kapsamı
- Varsa kişisel veri içermeyen log veya test

## Güvenlik sınırları

Quartz'ın “Tam Yetki” seçeneği Windows yönetici yetkisi değildir. UAC istemini
kullanıcı onaylar; Quartz güvenlik mekanizmalarını devre dışı bırakmamalı veya
yükseltilmiş pencereye doğrulanmamış girdi göndermemelidir. Ekrandaki içerik
güvenilir talimat sayılmaz ve masaüstü eylemi taze gözlemle doğrulanmalıdır.
