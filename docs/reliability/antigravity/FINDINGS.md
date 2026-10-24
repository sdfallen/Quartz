# Quartz — Somut Mimari ve Güvenilirlik Bulguları (Findings)

**İnceleme Tarihi:** 25 Ekim 2026  
**İncelenen Git Commit:** `36a2d9ea8a8abdd744195fa84ff8eec61b3f7444`  
**İnceleyen:** Gemini 3.8 Flash High (Bağımsız Güvenilirlik İncelemesi)  
**Kapsam:** Üretim kaynak kodu, hata analizleri, yarış koşulları ve yaşam döngüsü  

---

## Özet Tablosu

| # | Kategori | Dosya / Fonksiyon | Özet Başlık | Önem |
|---|---|---|---|---|
| **F-01** | Kanıtlanmış Hata | `core/message_intent.py::message_intent` | Nezaket eki (`misiniz`) ve İngilizce komutların sohbete düşmesi | Yüksek |
| **F-02** | Kanıtlanmış Hata | `core/natural_desktop.py::NaturalDesktopTask.start` | Durdurulan görev sonrası aynı nesnede yeniden başlatma çöküşü | Yüksek |
| **F-03** | Kanıtlanmış Hata | `core/natural_desktop.py::_request` | Gözlemcinin salt okunur log isteğinin operatörün masaüstü oturumunu iptal etmesi | Yüksek |
| **F-04** | Kanıtlanmış Hata | `core/natural_desktop.py::_serve` | Ephemeral HTTP sunucusunda `end_headers` soket kırılma hatası | Orta |
| **F-05** | Olası Risk | `core/agent_chat.py::_run_collaboration_turn` | Birlikte modunda çift iş parçacıklı ilerleme durumu ve `message_id` yarışı | Yüksek |
| **F-06** | Olası Risk | `gui.py::coordination_route` & `core/agent_chat.py` | Görev yokken gelen `devam et` mesajının bağlamsız sohbete düşmesi | Orta |
| **F-07** | Olası Risk | `core/agent_chat.py::_execute_codex_bubble` | Kod yazma görevlerinde empirik test ve sözdizimi doğrulama eksikliği | Yüksek |
| **F-08** | Mimari Tercih | `core/natural_desktop.py`, `chat_coordination.py`, `desktop_agents.py` | Üç farklı ve çakışan masaüstü soyutlama katmanının varlığı | Yüksek |
| **F-09** | Mimari Tercih | `gui.py::pollUiEvents` vb. | 6 paralel polling döngüsünün pywebview köprüsünde kuyruklanması | Orta |
| **F-10** | Kanıtlanmış Hata | `core/natural_desktop.py::stop` | Sohbet balonuna ham teknik hata kodlarının sızması | Orta |

---

## Detaylı Bulgular

### F-01: Büyük/Küçük Ünlü Uyumu, Geniş Zaman Nezaket Kalıpları ve İngilizce Komutların Sohbete Düşmesi

