# Kart yoklaması bağımsız incelemesi ve Antigravity durum ayrışması

İncelenen Claude dalı: claude/health-card-poll-20261110 / f492cc8.
Karar: SOURCE/TESTED kabul. ui/js_lifecycle.py mevcut chat_status poll sonucunu
renderEnvironmentHealth'e iletiyor. İlk async kontrol sonrası kartın güncellenmemesi
kök nedenine uygun dar düzeltme; ek izin veya probe çağrısı eklemiyor. Test:
python -B scripts/run_safe_tests.py tests.test_environment_health_card tests.test_gui_live_activity
→ Ran16 tests in4.928s / OK, skip0. Embedded JS exit0. Yeni LIVE kabulü değil;
Claude'un cb67194c canlı başarısızlık kanıtı tarihsel olarak korunuyor. Yeni paket kurulmadı.

## Antigravity sorusu

SOURCE ile doğrulanan iki ayrı veri akışı:

- Kart: MultiAgentService._antigravity_status → AgentChatService._diagnostics
  (AsyncSnapshot) → ChatEnvironmentHealth → environment_health._check_cli_agent.
  Backend runtime/probe cache'i ve sağlık cache'i kullanılır.
- Yan panel: gui.Api.onboarding_status → OnboardingService.status → ayrı
  AntigravityRuntime().probe sonucu / onboarding cache'i → js_setup.py
  agentConnectionView.providers.gemini.ready. Crew sütununun "Hazır" etiketi ise
  daha da dar: seçicinin disabled olmamasından türeyebilir; gerçek auth kanıtı değildir.

Aynı anda iki ekranın aynı snapshot/generation'ı göstermesi garanti edilmiyor.
Bu kaynak ayrışması doğrulandı; kullanıcının bildirdiği canlı uyuşmazlığın kesin
kök nedeni olduğu doğrulanmadı.

İkinci kaynak bulgusu: core/antigravity_runtime.py probe(), `-p /model` için
başarısız returncode'u her durumda authenticated=false/required yapıyor. Timeout,
kota, geçici CLI sorunu ile açık credential eksikliğini ayırmıyor. Sağlık modülü de
bu false değerini "oturumu açık değil" olarak sunuyor. Gerçek başarılı sohbet,
tek başına şu anki probe'un olumlu olduğunu veya hesabın her modele erişimini kanıtlamaz.

IR-AGY-AUTH-HEALTH-01 (Gemini/runtime sahibi): failed probe için açık auth-required
kanıtını timeout/availability/quota/unsupported-command hatalarından ayır; yoklama
zamanı/kaynak/generation korelasyonu sağla. Sağlık tüketicisi unknown sonucu kesin
logout engeli olarak sunmamalı. Birbirine zıt cache'leri sırf UI yeşil olsun diye
zorla ready/authenticated=true yapma. Negatif test: auth-probe timeout + cached
onboarding ready; açık eksik giriş ile karışmamalı.

Canlı read-only chat_status denemesi localhost55123 üzerinde WinError10061
(connection refused) verdi. Backend açılmadı/yeniden başlatılmadı; hesap probe'u
ve yeni model mesajı gönderilmedi. Bu sorunun canlı doğrulaması BLOCKED (aktif
backend yok). Sonraki mevcut oturumda yalnız timestamp/ready/authenticated/installed
ve sağlık check durumunu karşılaştıran tanılama yeterli; mesaj içeriği/anahtar/token
kaydedilmemeli. Yetki, giriş veya güvenlik ayarı değiştirilmedi.

S4 reddedilen değişiklik main'e alınmadı. 057eacb incelemesi bu dar dalın kapsamı dışı.
