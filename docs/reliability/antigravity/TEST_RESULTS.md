# Quartz — Bağımsız Güvenilirlik Test Sonuçları (Test Results)

**Test Tarihi:** 25 Ekim 2026  
**Test Ortamı:** Python 3.13.14 (Windows AMD64)  
**Baz Git Commit:** `36a2d9ea8a8abdd744195fa84ff8eec61b3f7444`  
**Test Paketi:** `tests/reliability_antigravity/` (Antigravity Bağımsız Sahiplik Alanı)  
**Çalıştırılan Komut:** `python -m unittest discover -s tests/reliability_antigravity -p "test_*.py" -v`  

---

## 1. Yönetici Özeti (Executive Summary)

Antigravity tarafından bağımsız hazırlanan güvenilirlik test paketi, sistemin intent ayrımı, görev yaşam döngüsü, eşzamanlılık ve kanıt doğrulama katmanlarını ampirik olarak test etmiştir.

* **Toplam Test Sayısı:** 18
* **Başarılı (OK):** 13
* **Beklenen Başarısızlık (Expected Failure - Sözleşme Testi):** 5
* **Beklenmeyen Hata / Çöküş:** 0
* **Test Süresi:** 2.689 saniye

```
----------------------------------------------------------------------
Ran 18 tests in 2.689s

OK (expected failures=5)
```

> [!NOTE]
> Testler hiçbir canlı ağ çağrısı, gerçek model kotası veya ekran/klavye müdahalesi yapmaz. Tamamen izole bellek içi sahte nesneler (`FakeBackend`, geçici dizinler ve mock nesneler) ile çalışır; arka planda çalışan canlı Quartz sürecine (PID 7640) kesinlikle dokunmaz.

---

## 2. Detaylı Test Matrisi

| Test Dosyası | Test Metodu | Hedef Bulgu | Sonuç | Açıklama |
|---|---|---|---|---|
| `test_message_intent_reliability.py` | `test_explicit_turkish_imperatives_are_tasks` | Temel Sağlamlık | **OK** | Emir kipleri (`aç`, `inceleyin`, `kontrol et`) doğru şekilde `'task'` döner. |
| `test_message_intent_reliability.py` | `test_polite_front_vowel_edebilir_misin_is_task` | Temel Sağlamlık | **OK** | İnce ünlülü `edebilir misin` ve tesadüfi önek eşleşmesi `misiniz` `'task'` döner. |
| `test_message_intent_reliability.py` | `test_reproduce_f01_vowel_harmony_polite_classified_as_conversation` | **F-01** (Hata Kanıtı) | **OK** | Kalın ünlü uyumlu (`bakar mısınız`, `çalıştırır mısınız`) ve geniş zamanlı nezaket kipleri `'conversation'` olarak etiketlenir (HATA KANITLANDI). |
| `test_message_intent_reliability.py` | `test_reproduce_f01_english_commands_classified_as_conversation` | **F-01** (Hata Kanıtı) | **OK** | İngilizce görev komutları (`Open Notepad`, `Inspect active window`) `'conversation'` olarak etiketlenir (HATA KANITLANDI). |
| `test_message_intent_reliability.py` | `test_contract_f01_vowel_harmony_and_aorist_polite_should_be_task` | **F-01** (Sözleşme) | **Expected Failure** | Codex regex yamasını uygulayana kadar beklenen başarısızlık olarak işaretlendi. |
| `test_message_intent_reliability.py` | `test_contract_f01_basic_english_commands_should_be_task` | **F-01** (Sözleşme) | **Expected Failure** | Codex İngilizce eylem fiillerini ekleyene kadar beklenen başarısızlık. |
| `test_message_intent_reliability.py` | `test_reproduce_f06_orphan_continuation_routing` | **F-06** (Risk Kanıtı) | **OK** | Aktif görev yokken `"devam et"` ifadesinin bağlamsız sohbete düştüğü kanıtlandı. |
| `test_message_intent_reliability.py` | `test_tools_disallowed_overrides_task_intent` | Temel Sağlamlık | **OK** | `"Sadece sohbet edelim"` ifadesi her zaman araçları engeller. |
| `test_task_lifecycle_reliability.py` | `test_reproduce_f02_natural_task_reuse_raises_runtime_error` | **F-02** (Hata Kanıtı) | **OK** | Görev `stop()` ile durdurulduktan sonra `self.job` temizlenmediği için aynı nesnede `start()` çağrısı `RuntimeError` fırlatır (HATA KANITLANDI). |
| `test_task_lifecycle_reliability.py` | `test_contract_f02_natural_task_should_allow_start_after_stop` | **F-02** (Sözleşme) | **Expected Failure** | `stop()` veya `start()` içinde durum sıfırlaması yapılana kadar beklenen başarısızlık. |
| `test_task_lifecycle_reliability.py` | `test_f03_verified_log_request_preserves_active_desktop_broker` | **F-03** (Doğrulandı) | **OK** | Codex'in çalışma ağacındaki `preserve_input` mantığı sayesinde salt-okunur log talebinin masaüstü bağlantısını kapatmadığı doğrulandı. |
| `test_task_lifecycle_reliability.py` | `test_stop_idempotency` | Yaşam Döngüsü | **OK** | `stop()` metodunun arka arkaya çağrılmasının güvenli ve idempotent olduğu doğrulandı. |
| `test_concurrency_and_races.py` | `test_ephemeral_server_resilient_to_client_disconnect` | **F-04** (Doğrulandı) | **OK** | Codex'in `end_headers` çağrısını try bloğu içine alan yaması sayesinde ani soket kopmalarının sunucuyu çökertmediği doğrulandı. |
| `test_concurrency_and_races.py` | `test_reproduce_f05_collaboration_turn_progress_race` | **F-05** (Risk Kanıtı) | **OK** | Paralel iki ajanın `_set_turn_progress` çağrısı yaptığında skalar `message_id` ve `progress_step` alanlarının birbirini ezdiği kanıtlandı. |
| `test_concurrency_and_races.py` | `test_contract_f05_collaboration_turn_should_track_per_agent_progress` | **F-05** (Sözleşme) | **Expected Failure** | Ajan bazlı durum sözlüğü eklenene kadar beklenen başarısızlık. |
| `test_verification_and_evidence.py` | `test_reproduce_f07_model_claim_does_not_guarantee_valid_syntax` | **F-07** (Risk Kanıtı) | **OK** | CLI çıkış kodunun 0 olması ve modelin "düzelttim" demesinin bozuk sözdizimini engellemediği, `ast.parse` gibi somut doğrulamanın şart olduğu kanıtlandı. |
| `test_verification_and_evidence.py` | `test_reproduce_f10_raw_technical_stop_reasons_in_chat_event` | **F-10** (Hata Kanıtı) | **OK** | `stop(reason)` çağrısındaki teknik İngilizce metinlerin (`blocked: foreground changed...`) kullanıcı sohbet balonuna sızdığı kanıtlandı. |
| `test_verification_and_evidence.py` | `test_contract_f10_stop_reason_should_be_localized_user_message` | **F-10** (Sözleşme) | **Expected Failure** | Durum kodları kullanıcı dostu Türkçe metinlere dönüştürülene kadar beklenen başarısızlık. |

