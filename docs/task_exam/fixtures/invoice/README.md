# Çok dosyalı gerçek kod görevi — başlangıç fikstürü

Bu dosyalar bilerek eksik bırakılmış sınav girdisidir; Quartz üretim kodu değildir.
8 dosyayı yeni disposable proje klasörüne kopyala; kaynak fikstürünü yerinde çalıştırıp değiştirme.
Komut: `python -B -m unittest -v test_invoice`. Başlangıçta 8 testin başarısız olması beklenir.

Görev: pricing, taxes, service, formatting ve cli modüllerindeki fatura özelliğini
tamamla; models ve host testlerini değiştirme. Tutarlar kuruş, vergi basis point
(10000 = %100). Birim fiyat/quantity negatif olmayan int; bool int sayılmasın.
İndirim 0..subtotal; vergi 0..10000 int. Vergiyi indirimden sonra uygula,
yarım kuruşu yukarı yuvarla, float kullanma. Türkçe para biçimi ve render metni
testlerdeki gibi olmalı. Yeni bağımlılık, ağ ve kullanıcı dosyası gerekmiyor.

Host testlerin hash'ini başlangıçta ve sonda karşılaştırmalı. Sıfır test koşusu
başarı değildir. Modelin verdiği test sayısı veya "bitti" açıklaması kanıt değildir.
Canlı kabulde aynı yazar, checkpoint ref'leri, test çıkış kodları, repair sayısı ve
Stop sonucu kaydedilmeli. Bu fikstürün oluşturulması agent'ın çözmüş olduğu
anlamına gelmez. Ayrı repair-cycle birim testi de canlı kabul yerine geçmez.