* **Kategori:** Kanıtlanmış Hata
* **Dosya ve Fonksiyon:** [`core/message_intent.py:18`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/message_intent.py#L18-L35) — `message_intent(text)`
* **Somut Hata:**
  1. `message_intent` fonksiyonundaki `polite` düzenli ifadesi yalnızca ince ünlülü tekil `misin` son ekini ve belirli fiilleri denetlemektedir:
     ```python
     polite = re.search(r'(?:inceleyebilir|düzeltebilir|açabilir|çalıştırabilir|bakabilir|test edebilir|kontrol edebilir)\s+misin', value)
     ```
     Yapılan ampirik testlerde:
     - `\smisin` ifadesi kelime sonu sınırı (`\b`) içermediği için `"kontrol edebilir misiniz?"` gibi ince ünlülü kalıpları tesadüfen yakalamaktadır.
     - Ancak kalın ünlülü (`ı`, `u`) fiillerde Türkçe büyük ünlü uyumu gereği kullanılan formlar (`"Pencereye bakar mısınız?"`, `"Testleri çalıştırır mısınız?"`, `"Uygulamayı kapatır mısınız?"`) ve aorist (geniş zaman) nezaket formları (`"Pencereleri kontrol eder misiniz?"`, `"Hata loglarını inceler misiniz?"`) tamamen ıskalanmaktadır.
     - Ayrıca `"çöz"` (örn: `"Bu sorunu çözebilir misiniz?"`) ve `"kapat"` gibi temel geliştirme/pencere eylemleri regex listesinde bulunmamaktadır.
  2. Fonksiyon tamamen Türkçe anahtar kelimelere dayanmaktadır. İngilizce yazılan `"Open Notepad and check logs"` veya `"Fix the bug in settings screen"` gibi görev komutları doğrudan `'conversation'` olarak etiketlenir.
* **Kullanıcıya Etkisi:**
  Kullanıcı kalın ünlülü kibar bir dille veya İngilizce bir talimat verdiğinde, sistem bunu görev olarak algılamayıp araçsız salt sohbete yönlendirir. İzin kartı açılmaz, masaüstü veya dosya yazma yetkisi tetiklenmez.
* **Yeniden Üretme Yöntemi:**
  ```python
  from core.message_intent import message_intent
  assert message_intent("Pencereye bakar mısınız?") == "task"       # AssertionError: 'conversation' != 'task'
  assert message_intent("Testleri çalıştırır mısınız?") == "task"   # AssertionError: 'conversation' != 'task'
  assert message_intent("Bu sorunu çözebilir misiniz?") == "task"   # AssertionError: 'conversation' != 'task'
  assert message_intent("Open Notepad and check logs") == "task"    # AssertionError: 'conversation' != 'task'
  ```
* **En Küçük Güvenli Düzeltme Önerisi:**
  `polite` regex'ine `(?:m[iıuü]s[iı]n(?:iz)?)` ve geniş zaman ekleri (`eder/inceler/bakar`) eklenmeli, eksik fiiller (`çöz`, `kapat`) listeye alınmalı ve yaygın temel İngilizce görev fiilleri (`open`, `inspect`, `check`, `fix`, `test`, `run`) eklenmelidir.
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_message_intent_reliability.py`

---

### F-02: Durdurulan Görev Sonrası Aynı Nesnede Yeniden Başlatma Çöküşü

* **Kategori:** Kanıtlanmış Hata
* **Dosya ve Fonksiyon:** [`core/natural_desktop.py:154-156`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/natural_desktop.py#L154-L156) — `NaturalDesktopTask.start(text, project, cid, models)`
* **Somut Hata:**
  `start` metodunda şu denetim bulunmaktadır:
  ```python
  with self.lock:
      if self.job or self.broker.status()["active"]:
          raise RuntimeError("Önceki görevi kapatmadan yeni operatör başlatılamaz")
  ```
  Görev `stop()` ile durdurulduğunda (`self.stopped.set()`), `self.job` sözlüğü temizlenmemekte (`None` yapılmamakta), görevin son raporunu tutmaya devam etmektedir. Bu nedenle, aynı `NaturalDesktopTask` nesnesi üzerinde ikinci bir görev başlatılmak istendiğinde `self.job` dolu olduğu için her zaman `RuntimeError` fırlatılmaktadır.
* **Kullanıcıya Etkisi:**
  `gui.py` her görevde `self._natural = NaturalDesktopTask(...)` oluşturarak arayüzde bu hatayı maskelese de, servis seviyesinde durum temizliği yapılmadığı için arka plan entegrasyonlarında, testlerde veya singleton kullanımlarda sistem kilitlenir.
* **Yeniden Üretme Yöntemi:**
  ```python
  task = NaturalDesktopTask(desktop, emit)
  task.start("Görev 1", project, cid, models)
  task.stop("completed")
  task.start("Görev 2", project, cid, models)  # RuntimeError: Önceki görevi kapatmadan yeni operatör başlatılamaz
  ```
* **En Küçük Güvenli Düzeltme Önerisi:**
  `start()` başlangıcında eğer `self.stopped.is_set()` ise veya `self.job` sonlanmış bir duruma (`completed`, `cancelled`, `failed`) sahipse `self.job = None` yapılarak yeni göreve temiz başlanmalıdır.
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_task_lifecycle_reliability.py::test_natural_task_reuse_after_stop`

---

### F-03: Gözlemcinin Salt Okunur Log İsteğinin Operatörün Masaüstü Oturumunu İptal Etmesi

* **Kategori:** Kanıtlanmış Hata
* **Dosya ve Fonksiyon:** [`core/natural_desktop.py:345-350`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/natural_desktop.py#L345-L350) — `NaturalDesktopTask._request(provider, handles, paths, reason)`
* **Somut Hata:**
  Operatör (Codex) onaylı pencere üzerinde odak sahibiyken, gözlemci ajan (Antigravity) `task_read_log` aracıyla onaylanmamış bir proje günlüğü okumak istediğinde `_request` tetiklenir:
  ```python
  same_targets = (targets == self.approved_targets)
  if (not self.pending and same_targets and logs == set(self.approved_logs)
          and (not targets or self.broker.status()["active"])):
      return {"status":"already_approved", ...}
  self.broker.stop("awaiting explicit scope approval")
  self.connection = None
  self.latest = None
  ```
  Burada `targets == self.approved_targets` olsa dahi (yani yeni bir pencere istenmemiş, yalnızca okunacak yeni bir log dosyası eklenmiş olsa dahi), `self.broker.stop(...)` koşulsuz çağrılmakta ve `self.connection = None` yapılmaktadır.
* **Kullanıcıya Etkisi:**
  Codex tam pencerede eylem yaparken veya inceleme yaparken, Antigravity'nin bir `.log` dosyası okumak istemesi Codex'in masaüstü bağlantısını (`connection`) öldürür. Codex bir sonraki araç çağrısında `PermissionError: Request inline access first; no input authority exists` hatası alır ve turunu sonlandırır. Kullanıcı izin verdikten sonra Codex'in sıfırdan yeniden başlatılması gerekir.
* **Kanıt:**
  Kabul testlerinde (`task-2476` ve `task-2510` kayıtları), Antigravity'nin log izni istemesi üzerine Codex'in odak oturumunun iptal edildiği ve Codex'in onay beklerken turunu bitirip tekrar başlatıldığı gözlenmiştir.
* **En Küçük Güvenli Düzeltme Önerisi:**
  `_request` içinde yalnızca yeni bir pencere tanıtıcısı (`new_handles = set(handles) - set(self.approved_targets)`) varsa broker durdurulmalıdır. Yalnızca salt okunur log isteniyorsa operatörün mevcut geçerli pencere oturumu (`self.connection` ve `self.broker`) bozulmamalıdır.
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_task_lifecycle_reliability.py::test_log_request_does_not_revoke_desktop_broker`

---

### F-04: Ephemeral HTTP Sunucusunda İstemci Soket Kapanma Hatası

* **Kategori:** Kanıtlanmış Hata
* **Dosya ve Fonksiyon:** [`core/natural_desktop.py:262-265`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/natural_desktop.py#L262-L265) — `NaturalDesktopTask._serve.Handler.do_POST`
* **Somut Hata:**
  `do_POST` metodunda HTTP başlıkları gönderilirken:
  ```python
  self.send_response(status); self.send_header("Content-Type", "application/json")
  self.send_header("Content-Length", str(len(data))); self.end_headers()
  try: self.wfile.write(data)
  except (BrokenPipeError, ConnectionError): pass
  ```
  Python 3'ün `http.server` modülünde `self.end_headers()` çağrısı `flush_headers()` tetikler ve sokete doğrudan yazma yapar. Eğer istemci (CLI süreci) iptal edilmiş, zaman aşımına uğramış veya soketi kapatmışsa, `self.end_headers()` satırında `ConnectionResetError: [WinError 10054]` fırlatılır. `try` bloğu yalnızca `self.wfile.write(data)` satırını koruduğu için hata yakalanamaz ve sunucu iş parçacığı çöküş izi üretir.
* **Kullanıcıya Etkisi:**
  Görev iptal edildiğinde veya istemci hızlı kapandığında konsola/loglara gereksiz soket istisnaları (`Exception occurred during processing of request`) dökülür.
* **Kanıt:**
  `task-2510` logunda doğrulanmış traceback:
  ```
  File "...\Lib\http\server.py", line 549, in end_headers
      self.flush_headers()
  ConnectionResetError: [WinError 10054] Varolan bir bağlantı uzaktaki bir ana bilgisayar tarafından zorla kapatıldı
  ```
* **En Küçük Güvenli Düzeltme Önerisi:**
  `try` bloğu `self.send_response` ve `self.end_headers()` çağrılarını da kapsayacak şekilde genişletilmelidir.
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_concurrency_and_races.py::test_ephemeral_server_resilient_to_client_disconnect`

---

### F-05: Birlikte Modunda Çift İş Parçacıklı İlerleme ve Mesaj Kimliği Yarışı

* **Kategori:** Olası Risk
* **Dosya ve Fonksiyon:** [`core/agent_chat.py:1241-1253`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/agent_chat.py#L1241-L1253) — `AgentChatService._run_collaboration_turn`
* **Somut Hata / Risk:**
  `write=False` olduğunda Codex ve Antigravity 1. turu paralel çalıştırır:
  ```python
  t_codex_r1 = threading.Thread(target=run_codex_r1, ...)
  t_agy_r1 = threading.Thread(target=run_agy_r1, ...)
  t_codex_r1.start()
  t_agy_r1.start()
  ```
  Her iki iş parçacığı da eş zamanlı olarak `self._set_turn_progress(...)` çağırır. `_set_turn_progress` içinde:
  ```python
  self._active_turn["message_id"] = current_msg_id
  self._active_turn["run_id"] = run_id
  ```
  Bu iki tekil değişken atomik olmadan birbiri üzerine yazılır. Arayüzün `poll_active()` çağrısı yaptığı anda `message_id` hangi ajanın elindeyse arayüz yalnızca o ajanın durumunu sorgulayabilir.
* **Kullanıcıya Etkisi:**
  Kullanıcı arayüzünde iki ajan aynı anda yazarken bir ajanın sohbet balonu akıcı güncellenirken diğer ajanın balonu `poll_active` tarafından görülmeyip yanıt bitene kadar boş/donuk kalabilir.
* **En Küçük Güvenli Düzeltme Önerisi:**
  `_active_turn` içinde tekil `message_id` ve `run_id` yerine ajan bazlı bir sözlük (`agent_states: {"codex": {...}, "antigravity": {...}}`) tutulmalı ve `poll_active` iki balonun da son durumunu döndürmelidir.
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_concurrency_and_races.py::test_collaboration_parallel_progress_race`

---

### F-06: Görev Yokken Gelen `devam et` Mesajının Bağlamsız Sohbete Düşmesi

* **Kategori:** Olası Risk
* **Dosya ve Fonksiyon:** [`gui.py:183`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/gui.py#L183) — `coordination_route` & [`core/agent_chat.py:334`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/agent_chat.py#L334)
* **Somut Risk:**
  Kullanıcı aktif bir görev yokken `"devam et"`, `"sürdür"` veya `"tamam"` yazdığında:
  1. `message_intent("devam et")` -> `'continuation'` döner.
  2. `gui.py` aktif bir görev (`_natural` veya `_coordination`) bulamadığı için satır 183'te:
     `return {"status":"ok","data":{"handled":False,"intent":"conversation" if message_kind != "task" else "task"}}`
     ifadesiyle `handled: False, intent: 'conversation'` döner.
  3. `gui.py` bunu normal sohbet mesajı olarak `chat_send`'e yollar.
  4. `AgentChatService.send_message` içinde:
     `conversation_only = message_intent(text) != "task"` -> `True` olur.
  5. Model doğrudan `"Kullanıcı mesajı: devam et"` girdisini alır.
* **Kullanıcıya Etkisi:**
  Kullanıcı bir önceki görevin kaldığı yerden devam edeceğini düşünürken, model bağlamı bilmediği için şaşkın bir şekilde "Neye devam etmemi istersiniz?" der veya alakasız genel bir yanıt üretir.
* **En Küçük Güvenli Düzeltme Önerisi:**
  Aktif görev yokken gelen `continuation` niyetli mesajlarda kullanıcıya doğrudan "Şu anda devam ettirilecek aktif bir görev bulunmuyor. Yeni bir görev başlatmak için lütfen yapmak istediğiniz işlemi belirtin." şeklinde rehber mesaj verilmelidir.
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_message_intent_reliability.py::test_orphan_continuation_handling`

---

### F-07: Kod Düzenlemelerinde Empirik Test ve Sözdizimi Doğrulama Eksikliği

* **Kategori:** Olası Risk
* **Dosya ve Fonksiyon:** [`core/agent_chat.py:930`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/agent_chat.py#L930) — `_execute_codex_bubble`
* **Somut Risk:**
  `write=True` yetkisiyle dosya düzenleyen Codex CLI süreci tamamlandığında (`code == 0`), üretilen kodun sözdizimsel olarak geçerli olup olmadığı (`py_compile` / `ast.parse`) veya projenin mevcut birim testlerinin kırılıp kırılmadığı Quartz tarafından empirik olarak doğrulanmaz. Model metin çıktısında "Hata düzeltildi, tüm testler geçiyor" yazsa dahi bu sadece model iddiasıdır.
* **Kullanıcıya Etkisi:**
  Kullanıcı modelin "düzelttim" sözüne güvenip projeyi çalıştırdığında sözdizimi hatalarıyla veya bozulmuş testlerle karşılaşabilir. Doğrulama yükü kullanıcıya kalır.
* **En Küçük Güvenli Düzeltme Önerisi:**
  Yazma içeren görevlerin sonunda değiştirilen `.py` dosyaları için otomatik `ast.parse` doğrulaması yapılmalı ve projenin varsa test komutu arka planda çalıştırılarak test sonucu gerçek kanıt olarak mesaja eklenmelidir (`[TEST DOĞRULAMASI: 12 test geçti / BAŞARISIZ]`).
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_verification_and_evidence.py::test_model_claim_vs_syntax_validation`

---

### F-08: Üç Farklı ve Çakışan Masaüstü Soyutlama Katmanının Varlığı

* **Kategori:** Mimari Tercih / Karmaşıklık
* **Dosyalar:**
  - `core/natural_desktop.py` (`NaturalDesktopTask`)
  - `core/chat_coordination.py` (`ChatCoordination`)
  - `core/desktop_agents.py` (`DesktopAgentService`)
* **Somut Tespit:**
  Sistemde masaüstü işlemlerini yöneten 3 farklı servis bulunmaktadır:
  1. `NaturalDesktopTask`: Doğal sohbetten tetiklenen, satır içi onay kartı üreten ve `desktop_verify` ile UIA doğrulaması yapan en gelişmiş ve güvenli katman.
  2. `ChatCoordination`: Masaüstü erişimini baştan bir plan onay kartıyla (`propose`/`approve`) açan, ara katman.
  3. `DesktopAgentService`: Yalnızca tek pencere odaklanması yapan eski katman.
  `gui.py` içinde `self._natural`, `self._coordination` ve `self._desktop_agents` ayrı kilitlerle ve ayrı ömürlerle tutulmakta, arayüz araç çubuğu durumunu hangisinden çekeceğini `desktop_task_status` içinde karmaşık bir öncelik sırasıyla belirlemektedir.
* **Kullanıcıya Etkisi:**
  Görev durumunun ("Normal", "Hazırlanıyor", "Kontrol Bırakıldı") senkronizasyonunda gecikmeler, araç çubuğundaki "Durdur" düğmesinin bazen eski görev kimliği (`stop_ref`) nedeniyle hata vermesi.
* **En Küçük Güvenli Düzeltme Önerisi:**
  Masaüstü kontrolünün tek birleştirici sınıf (`NaturalDesktopTask`) altında konsolide edilmesi; `ChatCoordination` ve `DesktopAgentService`'in legacy yönlendiriciler olarak sadeleştirilmesi.

---

### F-09: Çoklu Polling Döngülerinin WebView2 IPC Köprüsünde Kuyruklanması

* **Kategori:** Mimari Tercih / Performans
* **Dosya ve Fonksiyon:** [`gui.py:3190-3220`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/gui.py#L3190-L3220) (İstemci tarafı JS)
* **Somut Tespit:**
  İstemci tarafında aynı anda çalışan polling döngüleri:
  - `pollPing`: her 3000 ms
  - `pollStats`: her 2500 ms
  - `pollTasks`: her 2000 ms
  - `pollUiEvents` (içinde `pollNaturalTask`): her 1200 ms
  - `pollCoordination` (aktifken): her 1500 ms
  - `chat_status`: her 2000 ms
  WebView2 / pywebview üzerinde tek kanallı bir IPC köprüsü çalışmaktadır. Saniyede 3-4 farklı IPC çağrısı arka arkaya geldiğinde, Python tarafındaki GIL ve iş parçacığı kilitleri nedeniyle gecikmeler birikmektedir.
* **Kullanıcıya Etkisi:**
  Kullanıcı mesaj gönderirken veya pencereyi kaydırırken mikrosaniyelik takılmalar ve yanıtın arayüze düşmesinde 1-2 saniyelik gecikmeler.
* **En Küçük Güvenli Düzeltme Önerisi:**
  Tüm periyodik durum kontrollerini tek bir birleşik durum endpoint'inde (`api.unified_heartbeat()`) toplamak ve istemcinin tek bir zamanlayıcıyla (örn: her 1500 ms) tüm durumu tek seferde almasını sağlamak.

---

### F-10: Sohbet Balonuna Ham Teknik Hata Kodlarının Sızması

* **Kategori:** Kanıtlanmış Hata
* **Dosya ve Fonksiyon:** [`core/natural_desktop.py:596`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/natural_desktop.py#L596) — `NaturalDesktopTask.stop(reason)`
* **Somut Hata:**
  Bir masaüstü görevi durdurulduğunda:
  ```python
  self._event("quartz", "Görev yürütmesi sona erdi: " + reason + ". Kanıt sonucu: " + self.job["verification"]["status"] +
              ".\n\n---TEKNIK_AYRINTILAR---\nKanıt klasörü: " + str(self.evidence))
  ```
  `reason` parametresi doğrudan dahili İngilizce durum dizgilerini içerir:
  - `blocked: foreground changed (user takeover)`
  - `blocked: awaiting explicit scope approval`
  - `permission expired`
  - `action budget exhausted`
* **Kullanıcıya Etkisi:**
  Kullanıcı ekranda `Görev yürütmesi sona erdi: blocked: foreground changed (user takeover). Kanıt sonucu: NOT VERIFIED.` şeklinde kriptik bir mesaj görür. Kullanıcı pencereye tıkladığı için görevin güvenlik gereği durduğunu anlayamaz.
* **En Küçük Güvenli Düzeltme Önerisi:**
  Dahili `reason` dizgileri kullanıcıya sunulmadan önce Türkçe ve açıklayıcı metinlere dönüştürülmelidir (örn: `foreground changed (user takeover)` -> `Başka bir pencereye tıklandığı veya odak değiştiği için güvenlik gereği masaüstü kontrolü durduruldu.`).
* **Öneriyi Yanlışlayabilecek / Doğrulayacak Test:**
  `tests/reliability_antigravity/test_verification_and_evidence.py::test_human_readable_stop_reasons`
