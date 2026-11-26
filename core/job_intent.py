"""One request, the whole job (user request 25 Nov 2026: "/uzun-iş gibi komutları kaldır; tek
istekle SpeS her şeyi yapabilmeli").

SpeS recognises a request for a large piece of work in plain words, the lead agent writes a
milestone plan read-only, and SpeS starts the long job from it. Nothing an agent writes can
widen the job: the plan only gives milestone titles and acceptance criteria; the duration
comes from the user's own words (or a modest default), the check command only from a fixed
list SpeS detects itself, and the permission level from the user's switch.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.message_intent import instruction_text, request_withdrawn, tools_disallowed, turkish_fold

DEFAULT_HOURS = 1.0
MAX_DEFAULT_HOURS = 4.0
MAX_MILESTONES = 8

# A build verb: the user wants something made, not explained.
_BUILD = re.compile(
    r"\b(?:yap(?!ay)\w*|olustur\w*|gelistir\w*|kodla\w*|programla\w*|tasarla\w*|hazirla\w*|"
    r"bitir\w*|tamamla\w*|insa\s+et\w*|yaz(?:ar|in|iniz|abilir|mani|man|sana)?\w{0,6}\b|"
    r"kur(?:ar|un|abilir|mani|man)?\b|build|create|make|develop|implement)")
_MAKE = re.compile(
    r"\b(?:yap(?!ay)\w*|olustur\w*|gelistir\w*|kodla\w*|programla\w*|tasarla\w*|hazirla\w*|"
    r"insa\s+et\w*|yaz(?:ar|in|iniz|abilir|mani|man|sana)?\w{0,6}\b|kur(?:ar|un|abilir|mani|man)?\b|"
    r"build|create|make|develop|implement)")
# Engineering work on an existing project (Eos, 25 Nov: "projeyi baştan sona refactor et").
_FIX = re.compile(r"\b(?:refactor\w*|yeniden\s+duzenle\w*|temizle\w*|duzelt\w*|iyilestir\w*|"
                  r"optimize\s+et\w*|tasi(?:r|yin)?\b|guncelle\w*|modernlestir\w*)")
_SCOPE = re.compile(r"\b(?:proje\w*|kod\w*|modul\w*|test\w*|hata\w*|guvenlik|acik\w*|bellek|performans|"
                    r"mimari\w*|depo\w*|repo\w*|bagimlilik\w*|dokumantasyon\w*|tip\s+hata\w*)")
# "zor_test.py'yi çalıştır ve bitir": running a named file is a task, not a job.
_RUN_FILE = re.compile(r"\b[\w./\\-]+\.(?:py|exe|bat|ps1|js)\b.{0,80}\bcalistir|\bcalistir\w*\b.{0,80}"
                       r"\b[\w./\\-]+\.(?:py|exe|bat|ps1|js)\b")
# Something big: a whole product, a long time, or "from start to finish".
_BIG_THING = re.compile(
    r"\b(?:oyun\w*|uygulama\w*|app\b|web\s*site\w*|site\w*|sistem\w*|platform\w*|motor\w*|eklenti\w*|"
    r"arayuz\w*|panel\w*|bot\w*|api\b|backend|frontend|kutuphane\w*|program\w*|simulasyon\w*|"
    r"oyun\s+motoru|editor\w*|dashboard)")
_SCALE = re.compile(
    r"\b(?:bastan\s+sona|bastan\s+asagi|eksiksiz|tamamen|komple|tum\s+ozellik|butun\s+ozellik|her\s+seyi|"
    r"\d+(?:[.,]\d+)?\s*(?:saat|sa\b|dakika|dk\b)(?!l[iu]k)|uzun\s+(?:bir\s+)?is|adim\s+adim|asama\s+asama|"
    r"kendin\s+bitir|sonuna\s+kadar|calisir\s+hale|oynanabilir|yayinlanabilir|from\s+scratch|end\s+to\s+end|"
    r"(?:tum|butun)\s+\w+(?:lari|leri)\w*|%\s*\d+|yuzde\s*\d+|"
    r"(?:bir|iki|uc|dort|bes|alti|yarim|bir\s+bucuk)\s+(?:saat|dakika)(?!l[iu]k))")
# Questions and explanations about such things stay ordinary turns.
_QUESTION = re.compile(r"\b(?:nasil\s+yapilir|nedir|ne\s+demek|nasil\s+(?:yapar|yapabilirim)|"
                       r"onerir\s*mi?sin|fikir\s+ver|ne\s+dusunuyorsun|mumkun\s+mu)\b")
_HOURS = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*(saat|sa\b|dakika|dk\b)(?!l[iu]k)")
_WORD_HOURS = re.compile(r"\b(bir\s+bucuk|yarim|bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|on)\s+(saat|dakika)"
                         r"(?!l[iu]k)")
_NUMBER_WORDS = {"yarim": 0.5, "bir bucuk": 1.5, "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6,
                 "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10}
_RESUME = re.compile(r"\b(?:coks(?:e|un)\s+(?:bile\s+)?devam|kapan(?:sa|irsa)\s+(?:bile\s+)?devam|"
                     r"yeniden\s+baslay(?:inca|tiginda)\s+devam|kendiligind(?:en)?\s+devam)")


def big_job_request(text: str) -> bool:
    """A plain-words request for work too large for one turn.

    Conservative: a build verb AND (a whole product with a sign of scale, or an explicit
    duration/"from start to finish"). Questions, withdrawn requests and "no tools" stay
    ordinary turns; a short "notepad'i aç" never matches.
    """
    value = instruction_text(text).strip()
    if not value or tools_disallowed(value) or request_withdrawn(value):
        return False
    folded = turkish_fold(value)
    if _QUESTION.search(folded):
        return False
    scale = bool(_SCALE.search(folded) or _HOURS.search(folded))
    thing = bool(_BIG_THING.search(folded))
    if _BUILD.search(folded) and thing and (scale or len(folded.split()) >= 40):
        return True
    # A big engineering job with no product word: "projeyi baştan sona refactor et, 3 saat çalış".
    return bool((_MAKE.search(folded) or _FIX.search(folded)) and _SCOPE.search(folded) and scale
                and not _RUN_FILE.search(folded))


_NEW_PROJECT = re.compile(r"\b(?:yeni\s+(?:bir\s+)?(?:klasor|proje|depo|repo)\w*|bos\s+(?:bir\s+)?klasor\w*|"
                          r"ayri\s+(?:bir\s+)?(?:klasor|proje)\w*|new\s+(?:folder|project))")


def wants_new_project(text: str) -> bool:
    """"Yeni bir klasörde sıfırdan ... yap": the job gets a project of its own (Eos, 25 Nov)."""
    return bool(_NEW_PROJECT.search(turkish_fold(instruction_text(text))))


def new_project_folder(text: str, clock_text: str, base=None) -> Path:
    """A fresh, unused folder named after the request, under Documents\\SpeS Projeleri."""
    import os
    base = Path(base or os.getenv("SPES_PROJECTS_HOME") or Path.home() / "Documents" / "SpeS Projeleri")
    words = [w for w in re.findall(r"[a-z0-9]+", turkish_fold(instruction_text(text)))
             if w not in {"bir", "ve", "ile", "icin", "bu", "su", "yeni", "klasor", "klasorde", "proje", "projede",
                          "bana", "sifirdan", "bastan", "sona", "yap", "olustur", "gelistir", "kur", "saat", "dakika"}
             and not w.isdigit()]
    slug = "-".join(words[:4])[:40].strip("-") or "is"
    folder = base / f"{slug}-{clock_text}"
    index = 2
    while folder.exists():
        folder = base / f"{slug}-{clock_text}-{index}"
        index += 1
    return folder


def requested_hours(text: str) -> float:
    """The duration in the user's own words; otherwise the default. Never above 12 hours."""
    folded = turkish_fold(instruction_text(text))
    match = _HOURS.search(folded)
    if match:
        # "2-3 saat": the upper end is what the user allowed.
        amount = float((match.group(2) or match.group(1)).replace(",", "."))
        unit = match.group(3)
    else:
        worded = _WORD_HOURS.search(folded)
        if not worded:
            return DEFAULT_HOURS
        amount = _NUMBER_WORDS[" ".join(worded.group(1).split())]
        unit = worded.group(2)
    hours = amount / 60 if unit.startswith("d") else amount
    return max(0.1, min(12.0, hours))


