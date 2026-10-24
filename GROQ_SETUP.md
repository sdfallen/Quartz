# Quartz Groq bağlantısı

> 16 Eylül 2026: Varsayılan sohbet sağlayıcısı yeniden NVIDIA'ya alındı.
> Bu belge yalnızca Groq yedek seçeneğinin kurulum notudur.

Sohbet ve komut modeli: `openai/gpt-oss-120b`.
API adresi: `https://api.groq.com/openai/v1`.

1. https://console.groq.com/keys adresinden kendi anahtarınızı oluşturun.
2. Güncel `dist/Quartz/Quartz.exe` uygulamasını başlatın.
3. Bağlantı panelinde Groq seçiliyken anahtarı girip doğrulayın.

Anahtar uygulamanın yanındaki `.env` dosyasına kaydedilir; kaynak klasördeki
`.env` farklıdır. Kaynak koddan başlatıyorsanız anahtarı kaynak klasöründe girin.
Groq seçiliyken anahtar eksikse NVIDIA'ya otomatik geçiş yapılmaz.
Mevcut ekran görüntüsü analizi NVIDIA sağlayıcısında kalır; bu değişiklik
yalnızca sohbet ve komut planlayıcısını Groq'a taşır.

Ücretsiz kota istek ve token sınırlarına tabidir. Canlı hız ve araç çağrısı
anahtar girilmeden doğrulanamaz. Anahtarınızı sohbette paylaşmayın.

## Kota iyileştirmesi

Groq isteklerinde kısa selamlaşmalar araçsız gönderilir. Görevlerde ilgili araçlar
seçilir; eksik araçlar `discover_tools` ile bulunabilir. Önceki konuşma son dört
mesajla sınırlanır; mevcut turun araç çağrı/sonuç eşleşmeleri korunur. Uzun araç
çıktıları açık bir kısaltma uyarısıyla sınırlandırılır. Saklanan geçmiş silinmez.
429 yanıtında Retry-After süresi izlenir, en fazla iki yeniden deneme yapılır.
60 saniyeden uzun beklemeler kullanıcıya bildirilir; kısa beklemeler iptal edilebilir.

12 Eylül canlı model testi (masaüstü eylemi yürütülmedi): naber 1,92 sn;
YouTube açma araç seçimi 0,30 sn; devam araması araç seçimi 0,28 sn.
Üç istekte 429 görülmedi. Bu ölçüm sürekli veya sınırsız kullanım garantisi değildir.
83 yerel test geçti. Güncel EXE kullanın; eski Setup bu iyileştirmeleri içermez.
