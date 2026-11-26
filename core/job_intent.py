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
                       r"nasil\s+\w+(?:il|ul|in|un)ir|"
                       r"onerir\s*mi?sin|fikir\s+ver|ne\s+dusunuyorsun|mumkun\s+mu)\b")
# Work on documents and data, not code (26 Nov): "İndirilenler'deki tüm PDF faturaları tek bir
# tabloya aktar". A heavy verb, a document/data word and many of them; light verbs (özetle,
# incele) only with an explicit sign of scale.
_DATA_HEAVY = re.compile(r"\b(?:aktar\w*|donustur\w*|cevir\w*|birlestir\w*|ayikla\w*|derle\w*|"
                         r"karsilastir\w*|raporla\w*|tablo\w*\s+(?:yap|haline|olustur|hazirla|cikar)\w*|"
                         r"rapor\w*\s+(?:yap|hazirla|cikar|olustur)\w*)")
_DATA_LIGHT = re.compile(r"\b(?:ozetle\w*|analiz\s+et\w*|incele\w*|listele\w*|topla\w*|cikar\w*)")
_DATA_WORDS = r"(?:pdf|excel|xlsx|csv|tablo|fatura|belge|dokuman|evrak|word|docx|fis|makbuz|dekont|dosya|rapor|" \
              r"kayit|kayd|e-?posta|mail|cv|ozgecmis|log|json|txt|metin|fotograf|resim|gorsel)"
_DATA_OBJECT = re.compile(r"\b" + _DATA_WORDS + r"\w*")
_DATA_MANY = re.compile(r"\b(?:tum|butun|hepsi\w*|her\s+bir\w*|\d+\s+(?:tane|adet)|"
                        # Fides 26 Nov (D4): "12 faturayı", "iki PDF dosyasını" - Turkish keeps the noun singular.
                        r"(?:\d+|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|on|yirmi|elli|yuz|bin)\s+(?:\w+\s+)?"
                        + _DATA_WORDS + r"|"
                        r"\w*klasor\w*(?:daki|deki|ndaki|ndeki)|[a-z]+(?:daki|deki)\s+(?:\w+\s+){0,2}"
                        + _DATA_WORDS + r")|\b" + _DATA_WORDS + r"'?(?:lar|ler)\w*")
_HOURS = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*(saat|sa\b|dakika|dk\b)(?!l[iu]k)")
_WORD_HOURS = re.compile(r"\b(bir\s+bucuk|yarim|bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|on)\s+(saat|dakika)"
                         r"(?!l[iu]k)")
