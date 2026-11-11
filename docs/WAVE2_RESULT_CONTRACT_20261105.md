# Dalga 2 — sonuç sözleşmesi / IR-CLAUDE-OUTCOME-02

Backend değişikliği: yürütme bitişi, kaynak kanıtı ve hedef kabulü ayrı alanlar.
Modelin yazdığı “başardım”, süreç exit=0 veya source validation=VERIFIED bütün
görevi doğrulamaz. Birlikte turunda istenen iki ajandan biri başarısızsa tur
`partial`; tek başarılı yanıt tüm turun başarısı değildir.

| Alan | Anlamı |
|---|---|
| `execution_status` | Çalışmanın durumu; `completed` yalnız yürütme bitişi, `partial` katılımcı kaybı. |
| `evidence_status`, `evidence_scope` | Dar kanıt düzeyi/kapsamı; hedef kabulü değildir. |
| `goal_verdict` | `NOT VERIFIED`, `PARTIAL`, `FAILED`; yalnız bağımsız host oracle daha sonra doğrulanmış hedef üretebilir. |
| `goal_accepted` | Kullanıcı kabulü; model veya süreç tarafından true yapılamaz. |
| `completion_kind` | Şimdilik `execution_only`; kullanıcıya tamamlanmış hedef gibi gösterilmez. |
| `participants` | İstenen her ajanın gerçek tur sonucu; birlikte turunda AND sözleşmesi. |
| `cleanup_status` | Kaynak bırakma sonucu, hedef sonucundan bağımsız. |

Normalizasyon `task_outcome`, AgentChat mesaj/poll çıkışları ve MultiAgentService
run projeksiyonundadır. Eski metadata `outcome` değerleri bu host projeksiyonunu
geçersiz kılamaz. İç komutun başarısız olması otomatik olarak bütün hedefi
başarısız sayılmaz; beklenen negatif testler mümkündür.

Claude entegrasyon isteği: UI rozetleri ve tüm sonuç kartlarında `completed`
yerine bu sözleşmeyi tüket. `partial` için “Kısmi — istenen ajanlardan biri
tamamlayamadı”; `execution_only` için “Yürütme bitti, hedef henüz doğrulanmadı”.
SOURCE kanıtını LIVE veya kullanıcı kabulü olarak göstermeme. Günlük ayrıntıları
sakla; eski serbest metinden başarı rozeti üretme. Terminal `partial` kuyruğu
otomatik yeni görev başlatmaz. UI testi: iki katılımcıdan biri fail, ikisi
completed ama oracle yok, source syntax fail, scoped UI observation.

TESTED: `python -X utf8 -B scripts/run_safe_tests.py tests.test_wave2_outcomes
tests.test_agent_chat tests.test_multi_agent_service`: 29 test, 0 skip, PASS.
Özel ham çıktı depoya alınmadı. BUILT / LIVE: yapılmadı; paket kurulmadı.
