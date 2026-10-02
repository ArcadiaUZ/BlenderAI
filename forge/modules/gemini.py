"""Google AI Studio (Gemini) mijozi: matn + rasm generatsiya.

SDK talab qilmaydi - sof REST (urllib).
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

from . import config

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
RETRIES = 4

# Matn modellari — kunlik/daqiqalik limitlar turadi, shuning uchun
# zaxira zanjir kerak. Birinchisi ishlamasa keyingisiga o'tadi.
TEXT_FALLBACKS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]

# Rasm modellari - birinchisi ishlamasa keyingisiga o'tadi.
# Ba'zi kalitlarda bitta model kvotasi yoqilgan bo'ladi.
IMAGE_FALLBACKS = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image",
    "gemini-3-pro-image-preview",
]

_WORKING_TEXT_MODEL = None
_WORKING_IMAGE_MODEL = None


class QuotaError(RuntimeError):
    """Kalit to'g'ri, lekin kvota (pul tier / bepul limit) yetarli emas."""


class ModelGoneError(RuntimeError):
    """Bu model bu kalit uchun mavjud emas (eskirgan yoki yangi user'da yopiq)."""


def _post(model, payload, timeout=180):
    cfg = config.load_env()
    key = config.api_key()
    url = f"{API_BASE}/{model}:generateContent"
    last = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            last = f"HTTP {e.code}: {body[:400]}"
            if e.code == 429:
                # kvota tugagan - orqali urinish foyda bermaydi
                if "free_tier" in body and re.search(r"limit[\\\"']*:\s*0\b", body):
                    raise QuotaError(_quota_msg(body)) from None
                time.sleep(2 ** attempt * 3)
                continue
            # 429/503 -> backoff, 400 (kalit xato) -> darhol to'xta
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt * 3)
                continue
            if e.code == 404:
                raise ModelGoneError(f"{model}: {last}") from None
            break
        except (QuotaError, ModelGoneError):
            raise
        except Exception as e:  # tarmoq xatosi
            last = str(e)
            time.sleep(2 ** attempt * 3)
    raise RuntimeError(f"Gemini xatosi ({model}): {last}")


def _quota_msg(body):
    import re as _re
    models = sorted(set(_re.findall(r"model: ([A-Za-z0-9._-]+)", body)))
    which = ", ".join(models[:3]) if models else "tasdiqlanmagan"
    return (
        "Kvota yetarli emas (limit: 0).\n"
        f"  Model: {which}\n"
        "  Kalit to'g'ri, lekin bu Google Cloud loyihasida rasm generatsiyasi\n"
        "  uchun kvota yo'q. Yechim:\n"
        "    1) https://console.cloud.google.com/billing -> billing yoqish\n"
        "    2) https://aistudio.google.com/apikey -> yangi loyiha/kalit\n"
        "    3) https://ai.google.dev/gemini-api/docs/rate-limits -> limitlar"
    )


def _parts_of(resp):
    cands = resp.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini javobida candidate yo'q: {json.dumps(resp)[:300]}")
    return ((cands[0].get("content") or {}).get("parts")) or []


# --------------------------------------------------------------- matn

def text(prompt, model=None, system=None, temperature=0.6, max_retries=2):
    """Matn javobini str qaytaradi. Model ishlamasa zaxiraga o'tadi."""
    last = None
    for m in _text_chain(model):
        try:
            return _text_call(prompt, m, system, temperature, max_retries)
        except ModelGoneError as e:
            last = str(e)
            continue
        except QuotaError:
            # butun layner kvotasi tugagan bo'lishi mumkin
            last = f"{m}: kvota tugagan"
            continue
        except Exception as e:
            last = f"{m}: {str(e)[:200]}"
            continue
    raise RuntimeError("Matn javobi olinmadi:\n  " + str(last))


def _text_chain(preferred=None):
    first = preferred or config.cfg("FORGE_TEXT_MODEL", TEXT_FALLBACKS[0])
    if preferred and preferred == _WORKING_TEXT_MODEL:
        return [preferred]
    chain = [first] + [m for m in TEXT_FALLBACKS if m != first]
    return chain


def _text_call(prompt, model, system, temperature, max_retries):
    parts = []
    if system:
        parts.append({"text": f"System instruction: {system}"})
    parts.append({"text": prompt})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT"],
            "temperature": temperature,
        },
    }
    last = None
    for _ in range(max_retries + 1):
        resp = _post(model, payload)
        try:
            txt = "\n".join(p["text"] for p in _parts_of(resp) if "text" in p).strip()
            if txt:
                global _WORKING_TEXT_MODEL
                _WORKING_TEXT_MODEL = model
                return txt
            last = "bo'sh javob"
        except Exception as e:
            last = str(e)
    raise RuntimeError(f"Matn javobi olinmadi: {last}")