---

## 3. Codex Tarafından Çözülen ve Doğrulanan Bulgular

Test paketi yürütülürken, Codex'in çalışma ağacındaki mevcut değişiklikleri incelenmiş ve 2 kritik hatanın başarıyla çözüldüğü ampirik olarak doğrulanmıştır:

1. **F-04 Çözümü Doğrulandı (`test_ephemeral_server_resilient_to_client_disconnect`):**
   * *Sorun:* `self.end_headers()` try-except dışında kaldığı için istemci soketi kapandığında `ConnectionResetError` fırlatılıyordu.
   * *Codex Yaması:* `core/natural_desktop.py:261` satırında `try:` bloğu `send_response` ve `end_headers` çağrılarını kapsayacak şekilde genişletildi. Test bu düzeltmenin soket kopmalarını sessizce ve güvenle yuttuğunu kanıtladı.
2. **F-03 Çözümü Doğrulandı (`test_f03_verified_log_request_preserves_active_desktop_broker`):**
   * *Sorun:* Hedef pencere değişmeksizin salt-okunur log istendiğinde `self.broker.stop()` çağrılıyor ve operatörün masaüstü girdisi öldürülüyordu.
   * *Codex Yaması:* `core/natural_desktop.py:352` satırına `preserve_input = bool(same_targets and self.connection and self.broker.status()["active"])` koşulu eklendi. Test, mevcut onaylı pencere oturumunun log izin kartı açıldığında da korunduğunu kanıtladı.

---

## 4. Codex İçin Hazır Bekleyen Sözleşme Testleri (Pending Contracts)

Aşağıdaki 5 test `@unittest.expectedFailure` olarak işaretlenmiştir. Codex ilgili en küçük düzeltmeleri uyguladığında bu testler doğrudan yeşile dönecek ve düzelmeyi otomatik olarak belgeleyecektir:

1. `test_contract_f01_vowel_harmony_and_aorist_polite_should_be_task` (`core/message_intent.py`)
2. `test_contract_f01_basic_english_commands_should_be_task` (`core/message_intent.py`)
3. `test_contract_f02_natural_task_should_allow_start_after_stop` (`core/natural_desktop.py`)
4. `test_contract_f05_collaboration_turn_should_track_per_agent_progress` (`core/agent_chat.py`)
5. `test_contract_f10_stop_reason_should_be_localized_user_message` (`core/natural_desktop.py`)
