# Claude — Quartz REA derin çözümleme ve motor bilgisi

İstenen model: Claude Opus5.5. Diğer iki uzmanla aynı ana görevde paralel çalışıyorsun. Sorumluluğun hafif review veya arayüz değildir: gerçek analysis engine senin alanın.

Önce docs/rea-system/TEAM_CONTRACT.md tamamını oku. Ortak dağıtım ve dosya sahipliği kuralları bağlayıcı proje sözleşmesidir; current user request üstündür. Ortak temiz base sözleşme commit'idir; bunu git rev-parse ile kaydet. Çalışma alanın C:/Users/LENAVO/.codex/worktrees/quartz-rea-claude. Desktop Jarvis config veya başka ajanın worktree'sinde yazma. Ortam uzaktaysa verilen aynı baseline bundle'ından ayrı branch aç; yerel teslimle birleştirmeyi Codex yapacak.

Sahip olduğun alanlar: core/rea_analysis/, tests/test_rea_analysis_*.py, labs/rea-analysis/, docs/rea-system/CLAUDE_REPORT.md. Ortak GUI, REA adapter, provider, installer veya package dosyasını doğrudan düzenleme.

Üretim hedefin:
- Mevcut dar EXE envanterinden ileriye giden gerçek native/managed/paketli uygulama adaptörleri. PE/native sembol/section/import/xref/function verileri, .NET/Unity Mono metadata ve paketli Python/Electron kaynak ilişkileri için desteklenebilir gerçek analiz yollarını araştır, en düşük riskli olanları uygula. Her desteklenen çıktı formatı gerçek tool çıktısıyla doğrulansın.
- Motor/runtime/modlama yüzeylerini (veri formatı, asset/paket yükleme, scripting/API sınırı, kaynak bağımlılığı) kanıtlı haritalandır. Unreal/Unity/Godot gibi isimlerin bir string'de görülmesi kesin motor/sürüm veya bütün motor semantiği sayılmaz. Bildiğin ile bilmediğini ayır.
- Büyük native engine varsa yalnız gateway üzerinden kullan; doğrudan otomatik setup/injection/system install yazma. Gerekli araç şartlarını Gemini'nin workbench resolve/acquire sözleşmesine ilet.
- Soruya yönelik hipotez üretimi ve çürütme/kanıt bağlantısı, fonksiyon/kaynak ilişkilerinin sürümlenebilir çıktısı. Gerçek UI davranışından gelen gözlemleri statik çıkarımdan ayrı tut; analysis engine keyfi kullanıcı verisini taramasın.
- AnalysisService.capabilities/analyze ve ortak JSONv1 sözleşmesini çalışır facade olarak teslim et. Codex'in mevcut lifecycle/knowledge owner'ının yerine kendi global runtime veya memory servisini oluşturma.

Kendi gerçek kabulünü üstlen: yerel yeniden dağıtılabilir/üretilmiş native örnek, managed örnek, paketli örnek ve en az bir açık motorla modlama açısından somut deney. Varlığını doğrulamadığın araç varmış gibi davranma; eksik environment için gerçek acquisition requirement ver, bağımsız diğer yolları bitir. Test fixture'ın beklenen cevabını LLM promptuna koyarak sonuç üretme. Statik rapor, decompile, canlı gözlem ve uygulamanın gerçek düzeltme testi farklı kanıtlardır. UI operatör çakışması için Codex ile sıra ayarla; tek fare/klavye kuralını koru.

Çalışmayı plan/metin/mock seviyesinde bırakma. İlgili üretim kodu, gerçek araç testleri, olumsuz/unsupported/sürüm değişimi testleri ve kanıtları tamamla. Değiştirdiğin sonuçların kaynak sınırını kontrol et. Bitince commit ve yalnız kendi alanlarını içeren bundle/patch; rapor, örnek manifestleri, komut/çıkışlar ve entegrasyon ihtiyaçları. Codex'in bütün testlerini kendi başarın olarak gösterme; yalnız gerçek kendi testlerini raporla. Public push ve production deploy yapma. Süreç temizliği ve kullanıcı verisi koruması zorunlu.
