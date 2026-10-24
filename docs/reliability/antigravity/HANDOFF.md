# Quartz — Codex İçin Güvenilirlik Devir ve Eylem Planı (Handoff)

**Tarih:** 25 Ekim 2026  
**Hazırlayan:** Antigravity (Bağımsız Güvenilirlik İncelemesi)  
**Hedef:** Codex (Üretim Kodu Geliştiricisi)  
**İlgili Belgeler:**
- Mimari Haritası: [`docs/reliability/antigravity/ARCHITECTURE_MAP.md`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/docs/reliability/antigravity/ARCHITECTURE_MAP.md)
- Detaylı Bulgular: [`docs/reliability/antigravity/FINDINGS.md`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/docs/reliability/antigravity/FINDINGS.md)
- Test Sonuçları: [`docs/reliability/antigravity/TEST_RESULTS.md`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/docs/reliability/antigravity/TEST_RESULTS.md)
- Bağımsız Test Paketi: [`tests/reliability_antigravity/`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/tests/reliability_antigravity/)

---

## 1. Genel Durum ve Tebrik

Codex'in çalışma ağacındaki mevcut düzeltmeleri incelenmiş ve test edilmiştir:
- **F-04 (Soket kopma dayanıklılığı):** `core/natural_desktop.py:261` satırındaki try-bloğu genişletmesi doğrulandı (`test_ephemeral_server_resilient_to_client_disconnect` geçti).
- **F-03 (Log izni alırken masaüstü girdisinin korunması):** `preserve_input` mantığı doğrulandı (`test_f03_verified_log_request_preserves_active_desktop_broker` geçti).

Aşağıda, üretim kodunda çözülmesi gereken **en yüksek değerli 5 minimal müdahale** ve hazır diff taslakları yer almaktadır.

---

## 2. En Değerli 5 Müdahale Önerisi (Top 5 Interventions)

### Müdahale 1: Nezaket Uyumu, Eksik Fiiller ve İngilizce Komut Desteği (F-01)