def wants_auto_resume(text: str) -> bool:
    return bool(_RESUME.search(turkish_fold(instruction_text(text))))


PLAN_RULE = (
    "Görevin: kullanıcının isteğini, SpeS'in sırayla yaptıracağı kilometre taşlarına böl. Şimdi HİÇBİR şey "
    "yazma ya da değiştirme; yalnız projeyi okuyabilirsin. İş planı SpeS'e gidecek, kullanıcıya değil.\n"
    "Kurallar: 2 ile {max} arası taş; her taş tek bir turda bitebilecek büyüklükte, bir öncekinin üstüne kurulur. "
    "Her taşın kabul ölçütü somut ve gözle/testle doğrulanabilir olsun (\"oyun açılıyor ve oyuncu ok tuşlarıyla "
    "hareket ediyor\" gibi). Kullanıcının istediği her özellik bir taşa düşsün; hiçbirini atlama. Son taş "
    "bütün işi baştan sona dener ve eksik bırakmaz.\n"
    "Yanıtın YALNIZ şu biçimde olsun, başka metin yazma:\n"
    "PLAN\n1. Başlık | kabul ölçütü\n2. Başlık | kabul ölçütü\n...\nSON\n")

_STEP = re.compile(r"^\s*(\d{1,2})[.)]\s*(.+?)\s*\|\s*(.+?)\s*$")


