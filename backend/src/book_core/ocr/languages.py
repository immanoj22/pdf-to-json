"""Explicit Lingua/Tesseract mappings, script fallback, and installation discovery.

Lingua identifies languages, not the simplified/traditional Chinese orthography.
Both Chinese packs are therefore requested unless the job supplies one explicitly.
An absent language model is an error, never silently substituted with English.
"""

from pathlib import Path

# All 75 languages supported by Lingua 2.2; ISO-639-1, ISO-639-3, tessdata name.
_ROWS = """
af afr afr; sq sqi sqi; ar ara ara; hy hye hye; az aze aze; eu eus eus;
be bel bel; bn ben ben; nb nob nor; bs bos bos; bg bul bul; ca cat cat;
zh zho chi_sim+chi_tra; hr hrv hrv; cs ces ces; da dan dan; nl nld nld;
en eng eng; eo epo epo; et est est; fi fin fin; fr fra fra; lg lug -;
ka kat kat; de deu deu; el ell ell; gu guj guj; he heb heb; hi hin hin;
hu hun hun; is isl isl; id ind ind; ga gle gle; it ita ita; ja jpn jpn;
kk kaz kaz; ko kor kor; la lat lat; lv lav lav; lt lit lit; mk mkd mkd;
ms msa msa; mi mri mri; mr mar mar; mn mon mon; nn nno nor; fa fas fas;
pl pol pol; pt por por; pa pan pan; ro ron ron; ru rus rus; sr srp srp;
sn sna -; sk slk slk; sl slv slv; so som -; st sot -; es spa spa;
sw swa swa; sv swe swe; tl tgl fil; ta tam tam; te tel tel; th tha tha;
ts tso -; tn tsn -; tr tur tur; uk ukr ukr; ur urd urd; vi vie vie;
cy cym cym; xh xho -; yo yor yor; zu zul -
"""
LINGUA_TO_TESSERACT: dict[str, tuple[str, ...]] = {}
for _row in _ROWS.replace("\n", " ").split(";"):
    if _row.strip():
        _iso1, _iso3, _tesseract = _row.split()
        _codes = () if _tesseract == "-" else tuple(_tesseract.split("+"))
        LINGUA_TO_TESSERACT[_iso1] = LINGUA_TO_TESSERACT[_iso3] = _codes

# OSD names differ from recognition models in several cases; Han is ambiguous.
OSD_TO_TESSERACT = {
    **{
        name: (f"script/{name}",)
        for name in (
            "Arabic",
            "Armenian",
            "Bengali",
            "Cherokee",
            "Cyrillic",
            "Devanagari",
            "Ethiopic",
            "Fraktur",
            "Georgian",
            "Greek",
            "Gujarati",
            "Gurmukhi",
            "Hebrew",
            "Japanese",
            "Kannada",
            "Khmer",
            "Lao",
            "Latin",
            "Malayalam",
            "Myanmar",
            "Oriya",
            "Sinhala",
            "Syriac",
            "Tamil",
            "Telugu",
            "Thaana",
            "Thai",
            "Tibetan",
            "Vietnamese",
        )
    },
    "Han": ("script/HanS", "script/HanT"),
    "HanS": ("script/HanS",),
    "HanT": ("script/HanT",),
    "Hangul": ("script/Hangul",),
}


def installed_languages(tessdata: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(tessdata).with_suffix("").as_posix()
            for path in tessdata.rglob("*.traineddata")
        )
    )


def map_languages(languages: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Map Lingua aliases or accept an explicit Tesseract pack; preserve priority."""
    result = []
    for language in languages:
        if not language or language != language.strip() or any(c in language for c in "+\\"):
            raise ValueError(f"Invalid OCR language code: {language!r}")
        if "/" in language and not language.startswith("script/"):
            raise ValueError("Only script/ language model paths are accepted")
        if any(part in {"", ".", ".."} for part in language.split("/")):
            raise ValueError("Invalid OCR language model path")
        mapped = LINGUA_TO_TESSERACT.get(language, (language,))
        if not mapped:
            raise ValueError(f"Lingua language {language!r} has no tessdata_best language model")
        for code in mapped:
            if code not in result:
                result.append(code)
    return tuple(result)


def script_languages(script: str | None) -> tuple[str, ...]:
    if script not in OSD_TO_TESSERACT:
        raise ValueError(f"No recognition model for OSD script {script!r}; languages required")
    return OSD_TO_TESSERACT[script]


def require_language_packs(tessdata: Path, languages: tuple[str, ...]) -> None:
    missing = [code for code in languages if not (tessdata / f"{code}.traineddata").is_file()]
    if missing:
        raise FileNotFoundError(f"OCR language packs are not installed: {', '.join(missing)}")