_NUMBER_WORDS = {"yarim": 0.5, "bir bucuk": 1.5, "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6,
                 "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10}
_RESUME = re.compile(r"\b(?:coks(?:e|un)\s+(?:bile\s+)?devam|kapan(?:sa|irsa)\s+(?:bile\s+)?devam|"
                     r"yeniden\s+baslay(?:inca|tiginda)\s+devam|kendiligind(?:en)?\s+devam)")


# Fides 26 Nov (D1): "Tüm faturaları tabloya aktarma", "karşılaştırmak istemiyorum", "birleştirmek
# veri kaybına neden olur mu?", "nasıl birleştirebilirim?" started jobs. A question particle after
# a third/first person ("olur mu", "miyim") or a question word is a question; "aktarır mısın" is a
# polite request and stays one. A clause ending in a negative imperative or a refusal is a "no".
_ASKING = re.compile(r"\b(?:nasil|neden|niye|nicin|hangi\w*|ne\s+zaman|ne\s+kadar)\b|"
                     r"\bm[iu](?:yim|yiz|dur|dir)?\b|\w(?:ebilir|abilir)(?:im|iz)\b")
_POLITE_TAIL = re.compile(r"(?:\s+(?:lutfen|simdilik|artik|hemen|ya|be|bari|tamam\w*|olur\s*mu|sakin))+$")
_NEG_IMPERATIVE = re.compile(r"\w+(?:ma|me)(?:yin|yiniz|yalim|yelim)?$")
# Fides 2nd re-review 26 Nov: "Bunu yapma.", "İstemiyorum.", "Gerek yok." withdraw the request in a
# sentence of their own; only a pronoun ("bunu") or nothing at all stands for the work there.
_STANDALONE_NO = re.compile(r"(?:(?:bunu|bunlari|onu|onlari|sunu|bu|o|hic|ama|aslinda|yok|hayir)\s+)*"
                            r"(?:istemiyor\w*|istemem|gerek\s+yok|yapma(?:yin)?|etme(?:yin)?|yapmayalim|"
                            r"hayir|bosver\w*|iptal(?:\s+et)?|dur|durdur|birak)")


def forbidden_or_asked(text: str) -> bool:
    """The request is a question about the work or forbids it; it starts nothing."""
    folded = turkish_fold(instruction_text(text)).strip()
    if _ASKING.search(folded):
        return True
    # Fides re-review 26 Nov: "aktarma lütfen" is still a no; "aktar; kaynak dosyalara dokunma" is
    # a job with a limit. A clause refuses the work only when what it negates is the work itself.
    for clause in re.split(r"[.;!?,]+", folded):
        clause = _POLITE_TAIL.sub("", " " + clause.strip()).strip()
        if not clause:
            continue
        about_the_work = bool(_DATA_HEAVY.search(clause) or _DATA_LIGHT.search(clause))
        if re.search(r"\bvazgec\w*", clause) or _STANDALONE_NO.fullmatch(clause):
            return True
        if about_the_work and re.search(r"\b(?:istemiyor\w*|istemem|gerek\s+yok)\b", clause):
            return True
        if about_the_work and _NEG_IMPERATIVE.search(clause.split()[-1]):
            return True
    return False


def data_job_request(text: str) -> bool:
    """Many documents or records turned into something new ("tüm faturaları tabloya aktar").

    A single file ("bu PDF'i özetle", "faturayı Excel'e aktar") stays an ordinary turn, and so
    does a question ("PDF'ten Excel'e nasıl aktarılır")."""
    value = instruction_text(text).strip()
    if not value or tools_disallowed(value) or request_withdrawn(value):
        return False
    folded = turkish_fold(value)
    if _QUESTION.search(folded) or _RUN_FILE.search(folded) or not _DATA_OBJECT.search(folded):
        return False
    if forbidden_or_asked(value):
        return False
    scale = bool(_SCALE.search(folded) or _HOURS.search(folded))
    if _DATA_HEAVY.search(folded):
        return bool(_DATA_MANY.search(folded) or scale)
    # "tüm mailleri özetle" is one answer; only a stated duration makes it a job.
    timed = bool(_HOURS.search(folded) or _WORD_HOURS.search(folded))
    return bool(_DATA_LIGHT.search(folded) and _DATA_MANY.search(folded) and timed)


def _code_job_request(text: str) -> bool:
    """A build or engineering job (see big_job_request)."""
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


def source_paths(text: str, limit: int = 5) -> list[str]:
    """Existing files and folders the request names by an absolute path, spaces included
    ("C:\\Users\\...\\SpeS Projeleri\\faturalar klasöründeki" -> that folder)."""
    words = str(text or "").split()
    found, i = [], 0
    while i < len(words) and len(found) < limit:
        if re.match(r"^[\"'(]?[A-Za-z]:[\\/]", words[i]):
            best, end = None, i
            for j in range(i, min(len(words), i + 12)):
                candidate = " ".join(words[i:j + 1]).strip("\"'().,;:")
                for option in (candidate, re.sub(r"'\w*$", "", candidate)):
                    try:
                        if option and Path(option).exists():
                            best, end = option, j
                    except OSError:
                        pass
            if best:
                path = str(Path(best))
                if path not in found:
                    found.append(path)
                i = end + 1
                continue
        i += 1
    return found


_HERE = re.compile(r"\b(?:bu|su|o)\s+(?:klasor|proje|dizin|dosyalar)\w*|\bburada\w*|\bburadaki\b|"
                   r"\bmevcut\s+(?:klasor|proje)\w*|\bprojedeki\b|\bprojemdeki\b")
# The user's well-known folders by their Turkish names ("İndirilenler'deki", "Masaüstündeki").
_KNOWN_FOLDERS = (("indirilenler", "Downloads"), ("masaustu", "Desktop"), ("belgeler", "Documents"),
                  ("resimler", "Pictures"), ("muzik", "Music"), ("videolar", "Videos"))


def named_sources(text: str) -> list[str]:
    """Sources a data request names: absolute paths, then the user's well-known folders.

    26 Nov: a request without a path took the conversation's project as its source, which after
    one job is that job's output folder. "Bu klasör" still means it (refers_here); a named folder
    is resolved only when it exists; anything else gets no source rather than a wrong one."""
    found = source_paths(text)
    if found:
        return found
    folded = turkish_fold(instruction_text(text))
    home = Path.home()
    for word, name in _KNOWN_FOLDERS:
        if re.search(r"\b" + word + r"\w*", folded):
            for folder in (home / name, home / "OneDrive" / name):
                if folder.is_dir():
                    found.append(str(folder))
                    break
    return found[:5]


def refers_here(text: str) -> bool:
    """"Bu klasördeki", "buradaki", "projedeki": the request means the conversation's project."""
    return bool(_HERE.search(turkish_fold(instruction_text(text))))


def without_paths(text: str) -> str:
    """The request with its file paths left out: the words of a path never decide what the job is.

    Live 26 Nov 14:22: "C:\\...\\SpeS Projeleri\\faturalar klasöründeki tüm faturaları firmalara göre
    karşılaştır ve rapor hazırla, 20 dakika çalış" became a code job ("Projeleri" + "hazırla" + "20
    dakika"), so it got no folder of its own and no source check."""
    return " ".join(w for w in str(text or "").split() if "\\" not in w and "/" not in w)


def job_kind(text: str) -> str | None:
    """"code" for a build or engineering job, "data" for work on documents, else None."""
    text = without_paths(text)
    if _code_job_request(text):
        return "code"
    return "data" if data_job_request(text) else None


def big_job_request(text: str) -> bool:
    """A plain-words request for work too large for one turn: a code job or a data job.

    Conservative: a build verb AND (a whole product with a sign of scale, or an explicit
    duration/"from start to finish"); or many documents turned into something new.
    Questions, withdrawn requests and "no tools" stay ordinary turns; a short "notepad'i aç"
    never matches."""
    return job_kind(text) is not None


_NEW_PROJECT = re.compile(r"\b(?:yeni\s+(?:bir\s+)?(?:klasor|proje|depo|repo)\w*|bos\s+(?:bir\s+)?klasor\w*|"
                          r"ayri\s+(?:bir\s+)?(?:klasor|proje)\w*|new\s+(?:folder|project))")


def wants_new_project(text: str) -> bool:
    """"Yeni bir klasörde sıfırdan ... yap": the job gets a project of its own (Eos, 25 Nov)."""
    return bool(_NEW_PROJECT.search(turkish_fold(instruction_text(text))))


def new_project_folder(text: str, clock_text: str, base=None) -> Path:
    """A fresh, unused folder named after the request, under Documents\\SpeS Projeleri."""
    import os
    base = Path(base or os.getenv("SPES_PROJECTS_HOME") or Path.home() / "Documents" / "SpeS Projeleri")
    # Live 26 Nov: "C:\Users\...\fatura-kaynaklari klasöründeki ..." named the folder "c-users-lenavo-...";
    # paths in the request never name the job.
    request = " ".join(w for w in instruction_text(text).split() if "\\" not in w and "/" not in w)
    words = [w for w in re.findall(r"[a-z0-9]+", turkish_fold(request))
             if w not in {"bir", "ve", "ile", "icin", "bu", "su", "yeni", "klasor", "klasorde", "proje", "projede",
                          "bana", "sifirdan", "bastan", "sona", "yap", "olustur", "gelistir", "kur", "saat", "dakika",
                          "tum", "butun", "tek", "deki", "daki", "hepsini", "lutfen", "klasorundeki", "klasordeki",
                          "calis", "dakika", "da", "de"}
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
    "{kind_rule}"
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
    # Live 26 Nov: "spes/1126-1232-c-users-lenavo-documents-spes-pr"; a path never names the branch.
    words = " ".join(w for w in str(goal or "").split() if "\\" not in w and "/" not in w)
    slug = re.sub(r"[^a-z0-9]+", "-", turkish_fold(words))[:32].strip("-") or "is"
    return f"spes/{clock_text}-{slug}"


DATA_PLAN_RULE = (
    "Bu bir dosya/veri işi, yazılım değil. Kaynak dosyalar yalnız okunur; hiçbiri değiştirilmez, taşınmaz, "
    "yeniden adlandırılmaz ya da silinmez. Bütün çıktılar projenin klasörüne yazılır. İlk taş kaynakları bulur "
    "ve projeye kaynaklar.md olarak listeler (yol, sayı). Kabul ölçütleri dosyalarla doğrulanabilir olsun "
    "(\"cikti/faturalar.csv var; 12 faturanın her biri bir satır; tarih, firma, tutar sütunları dolu\" gibi).\n")


def plan_rule(kind: str | None = None, sources=()) -> str:
    rule = DATA_PLAN_RULE if kind == "data" else ""
    if rule and sources:
        rule += ("KAYNAKLAR (yalnız okunur; isteğin \"bu klasör\" dediği yer dahil): "
                 + "; ".join(str(s) for s in sources) + "\n")
    return PLAN_RULE.format(max=MAX_MILESTONES, kind_rule=rule)


def job_spec(text: str, milestones: list[dict], project_path, clock_text: str, full_access=False,
             kind: str | None = None, sources=()) -> dict:
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
            "git_branch": job_branch(project_path, goal, clock_text), "kind": "data" if kind == "data" else "code",
            **({"sources": [str(s) for s in sources][:5]} if kind == "data" and sources else {})}


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