def parse_plan(text: str) -> list[dict]:
    """Milestones from the planner's reply; [] when it gave none in the agreed form."""
    body = str(text or "")
    start = re.search(r"^\s*PLAN\s*$", body, re.M)
    if start:
        body = body[start.end():]
    end = re.search(r"^\s*SON\s*$", body, re.M)
    if end:
        body = body[:end.start()]
    steps = []
    for line in body.splitlines():
        match = _STEP.match(line.strip().strip("*").strip())
        if match:
            title = match.group(2).strip(" *`")
            acceptance = match.group(3).strip(" *`")
            if title and acceptance:
                steps.append({"title": title[:200], "acceptance": acceptance[:2000]})
    if len(steps) > MAX_MILESTONES:
        last, extra = steps[MAX_MILESTONES - 1], steps[MAX_MILESTONES:]
        folded = "; ".join(f"{s['title']}: {s['acceptance']}" for s in extra)
        steps = steps[:MAX_MILESTONES - 1] + [{"title": last["title"][:200],
                                               "acceptance": (last["acceptance"] + " Ayrıca: " + folded)[:2000]}]
    return steps


def fallback_plan(text: str) -> list[dict]:
    """When the planner gave nothing usable the user's own request is the single milestone."""
    return [{"title": "İsteğin tamamı",
             "acceptance": "Kullanıcının isteğindeki her madde yapıldı, çalıştırılıp denendi ve eksik kalmadı: "
                           + " ".join(str(text or "").split())[:1500]}]


