"""Языки локализации Paradox и языки текста — это разные вещи.

Одно поле «язык перевода» делало две работы, и для CK3+русского они совпадали,
поэтому не жало:

* **папка игры** (`tgt_lang`) — имя каталога `localization/russian`, метка
  `_l_russian` в имени файла и заголовок `l_russian:` внутри. Это диктует игра,
  и список здесь закрытый: чего игра не знает, то она не загрузит;
* **язык текста** (`tgt_locale`) — на каком языке, собственно, написан перевод.
  Это нужно машинному переводу, именованию баз памяти и языковым правилам
  проверки.

Расходятся они ровно тогда, когда переводят на язык, которого в игре нет:
португальский в CK3 кладут в файлы `l_english`, потому что своей папки у него
не существует. Ровно так и поступает ModTranslationHelper, и без разделения
такой перевод в проекте не выразить.

Пустая локаль означает «совпадает с папкой языка» — так заведены все проекты,
созданные до расщепления, и переписывать их не нужно.
"""
from __future__ import annotations

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate

# Папки языков, которые понимают игры Paradox. Список открытый в том смысле,
# что поле редактируемое: моды иногда заводят свои имена.
PARADOX_LANGUAGES: tuple[str, ...] = (
    "english", "french", "german", "spanish", "russian", "simp_chinese",
    "korean", "japanese", "braz_por", "polish", "turkish",
)

# Как язык папки называется по-человечески. Показывается рядом с самим именем
# папки, а не вместо него: в путях и заголовках файлов стоит именно `russian`,
# и прятать это от переводчика незачем.
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

# Код языка текста для папок, у которых он очевиден. Служит и подсказкой при
# создании проекта, и значением по умолчанию, когда локаль не задана.
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

# Языки текста, которые можно выбрать, когда он не совпадает с папкой игры.
# Шире списка папок: сюда и попадают те, ради кого расщепление затевалось.
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
    """Код языка текста, подразумеваемый папкой игры.

    Незнакомая папка (мод завёл своё имя) даёт пустую локаль — угадывать по
    имени каталога нечего, пусть переводчик выберет сам.
    """
    return LANGUAGE_LOCALES.get(language, "")


def resolve_locale(language: str, locale: str | None) -> str:
    """Действующий язык текста: заданный явно либо выведенный из папки."""
    return (locale or "").strip() or default_locale(language)


def language_name(language: str) -> str:
    """«russian» → «Русский (russian)». Имя папки остаётся на виду."""
    known = LANGUAGE_NAMES.get(language)
    if not known:
        return language
    name = translate("Languages", known)      # вне f-строки: см. core/i18n
    return f"{name} ({language})"


def locale_name(locale: str) -> str:
    known = TEXT_LOCALES.get(locale)
    if not known:
        return locale
    name = translate("Languages", known)
    return f"{name} ({locale})"
