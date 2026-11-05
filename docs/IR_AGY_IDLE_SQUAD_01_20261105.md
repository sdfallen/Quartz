# IR-AGY-IDLE-SQUAD-01 — uygulama

`MultiAgentService.status` artık boşta proje için Squad görüntüsünü önbelleğe
alır. DB + WAL inode/boyut/mtime değişimi anında geçersiz kılar. Aktif run veya
birlikte işi varsa cache kullanılmaz; aktiflikten çıkınca yeni okuma yapılır.
Hata/missing DB cache'e girmez. En fazla 300 saniyede tekrar okuma, yavaş sorgu
bitiminden başlar. Dışarıya derin kopya döner; sonuç yazılarak cache bozulamaz.

Bu sadece ekrana sunulan liste önbelleğidir. Dispatch/izin/yazıcı/bağlantı
kararlarında kullanılmaz; ikinci otorite oluşturmaz. Sorgu sırasında değişen
DB cache'e alınmaz. Broker, UI ve Squad veri şeması değişmedi.

TESTED: `python -X utf8 -B scripts/run_safe_tests.py tests.test_squad_idle_cache
tests.test_multi_agent_service tests.test_runtime_efficiency_idle_snapshot`:
32 test, 0 skip, PASS (beş yeni cache testi; import edilen mevcut suite dahildir).

600 saniyelik önce/sonra gerçek alt süreç sayımı özel kanıt dizinine yazılır;
son ölçüm teslim raporuna eklenecektir. Bu doküman ölçüm tamamlanmadan bir süreç
azalması, FPS veya CPU kazancı iddia etmez. Grafik arayüz açılmadı; model çağrısı
engelli, yalnız gerçek salt okunur CLI/Squad sorguları kullanılıyor.
