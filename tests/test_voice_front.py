"""Voice front: fast answers only from visible state; everything else goes to the team."""
import unittest

from core.voice_front import ASK_TEAM, VoiceFront, build_context, needs_team

STATE = {"busy": True, "progress": "Fatum düzeltmeyi hazırlıyor", "last_seq": 7, "messages": [
    {"role": "user", "sender": "user", "persona": "", "text": "Giriş sayfasını test edin"},
    {"role": "assistant", "sender": "codex", "persona": "Fides", "failed": True,
     "text": "Test başarısız: parola boşken 500.\n---TEKNIK_AYRINTILAR---\nC:\\proje\\app.py satır 12"},
    {"role": "assistant", "sender": "claude", "persona": "Fatum", "text": "Düzeltiyorum ```kod``` bakınız https://x.y/z"},
]}


class FakePost:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.bodies = reply, error, []

    def __call__(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        return {"choices": [{"message": {"content": self.reply}}]}


class VoiceFrontTests(unittest.TestCase):
    def front(self, **kw):
        post = FakePost(**kw)
        return VoiceFront(api_key="test", model="m", post=post), post

    def test_plain_question_is_answered_from_the_context(self):
        front, post = self.front(reply="Fides'in testi başarısız oldu, Fatum düzeltiyor.")
        result = front.answer("Ne oldu?", STATE)
        self.assertEqual(result["route"], "answered")
        system = post.bodies[0]["messages"][0]["content"]
        self.assertIn("Fides (başarısız)", system)
        for leaked in ("TEKNIK_AYRINTILAR", "app.py", "https://", "```"):
            self.assertNotIn(leaked, system)
        self.assertEqual(post.bodies[0]["chat_template_kwargs"], {"enable_thinking": False})

    def test_risk_and_action_questions_never_reach_the_model(self):
        for q in ("Bu hata kullanıcı verisini tehlikeye atar mı?", "Fides'e testi tekrar çalıştırmasını söyle.",
                  "Güvenli mi?", "Kodu düzelt", "Bunu commit et"):
            with self.subTest(q=q):
                front, post = self.front(reply="Hayır, sorun yok.")
                self.assertEqual(front.answer(q, STATE)["route"], "team")
                self.assertEqual(post.bodies, [])
        self.assertFalse(needs_team("Ekip şu an ne yapıyor?"))
        self.assertFalse(needs_team("Selam, nasılsın?"))
        self.assertFalse(needs_team("NASILSIN, ne oldu?"))
        self.assertTrue(needs_team("Şu dosyayı SİL"))
        # Memory requests and questions must reach the team, which stores and sees memory.
        for q in ("Benim adım Ali, bunu hatırla", "Bunu unutma", "Adım neydi?", "Adım ne?",
                  "Beni hatırlıyor musun?", "Hakkımda ne biliyorsun", "Bunu aklında tut"):
            self.assertTrue(needs_team(q), q)

    def test_model_deferral_errors_and_bad_answers_go_to_the_team(self):
        cases = [dict(reply=ASK_TEAM), dict(reply=""), dict(reply="x" * 400), dict(reply="```py```"),
                 dict(error=TimeoutError()), dict(error=ValueError("bad json"))]
        for kw in cases:
            with self.subTest(kw=str(kw)[:40]):
                front, _ = self.front(**kw)
                self.assertEqual(front.answer("Ne oldu?", STATE)["route"], "team")

    def test_no_key_or_secret_question_skips_the_model(self):
        post = FakePost(reply="x")
        self.assertEqual(VoiceFront(api_key="", post=post).answer("Ne oldu?", STATE)["reason"], "no_key")
        self.assertEqual(VoiceFront(api_key="k", post=post).answer("Şifrem 1234 mü?", STATE)["route"], "team")
        self.assertEqual(post.bodies, [])

    def test_bug_reports_about_passwords_stay_readable_but_values_do_not(self):
        from core.voice_front import contains_secret
        self.assertFalse(contains_secret("Test başarısız: parola alanı boşken 500 hatası dönüyor."))
        self.assertIn("parola alanı boşken", build_context(STATE | {"messages": [
            {"role": "assistant", "persona": "Fides", "text": "parola alanı boşken 500"}]}))
        for value in ("şifrem 1234", "password: hunter2", "Parolam kedi99", "kart 4111 1111 1111 1111"):
            self.assertTrue(contains_secret(value), value)

    def test_remembered_facts_are_not_sent(self):
        state = {"busy": False, "messages": [
            {"role": "user", "sender": "user", "memory": "saved", "text": "Benim adım Ali, bunu hatırla"},
            {"role": "assistant", "persona": "Fatum", "text": "Tamam."}]}
        text = build_context(state)
        self.assertNotIn("Ali", text)
        self.assertIn("Fatum: Tamam.", text)

    def test_context_redacts_secrets_and_keeps_six_messages(self):
        many = {"busy": False, "messages": [{"role": "assistant", "persona": "Eos", "text": f"mesaj {i}"} for i in range(10)]
                + [{"role": "assistant", "persona": "Eos", "text": "parolam kedi99"}]}
        text = build_context(many)
        self.assertNotIn("kedi99", text)
        self.assertNotIn("mesaj 4", text)
        self.assertIn("Ekip: boşta.", text)


if __name__ == "__main__":
    unittest.main()
