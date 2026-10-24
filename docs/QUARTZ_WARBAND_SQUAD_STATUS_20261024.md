# Warband proje seçimi / Squad göstergesi

Kök neden: `MultiAgentService.status` genel projelerde olduğu gibi
`C:/WarbandIsland/.squad` veritabanını sorguluyordu. Korunan Warband akışında
`NaturalDesktopTask`, mod klasörüne yazmamak için her görevde kanıt klasöründe
ayrı Squad veritabanı oluşturur. Proje özeti bu tasarımı tanımadığı için görev
başlamadan bağlantı sorunu gösteriyordu. Kurulu gerçek CLI: squad 0.7.6.

- Proje seçimi şimdi `task-isolated` durumunu döndürür; CLI hazırsa
  **Squad: Görevle bağlanır** yazar. Henüz veritabanına bağlı olduğunu iddia etmez.
- Gerçek görev başlangıcında DB, agent join, task create/ack işlemlerinden
  alınan bağlantı bilgisi arayüze aktarılır. Yalnız o sohbetin aktif görevinde
  **Bağlı** yazılır ve gerçek DB yolu açıklamada bulunur.
- Görev sonlanınca/sohbet değişince eski görevin bağlantısı kullanılmaz.
- CLI eksikliği veya gerçek görev DB hataları gizlenmez. Genel projelerdeki
  bağlantı hatası davranışı ve korunan projenin genel yazma engeli değiştirilmez.
- Yeni root DB, genel yetki yükseltmesi, mod kaynak/kayıt değişikliği yoktur.

`tests/test_warband_squad_status.py`: idle/active/error ve sohbet kapsamı testleri.
Gerçek bağlantı testi `scripts/warband_squad_status_acceptance.py`, yalnız
yerel disposable kanıt klasöründe kurulu Squad CLI ile init/join/task/send/receive
yapar. Model veya oyun başlatmaz; bu test canlı ajan/görüşme kabulü değildir.
İlk test düzeneğinde Thread mock'u subprocess okuyucularını da etkiledi;
düzeneğin bu müdahalesi kaldırıldı ve gerçek komutlar başarıyla tamamlandı.
Başarılı kanıt: `labs/warband-squad-20261024-135358/acceptance.json`.

## Son doğrulama ve dağıtım

- İkinci gerçek CLI kanıtı idle/task ayrımını da kaydeder:
  `labs/warband-squad-20261024-135632/acceptance.json`.
- Son regresyon: 361 test PASS, gömülü JavaScript PASS.
- Paket kod/imza, yardımcı araç şeması, CSS ve Q ikon kontrolleri PASS;
  `core.multi_agent_service` de paket kaynak eşleşmesine dahil edildi.
- Kurulu EXE SHA256:
  `f08fe876ce9b0932586afa5d4b377480213bb15eaf0308dd35503bfaff2732ab`.
  Dağıtım kanıtı:
  `C:/Users/LENAVO/.codex/backups/quartz-warband-squad-package-20261024`.
- Önceki dağıtım `quartz-before-desktop-bridge-20261024-140258` yedeğinde.
  Yerel kullanıcı verileri dağıtım öncesi/sonrası eşleşti.
- Gerçek açılmış Quartz penceresinin erişilebilirlik verisinde seçili proje
  `ASTER · Warband / Universal Modder`, gösterge `Squad: Görevle bağlanır`
  ve açıklaması ayrı görev veritabanını doğruladı. Bu UIA kanıtıdır;
  GPU ekran yakalama zaman aşımı nedeniyle piksel bazlı görsel QA iddia edilmez.
- Kullanıcının gönderilmemiş taslağı `Bu warband modunu inceleyin` normal UIA
  alanına geri kondu, tekrar okundu; Gönder'e basılmadı veya görev başlatılmadı.
- ASTER kökünde `.squad` yok; gameplay scripts SHA256 değişmedi:
  `27d6f9b7612e942f02e274dd967de6eba1d4afbb27ef268b2fa2277506345d60`.