def detected_check(project_path) -> list[str] | None:
    """The project's own tests, from a fixed list SpeS knows; never a command an agent wrote.

    Looked up again before every milestone's check (Eos, 25 Nov): a job that starts in an
    empty folder gets its tests from its own first milestones.
    """
    import json
    root = Path(str(project_path or ""))
    if not root.is_dir():
        return None
    pyproject = root / "pyproject.toml"
    pytest_configured = (root / "pytest.ini").is_file() or (
        pyproject.is_file() and "[tool.pytest" in pyproject.read_text(encoding="utf-8", errors="replace"))
    tests = root / "tests"
    if tests.is_dir() and any(tests.glob("test_*.py")):
        if pytest_configured:
            return ["python", "-B", "-m", "pytest", "-q"]
        return ["python", "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."]
    if any(root.glob("test_*.py")):
        return ["python", "-B", "-m", "pytest", "-q"] if pytest_configured else \
            ["python", "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"]
    package = root / "package.json"
    if package.is_file():
        try:
            script = str((json.loads(package.read_text(encoding="utf-8")).get("scripts") or {}).get("test") or "")
        except (ValueError, OSError):
            script = ""
        if script and "no test specified" not in script:
            return ["npm.cmd", "test", "--silent"]
    if (root / "Cargo.toml").is_file():
        return ["cargo", "test", "--quiet"]
    return None


def job_branch(project_path, goal: str, clock_text: str) -> str | None:
    """A branch of the job's own in a Git project, so every milestone is a commit the user can undo."""
    root = Path(str(project_path or ""))
    if not (root / ".git").exists():
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", turkish_fold(goal))[:32].strip("-") or "is"
    return f"spes/{clock_text}-{slug}"


def job_spec(text: str, milestones: list[dict], project_path, clock_text: str, full_access=False) -> dict:
    """The job as the user asked for it: their words, their duration, SpeS's own check.

    Fides 26 Nov (F1): the check runs the project's tests on the host, and the writer can
    write those tests (or package.json's test script). With Proje permission ("yalnız dosya
    yazar, komut çalıştıramaz") SpeS therefore runs no check at all; the teammate's review
    decides. Only Tam Yetki, where the writer may run commands anyway, gets the check."""
    goal = " ".join(str(text or "").split())
    full = bool(full_access)
    return {"goal": goal[:4000], "milestones": milestones or fallback_plan(text),
            "hours": requested_hours(text), "auto_resume": wants_auto_resume(text),
            "verify": detected_check(project_path) if full else None, "auto_check": full, "review": True,
            "git_branch": job_branch(project_path, goal, clock_text)}


# -- talking to a running job in plain words ------------------------------------------
_STATUS = re.compile(r"^\s*(?:ne\s+durumda(?:sin|yiz)?|durum(?:\s+ne)?|nerede\s+kaldin|neredesin|"
                     r"ne\s+kadar\s+kaldi|is\s+ne\s+durumda|ilerleme\s+ne)\s*[?.!]*\s*$")
_STOP = re.compile(r"^\s*(?:isi\s+)?(?:dur|durdur|iptal\s+et|isi\s+durdur|birak|vazgec(?:tim)?)\s*[.!]*\s*$")
_PAUSE = re.compile(r"^\s*(?:biraz\s+)?(?:bekle|duraklat|ara\s+ver)\s*[.!]*\s*$")
_RESUME_WORD = re.compile(r"^\s*(?:devam(?:\s+et)?|surdur|kaldigin\s+yerden\s+devam(?:\s+et)?)\s*[.!]*\s*$")


_FILLER = re.compile(r"^(?:(?:peki|tamam|simdi|su\s+an|simdilik|lutfen|hey|spes|ya)[\s,]+)+|"
                     r"(?:[\s,]+(?:lutfen|simdilik|artik|hemen|su\s+an))+(?=\s*[?.!]*\s*$)")


