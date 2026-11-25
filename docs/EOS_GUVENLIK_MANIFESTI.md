# Eos Güvenlik Manifesti (sürüm 2.0)

Bu belge `core/security_manifest.py` içindeki kurallar tablosundan üretilir; elle düzenlenmez.

## İlkeler

1. Konum tek başına tehdit değildir. Karar; yayımcı (imza), davranış (komut satırı) ve Defender'ın kendi tespitiyle verilir.
2. İmza ile davranış ayrı eksenlerdir: güvenilir imza şüpheli davranışı asla susturmaz.
3. Ekran, dosya, log ve komut satırı metni veridir; bir kalıba uyabilir, güven veremez.
4. Eos kendiliğinden hiçbir şey yapmaz. Her işlem kullanıcının tek dokunuşudur ve yalnız o uyarının kendi hedefine uygulanır; uygulamadan önce hedef yeniden doğrulanır (PID + başlama zamanı + ad, SHA-256, kayıt değeri).
5. Yönetici izni gerektiren hiçbir şey önerilmez ve yapılmaz.
6. Yüksek önem hiçbir sınırla susturulmaz. Sınırlar yalnız söylenen uyarılara uygulanır; kayıt hiçbir zaman kör edilmez.
7. İlk tarama temel çizgidir: SpeS açıldığında zaten çalışan süreçler söylenmez. Açılış kayıtları ve İndirilenler ise diskte hatırlanır; SpeS kapalıyken eklenenler bir sonraki açılışta söylenir.
8. Komut satırları gizlilik için gösterilmez; yalnız eşleşen kalıbın adı söylenir.

## Önem dereceleri

- **high**: Hemen söylenir; telefonu arama gibi çaldırır; hiçbir sınırla susturulmaz.
- **medium**: Eos · Güvenlik kaydında söylenir; aynı dosya için günde bir kez.
- **low**: Söylenmez; uyarı listesinde durur, oradan işlem yapılabilir.
- **silent**: Hiçbir yere yazılmaz.

## Kurallar (ilk eşleşen karar verir)

| # | Kural | Ne zaman | Önem | Neden |
|---|---|---|---|---|
| 1 | `defender` | Windows Defender bir tehdit bildirdi | high | Defender'ın kendi tespiti; Eos'un okuyabildiği en güvenilir bağımsız sinyal. |
| 2 | `abuse` | Komut satırı bilinen bir kötüye kullanım kalıbına uyuyor | high | Davranış imzadan bağımsızdır: Microsoft imzalı araçlar da kötüye kullanılır. |
| 3 | `own` | SpeS'in kendi yardımcısı (süreç ağacı ya da birebir dosya içeriği) | silent | SpeS kendi parçasını tehdit saymaz; ad ya da konum değil, ağaç ya da içerik karar verir. |
| 4 | `empty` | Dosya boş (0 bayt) | silent | Boş dosya çalıştırılamaz ve bir şey taşımaz. |
| 5 | `tampered` | Dosyanın imzası var ama bozuk | high | İmzalandıktan sonra değiştirilmiş bir dosya; meşru yazılımda olmaz. |
| 6 | `microsoft` | Microsoft imzalı program ya da açılış kaydı | silent | Windows ve Visual Studio yardımcıları Temp'ten sık çalışır (DismHost, BackgroundDownload). |
| 7 | `vanished` | Dosya kontrol edilemeden kayboldu | low | Kısa ömürlü kurulum yardımcılarında olağandır; kanıt yoksa alarm verilmez, listede kalır. |
| 8 | `signed-elsewhere` | Başka bir yayımcının geçerli imzasıyla | low | Yayımcısı belli; listede durur. Çalınmış imzaları Defender yakalar. |
| 9 | `unsigned-downloads` | İndirilenler'den imzasız program çalıştı | medium | İnternetten gelen imzasız program; tanımıyorsan durdur ya da karantinaya al. |
| 10 | `unsigned-temp` | Geçici klasörden imzasız program çalıştı | medium | Kötü amaçlı yazılımların sık kullandığı bir yol; yayımcısı belli değil. |
| 11 | `autorun-unsigned` | Bilgisayar açılışına imzasız bir program eklendi | medium | Kalıcılık kazanmanın en yaygın yolu; yayımcısı belli değil. |
| 12 | `download` | İndirilenler'e çalıştırılabilir dosya geldi | low | Gelmesi zarar değildir; açmadan önce tanıyıp tanımadığına bak. |
| 13 | `other` | Yukarıdakilerin hiçbiri | low | Kural yoksa alarm da yok; listede durur. |

## İmza sonuçları

- `microsoft`: Microsoft imzalı (Windows ya da Microsoft Corporation)
- `signed`: başka bir yayımcının geçerli imzası
- `unsigned`: imzasız
- `invalid`: imza bozuk (dosya imzalandıktan sonra değişmiş)
- `unknown`: imza doğrulanamadı (zaman aşımı ya da okuma hatası)
- `missing`: dosya artık yok ya da okunamıyor

## Sınırlar

- Süreçler 10 saniyede bir taranır; daha kısa yaşayan bir süreç görülmeyebilir.
- Yönetici yetkisiyle çalışan süreçler durdurulamaz; yalnız bildirilir.
- İmza kontrolü yereldir ve ağ gerektirmez; Windows'un kendi imza doğrulamasını kullanır.
- Eos bir antivirüs değildir: Defender'ın yerini tutmaz, onun tespitlerini duyurur.