def json_text(prompt, schema_hint="", system=None, model=None, temperature=0.4,
              strip_thinking=True):
    """Modeldan JSON qaytarishni so'raydi va parse qiladi."""
    base = "Faqat JSON obyekti qaytarib ber. Markdown code fence ishlatma."
    if strip_thinking:
        base += "\nO'ylab ko'rish (thinking) matnini umuman yozma."
    body = "\n\n".join(x for x in [base, schema_hint, prompt] if x)
    raw = text(body, model=model, system=system, temperature=temperature)
    return parse_json(raw)


def parse_json(raw):
    """Model javobidan JSON topishga (code fence / kirish-chiqish tozalash)."""
    if not raw:
        raise RuntimeError("Bo'sh javob")
    s = raw.strip()
    s = re.sub(r"^<think>.*?</think>", "", s, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, flags=re.S)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    # birinchi { ... } yoki [ ... ] qismni topamiz
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = s.find(open_c), s.rfind(close_c)
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                pass
    raise RuntimeError(f"JSON parse qilinmadi:\n{raw[:600]}")


# --------------------------------------------------------------- rasm

def image_model():
    """Ishlaydigan rasm modelini topadi va keshlaydi."""
    global _WORKING_IMAGE_MODEL
    if _WORKING_IMAGE_MODEL:
        return _WORKING_IMAGE_MODEL
    first = config.cfg("FORGE_IMAGE_MODEL", IMAGE_FALLBACKS[0])
    chain = [first] + [m for m in IMAGE_FALLBACKS if m != first]
    errors = []
    for m in chain:
        try:
            _check_image_model(m)
            _WORKING_IMAGE_MODEL = m
            return m
        except ModelGoneError as e:
            errors.append(f"{m}: model mavjud emas")
        except QuotaError as e:
            errors.append(f"{m}: kvota 0")
        except Exception as e:
            errors.append(f"{m}: {str(e)[:120]}")
    raise QuotaError("Ishlaydigan rasm modeli topilmadi:\n  "
                     + "\n  ".join(errors) + "\n\n" + _quota_msg("free_tier limit: 0"))


def _check_image_model(m):
    """Model mavjudligi va kvotani tekshiradi (arzon - rasm yaratmaydi,
    faqat 1 so'rov yuboradi; muvaffaqiyatsiz bo'lsa hech narsa sarflanmaydi)."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {"responseModalities": ["TEXT"]},
    }
    _post(m, payload, timeout=60)


def image(prompt, out_path, model=None, aspect="1:1", timeout=300, retries=2):
    """Matndan rasm yaratadi va PNG fayliga saqlaydi. Qaytaradi: out_path"""
    model = model or image_model()
    full = (
        f"{prompt}\n\n"
        f"Aspect ratio: {aspect}. Output must be a single image, no text, "
        f"no watermark, no border, no frame, no collage."
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": full}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "temperature": 1.0,
        },
    }
    last = None
    for attempt in range(retries):
        resp = _post(model, payload, timeout=timeout)
        for p in _parts_of(resp):
            inline = p.get("inline_data") or p.get("inlineData")
            if inline and inline.get("data"):
                data = base64.b64decode(inline["data"])
                out_path = os.fspath(out_path)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(data)
                return out_path
        last = "rasm qaytarilmadi"
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"Rasm yaratilmadi: {last}")


def test_key():
    """Kalit ishlayotganini tekshirish. Qaytaradi: (ok, xabar)."""
    if not (config.cfg("GEMINI_API_KEY") or config.cfg("GOOGLE_API_KEY") or "").strip():
        return False, "forge/.env da GEMINI_API_KEY bo'sh qoldirilgan"
    try:
        out = text("Reply with exactly: OK", temperature=0.0)
        return True, f"{_WORKING_TEXT_MODEL} -> {out.strip()[:20]}"
    except QuotaError as e:
        return False, f"kvota: {str(e)[:200]}"
    except Exception as e:
        return False, str(e)[:300]


def test_image():
    """Rasm kvotasi bormi. Qaytaradi: (ok, xabar)."""
    try:
        return True, image_model()
    except Exception as e:
        return False, str(e)
