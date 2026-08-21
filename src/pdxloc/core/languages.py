"""A Paradox localisation folder and a text language are different things.

One «translation language» field used to do both jobs, and for CK3 with Russian
the two coincided, so it never pinched:

* the **game folder** (`tgt_lang`) — the name of the `localization/russian`
  directory, the `_l_russian` marker in the file name and the `l_russian:` header
  inside it. The game dictates this, and the list is closed: what the game does
  not know it will not load;
* the **text language** (`tgt_locale`) — what language the translation is
  actually written in. Machine translation, the naming of memory databases and
  the language rules of the check all need it.

The two part company exactly when the target language has no folder in the game:
Portuguese in CK3 goes into `l_english` files because no folder of its own
exists. ModTranslationHelper does precisely the same, and without the split such
a translation cannot be expressed in a project at all.

An empty locale means «the same as the language folder» — that is how every
project created before the split is set up, and none of them needs rewriting.
"""
from __future__ import annotations

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate

# Language folders the Paradox games understand. The list is open in the sense
# that the field is editable: mods sometimes invent names of their own.
PARADOX_LANGUAGES: tuple[str, ...] = (
    "english", "french", "german", "spanish", "russian", "simp_chinese",
    "korean", "japanese", "braz_por", "polish", "turkish",
)

# What a folder language is called in human words. Shown next to the folder
# name rather than instead of it: paths and file headers carry `russian`
# itself, and there is no point hiding that from the translator.
LANGUAGE_NAMES: dict[str, str] = {
    "english": QT_TRANSLATE_NOOP("Languages", "English"),
    "french": QT_TRANSLATE_NOOP("Languages", "French"),
    "german": QT_TRANSLATE_NOOP("Languages", "German"),
    "spanish": QT_TRANSLATE_NOOP("Languages", "Spanish"),
    "russian": QT_TRANSLATE_NOOP("Languages", "Russian"),
    "simp_chinese": QT_TRANSLATE_NOOP("Languages", "Simplified Chinese"),
    "korean": QT_TRANSLATE_NOOP("Languages", "Korean"),
    "japanese": QT_TRANSLATE_NOOP("Languages", "Japanese"),
    "braz_por": QT_TRANSLATE_NOOP("Languages", "Brazilian Portuguese"),
    "polish": QT_TRANSLATE_NOOP("Languages", "Polish"),
    "turkish": QT_TRANSLATE_NOOP("Languages", "Turkish"),
}

# The text language of the folders where it is obvious. Serves both as a hint
# when a project is created and as the default when no locale is set.
LANGUAGE_LOCALES: dict[str, str] = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "russian": "ru",
    "simp_chinese": "zh",
    "korean": "ko",
    "japanese": "ja",
    "braz_por": "pt",
    "polish": "pl",
    "turkish": "tr",
}

# Text languages that can be chosen when the language does not match a game
# folder. Wider than the list of folders: this is where the ones the split was
# made for live.
TEXT_LOCALES: dict[str, str] = {
    "en": QT_TRANSLATE_NOOP("Languages", "English"),
    "ru": QT_TRANSLATE_NOOP("Languages", "Russian"),
    "zh": QT_TRANSLATE_NOOP("Languages", "Chinese"),
    "fr": QT_TRANSLATE_NOOP("Languages", "French"),
    "de": QT_TRANSLATE_NOOP("Languages", "German"),
    "es": QT_TRANSLATE_NOOP("Languages", "Spanish"),
    "pt": QT_TRANSLATE_NOOP("Languages", "Portuguese"),
    "it": QT_TRANSLATE_NOOP("Languages", "Italian"),
    "pl": QT_TRANSLATE_NOOP("Languages", "Polish"),
    "tr": QT_TRANSLATE_NOOP("Languages", "Turkish"),
    "uk": QT_TRANSLATE_NOOP("Languages", "Ukrainian"),
    "cs": QT_TRANSLATE_NOOP("Languages", "Czech"),
    "ja": QT_TRANSLATE_NOOP("Languages", "Japanese"),
    "ko": QT_TRANSLATE_NOOP("Languages", "Korean"),
}


def default_locale(language: str) -> str:
    """The text language a game folder implies.

    An unfamiliar folder — a mod invented a name of its own — gives an empty
    locale: there is nothing to guess from a directory name, so let the
    translator choose.
    """
    return LANGUAGE_LOCALES.get(language, "")


def resolve_locale(language: str, locale: str | None) -> str:
    """The text language in force: the one set explicitly, or the one the folder
    implies."""
    return (locale or "").strip() or default_locale(language)


def language_name(language: str) -> str:
    """«russian» → «Russian (russian)». The folder name stays in sight."""
    known = LANGUAGE_NAMES.get(language)
    if not known:
        return language
    name = translate("Languages", known)      # outside the f-string: see core/i18n
    return f"{name} ({language})"


def locale_name(locale: str) -> str:
    known = TEXT_LOCALES.get(locale)
    if not known:
        return locale
    name = translate("Languages", known)
    return f"{name} ({locale})"
