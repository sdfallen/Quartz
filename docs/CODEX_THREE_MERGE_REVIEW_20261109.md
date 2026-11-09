# Üç birleşimin bağımsız incelemesi

Taban: a182779. Komut: python -B scripts/run_safe_tests.py tests.test_key_sequence tests.test_stop_lock_chain tests.test_smart_open_fast tests.test_gui_wave2_status tests.test_gui_live_activity.
Gerçek çıktı: Ran 38 tests in 7.723s / OK, skip0. Mock/Node testidir; yeni LIVE kabulü değildir.

## 826f846 — SOURCE / TESTED kabul

core/natural_desktop.py `_watch`, `status`, `task_context`: broker beklemesi görev kilidi dışına taşınmış. Watchdog eski bağlantı gözlemine göre yeni bağlantıyı iptal etmiyor (nesne kimliği kontrolü). Stop sırasında token kaldırma korunuyor. Durum snapshot'ları anlık görüntüdür; izin otoritesi yerine kullanılmıyor. tests/test_stop_lock_chain.py kilit serbestliği ve Stop için eşzamanlı kontroller içeriyor. UI ara mesajları terminal başarı üretmiyor.

## 095e71c — SOURCE / TESTED kabul, sınır notuyla

advanced_controller.py `smart_open`: bilinen komut/Türkçe isimler doğrudan aynı normal launch yoluna gider, yönetici yetkisi eklemez. `_search_dir_limited` eşleşmeleri değil incelenen adayları sayar. tests/test_smart_open_fast.py alias ve sınır testleri geçti. Süre denetimi yalnız `rglob` bir sonraki adayı verdiğinde çalışır; takılmış ağ/disk iterator'ünü kesen kesin wall-clock timeout değildir. Yerel dizin optimizasyonu için kabul, sistem genelinde kesin 1,5 sn garantisi olarak raporlanmamalı.

## cb962b7 — koşulsuz kabul RET; P1 düzeltme isteği

core/desktop_native.py:519–548: kritik odaklanmış denetim ve `_before_input` yalnız dizi başında kontrol edilir. Sonraki tuşlarda yalnız iptal bayrağı ve foreground denetlenir. Aynı pencerede `tab enter` ile sıradan kontrolden `Pay/Delete/Send` düğmesine geçildiğinde ikinci tuş öncesi kritik denetim yenilenmez. Bu tek-tuş yolundaki her çağrı öncesi kontrolü zayıflatır. Kaynakla doğrulanan kontrol akışı bulgusudur; gerçek ödeme/silme denenmedi.

Claude integration request IR-KEY-SEQUENCE-CRITICAL-01: her tuş öncesi güncel focused-control/critical, identity, input desktop ve integrity kontrolünü koru; ya da gözlem/denetim geçişi gerektiren tuşları çoklu diziden çıkar. Stop ve foreground kesmesini koru. Negatif test: ilk key sonrası aynı pencerede kritik kontrole geç; Enter gönderilmemeli. Yeni oturumun Stop bayrağını temizlemesi ve eski oturumun girdi üretememesi de test edilmeli.

Mevcut testler Stop/foreground ve 24 tuş sınırını doğruluyor; kritik kontrol değişimini kapsamıyor. Kod zaten main'de; inceleme sonucu bu gerçeği gizlemez ve bu oturum kodu geri almadı. Kullanıcı onaylı çalışan pakete müdahale edilmedi.

S3 ve bağımsız belge/test dalı main'e d4789f0 ve a182779 ile alındı. Yeni otomatik düzeltme bileşenleri ayrı codex/repair-loop-20261109 dalında geliştirilecek; bağımsız incelemeden main'e alınmayacak.
