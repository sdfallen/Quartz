"""Desktop intent and truthful UI state, without native access or permission grants."""
import re
import time

NORMAL_CHAT_DESKTOP_NOTICE = (
    "[QUARTZ MASAÜSTÜ BAĞLANTISI]\n"
    "Bu normal sohbet oturumuna Quartz masaüstü capability araçları bağlanmaz. "
    "Bu, Quartz uygulamasının bilgisayarı hiç kontrol edemediği anlamına gelmez. "
    "Masaüstü görevleri ana sohbetten başlatılır; kullanıcıyı ayrı Ajan Merkezi veya kontrol paneline yönlendirme. "
    "Bu oturumda araç yoksa bunu açıkça belirt; masaüstünü gözlemlemiş gibi davranma. "
    "Pencere/log/süre için ayrı açık onay gerekir; Tam dosya erişimi bunun yerine geçmez. "
    "Kendine yetki vermeye veya sınırları aşmaya çalışma, kullanıcıdan yönetici/OS güvenlik ayarlarını değiştirmesini isteme. "
    "Canlı masaüstü durumunu bu sohbetten biliyormuş gibi davranma; arayüzdeki gerçek görev durumu esastır.\n"
)


def desktop_intent(text):
    from core.message_intent import instruction_text, message_intent, tools_disallowed
    value = instruction_text(text).strip()
    if tools_disallowed(text): return None
    kind = message_intent(text)
    if re.search(r"warband|aster|gate\s*b",value) and kind == 'task': return "task"
    if re.search(r"kendin(?:ize|e|iz).{0,40}(?:yetki|izin|erişim)",value): return "help"
    subject = re.search(r"masaüst|masaustu|bilgisayar|pencere|fare|klavye|not\s*defteri|notepad|uygulama|ekran|chrome|edge|firefox|youtube|tarayıcı|oyun|window|application|browser|screenshot|button", value)
    if not subject: return None
    access = re.search(r"yetki|erişim|erisim|kontrol|hak|izin", value)
    if access and (re.search(r"nasıl|neden|niye|var mı|varmı|yok|versem|verebilir|verebil|alabilir|alabil|açabilir|açabil|mümkün", value)
                   or re.search(r"(?:yetki|erişim|erisim|izin).{0,20}sorun", value)):
        return "help"
    if re.search(r"kontrol etme\b|kontrol etmeyin\b|kontrolünü alma\b|yönetme\b|istemiyorum", value):
        return "help" if access else None
    # The same task decision drives chat and desktop routing. A polite verb is
    # not a capability question, and quoted/sample commands cannot start work.
    if kind == 'task' and not re.search(r'\b(?:sınıf|sınıfını|fonksiyon|fonksiyonunu|regex|kodunu|class|function)\b',value):
        return 'task'
    if access: return "help"
    return None


def desktop_view(coordination=None, desktop=None, pending=None, now=None):
    """A running analyst does not imply an active OS input capability."""
    now = time.time() if now is None else now
    coordination = coordination or {}
    job = coordination.get("job") or {}
    operator = desktop or coordination.get("operator") or {}
    session = operator.get("session") or {}
    base = {"code":"normal", "label":"Normal sohbet", "control_active":False,
            "stop_ref":None, "pending_id":None,
            "detail":"Dosya erişimi ayrı; masaüstü kontrolü görev onayı olmadan açılmaz."}
    if session.get("active"):
        provider = session.get("provider")
        name = "Codex" if provider == "codex" else "Gemini" if provider == "antigravity" else "Operatör"
        linked = bool(coordination.get("active") and job)
        ref = "coord:"+job["id"] if linked else "desktop:"+session["id"] if session.get("id") else None
        return {**base,"code":"active","label":name+" kontrol ediyor", "control_active":True,
                "stop_ref":ref, "conversation_id":job.get("conversation_id") if linked else None,
                "detail":f"{len(session.get('targets') or [session.get('target')])} onaylı pencere · tek operatör. Gözlemci fare/klavye yetkisi almaz."}
    if coordination.get("active"):
        reason = session.get("stop_reason")
        starting = job.get("status") == "starting"
        return {**base,"code":"preparing" if starting else "released",
                "label":"Görev hazırlanıyor" if starting else "Kontrol bırakıldı",
                "stop_ref":"coord:"+job["id"], "conversation_id":job.get("conversation_id"),
                "detail":"Henüz masaüstü yetkisi yok." if starting else "Girdi yetkisi etkin değil; analiz/temizlik sürebilir. "+str(reason or "")[:200]}
    if pending:
        expired = now >= pending.get("expires_at",float("inf"))
        return {**base,"code":"pending","label":"Onay süresi doldu" if expired else "Onay bekliyor",
                "pending_id":pending["id"], "conversation_id":pending.get("conversation_id"),
                "detail":"Yeni görev hazırlayın; eski kart yetki veremez." if expired else "Pencere, proje logu ve süre seçilmeden, açık onay verilmeden hiçbir ajan masaüstünü kontrol edemez."}
    if job or session.get("stop_reason") not in {None,"","not started"}:
        return {**base,"code":"released","label":"Kontrol bırakıldı",
                "detail":"Yeni işlem yeni görev onayı gerektirir. "+str(session.get("stop_reason") or job.get("status") or "")[:200]}
    return base


def desktop_help(view):
    return ("Masaüstü durumu: "+view["label"]+". "+view["detail"]+
            "\nGörevi doğrudan bu sohbete yazın; ayrı kontrol ekranı gerekmez. "
            "Ajan gereken uygulama veya günlük erişimini burada sorar ve onaydan sonra aynı göreve devam eder. "
            "İkinci ajan verilen analiz işini Squad üzerinden yürütür; tek ajan fare/klavyeyi yönetir. "
            "Tam dosya erişimi masaüstü izni değildir; ajanların kendilerine yetki vermesi gerekmez. "
            "Warband için ASTER · Warband / Universal Modder projesini seçin; görev aynı sohbetten özel oyun araçlarına yönlendirilir.")