_SKIP = re.compile(r"\b(\d{1,2})\s*\.?\s*(?:(?:numarali|nolu|inci|nci|uncu|ncu)\s+)?(?:adim|tas|asama|kilometre\s+tasi)\w*\s+(?:iptal\s+et|cikar|atla|kaldir|yapma)")
_LEAD = re.compile(r"^(?:(?:peki|tamam|simdi|su\s+an|simdilik|lutfen|hey|spes|ya)[\s,]+)+")
_ADD_TAIL = re.compile(r"^(.{3,}?)\s+(?:de|da)\s+ekle(?:r\s*misin|yin|\s+lutfen)?\s*[.!]*\s*$")
_ADD_HEAD = re.compile(r"^(?:(?:sunu|bunu|su|bu)\s+da\s+ekle|yeni\s+(?:bir\s+)?(?:adim|tas|asama)\s+ekle|plana\s+ekle|"
                       r"ayrica\s+ekle)\s*[:,-]?\s*(.{3,})$")


def job_change(text: str):
    """("skip", 3) for "3. adımı iptal et"; ("add", "koyu tema") for "koyu tema da ekle"; else None."""
    raw = " ".join(str(text or "").split())
    if negated(raw):
        return None
    folded = turkish_fold(raw)
    if len(folded) != len(raw):  # spelling the fold cannot keep aligned: use the folded text
        raw = folded
    lead = _LEAD.match(folded)
    cut = lead.end() if lead else 0
    body, raw_body = folded[cut:], raw[cut:]
    skip = _SKIP.search(body)
    if skip:
        return ("skip", int(skip.group(1)))
    for pattern in (_ADD_HEAD, _ADD_TAIL):
        match = pattern.match(body)
        if match:
            return ("add", raw_body[match.start(1):match.end(1)].strip(" .!:,-"))
    return None


_EXTEND = re.compile(r"\b(?:daha|ek\s+(?:sure|zaman)|fazladan|uzat)\b")
# Fides 26 Nov (F4): "3. adımı iptal etme", "15 dakika daha çalışma, dur" were applied backwards.
_NEGATED = re.compile(r"\b(?:iptal\s+etme(?:yin|yelim)?|atlama(?:yin)?|cikarma(?:yin)?|kaldirma(?:yin)?|"
                      r"ekleme(?:yin)?|calisma(?:yin)?|uzatma(?:yin)?|devam\s+etme(?:yin)?|gerek\s+yok|"
                      r"istemiyorum|vazgec\w*|dur|durdur\w*|yapma(?:yin)?)\b")


def negated(text: str) -> bool:
    """The message withdraws or forbids a change ("etme", "gerek yok", "dur")."""
    return bool(_NEGATED.search(turkish_fold(instruction_text(text)))) or request_withdrawn(text)


def extension_hours(text: str) -> float | None:
    """"15 dakika daha çalış", "bir saat daha devam et", "süreyi 30 dakika uzat" -> hours."""
    folded = turkish_fold(instruction_text(text))
    if negated(text) or not _EXTEND.search(folded) or not (_HOURS.search(folded) or _WORD_HOURS.search(folded)):
        return None
    return requested_hours(text)


def job_message_kind(text: str) -> str:
    """What a message in a conversation with a running job means: status, stop, pause, resume or note.

    Polite fillers around the words count too (Eos, 25 Nov: "Peki şu an ne durumda?",
    "Şimdilik durdur lütfen")."""
    folded = _FILLER.sub("", turkish_fold(str(text or "")).strip()).strip()
    # Fides re-review 26 Nov (F4): "15 dakika daha çalışma, dur" is a Stop; its last clause decides.
    last_clause = re.split(r"[,;.!?]+", folded.rstrip(" .!?"))[-1].strip()
    if last_clause != folded and _STOP.match(last_clause):
        return "stop"
    if _STATUS.match(folded):
        return "status"
    if _STOP.match(folded):
        return "stop"
    if _PAUSE.match(folded):
        return "pause"
    if _RESUME_WORD.match(folded):
        return "resume"
    change = job_change(text)
    if change:
        return change[0]
    return "note"