* **Dosya:** [`core/message_intent.py`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/message_intent.py#L26-L35)
* **Neden Gerekli:** Kullanıcı büyük ünlü uyumlu kibar ifadeler kullandığında (`"Pencereye bakar mısınız?"`, `"Testleri çalıştırır mısınız?"`), geniş zaman nezaketi (`"eder misiniz"`) kullandığında, `"çöz"` / `"kapat"` dediğinde veya İngilizce talimat verdiğinde sistem görevi salt sohbete düşürmektedir.
* **Doğrulayıcı Test:** `python -m unittest tests/reliability_antigravity/test_message_intent_reliability.py`
* **Önerilen Minimal Diff:**
  ```python
  # core/message_intent.py satır 26 civarı:
      explicit = re.search(
          r'\b(?:incele(?:yin|yiniz|yip|yerek)?|düzelt(?:in|iniz)?|derle(?:yin)?|geliştir(?:in)?|'
          r'çalıştır(?:ın|in)?|başlat(?:ın)?|aç(?:ın|in)?|oku(?:yun)?|araştır(?:ın)?|'
          r'tıkla(?:yın)?|yükle(?:yin)?|kaydet|sil|ekle(?:yin)?|oluştur(?:un)?|'
          r'test et|kontrol et|test edip|kontrol edip|debug yap|test yap|bi(?:r)? test bakalım|dene(?:yin)?|'
          r'bul|tara|yaz|güncelle|değiştir|çöz(?:ün)?|kapat(?:ın)?|'
          r'open|inspect|check|fix|test|run|debug|search|update|modify|close)\b', value)
      polite = re.search(
          r'(?:inceleyebilir|düzeltebilir|açabilir|çalıştırabilir|bakabilir|test edebilir|kontrol edebilir|'
          r'çözebilir|kapatabilir|inceler|düzenler|açar|çalıştırır|bakar|kontrol eder|çözer|kapatır)\s+'
          r'm[iıuü]s[iı]n(?:iz)?', value)
  ```

---

### Müdahale 2: Durdurulan Görev Sonrası Yeniden Başlatma (F-02)

* **Dosya:** [`core/natural_desktop.py`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/natural_desktop.py#L156-L160)
* **Neden Gerekli:** `stop()` çağrısı `self.job` sözlüğünü temizlemediği için aynı `NaturalDesktopTask` nesnesi üzerinde ikinci bir `start()` çağrıldığında `RuntimeError("Önceki görevi kapatmadan yeni operatör başlatılamaz")` oluşmaktadır.
* **Doğrulayıcı Test:** `python -m unittest tests/reliability_antigravity/test_task_lifecycle_reliability.py`
* **Önerilen Minimal Diff:**
  ```python
  # core/natural_desktop.py def start(...) içinde satır 156:
          with self.lock:
              if self.stopped.is_set() or (self.job and self.job.get("status") in {"completed", "failed", "cancelled", "expired"}):
                  self.job = None
                  self.stopped.clear()
              if self.job or self.broker.status()["active"]:
                  raise RuntimeError("Önceki görevi kapatmadan yeni operatör başlatılamaz")
  ```

---

### Müdahale 3: Birlikte Modunda Ajan Bazlı Durum Takibi (F-05)

* **Dosya:** [`core/agent_chat.py`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/agent_chat.py#L597-L616)
* **Neden Gerekli:** Codex ve Antigravity 1. turu paralel yürütürken tekil `message_id` ve `progress_step` alanları üzerine yazılmakta (race condition), arayüz poller'ı sadece son yazan ajanı takip edebilmektedir.
* **Doğrulayıcı Test:** `python -m unittest tests/reliability_antigravity/test_concurrency_and_races.py`
* **Önerilen Minimal Diff:**
  `_active_turn` içine `agent_progress: dict` eklenmesi ve `_set_turn_progress` metoduna `agent: str | None = None` parametresi verilerek ajan bazlı güncellenmesi.

---

### Müdahale 4: Aktif Görev Yokken Gelen `devam et` Koruması (F-06)

* **Dosya:** [`gui.py`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/gui.py#L180-L195)
* **Neden Gerekli:** Ortada aktif bir görev yokken kullanıcının yazdığı `"devam et"`, `"sürdür"` mesajları yapay zekaya bağlamsız salt metin olarak gitmekte ve model "Neye devam etmemi istersiniz?" şeklinde şaşırmaktadır.
* **Önerilen Minimal Davranış:**
  Eğer `message_intent(text) == 'continuation'` ise ve ne `_natural` ne de `_coordination` aktif bir göreve sahip değilse, arayüz doğrudan kullanıcıya:
  *"Şu anda devam ettirilecek aktif bir görev bulunmuyor. Yeni bir işlem başlatmak için lütfen yapmak istediğiniz görevi belirtin."*
  mesajını dönmeli ve LLM kotasını gereksiz tüketmemelidir.

---

### Müdahale 5: Masaüstü Kapanış Sebeplerinin Yerelleştirilmesi (F-10)

* **Dosya:** [`core/natural_desktop.py`](file:///C:/Users/LENAVO/Desktop/Jarvis%20config/core/natural_desktop.py#L620)
* **Neden Gerekli:** Görev bittiğinde kullanıcı sohbetinde `Görev yürütmesi sona erdi: blocked: foreground changed (user takeover). Kanıt sonucu: NOT VERIFIED.` şeklinde kriptik İngilizce kodlar görünmektedir.
* **Doğrulayıcı Test:** `python -m unittest tests/reliability_antigravity/test_verification_and_evidence.py`
* **Önerilen Minimal Diff:**
  ```python
  REASON_LABELS = {
      "completed": "Başarıyla tamamlandı",
      "failed": "Hata nedeniyle durduruldu",
      "cancelled": "Kullanıcı tarafından iptal edildi",
      "expired": "Görev süresi doldu",
      "permission expired": "İzin onay süresi doldu",
      "permission denied": "Kullanıcı izin isteğini reddetti",
      "blocked: foreground changed (user takeover)": "Başka bir pencereye odaklanıldığı veya kullanıcı müdahale ettiği için güvenlik gereği durduruldu",
      "blocked: awaiting explicit scope approval": "Yeni uygulama/log izni beklendiği için durduruldu",
      "blocked: user takeover lease expired": "Operatör pencere kontrol oturumu zaman aşımına uğradı",
  }
  friendly_reason = REASON_LABELS.get(reason, reason)
  self._event("quartz", f"Görev yürütmesi sona erdi: {friendly_reason}. Kanıt sonucu: {self.job['verification']['status']}.")
  ```

---

## 3. Doğrulama Komutları

Codex düzeltmeleri uyguladıktan sonra tüm bağımsız test paketini şu komutla tek seferde doğrulayabilir:

```powershell
cd "C:\Users\LENAVO\Desktop\Jarvis config"
python -m unittest discover -s tests/reliability_antigravity -p "test_*.py" -v
```

Beklenen nihai durum: `@unittest.expectedFailure` olarak işaretlenmiş testlerin tamamının `unexpected success` vererek düzeltmeleri teyit etmesidir.
