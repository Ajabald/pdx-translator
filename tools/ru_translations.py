"""Русский перевод интерфейса: пары «английский оригинал → русский текст».

Заполняется при переносе строк кода на английский и скармливается
`tools/seed_ts.py`, который раскладывает пары по контекстам в
`gui/translations/pdxloc_ru.ts`.

Почему не правим `.ts` руками: записей около девятисот, и ручная правка XML
такого размера — верный способ потерять десяток строк молча. Здесь же пара
видна целиком, а расхождение с кодом ловит `tools/seed_ts.py`: он ругается
на перевод, которому в `.ts` не нашлось оригинала.

Ключ верхнего уровня — контекст перевода (он же `<context><name>` в `.ts`).
"""
from __future__ import annotations

RU: dict[str, dict[str, str]] = {}

RU["Actions"] = {
    "Projects…": "Проекты…",
    "Back to the project list": "Вернуться к списку проектов",
    "Open project…": "Открыть проект…",
    "Save project as…": "Сохранить проект как…",
    "Load translation from mod…": "Загрузить перевод из мода…",
    "Take translations from ready localization files — someone else's "
    "translation of this mod, or your own edits made directly in the files":
        "Принять переводы из готовых файлов локализации — чужой перевод "
        "этого мода или свои правки, сделанные прямо в файлах",
    "Write translation to mod…": "Записать перевод в мод…",
    "Preferences…": "Параметры…",
    "Quit": "Выход",
    "Copy cell": "Копировать ячейку",
    "Paste into translation": "Вставить в перевод",
    "Copy key": "Копировать ключ",
    "Reset translation": "Сбросить перевод",
    "Save row translation": "Сохранить перевод строки",
    "Edits are saved anyway when you leave the row — this is just in case":
        "Правки и так сохраняются при уходе со строки — это на всякий случай",
    "Undo last operation": "Отменить последнюю операцию",
    "Rolls back the last batch of edits. In the translation field Ctrl+Z "
    "still undoes typing":
        "Откат последней пачки правок. В поле перевода Ctrl+Z по-прежнему "
        "отменяет набор текста",
    "Translation = Original": "Перевод = Оригинал",
    "For names, numbers and anything untranslatable":
        "Для имён, чисел и всего, что не переводится",
    "Fill from translation memory": "Подставить из памяти переводов",
    "Machine-translate the row": "Перевести строку сервисом",
    "Sends the original to the service set up in «File → Preferences». "
    "The result is marked «Machine (unchecked)»":
        "Отправляет оригинал сервису, настроенному в «Файл → Параметры». "
        "Результат помечается «Машинный (не проверен)»",
    "Machine translation…": "Машинный перевод…",
    "Translate many rows at once through the service set up in "
    "«File → Preferences»":
        "Перевести сразу много строк сервисом, настроенным в "
        "«Файл → Параметры»",
    "Apply to all rows with the same original":
        "Применить ко всем с таким же оригиналом",
    "Validate": "Подтвердить",
    "Mark the row as reviewed": "Пометить строку проверенной",
    "Unvalidate": "Снять подтверждение",
    "Back to the «Translated» status": "Вернуть статус «Переведено»",
    "Custom status": "Кастомный статус",
    "Ignore": "Игнорировать",
    "Nothing to translate — a row of bare tags, say":
        "Переводить нечего — например, строка из одних тегов",
    "Next untranslated": "Следующая непереведённая",
    "Previous row": "Предыдущая строка",
    "Next row": "Следующая строка",
    "Save and go to next": "Сохранить и перейти к следующей",
    "Find row…": "Найти строку…",
    "Puts the cursor in the search box": "Курсор в поле поиска",
    "Only with issues": "Только с замечаниями",
    "Show only rows the check has questions about":
        "Показать только строки, к которым есть вопросы у проверки",
    "Show deleted": "Показывать удалённые",
    "Rows whose keys are gone from the original":
        "Строки, ключей которых больше нет в оригинале",
    "Reset filters": "Сбросить фильтры",
    "Drops the status, file and search filters. The sort order stays":
        "Снять фильтры по статусу, файлу и поиску. Порядок сортировки остаётся",
    "Toolbar": "Панель инструментов",
    "File tree": "Дерево файлов",
    "Languages and databases in the header": "Языки и базы в шапке",
    "Scan": "Сканировать",
    "Re-read the original files and find changes":
        "Перечитать файлы оригинала и найти изменения",
    "Actualize cosmetic edits…": "Актуализировать косметические правки…",
    "Confirm translations of rows where the mod author only changed formatting":
        "Подтвердить переводы строк, где автор мода правил только оформление",
    "Archive of old translations…": "Архив старых переводов…",
    "Change original folder…": "Сменить папку оригинала…",
    "If the mod was re-downloaded elsewhere, or the project came from "
    "another person":
        "Если мод скачали заново в другое место или проект пришёл "
        "от другого человека",
    "Show original in Explorer": "Открыть оригинал в проводнике",
    "Project languages…": "Языки проекта…",
    "Game folders (l_english) and the language the text is actually written in":
        "Папки игры (l_english) и язык, на котором на самом деле написан текст",
    "Check the whole project…": "Проверить весь проект…",
    "Configure checks…": "Настроить проверки…",
    "Which rules are on, with what leniency, and how often they fire on "
    "this project":
        "Какие правила работают, с какими послаблениями и сколько раз "
        "срабатывают на этом проекте",
    "Marked «not an error»…": "Помеченные «не ошибка»…",
    "Silenced issues — they can be put back into the check":
        "Заглушённые замечания — их можно вернуть в проверку",
    "Translation memory…": "Память переводов…",
    "Memory entries, attached databases and building new ones — in a "
    "single window":
        "Записи памяти, подключённые базы и сборка новых баз — одним окном",
    "Glossary…": "Глоссарий…",
    "Terms and candidates for them: statistics suggests, you accept":
        "Термины и кандидаты в них: статистика предлагает, вы подтверждаете",
    "How was this translated before…": "Как переводили это раньше…",
    "Search the memory for the selected piece of the original":
        "Поиск по памяти для выделенного куска оригинала",
    "Open databases folder": "Открыть папку баз",
    "Keyboard shortcuts": "Горячие клавиши",
    "About": "О программе",
}

RU["MainWindow"] = {
    "&File": "&Файл",
    "&Edit": "&Правка",
    "&Translation": "&Перевод",
    "F&ilters": "&Фильтры",
    "&View": "&Вид",
    "&Project": "&Проект",
    "&Check": "Про&верка",
    "T&ools": "&Инструменты",
    "&Help": "&Справка",
    "Check preset: %1": "Набор проверок: %1",
    # подменю
    "Show": "Показывать",
    "All": "Все",
    "Sort": "Сортировка",
    "No sorting": "Без сортировки",
    "Descending": "По убыванию",
    "Theme": "Тема",
    "Rule preset": "Набор правил",
    "Columns": "Колонки",
    "Status buttons": "Кнопки статуса",
    "Hides the toolbar button only — the command stays in the menu and its "
    "shortcut keeps working":
        "Прячет только кнопку панели — команда остаётся в меню, и её клавиша "
        "продолжает работать",
    # загон чужой игры
    "Project of another game": "Проект другой игры",
    "The project «%1» belongs to %2, but lies in the folder of %3.\n\n"
    "Move it to %4?":
        "Проект «%1» относится к %2, а лежит в папке %3.\n\n"
        "Перенести его в %4?",
    "no game in particular": "не относящейся ни к одной игре",
    "Could not move the file:\n%1": "Не удалось перенести файл:\n%1",
    # статус-бар
    "Choose or create a project": "Выберите или создайте проект",
    "Rows selected: %1": "Выбрано строк: %1",
    # горячие клавиши
    "Keyboard shortcuts": "Горячие клавиши",
    "F2, double click": "F2, двойной клик",
    "Edit the translation in the cell": "Править перевод прямо в ячейке",
    # удаление проекта
    "Delete project": "Удаление проекта",
    "Delete": "Удалить",
    "Cancel": "Отмена",
    "Delete the backups next to it as well": "Удалить и резервные копии рядом",
    "The file goes to the recycle bin": "Файл уйдёт в корзину",
    "The file will be deleted": "Файл будет удалён",
    "The recycle bin did not accept the file, so it was deleted permanently:\n"
    "%1\n\nUsually this means the file is larger than the bin allows.":
        "Корзина не приняла файл, поэтому он удалён безвозвратно:\n%1\n\n"
        "Обычно это значит, что файл больше, чем корзина позволяет.",
    "\n\nTranslations that will be lost: %1 of %2 rows.":
        "\n\nБудут потеряны переводы: %1 из %2 строк.",
    "Delete the project «%1» together with its file?\n\n%2%3\n\n%4. "
    "Mod files and translation memory databases are untouched.":
        "Удалить проект «%1» вместе с файлом?\n\n%2%3\n\n%4. "
        "Файлы мода и базы памяти переводов не тронуты.",
    "Could not delete the file:\n%1\n\n%2\n\n"
    "Most likely it is open in another program.":
        "Не удалось удалить файл:\n%1\n\n%2\n\n"
        "Скорее всего он открыт другой программой.",
    "Project deleted: %1 (%2 files)": "Проект удалён: %1 (файлов: %2)",
    # открытие и сохранение
    "Project": "Проект",
    "Project file not found:\n%1": "Файл проекта не найден:\n%1",
    "Could not open the project:\n%1": "Не удалось открыть проект:\n%1",
    "%1 rows with no translatable text were marked as ignored "
    "(bare tags such as [GetName], empty values) — Ctrl+Z undoes it":
        "%1 строк без переводимого текста помечены как игнорируемые "
        "(голые теги вроде [GetName], пустые значения) — Ctrl+Z вернёт как было",
    "auto-ignore of rows with nothing to translate":
        "автопометка строк, где переводить нечего",
    "Open project": "Открыть проект",
    "Translation project (*%1);;All files (*)":
        "Проект перевода (*%1);;Все файлы (*)",
    "Save project as": "Сохранить проект как",
    "Translation project (*%1)": "Проект перевода (*%1)",
    "Saving": "Сохранение",
    "Could not save:\n%1": "Не удалось сохранить:\n%1",
    "Project saved:\n%1\n\nOpening the copy.":
        "Проект сохранён:\n%1\n\nОткрываю копию.",
    # сканирование
    "Scanning": "Сканирование",
    "Scan interrupted — changes were not saved":
        "Сканирование прервано — изменения не сохранены",
    "Error:\n%1": "Ошибка:\n%1",
    # косметические правки
    "Cosmetic edits": "Косметические правки",
    "There are no outdated rows with cosmetic edits.\n\n"
    "Those are changes of punctuation, case and spaces — when the meaning "
    "of the original did not change.":
        "Устаревших строк с косметическими правками нет.\n\n"
        "Такими считаются изменения пунктуации, регистра и пробелов — "
        "когда смысл оригинала не поменялся.",
    "Confirm translations of %1 rows where the original was edited "
    "cosmetically only?\n\nThe translations themselves do not change — the "
    "«Outdated» mark is removed. The operation can be undone (Ctrl+Z).":
        "Подтвердить переводы %1 строк, где оригинал правили только "
        "косметически?\n\nСами переводы не изменятся — снимется пометка "
        "«Устарело». Операцию можно отменить (Ctrl+Z).",
    "Rows actualized: %1": "Актуализировано строк: %1",
    # напоминание о базах памяти при открытии проекта
    "Translation memory": "Память переводов",
    "There is not a single translation memory database.\n\n"
    "A database built from your copy of the game fills in strings the mod "
    "copied from it — often hundreds of them.\n\nBuild one now?":
        "Нет ни одной базы памяти переводов.\n\n"
        "База, собранная из вашей копии игры, подставляет строки, которые мод "
        "скопировал из неё, — часто это сотни строк.\n\nСобрать сейчас?",
    # смена папки оригинала
    "Change of the original folder": "Смена папки оригинала",
    "The folder has changed. Scan the project now?\n\nScanning re-reads the "
    "files: translations are kept, changed rows become «Outdated».":
        "Папка изменена. Сканировать проект сейчас?\n\nСканирование "
        "перечитает файлы: переводы сохранятся, изменившиеся строки "
        "станут «Устарело».",
    # отмена операции
    "Undo": "Отмена",
    "Nothing to undo.": "Отменять нечего.",
    "Undo operation": "Отмена операции",
    "actualization": "актуализация",
    "status change": "смена статуса",
    "translation edit": "правка перевода",
    "bulk replace": "замена",
    "glossary rules": "правила глоссария",
    "fill from memory": "подстановка из памяти",
    "translation import": "загрузка перевода из мода",
    "machine translation": "машинный перевод",
    "Undo the last operation (%1) and return %2 rows to their previous state?":
        "Отменить последнюю операцию (%1) и вернуть %2 строк к прежнему состоянию?",
    "Rows reverted: %1": "Возвращено строк: %1",
    # о программе
    "(no project open)": "(проект не открыт)",
    "A translator's workbench for the localisation of Paradox game mods.<br>"
    "Format: Paradox pseudo-YAML (UTF-8 with BOM) and the older CSV.<br><br>":
        "Рабочее место переводчика локализаций модов игр Paradox.<br>"
        "Формат: Paradox pseudo-YAML (UTF-8 c BOM) и старый CSV.<br><br>",
    "This program comes with ABSOLUTELY NO WARRANTY. It is free software, and "
    "you are welcome to redistribute it under the terms of the GNU General "
    "Public License, version 3 or later — see the LICENSE file.<br><br>"
    "Uses Qt through PySide6 under the GNU LGPL v3.<br><br>":
        "Программа распространяется БЕЗ ВСЯКИХ ГАРАНТИЙ. Это свободное "
        "программное обеспечение, и вы можете распространять его на условиях "
        "GNU General Public License версии 3 или новее — см. файл LICENSE."
        "<br><br>Использует Qt через PySide6 на условиях GNU LGPL v3.<br><br>",
    "Project: %1<br>Memory databases: %2": "Проект: %1<br>Базы памяти: %2",
    "Project languages": "Языки проекта",
    "The language of the folders changed. Scan the project now?\n\n"
    "Scanning re-reads the files under the new names.":
        "Язык папок изменился. Сканировать проект сейчас?\n\n"
        "Сканирование перечитает файлы под новыми именами.",
}

RU["Welcome"] = {
    "Getting started": "Знакомство",
    "Skip": "Пропустить",
    "Back": "Назад",
    "Next": "Далее",
    "Done": "Готово",
    # шаг 1 — язык
    "Interface language": "Язык интерфейса",
    "Choose the language of the interface. It can be changed at any time in "
    "«File → Preferences».":
        "Выберите язык интерфейса. Его можно поменять в любой момент в "
        "«Файл → Параметры».",
    "The interface language has nothing to do with the languages you "
    "translate between — those belong to the project.":
        "Язык интерфейса не связан с языками, между которыми вы переводите: "
        "те задаются в проекте.",
    # шаг 2 — базы памяти
    "Translation memory": "Память переводов",
    "There are no translation memory databases yet. A database built from "
    "your copy of the game fills in strings the mod copied from it — often "
    "hundreds of them — and prompts you with how similar lines were "
    "translated before.\n\n"
    "Building takes seconds and needs nothing but the game localization "
    "folders.":
        "Баз памяти переводов пока нет. База, собранная из вашей копии игры, "
        "подставляет строки, которые мод скопировал из неё, — часто это сотни "
        "строк, — и подсказывает, как переводили похожие.\n\n"
        "Сборка занимает секунды, и нужны для неё только папки локализации "
        "игры.",
    "Translation memory databases found: %1. They fill in strings the mod "
    "copied from the game and prompt you with how similar lines were "
    "translated before.":
        "Найдено баз памяти переводов: %1. Они подставляют строки, которые мод "
        "скопировал из игры, и подсказывают, как переводили похожие.",
    "Build a database…": "Собрать базу…",
    "Build one more…": "Собрать ещё одну…",
    # шаг 3 — первый проект
    "First project": "Первый проект",
    "A project holds everything: rows, statuses, translation memory and the "
    "history of the original. It is a single file you can copy or hand to "
    "another person.":
        "В проекте лежит всё: строки, статусы, память переводов и история "
        "оригинала. Это один файл — его можно скопировать или передать "
        "другому человеку.",
    "Create a project…": "Создать проект…",
    "Open a project…": "Открыть проект…",
}

RU["Ask"] = {
    "Do not ask again": "Больше не спрашивать",
}

RU["Languages"] = {
    "English": "Английский",
    "French": "Французский",
    "German": "Немецкий",
    "Spanish": "Испанский",
    "Russian": "Русский",
    "Simplified Chinese": "Китайский упрощённый",
    "Chinese": "Китайский",
    "Korean": "Корейский",
    "Japanese": "Японский",
    "Brazilian Portuguese": "Португальский (Бразилия)",
    "Portuguese": "Португальский",
    "Polish": "Польский",
    "Turkish": "Турецкий",
    "Italian": "Итальянский",
    "Ukrainian": "Украинский",
    "Czech": "Чешский",
}

RU["LanguagesDialog"] = {
    "Project languages": "Языки проекта",
    "Game:": "Игра:",
    "The game is now %1. The project file stays where it lies; moving it "
    "to the pen of the new game will be offered the next time the project "
    "is opened.":
        "Игра теперь %1. Файл проекта остаётся на месте; перенести его в "
        "загон новой игры предложит следующее открытие проекта.",
    "The game folder decides the file names (*_l_english.yml) and the header "
    "inside them. The text language says what the text actually is — machine "
    "translation, memory database naming and language-specific checks go by it.":
        "Папка игры задаёт имена файлов (*_l_english.yml) и заголовок внутри "
        "них. Язык текста говорит, на каком языке он написан на самом деле — "
        "по нему работают машинный перевод, именование баз памяти и языковые "
        "правила проверки.",
    "Game folders:": "Папки игры:",
    "The text is in another language": "Текст на другом языке",
    "Turn on when translating into a language the game does not know: "
    "Portuguese in CK3, say, lives in l_english files":
        "Включите, если переводите на язык, которого игра не знает: "
        "португальский в CK3, например, лежит в файлах l_english",
    "Text languages:": "Языки текста:",
    "The folder of the original itself is changed in "
    "«Project → Change original folder…».":
        "Саму папку оригинала меняют в «Проект → Сменить папку оригинала…».",
    "Apply": "Применить",
    "Only %1 files out of %2 carry the label _l_%3.\n\nTranslations are not "
    "deleted: they stay in the archive and in the translation memory. "
    "Change the languages?":
        "Метку _l_%3 несут только %1 файлов из %2.\n\nПереводы не удаляются: "
        "они остаются в архиве и в памяти переводов. Сменить языки?",
}

RU["ScanStats"] = {
    "EN files: %1, RU: %2": "Файлов EN: %1, RU: %2",
    "New keys: %1": "Новых ключей: %1",
    "Unchanged: %1": "Без изменений: %1",
    "The original changed: %1 (meaningful %2, cosmetic %3)":
        "Оригинал изменился: %1 (смысловых %2, косметических %3)",
    "Deleted from EN: %1": "Удалено из EN: %1",
    "Restored: %1": "Восстановлено: %1",
    "Moved to the archive (absent from the original): %1":
        "Перенесено в архив (нет в оригинале): %1",
    "Filled from translation memory: %1": "Заполнено из памяти переводов: %1",
    "Ignored automatically (nothing to translate): %1":
        "Игнорировано автоматически (переводить нечего): %1",
    "RU conflicts (the database wins): %1": "Конфликтов RU (БД главнее): %1",
    "Duplicate keys (original): %1": "Дубликатов ключей (оригинал): %1",
    "Duplicate keys (translation): %1": "Дубликатов ключей (перевод): %1",
    "Keys with an empty original: %1": "Ключей с пустым оригиналом: %1",
    "Parser warnings: %1": "Предупреждений парсера: %1",
}

RU["Stats"] = {
    "Translated %1 / %2 (%3%) · left %4":
        "Переведено %1 / %2 (%3%) · осталось %4",
    " · auto: %1": " · авто: %1",
    " · outdated: %1": " · устарело: %1",
    " · machine: %1": " · машинных: %1",
}

RU["LocImport"] = {
    "Translation files found: %1": "Файлов перевода найдено: %1",
    "Rows taken: %1": "Строк принято: %1",
    "Already the same: %1": "Уже совпадало: %1",
    "Skipped (a translation already exists): %1":
        "Пропущено (перевод уже есть): %1",
    "Skipped (translation equals the original): %1":
        "Пропущено (перевод равен оригиналу): %1",
    "Skipped (the «needs translation» marker): %1":
        "Пропущено (маркер «требует перевода»): %1",
    "Keys absent from the project: %1": "Ключей нет в проекте: %1",
    "Translation folder not found: %1": "Папка перевода не найдена: %1",
    "Project id=%1 not found": "Проект id=%1 не найден",
}

RU["TmImport"] = {
    "This SQLite build has no FTS5 — similarity search is unavailable":
        "В этой сборке SQLite нет FTS5 — поиск похожих недоступен",
    "building the index…": "построение индекса…",
    "compacting…": "сжатие…",
    "building the similar-rows index…": "построение индекса похожих строк…",
    "saving the database…": "сохранение базы…",
    "Files processed: %1": "Файлов обработано: %1",
    "Translation pairs: %1": "Пар переводов: %1",
    "Skipped (no translation): %1": "Пропущено (нет перевода): %1",
    "Parser warnings: %1": "Предупреждений парсера: %1",
    "Original folder not found: %1": "Папка оригинала не найдена: %1",
    "Translation folder not found: %1": "Папка перевода не найдена: %1",
    "No translation folder found next to %1 (…/%2 was expected)":
        "Не найдена папка перевода рядом с %1 (ожидалась …/%2)",
    "The folder %1 has no localization files of the language «%2» "
    "(names like *_l_%2.yml were expected)":
        "В папке %1 нет файлов локализации языка «%2» "
        "(ожидались имена вида *_l_%2.yml)",
    " · pairs: %1": " · пар: %1",
    "Not a single «original — translation» pair was found.\n\nOriginal files "
    "checked: %1, of them with a pair in the translation folder: %2.\n"
    "Usually the reason is that the game or mod root was given instead of the "
    "localization folders (…\\game\\localization\\%3 and "
    "…\\localization\\%4, say).":
        "Не найдено ни одной пары «оригинал — перевод».\n\nПроверено файлов "
        "оригинала: %1, из них с парой в папке перевода: %2.\nОбычно причина "
        "в том, что указан корень игры или мода, а не папки локализации "
        "(например …\\game\\localization\\%3 и …\\localization\\%4).",
    "Could not replace the database file: %1\n\nMost likely it is attached to "
    "the current project — detach it in «Tools → Translation memory…» and try "
    "again.":
        "Не удалось заменить файл базы: %1\n\nСкорее всего она подключена к "
        "текущему проекту — отключите её в «Инструменты → Память переводов…» "
        "и повторите.",
}

RU["Relocate"] = {
    "Folder: %1": "Папка: %1",
    "%1 was chosen, but the localization files lie in %2 — that is what will "
    "be recorded.":
        "Выбрана %1, но файлы локализации лежат в %2 — записана будет она.",
    "Files matched: %1 out of the %2 the database knows.":
        "Совпало файлов: %1 из %2, известных базе.",
    "Files not found: %1 — %2": "Не найдено файлов: %1 — %2",
    "%1 rows will become deleted": "%1 строк станут удалёнными",
    ", of them %1 with a translation will go to the archive.":
        ", из них %1 с переводом уйдут в архив.",
    "  … and %1 more": "  … и ещё %1",
    "New files: %1 — rows from them appear on the next scan.":
        "Новых файлов: %1 — строки из них заведутся при сканировании.",
    "Not a single database file was found in this folder. Looks like another "
    "mod's folder was chosen: after the change the whole translation goes to "
    "the archive.":
        "Ни один файл базы в этой папке не найден. Похоже, выбрана папка "
        "другого мода: после смены весь перевод уедет в архив.",
    "The file set matches completely — the translation is safe.":
        "Набор файлов совпадает полностью — перевод не пострадает.",
    "After the folder change a scan (F5) is needed: it re-reads the files and "
    "shows what changed in the original.":
        "После смены папки нужно сканирование (F5): именно оно перечитает "
        "файлы и покажет, что изменилось в оригинале.",
    "Project id=%1 not found": "Проект id=%1 не найден",
    "Folder not found: %1": "Папка не найдена: %1",
    "The folder has no localization files *%1*.yml:\n%2":
        "В папке нет файлов локализации *%1*.yml:\n%2",
    # смена языка папки
    "Only the text language changes — files and rows are not affected. "
    "Machine translation, memory database naming and language-specific checks "
    "will use the new value.":
        "Меняется только язык текста — файлы и строки не затронуты. Новое "
        "значение получат машинный перевод, именование баз памяти и языковые "
        "правила проверки.",
    "Files with the label _l_%1 in the original folder: %2 of the %3 the "
    "database knows.":
        "Файлов с меткой _l_%1 в папке оригинала: %2 из %3, известных базе.",
    "Not a single file was found. After the change the scan will consider "
    "every row deleted and the translations will go to the archive.":
        "Не найдено ни одного файла. После смены сканирование сочтёт все "
        "строки удалёнными, а переводы уйдут в архив.",
    "%1 rows will become deleted, of them %2 with a translation.":
        "%1 строк станут удалёнными, из них %2 с переводом.",
    "After the change a scan (F5) is needed: it re-reads the files under the "
    "new names.":
        "После смены нужно сканирование (F5): оно перечитает файлы под "
        "новыми именами.",
}

RU["Db"] = {
    "The database has schema version %1, the application expects %2. "
    "Please update the application.":
        "БД имеет версию схемы %1, приложение ожидает %2. "
        "Обновите приложение.",
    "Could not upgrade the database schema from version %1 to %2.":
        "Не удалось обновить схему БД с версии %1 до %2.",
    "Migration v1→v2: foreign keys violated: %1":
        "Миграция v1→v2: нарушены внешние ключи: %1",
    "Migration v2→v3: orphaned translations were not archived":
        "Миграция v2→v3: осиротевшие переводы не заархивированы",
    "Migration v2→v3: foreign keys violated: %1":
        "Миграция v2→v3: нарушены внешние ключи: %1",
    "Migration v3→v4: foreign keys violated: %1":
        "Миграция v3→v4: нарушены внешние ключи: %1",
    "Migration v5→v6: row count mismatch (was %1, became %2)":
        "Миграция v5→v6: не сходится число строк (было %1, стало %2)",
    "Migration v5→v6: foreign keys violated: %1":
        "Миграция v5→v6: нарушены внешние ключи: %1",
    "Migration v2→v3: row count mismatch (was %1, became %2, orphaned %3)":
        "Миграция v2→v3: расхождение в строках (было %1, стало %2, "
        "осиротевших %3)",
    "Migration v2→v3: translation memory mismatch (unique before %1, after %2)":
        "Миграция v2→v3: расхождение в памяти переводов "
        "(было уникальных %1, стало %2)",
    "Migration v3→v4: mismatch (rows before %1, after %2; translations "
    "before %3, after %4)":
        "Миграция v3→v4: расхождение (строк было %1, стало %2; "
        "переводов было %3, стало %4)",
}

RU["Project"] = {
    "game database": "база игры",
    "project export": "экспорт проекта",
    "import": "импорт",
    "The project file already exists: %1": "Файл проекта уже существует: %1",
    "The file already exists: %1": "Файл уже существует: %1",
    "(unnamed)": "(без имени)",
}

RU["Scanner"] = {
    "Project id=%1 not found": "Проект id=%1 не найден",
    "Original folder not found: %1": "Папка оригинала не найдена: %1",
}

RU["Exporter"] = {"Project id=%1 not found": "Проект id=%1 не найден"}

RU["MtDialog"] = {
    "Machine translation": "Машинный перевод",
    "Translate": "Перевести",
    "Through a web translator": "Через веб-переводчик",
    "Interrupt": "Прервать",
    "Service: %1": "Сервис: %1",
    "No service is set up — choose one in "
    "«File → Preferences → Machine translation»":
        "Сервис не настроен — выберите его в "
        "«Файл → Параметры → Машинный перевод»",
    # охват
    "Which rows to translate:": "Какие строки переводить:",
    "Selected rows": "Выделенные строки",
    "Not translated": "Непереведённые",
    "Not translated and filled from memory":
        "Непереведённые и подставленные из памяти",
    "The whole project": "Весь проект",
    "Also re-translate outdated rows (their existing translation will be "
    "replaced)":
        "Переводить заново и устаревшие (их нынешний перевод будет заменён)",
    "Reviewed, custom and ignored rows are never touched, nor are rows with "
    "nothing to translate — a bare [GetName] costs money and returns nothing.":
        "Проверенные, кастомные и игнорируемые строки не трогаются никогда, "
        "как и строки, где переводить нечего: голый [GetName] стоит денег и "
        "не даёт ничего.",
    # прогон
    "Rows: %1 · characters: %2 · requests: %3 · roughly %4 minutes":
        "Строк: %1 · символов: %2 · запросов: %3 · примерно %4 мин",
    "%1 rows are longer than the service takes in one request and will be "
    "left untouched":
        "%1 строк длиннее, чем сервис принимает за один запрос, — они "
        "останутся нетронутыми",
    "Send %1 rows (%2 characters) to the service?\n\n"
    "The result is written with the «Machine (unchecked)» status. The whole "
    "run is one batch — Ctrl+Z undoes it all.":
        "Отправить сервису %1 строк (%2 символов)?\n\n"
        "Результат запишется со статусом «Машинный (не проверен)». Весь "
        "прогон — одна пачка: Ctrl+Z отменит его целиком.",
    "Translated %1 of %2": "Переведено %1 из %2",
    "Interrupting…": "Прерываю…",
    "Rows worth looking at:": "Строки, на которые стоит взглянуть:",
    "… and %1 more": "… и ещё %1",
    # ручной режим
    "Rows are taken by the same rules as on the «Translate» tab, and the "
    "result is written the same way — the only difference is that you carry "
    "the text to a translator yourself.":
        "Строки берутся по тем же правилам, что и на вкладке «Перевести», и "
        "результат записывается так же — разница только в том, что текст до "
        "переводчика вы несёте сами.",
    "Copy this into a web translator of your choice:":
        "Скопируйте это в любой веб-переводчик:",
    "Copy": "Копировать",
    "Paste the result here:": "Вставьте результат сюда:",
    "Take the result and go to the next batch":
        "Принять результат и перейти к следующей пачке",
    "Nothing left to translate.": "Переводить больше нечего.",
    "Batch %1 of %2 · %3 rows": "Пачка %1 из %2 · строк: %3",
}

RU["Mt"] = {
    "Off": "Отключён",
    "The provider returned %1 rows instead of %2":
        "Провайдер вернул %1 строк вместо %2",
    # ошибки: разделены по тому, что человеку с ними делать
    "Could not reach %1: %2": "Не удалось связаться с %1: %2",
    "%1 refused: the request limit or the quota is exhausted.":
        "%1 отказал: исчерпан лимит запросов или объёма.",
    "%1 rejected the key. Check it in "
    "«File → Preferences → Machine translation».":
        "%1 не принял ключ. Проверьте его в "
        "«Файл → Параметры → Машинный перевод».",
    "%1 answered with an error (code %2).": "%1 ответил ошибкой (код %2).",
    "%1 returned an answer that could not be read.":
        "%1 вернул ответ, который не удалось прочитать.",
    "%1 declined to translate this batch.":
        "%1 отказался переводить эту пачку.",
    "%1 also needs a folder id — fill it in "
    "«File → Preferences → Machine translation».":
        "%1 нужен ещё идентификатор каталога — впишите его в "
        "«Файл → Параметры → Машинный перевод».",
    "The answer has %1 separators instead of %2, or their order changed. "
    "Nothing from this batch was applied.":
        "В ответе %1 разделителей вместо %2, либо их порядок изменился. "
        "Из этой пачки не применено ничего.",
    "Manual — through a web translator": "Вручную — через веб-переводчик",
    "The manual mode is driven from its own tab, not from here.":
        "Ручным режимом управляют с его собственной вкладки, не отсюда.",
}

RU["MtRun"] = {
    "Rows translated: %1": "Переведено строк: %1",
    "Characters sent: %1": "Отправлено символов: %1",
    "Requests made: %1": "Сделано запросов: %1",
    "Rows where the translation lost a placeholder: %1 — they are written, "
    "but need fixing":
        "Строк, где перевод потерял подстановку: %1 — они записаны, но их "
        "надо починить",
    "Rows not translated: %1": "Не переведено строк: %1",
    "Interrupted. What had been translated by then is kept — Ctrl+Z undoes "
    "the whole run.":
        "Прервано. Переведённое к этому моменту сохранено — Ctrl+Z отменит "
        "весь прогон целиком.",
    "The row is longer than the service accepts in one request. It was left "
    "untouched.":
        "Строка длиннее, чем сервис принимает за один запрос. Она осталась "
        "нетронутой.",
    "The service returned nothing for this row.":
        "Сервис ничего не вернул по этой строке.",
}

RU["ParadoxYaml"] = {
    "%1:%2: an l_*: header was expected, found: %3":
        "%1:%2: ожидался заголовок l_*:, найдено: %3",
    "%1:%2: no closing quote for the key %3 — the text was taken to the end "
    "of the line":
        "%1:%2: нет закрывающей кавычки у ключа %3 — текст взят до конца строки",
    "%1:%2: unrecognized line: %3": "%1:%2: нераспознанная строка: %3",
}

RU["ParadoxCsv"] = {
    "%1:%2: a line without a «;» separator: %3":
        "%1:%2: строка без разделителя «;»: %3",
}

RU["TextDiff"] = {
    "cosmetic edit": "косметическая правка",
    "the text changed": "изменён текст",
    "removed: %1": "убрано: %1",
    "added: %1": "добавлено: %1",
}

RU["Theme"] = {"Light": "Светлая", "Dark": "Тёмная"}

RU["RootDialog"] = {
    "Change the original folder": "Сменить папку оригинала",
    "The folder the original is read from. It needs changing if the mod was "
    "re-downloaded elsewhere, the game library was moved, or the project came "
    "from another person.":
        "Папка, из которой читается оригинал. Менять её нужно, если мод "
        "скачали заново в другое место, перенесли библиотеку игры или проект "
        "пришёл от другого человека.",
    "Now: %1": "Сейчас: %1",
    "New folder:": "Новая папка:",
    "Browse…": "Обзор…",
    "Change the folder": "Сменить папку",
    "Original folder": "Папка оригинала",
    "Could not read the folder:\n%1": "Не удалось прочитать папку:\n%1",
    "\n\nRows that will become deleted: %1"
    "\nTranslations that go to the archive: %2":
        "\n\nСтрок станет удалёнными: %1\nПереводов уйдёт в архив: %2",
    "Change of the original folder": "Смена папки оригинала",
    "The new folder holds %1 files out of the %2 the database knows.%3\n\n"
    "Translations are not deleted: they stay in the archive and in the "
    "translation memory. Change the folder?":
        "В новой папке нашлось %1 файлов из %2, известных базе.%3\n\n"
        "Переводы не удаляются: они остаются в архиве и в памяти переводов. "
        "Сменить папку?",
}

RU["Archive"] = {
    "File": "Файл",
    "Key": "Ключ",
    "Translation": "Перевод",
    "Archived on": "В архиве с",
    "Archive of old translations": "Архив старых переводов",
    "Translations of keys that are gone from the mod original: deleted rows "
    "and typos in keys.\nThey do not reach the write-to-mod step but are "
    "kept here.":
        "Переводы ключей, которых больше нет в оригинале мода: удалённые "
        "строки и опечатки в ключах.\nВ запись перевода в мод не попадают, "
        "но сохраняются здесь.",
    "Search:": "Поиск:",
    "by key, file or translation text…":
        "по ключу, файлу или тексту перевода…",
    "Copy the translation": "Копировать перевод",
    "Copy everything (key + translation)":
        "Копировать всё (ключ + перевод)",
    "entries: %1": "записей: %1",
}

RU["Import"] = {
    "Load translation from mod": "Загрузить перевод из мода",
    "Take translations from a folder with ready localization files — someone "
    "else's translation of this mod, say, or your own edits made directly in "
    "the files.":
        "Принять переводы из папки с готовыми файлами локализации — например, "
        "из чужого перевода этого мода или из своих правок, сделанных прямо "
        "в файлах.",
    "Translation folder:": "Папка перевода:",
    "Translation folder": "Папка перевода",
    "Browse…": "Обзор…",
    "Overwrite existing translations": "Перезаписывать существующие переводы",
    "Off — only rows that have no translation yet are taken":
        "Выключено — принимаются только строки, у которых перевода ещё нет",
    "Do not take rows where the translation equals the original":
        "Не принимать строки, где перевод совпадает с оригиналом",
    "Take the translations": "Принять переводы",
    "What will change (first rows):": "Что изменится (первые строки):",
    "(empty)": "(пусто)",
    "Parser warnings: %1": "Предупреждения парсера: %1",
    "Loading a translation": "Загрузка перевода",
    "Take %1 rows from the chosen folder?\n\nThe operation is recorded as a "
    "single batch — it can be undone as a whole via «Edit → Undo last "
    "operation» (Ctrl+Z).":
        "Принять %1 строк из выбранной папки?\n\nОперация записывается одной "
        "пачкой — её можно отменить целиком через «Правка → Отменить "
        "последнюю операцию» (Ctrl+Z).",
    "Nothing was taken — the write failed:\n%1":
        "Ничего не взято — запись не удалась:\n%1",
    "\n\nDone. Undo it all with Ctrl+Z.":
        "\n\nГотово. Отменить целиком — Ctrl+Z.",
}

RU["Export"] = {
    "Writing the translation to mod files": "Запись перевода в файлы мода",
    " · ignored: %1": " · игнорировано: %1",
    "Rows in total: %1, going to the mod: %2, without a translation: %3%4":
        "Всего строк: %1, в мод пойдёт: %2, без перевода: %3%4",
    "Translated only (%1 rows)": "Только переведённые (%1 строк)",
    "All rows — untranslated ones stay in English (%1 rows)":
        "Все строки — без перевода останутся на английском (%1 строк)",
    "Include outdated translations (EN changed)":
        "Включать устаревшие переводы (EN изменился)",
    "Include machine translations (nobody has checked them)":
        "Включать машинный перевод (его никто не проверял)",
    "Include machine translations, %1 rows (nobody has checked them)":
        "Включать машинный перевод, %1 строк (их никто не проверял)",
    "Machine translation has been read by no one. In the game it can be wrong "
    "in meaning, break tooltips or lose icons.":
        "Машинный перевод не читал никто. В игре он может соврать по смыслу, "
        "сломать тултипы или потерять иконки.",
    "Back up the files being overwritten":
        "Резервная копия перезаписываемых файлов",
    "Previous versions go into the backups folder — outside the localization "
    "tree, otherwise the game would read the copies as if they were real files":
        "Прежние версии складываются в папку backups — вне дерева локализации, "
        "иначе игра прочитает копии наравне с настоящими файлами",
    "Mod folder:": "Папка мода:",
    "Mod folder": "Папка мода",
    "Browse…": "Обзор…",
    "Choose a folder — the mod folder in Documents, say":
        "Выбрать папку — например, папку мода в Documents",
    "Last write: %1": "Последняя запись: %1",
    "Write": "Записать",
    # Имя файла и заголовок в нём диктует формат игры, а он бывает разный: у
    # CK3 это `mod_l_russian.yml` с `l_russian:` внутри, у CK2 — `text.csv`,
    # где язык вообще колонка. Поэтому в подсказке остаётся сам путь.
    "Files are written for the game, for example:\n%1":
        "Для игры пишутся файлы, например:\n%1",
    "Files of the language «%1» are written for the game":
        "Для игры пишутся файлы языка «%1»",
    "This is the folder the translation was imported from: its files will be "
    "overwritten with the project content.":
        "Это папка, из которой импортирован перевод: её файлы будут "
        "перезаписаны содержимым проекта.",
    "Writing the translation": "Запись перевода",
    "Enter the mod folder.": "Укажите папку мода.",
    "Previous versions will be kept in the backups folder.":
        "Прежние версии сохранятся в папке backups.",
    "Backup is off — there will be nothing to restore the previous versions "
    "from.":
        "Резервная копия отключена — вернуть прежние версии будет нечем.",
    "The folder already holds %1 translation files — they will be overwritten "
    "with the project content.\n\nThe project is the source of truth: rows it "
    "does not have will disappear from the files.\n%2\n\nContinue?":
        "В папке уже есть %1 файлов перевода — они будут перезаписаны "
        "содержимым проекта.\n\nИсточник истины — проект: строки, которых в "
        "нём нет, из файлов исчезнут.\n%2\n\nПродолжить?",
    "Write error:\n%1": "Ошибка записи:\n%1",
    "Files written: %1": "Файлов записано: %1",
    "Files unchanged: %1": "Файлов без изменений: %1",
    "Rows written: %1": "Строк записано: %1",
    "Skipped (no translation): %1": "Пропущено (нет перевода): %1",
    "Left in English: %1": "Оставлено на английском: %1",
    "Previous versions: %1": "Прежние версии: %1",
    "rows": "строк",
    " (skipped %1)": " (пропущено %1)",
}

RU["RulesWindow"] = {
    "One per line":
        "По одному в строке",
    "Values: %1":
        "Значений: %1",
    "The inflection helpers of the target language are added when a project is open — they come with its translation language.":
        "Функции склонения языка перевода подключаются при открытом проекте — они приходят вместе с его языком.",
    "all projects": "все проекты",
    "this project": "этот проект",
    "Error": "Ошибка",
    "Warning": "Предупреждение",
    "Signal": "Сигнал",
    "Comma separated: Concept, Select_CString":
        "Через запятую: Concept, Select_CString",
    "Comma separated: #L, #P": "Через запятую: #L, #P",
    "Comma separated": "Через запятую",
    "Comma separated; fragments of a regular expression are allowed":
        "Через запятую; допустимы фрагменты регулярного выражения",
    "multiset — with counts, set — composition only, count — the number only":
        "multiset — с количеством, set — только состав, count — только число",
    "any — any discrepancy, fewer — lost ones only, more — extra ones only":
        "any — любое расхождение, fewer — только потерянные, "
        "more — только лишние",
    "The wrapper is not «on top of» but «instead of» the reference — 59% of "
    "all bracket discrepancies":
        "Обёртка не «сверх», а «вместо» ссылки — 59% всех расхождений "
        "по скобкам",
    "Stay silent if the same space is in the original":
        "Молчать, если такой же пробел есть в оригинале",
    "Stay silent if the original itself is unbalanced":
        "Молчать, если несбалансирован сам оригинал",
    "Stay silent if the double space is in the original":
        "Молчать, если двойной пробел есть в оригинале",
    "Do not count formatting flags like |E as a discrepancy":
        "Не считать расхождением флаги оформления вида |E",
    "Count brackets after stripping the markup":
        "Считать скобки после снятия разметки",
    "Complain only when not a single variable is left in the translation, and "
    "stay silent when the set merely differs":
        "Ругаться, только если в переводе не осталось ни одной переменной, а на "
        "отличающийся набор молчать",
    "Preset:": "Набор:",
    "Scope:": "Область:",
    "Where to record the setting: into a file next to the application or "
    "inside this project":
        "Куда записать настройку: в файл рядом с приложением или внутрь "
        "этого проекта",
    # сброс — двумя разными действиями: возврат к умолчанию и удаление своей
    # работы путать в одной кнопке нельзя
    "Reset…": "Сбросить…",
    "Return built-in rules to the preset": "Вернуть базовые правила к набору",
    "The built-in rules already match the preset.":
        "Базовые правила и так совпадают с набором.",
    "Return %1 rules to the preset values? Own rules stay as they are.":
        "Вернуть %1 правил к значениям набора? Свои правила останутся как есть.",
    "Delete all own rules": "Удалить все свои правила",
    "There are no own rules in this layer.":
        "В этом слое нет ни одного своего правила.",
    "Delete %1 own rules? This cannot be undone.":
        "Удалить %1 своих правил? Отменить это будет нельзя.",
    "Return the rule to the preset": "Вернуть правило к набору",
    "Set by hand — differs from the preset":
        "Настроено вручную — отличается от набора",
    # корни дерева: что чьё
    "Built-in rules": "Базовые правила",
    "The check is written in the application: it can be switched on and off "
    "and made more lenient, but not rewritten or deleted":
        "Проверку пишет приложение: её можно включить, выключить и смягчить, "
        "но не переписать и не удалить",
    "Rules of your own: they can be added, edited, duplicated and deleted":
        "Правила своей выделки: их можно заводить, править, дублировать и "
        "удалять",
    "Other languages": "Другие языки",
    "Rules of a language other than this project's: they stay silent, but can "
    "be switched on by hand":
        "Правила не того языка, на который переводят в этом проекте: они "
        "молчат, но включить их вручную можно",
    # панель: проверка отдельно, настройка отдельно
    "Check": "Проверка",
    "Check · %1": "Проверка · %1",
    "Setting": "Настройка",
    "🔒 Built-in rule: the check and its wording live in the application. It "
    "can be switched off and made more lenient, but not rewritten or deleted.":
        "🔒 Базовое правило: сама проверка и её формулировка живут в "
        "приложении. Его можно выключить и смягчить, но не переписать и не "
        "удалить.",
    "Duplicate": "Дублировать",
    "A copy of your own rule to edit without losing the original. A built-in "
    "rule cannot be copied — its check is code, not an expression":
        "Копия своего правила, чтобы править её, не теряя рабочего. Базовое "
        "скопировать нечем — его проверка это код, а не выражение",
    "%1 (copy)": "%1 (копия)",
    # свои правила
    "A regular expression; a match counts whole, brackets inside do not "
    "change that":
        "Регулярное выражение; совпадение считается целиком, скобки внутри "
        "этого не меняют",
    "A regular expression over the original":
        "Регулярное выражение по оригиналу",
    "What must be in the translation. Groups of the original are substituted "
    "as \\1":
        "Что обязано быть в переводе. Группы оригинала подставляются как \\1",
    "Treat the answer as a regular expression too. Off, the answer is "
    "searched as plain text — that is why $\\1$ works":
        "Считать ответ тоже регулярным выражением. Выключено — ответ ищется "
        "как текст, потому и работает $\\1$",
    "forbid — fires when found, require — fires when missing":
        "forbid — срабатывает, если нашлось; require — если не нашлось",
    "Ignore the case": "Не различать регистр",
    "Comma separated, two characters each: «», ()":
        "Через запятую, по два символа: «», ()",
    "In a row, without separators: …—": "Подряд, без разделителей: …—",
    "How big a difference is still not an issue":
        "Насколько велика разница, которая ещё не замечание",
    "Own rule…": "Своё правило…",
    "A rule of your own: an expression instead of a built-in check":
        "Правило своей выделки: выражение вместо встроенной проверки",
    "Own rule": "Своё правило",
    # эти две lupdate подставил сам, «по совпадению текста», и пометил
    # непроверенными: пары обязаны жить здесь, а не приезжать из чужого окна
    "Name:": "Название:",
    "Delete": "Удалить",
    "Message:": "Замечание:",
    "same as the name": "как называется",
    "What the check will say about the row":
        "Что проверка скажет про строку",
    "Kind:": "Вид:",
    "for example: No ellipsis as one character":
        "например: Троеточие одним символом",
    "Delete the rule": "Удалить правило",
    "Delete the rule «%1»?": "Удалить правило «%1»?",
    "The rule is set for all projects — here it can only be switched off":
        "Правило задано на все проекты — здесь его можно только выключить",
    # обмен
    "Import…": "Импорт…",
    "Take the setting from a file — someone else's or your own from another "
    "machine":
        "Взять настройку из файла — чужую или свою с другой машины",
    "Export…": "Экспорт…",
    "Write the setting to a file to pass it on":
        "Записать настройку в файл, чтобы передать её дальше",
    "Export check settings": "Экспорт настройки проверок",
    "Import check settings": "Импорт настройки проверок",
    "Check settings (*%1)": "Настройка проверок (*%1)",
    "Check settings (*%1);;All files (*)":
        "Настройка проверок (*%1);;Все файлы (*)",
    "Written: %1": "Записано: %1",
    "The file cannot be read: %1": "Файл не прочитать: %1",
    "Preset: %1": "Набор: %1",
    "Rules edited: %1": "Правил с правками: %1",
    "Own rules: %1": "Своих правил: %1",
    "Not understood and skipped: %1 (%2)": "Не понято и пропущено: %1 (%2)",
    "Replace the setting for «%1»?": "Заменить настройку для области «%1»?",
    "Rule": "Правило",
    "Hits": "Раз",
    "Severity": "Серьёзность",
    "How many times the rule fires on this project":
        "Сколько раз правило срабатывает на этом проекте",
    "Severity:": "Серьёзность:",
    "Leniency": "Послабления",
    "This rule has no settings.": "У этого правила нет настроек.",
    "This rule has no self-check examples — try it on a pair above.":
        "У этого правила нет примеров-самопроверок — проверьте его на паре выше.",
    "Examples — the rule checks itself with them:":
        "Примеры — правило проверяет себя ими само:",
    "Original": "Оригинал",
    "Translation": "Перевод",
    "Expected": "Ожидается",
    "Now": "Сейчас",
    "fires": "срабатывает",
    "silent": "молчит",
    "Check on a pair": "Проверить на паре",
    "original": "оригинал",
    "translation": "перевод",
    "Take the current row": "Взять текущую строку",
    "Insert the pair from the row selected in the project table":
        "Подставить пару из строки, выбранной в таблице проекта",
    "No issues.": "Замечаний нет.",
    "project-wide": "по проекту",
    "The hit counter needs an open project.":
        "Счётчик срабатываний доступен при открытом проекте.",
    "Counting the hits…": "Считаю срабатывания…",
    "Hits counted on %1 translated rows of the project.":
        "Срабатываний посчитано на %1 переведённых строках проекта.",
    "Return to the check": "Вернуть в проверку",
    "Return all": "Вернуть все",
    "Nothing has been silenced yet.\n\n"
    "This is where issues go after the «Not an error» button in the "
    "check report (F6): a silenced issue stops showing up both in the "
    "report and in the «!» column of the table. From here it can be "
    "put back into the check.":
        "Пока ничего не заглушено.\n\n"
        "Сюда попадают замечания после кнопки «Не ошибка» в отчёте "
        "проверки (F6): заглушённое замечание перестаёт показываться и в "
        "отчёте, и в колонке «!» таблицы. Отсюда его можно вернуть в "
        "проверку.",
    "Nothing is marked «not an error».":
        "Ничего не помечено как «не ошибка».",
    "Marked «not an error»: %1.": "Помечено «не ошибка»: %1.",
    "Return all %1 issues to the check?":
        "Вернуть в проверку все %1 замечаний?",
    "Check settings": "Настройка проверок",
    "Rules": "Правила",
    "Marked «not an error»": "Помеченные «не ошибка»",
    "Apply and close": "Применить и закрыть",
}

RU["TmBuild"] = {
    "Game:": "Игра:",
    "From localization folders": "Из папок локализации",
    "From the current project translations": "Из переводов текущего проекта",
    "An open project is needed": "Нужен открытый проект",
    "Create the database": "Создать базу",
    "Export": "Выгрузить",
    "Interrupt": "Прервать",
    "Interrupting…": "Прерывание…",
    "Done": "Готово",
    "Database name:": "Название базы:",
    "Original folder:": "Папка оригинала:",
    "Translation folder:": "Папка перевода:",
    "Browse…": "Обзор…",
    "Choose a folder": "Выбор папки",
    "Languages:": "Языки:",
    "Game database (vanilla localization)":
        "База игры (ванильная локализация)",
    "Import of someone else's translation": "Импорт чужого перевода",
    "Database kind:": "Тип базы:",
    "For a game database point at the localization folders of the installed "
    "CK3, for example:\n…\\Crusader Kings III\\game\\localization\\english and "
    "…\\localization\\russian.\nThe finished database appears in the folder %1.":
        "Для базы игры укажите папки локализации установленной CK3, например:\n"
        "…\\Crusader Kings III\\game\\localization\\english и "
        "…\\localization\\russian.\nГотовая база появится в папке %1.",
    "Translated and reviewed rows of the project go into a separate database "
    "in the folder %1 — it can be attached to another project.":
        "Переведённые и проверенные строки проекта лягут отдельной базой в "
        "папку %1 — её можно подключить к другому проекту.",
    " · took the nested translation folder: %1":
        " · взята вложенная папка перевода: %1",
    "(0 pairs)": "(0 пар)",
    " · nested checked: %1": " · проверены вложенные: %1",
    "Localization folder found: %1": "Найдена папка локализации: %1",
    "There are no localization files in the original folder":
        "В папке оригинала нет файлов локализации",
    "Original files: %1, but none of them has a pair in the translation "
    "folder — check that the localization folders are the ones given":
        "Файлов оригинала: %1, но ни у одного нет пары в папке перевода — "
        "проверьте, что указаны именно папки локализации",
    "Original files: %1, of them with a pair: %2":
        "Файлов оригинала: %1, из них с парой: %2",
    "Translation database": "База переводов",
    "Enter the database name and the original folder.":
        "Укажите название базы и папку оригинала.",
    "The file already exists:\n%1\n\nOverwrite?":
        "Файл уже существует:\n%1\n\nПерезаписать?",
    "Could not export:\n%1": "Не удалось выгрузить:\n%1",
    "Translation pairs exported: %1": "Выгружено пар переводов: %1",
    "Done: %1 translation pairs.\n\n%2": "Готово: %1 пар переводов.\n\n%2",
    "— 0 pairs": "— 0 пар",
    "None of the %1 original files has a pair in the translation folder.\n\n"
    "Folders checked:\n%2\n\nUsually this means the game or mod root was "
    "given while localization folders are needed — for example:\n"
    "  …\\game\\localization\\%3\n  …\\game\\localization\\%4\n\n"
    "A translation mod keeps files in its own tree: for Russian translations "
    "that is usually …\\localization\\%4, and next to it lies "
    "…\\localization\\replace\\%4 — a replacement of vanilla strings, "
    "unrelated to the mod's own strings.":
        "Ни один из %1 файлов оригинала не имеет пары в папке перевода.\n\n"
        "Проверены папки:\n%2\n\nОбычно это значит, что указан корень игры "
        "или мода, а нужны папки локализации — например:\n"
        "  …\\game\\localization\\%3\n  …\\game\\localization\\%4\n\n"
        "Перевод-мод хранит файлы в своём дереве: у русификаторов это обычно "
        "…\\localization\\%4, а рядом лежит …\\localization\\replace\\%4 — "
        "замена ванильных строк, к строкам мода отношения не имеющая.",
    "%1 files will be processed — this may take about %2 seconds, and the "
    "database will take noticeable disk space.\n\nContinue?":
        "Будет обработано %1 файлов — это может занять около %2 секунд, "
        "а база займёт заметное место на диске.\n\nПродолжить?",
    "Build interrupted — the database file was not created":
        "Сборка прервана — файл базы не создан",
    "File: %1": "Файл: %1",
    "Parser warnings:": "Предупреждения парсера:",
    "Could not create the database:\n%1": "Не удалось создать базу:\n%1",
}

RU["TmSources"] = {
    "The database is of another game — %1": "База другой игры — %1",
    "Refresh the list": "Обновить список",
    "Build the similar-rows index": "Построить индекс похожих строк",
    "Without an index the database answers exact matches only.\n"
    "Building takes seconds and adds about 20% to the file size.":
        "Без индекса база отвечает только на точные совпадения.\n"
        "Постройка занимает секунды и добавляет к файлу базы около 20% объёма.",
    "No databases yet. Build one from localization folders on the "
    "«Build a database» tab.":
        "Баз пока нет. Соберите базу из папок локализации на вкладке "
        "«Собрать базу».",
    "Checked databases provide suggestions and autofill (%1 → %2). "
    "Changes apply immediately.":
        "Отмеченные базы дают подсказки и автозаполнение (%1 → %2). "
        "Изменения применяются сразу.",
    "(file not found in the Bdd folder)": "(файл не найден в папке Bdd)",
    "entries": "записей",
    "with a similarity index": "с индексом похожих",
    "without a similarity index": "без индекса похожих",
    "The database languages do not match the project languages":
        "Языки базы не совпадают с языками проекта",
    "databases in the folder: %1 · attached: %2":
        "баз в папке: %1 · подключено: %2",
    " · entries: %1": " · записей: %1",
    "Index": "Индекс",
    "Choose a database in the list.": "Выберите базу в списке.",
    "Database file not found:\n%1": "Файл базы не найден:\n%1",
    "Could not build the index:\n%1": "Не удалось построить индекс:\n%1",
    "Index built: %1 entries.\n\nThe database now suggests not only exact "
    "matches but similar rows too.":
        "Индекс построен: %1 записей.\n\nТеперь база подсказывает не только "
        "точные совпадения, но и похожие строки.",
}

RU["TmEntries"] = {
    "Original": "Оригинал",
    "Translation": "Перевод",
    "Source": "Источник",
    "Key": "Ключ",
    "Changed": "Изменено",
    "Click — ascending, again — descending, again — as the database returns it":
        "Клик — по возрастанию, ещё — по убыванию, ещё — как отдаёт база",
    "Search:": "Поиск:",
    "by original, translation or key…": "по оригиналу, переводу или ключу…",
    "my entries only": "только мои записи",
    "Hide entries of attached databases — they are read only":
        "Скрыть записи подключённых баз — они доступны только для чтения",
    "Double click on a translation to edit it. Entries of attached databases "
    "are dimmed: their files are open read only.":
        "Двойной клик по переводу — правка. Записи подключённых баз "
        "приглушены: их файлы открыты только на чтение.",
    "Delete selected": "Удалить выделенные",
    "Clear my memory…": "Очистить мою память…",
    " · from attached databases: %1": " · из подключённых баз: %1",
    " (first ones shown — refine the search)":
        " (показаны первые — уточните поиск)",
    "shown: %1%2 · my entries: %3%4": "показано: %1%2 · моих записей: %3%4",
    "Translation memory": "Память переводов",
    "Only entries of attached databases are selected — they are read only.\n"
    "A database can be detached on the «Databases» tab.":
        "Выделены только записи подключённых баз — они доступны только для "
        "чтения.\nОтключить базу можно на вкладке «Базы».",
    "\n\nEntries of attached databases (%1) will not be touched.":
        "\n\nЗаписи подключённых баз (%1) затронуты не будут.",
    "Deletion": "Удаление",
    "Delete %1 entries from the translation memory?%2\n\nThe translations of "
    "the project rows themselves do not change.":
        "Удалить %1 записей из памяти переводов?%2\n\nПереводы самих строк "
        "проекта при этом не меняются.",
    "Clear the memory": "Очистить память",
    "Delete all %1 entries of my translation memory?\n\nThe translations of "
    "the project rows stay in place — the memory fills up again on the next "
    "scan.":
        "Удалить все %1 записей моей памяти переводов?\n\nПереводы строк "
        "проекта останутся на месте — память заполнится заново при следующем "
        "сканировании.",
}

RU["Prefs"] = {
    "Browse…": "Обзор…",
    "Choose a folder": "Выбор папки",
    "Preferences": "Параметры",
    "General": "Общие",
    "Folders": "Папки",
    "Editor": "Редактор",
    "Memory": "Память",
    "Interface language:": "Язык интерфейса:",
    "Colour theme:": "Тема оформления:",
    "Open the last project on startup": "Открывать последний проект при запуске",
    "Show hidden reminders again": "Снова показывать скрытые напоминания",
    "Reminders you switched off with «Do not ask again»":
        "Напоминания, отключённые галкой «Больше не спрашивать»",
    "No reminders are hidden right now": "Сейчас ничего не скрыто",
    "The interface language applies immediately. It is not related to the "
    "translation languages — those are set in the project itself.":
        "Язык интерфейса применяется сразу. Он не связан с языками перевода: "
        "те задаются в самом проекте.",
    "Translation memory databases:": "Базы памяти переводов:",
    "Projects:": "Проекты:",
    "Backups:": "Резервные копии:",
    "Snapshots of files overwritten when writing the translation to the "
    "mod.\n0 — do not keep any.":
        "Снимки файлов, перезаписанных при записи перевода в мод.\n"
        "0 — не хранить вовсе.",
    "Keep copies per project:": "Хранить копий на проект:",
    "Copies must not be put next to the localization: the game reads every "
    "*.yml from that folder and would load a backup file as if it were a "
    "real one.":
        "Копии нельзя класть рядом с локализацией: игра читает из её папки "
        "все *.yml и загрузила бы файл-бэкап наравне с настоящим.",
    "Font of the original and translation fields:":
        "Шрифт полей оригинала и перевода:",
    "Font size:": "Размер шрифта:",
    "Table row height:": "Высота строки таблицы:",
    "Long rows are truncated in the cell — the full text is always visible "
    "in the editor pane and in the tooltip":
        "Длинные строки обрезаются в ячейке — полный текст всегда виден "
        "в панели редактора и в подсказке",
    "Truncate cell text after, characters:":
        "Обрезать текст ячейки после, символов:",
    "Show the table grid": "Показывать сетку таблицы",
    "Highlight changes of the original": "Подсвечивать изменения оригинала",
    "Below this similarity, similar rows do not appear in the suggestions":
        "Ниже этого сходства похожие строки в подсказки не попадают",
    "Suggestion similarity threshold:": "Порог похожести подсказок:",
    "Suggestions to show:": "Показывать подсказок:",
    "Exact matches are always shown and come first — the threshold applies "
    "to similar rows only.":
        "Точные совпадения показываются всегда и идут первыми — порог "
        "касается только похожих строк.",
    # вкладка машинного перевода
    "Machine translation": "Машинный перевод",
    "Service:": "Сервис:",
    "Access key:": "Ключ доступа:",
    "Show": "Показать",
    "Check": "Проверить",
    "Checking…": "Проверяю…",
    "The key works.": "Ключ работает.",
    "Used %1 of %2 characters": "Израсходовано %1 из %2 символов",
    "The key is protected by Windows for your account. It is unreadable from "
    "another account, but a program running as you can read it.":
        "Ключ защищён Windows для вашей учётной записи. Из другой учётной "
        "записи его не прочесть, но программа, запущенная от вашего имени, "
        "прочтёт.",
    "The key is stored as plain text: this system cannot protect it.":
        "Ключ хранится открытым текстом: эта система защитить его не умеет.",
    "Pro subscription (a different address, not a tariff)":
        "Подписка Pro (это другой адрес, а не тариф)",
    "Model:": "Модель:",
    "the service default": "умолчание сервиса",
    "Extra instructions:": "Дополнительные указания:",
    "For example: formal tone, «you» in the plural, keep the names as in the "
    "glossary":
        "Например: официальный тон, обращение на «вы», имена как в глоссарии",
    "Folder id:": "Идентификатор каталога:",
    "Characters per request:": "Символов на запрос:",
    "How many characters go into one request. Rows are never cut in half: one "
    "that does not fit is left untranslated":
        "Сколько символов уходит в один запрос. Строки не режутся пополам: "
        "не влезающая остаётся непереведённой",
    "Pause between requests:": "Пауза между запросами:",
    "A pause between requests. Without it services start refusing halfway "
    "through a long run":
        "Пауза между запросами. Без неё сервисы начинают отказывать посреди "
        "длинного прогона",
    "Retries after a refusal:": "Повторов после отказа:",
    "Request timeout:": "Ожидание ответа:",
    "Machine translation is written with the «Machine (unchecked)» status. It "
    "does not go into the translation memory and is not written to the mod "
    "until you allow it in the export window.":
        "Машинный перевод записывается со статусом «Машинный (не проверен)». "
        "В память переводов он не попадает и в мод не пишется, пока вы не "
        "разрешите это в окне записи.",
}

RU["StartScreen"] = {
    "Translation projects": "Проекты перевода",
    "Game not specified": "Игра не указана",
    "New project": "Новый проект",
    "Game:": "Игра:",
    "Format is the same across the series. Of another game — type its name: "
    "it gets a pen of its own next to the rest":
        "Формат у всей серии общий. Другая игра — впишите её название: "
        "у неё появится свой загон рядом с остальными",
    "Name:": "Название:",
    "Original folder:": "Папка оригинала:",
    "Translation folder:": "Папка перевода:",
    "Browse…": "Обзор…",
    "Choose a folder": "Выбор папки",
    "Choose where to put the project file":
        "Выбрать, куда положить файл проекта",
    "Project file:": "Файл проекта:",
    "Project file": "Файл проекта",
    "The original folder is the one holding *_l_%1.yml "
    "(for example …\\localization\\english).\n"
    "The translation folder is where *_l_%2.yml go; it may not exist yet.\n"
    "The project file is portable: put it anywhere.":
        "Папка оригинала — та, где лежат *_l_%1.yml "
        "(например …\\localization\\english).\n"
        "Папка перевода — куда писать *_l_%2.yml; её может ещё не быть.\n"
        "Файл проекта переносим: его можно положить куда угодно.",
    "Translation project (*%1)": "Проект перевода (*%1)",
    "Translation project (*%1);;All files (*)":
        "Проект перевода (*%1);;Все файлы (*)",
    "Project": "Проект",
    "Enter the project name.": "Укажите название проекта.",
    "The original folder does not exist:\n%1":
        "Папка оригинала не существует:\n%1",
    "Enter the translation folder.": "Укажите папку перевода.",
    "Enter the project file.": "Укажите файл проекта.",
    "The file already exists:\n%1": "Файл уже существует:\n%1",
    "Could not create the project:\n%1": "Не удалось создать проект:\n%1",
    "Project file not found:\n%1": "Файл проекта не найден:\n%1",
    "Open project": "Открыть проект",
    "Create…": "Создать…",
    "Open": "Открыть",
    "Open file…": "Открыть файл…",
    "Show in Explorer": "Показать в проводнике",
    "Remove from the list": "Убрать из списка",
    "Delete…": "Удалить…",
    "file not found": "файл не найден",
    "Remove the project from the recent list?\n\nThe file %1 itself stays "
    "on disk.":
        "Убрать проект из списка недавних?\n\nСам файл %1 останется на диске.",
    "Game folders:": "Папки игры:",
    "The text is in another language": "Текст на другом языке",
    "Portuguese in CK3, say, lives in l_english files: the game has no folder "
    "of its own for it":
        "Португальский в CK3, например, лежит в файлах l_english: своей папки "
        "у него в игре нет",
    "Text languages:": "Языки текста:",
}

RU["ScanDialog"] = {
    "Scanning…": "Сканирование…",
    "Preparing…": "Подготовка…",
    "Processed files:": "Обработанные файлы:",
    "Interrupt": "Прервать",
    "File %1 of %2: %3": "Файл %1 из %2: %3",
    "Interrupting — rolling back changes…": "Прерывание — откат изменений…",
    "Scan results": "Результаты сканирования",
    "Original files: %1 · translation files: %2":
        "Файлов оригинала: %1 · файлов перевода: %2",
    "What": "Что",
    "How many": "Сколько",
    "Show": "Показать",
    "Show details (%1)": "Показать подробности (%1)",
    "Hide details": "Скрыть подробности",
    "New rows": "Новых строк",
    "The original changed in meaning": "Оригинал изменился по смыслу",
    "The original was edited cosmetically": "Оригинал правили косметически",
    "Filled from translation memory": "Заполнено из памяти переводов",
    "Ignored (nothing to translate)": "Игнорируется (переводить нечего)",
    "Deleted from the original": "Удалено из оригинала",
    "Moved to the archive": "Перенесено в архив",
    "Unchanged": "Без изменений",
    "The discrepancies below were left as they are: the project has its own "
    "version. To take the version from the files use «Project → Load "
    "translation from mod…» with the «Overwrite existing translations» "
    "checkbox.":
        "Расхождения ниже оставлены как есть: в проекте своя версия. "
        "Принять версию из файлов — «Проект → Загрузить перевод из мода…» "
        "с галочкой «Перезаписывать существующие переводы».",
    "Discrepancy with the file · %1: %2": "Расхождение с файлом · %1: %2",
    "      in project: %1": "      в проекте: %1",
    "      in file:    %1": "      в файле:   %1",
    "Duplicate key (original) · %1": "Дубликат ключа (оригинал) · %1",
    "Duplicate key (translation) · %1": "Дубликат ключа (перевод) · %1",
    "Empty original · %1": "Пустой оригинал · %1",
    "Translation file without a pair · %1": "Файл перевода без пары · %1",
    "Parser · %1": "Парсер · %1",
}

RU["QaPanel"] = {
    "Key": "Ключ",
    "File": "Файл",
    "Issue": "Проблема",
    "Severity": "Серьёзность",
    "Error": "Ошибка",
    "Warning": "Предупреждение",
    "Signal": "Сигнал",
    "Project check": "Проверка проекта",
    "Check": "Проверить",
    "Filter:": "Фильтр:",
    "All issues": "Все проблемы",
    "Not an error": "Не считать ошибкой",
    "Mark the selected issue as false — do not show it again":
        "Пометить выделенное замечание как ложное — больше не показывать",
    "Configure this rule…": "Настроить это правило…",
    "Open the settings of the rule behind the selected issue":
        "Открыть настройку правила, по которому сделано выделенное замечание",
    "Close": "Закрыть",
    "issues: %1 (errors: %2)": "проблем: %1 (ошибок: %2)",
}

RU["TmWindow"] = {
    "Translation memory": "Память переводов",
    "Entries": "Записи",
    "Databases": "Базы",
    "Build a database": "Собрать базу",
    "Building a database": "Сборка базы",
    "The database is still being built. Interrupt it and close the window?\n\n"
    "An unfinished database file will not be created.":
        "База ещё собирается. Прервать сборку и закрыть окно?\n\n"
        "Недособранный файл базы создан не будет.",
}

RU["Concordance"] = {
    "How was this translated before": "Как переводили это раньше",
    "Fragment:": "Фрагмент:",
    "a word or a piece of a phrase from the original…":
        "слово или кусок фразы из оригинала…",
    "Original": "Оригинал",
    "Translation": "Перевод",
    "Source": "Источник",
    "Nothing found": "Ничего не найдено",
    "Found: %1 · double click copies the translation":
        "Найдено: %1 · двойной клик копирует перевод",
    "Translation copied to the clipboard": "Перевод скопирован в буфер",
}

RU["FileTree"] = {"ALL": "ВСЕ"}

RU["StatusChips"] = {
    "%1 — click to filter": "%1 — клик для фильтра",
    "Rows with issues among those loaded — click to keep only them":
        "Строк с замечаниями среди загруженных — клик оставит только их",
}

RU["Toolbar"] = {
    "Toolbar": "Панель инструментов",
    "Project languages: original → translation":
        "Языки проекта: оригинал → перевод",
    "Attached translation memory databases — they can be switched on and "
    "off right here":
        "Подключённые базы памяти переводов — можно включать и отключать "
        "прямо отсюда",
    "Memory databases": "Базы памяти",
    "No databases yet": "Баз пока нет",
    "entries": "записей",
}

RU["Editor"] = {
    "Status:": "Статус:",
    "All": "Все",
    "Search: key / EN / RU…  (Ctrl+F)": "Поиск: ключ / EN / RU…  (Ctrl+F)",
    "with issues": "с замечаниями",
    "Show only rows the check has questions about":
        "Показать только строки, к которым есть вопросы у проверки",
    "deleted": "удалённые",
    "Rows selected: %1": "Выделено строк: %1",
    "Apply to all": "Применить ко всем",
    "There are no untranslated rows with the same EN text.":
        "Непереведённых строк с таким же EN-текстом нет.",
    "Apply this translation to %1 rows with the same English text?":
        "Применить этот перевод к %1 строкам с таким же английским текстом?",
    "Changed %1 of %2 (a status is not set without a translation)":
        "Изменено %1 из %2 (без перевода статус не ставится)",
    "Reset translation": "Сбросить перевод",
    "Reset the translation of %1 rows?": "Сбросить перевод %1 строк?",
    "No translation service is set up — "
    "«File → Preferences → Machine translation»":
        "Сервис перевода не настроен — "
        "«Файл → Параметры → Машинный перевод»",
    "Translating…": "Перевожу…",
    "The translation lost a placeholder — check the row":
        "Перевод потерял подстановку — проверьте строку",
    "Translated by the service — Ctrl+Z undoes it":
        "Переведено сервисом — Ctrl+Z вернёт как было",
}

RU["DetailPane"] = {
    # подпись собственной памяти проекта в колонке «Источник» (db.OWN_ORIGIN)
    "Project": "Проект",
    "highlight terms": "подсвечивать термины",
    "Highlight glossary terms in the original; hover shows the accepted "
    "translation":
        "Подсвечивать в оригинале термины глоссария; при наведении виден "
        "принятый перевод",
    "my translations": "мои переводы",
    "import": "импорт",
    "game database": "база игры",
    "project export": "экспорт проекта",
    "Entry original (%1 similarity):": "Оригинал записи (%1 сходства):",
    "Source: %1": "Источник: %1",
    "Read only (attached database)": "Только для чтения (подключённая база)",
    "Open translation memory…": "Открыть память переводов…",
    "Insert into translation": "Подставить в перевод",
    "Copy text": "Копировать текст",
    "Edit the memory entry…": "Изменить запись в памяти…",
    "Delete from memory": "Удалить из памяти",
    "An entry from an attached database — read only":
        "Запись из подключённой базы — только для чтения",
    "Edit memory entry": "Изменить запись памяти",
    "Translation in memory (suggestions for identical rows):":
        "Перевод в памяти (подсказки для одинаковых строк):",
    "Remove this variant from the translation memory?\n\n%1\n\n"
    "The translation of the current row stays in place.":
        "Убрать этот вариант из памяти переводов?\n\n%1\n\n"
        "Перевод текущей строки останется на месте.",
    "Original (EN):": "Оригинал (EN):",
    "highlight changes": "подсвечивать изменения",
    "Highlight in the original what was not in the previous revision":
        "Закрашивать в оригинале то, чего не было в прежней редакции",
    "Change of the original (was → became):":
        "Изменение оригинала (было → стало):",
    "Actualize": "Актуализировать",
    "Confirm that the translation matches the new original":
        "Подтвердить, что перевод соответствует новому оригиналу",
    "Translation (RU):": "Перевод (RU):",
    "Translation memory (double click — insert, right button — actions):":
        "Память переводов (двойной клик — подставить, правая кнопка — действия):",
    "unsaved edits (Ctrl+S)": "есть несохранённые правки (Ctrl+S)",
    "saved": "сохранено",
    "(no original — the key exists only in RU)":
        "(нет оригинала — ключ только в RU)",
    " (cosmetic edit)": " (косметическая правка)",
    "The original changed%1 — was → became:":
        "Оригинал изменился%1 — было → стало:",
}

RU["QaRules"] = {
    "Every rule on, nothing forgiven. For the final read-through, when you would rather sift ten false alarms than miss one real fault.":
        "Все правила включены, ничего не прощается. Для финальной вычитки, когда лучше перебрать десяток ложных тревог, чем пропустить одну настоящую.",
    "What a CK3 translator does on purpose stops counting as a mistake: a reference wrapped so it can be inflected, an added #L, formatting flags. The helpers your language uses are added on their own.":
        "То, что переводчик CK3 делает намеренно, перестаёт быть ошибкой: обёртка вокруг ссылки ради склонения, дописанный #L, флаги оформления. Помощники вашего языка подключаются сами.",
    "HOI4 gives each language its own inflection helpers, and a translation swaps plain references for them. This set knows them, so a swap stops reading as a loss.":
        "HOI4 даёт каждому языку свои функции склонения, и перевод меняет на них обычные ссылки. Набор их знает, поэтому замена перестаёт читаться как потеря.",
    "CK2 translations inflect nearly everything and add forms of address the English has none of. That is expected here — a reference that went missing is still caught.":
        "Переводы CK2 склоняют почти всё и дописывают обращения, которых в английском нет. Здесь это в порядке вещей — а пропавшую ссылку правило по-прежнему поймает.",
    "Stellaris inflects names through a grammar system of its own, and many terms are meant to stay as they are in the original. Those stop shouting; anything that breaks the text still does.":
        "Stellaris склоняет имена собственной грамматической системой, и многие термины должны остаться как в оригинале. Такие перестают кричать; то, что ломает текст, кричит по-прежнему.",
    "Only what breaks the text in the game: a lost variable or icon, an unclosed tag, an empty translation. Everything else keeps quiet.":
        "Только то, что ломает текст в игре: потерянная переменная или иконка, незакрытый тег, пустой перевод. Остальное молчит.",
    "The built-in values with nothing on top. Start here to set every rule by hand.":
        "Встроенные значения и ничего сверху. Отсюда начинают, когда хотят настроить каждое правило руками.",
    "A lost variable leaves a hole in the text in the game. A set that merely differs is a softer case, and «only_if_all_lost» keeps quiet about it":
        "Потерянная переменная оставляет в тексте дыру прямо в игре. Просто различающийся набор — случай мягче, и «only_if_all_lost» о нём молчит",
    "@gold! is the CK3 icon; the £gold£ form belongs to EU4, HOI4 and Stellaris. Both are checked, because a translator who has worked on another game types the icon they are used to":
        "@gold! — иконка CK3; форма £gold£ принадлежит EU4, HOI4 и Stellaris. Проверяются обе: переводчик, работавший над другой игрой, наберёт привычную",
    "The colour of HOI4, EU4 and Stellaris: §Y…§!. A lost §! paints the rest of the line, and a swapped code can turn a warning green":
        "Цвет HOI4, EU4 и Stellaris: §Y…§!. Потерянный §! красит остаток строки, а перепутанный код способен сделать предупреждение зелёным",
    "The Stellaris grammar system: «Empress&!fem,vowel» and «A $1$|||vowel:An $1$». Variants the translator adds for cases are fine; a lost tag is not — it changes the gender of a name everywhere it is substituted":
        "Грамматическая система Stellaris: «Empress&!fem,vowel» и «A $1$|||vowel:An $1$». Варианты, дописанные ради падежей, — норма; потерянный тег — нет: он меняет род имени всюду, куда его подставят",
    "An edge space is often in the original too: that is how the game glues strings together. Compared against the source, the rule stays quiet about those":
        "Краевой пробел часто есть и в оригинале: так игра склеивает строки. При сверке с оригиналом правило о таких молчит",
    "The original is often unbalanced itself, and the translation has nothing to do with it — hence the check against the source":
        "Оригинал и сам часто несбалансирован, а перевод тут ни при чём — потому и сверка с оригиналом",
    "A repetition inside a repeated group — on a long row the check can "
    "take minutes. Consider (?:…) or a stricter pattern.":
        "Повтор внутри повторяемой группы — на длинной строке проверка может "
        "занять минуты. Подумайте о (?:…) или более строгом шаблоне.",
    # категории
    "Markup": "Разметка",
    "Formatting": "Оформление",
    "Typography": "Типографика",
    "Target language": "Язык перевода",
    "Consistency": "Согласованность",
    "Length": "Длина",
    "Own rules": "Свои правила",
    # виды своих правил
    "Same set of matches": "Тот же набор совпадений",
    "What the expression finds in the original must be found in the "
    "translation — the same items and as many":
        "Что выражение нашло в оригинале, должно найтись и в переводе — то же "
        "самое и столько же",
    "Same number of matches": "То же число совпадений",
    "Only the count is compared, the items themselves may differ — for things "
    "that get translated":
        "Сравнивается только количество, сами куски могут отличаться — для "
        "того, что переводится",
    "Expression in the translation": "Выражение в переводе",
    "forbid — fires when found, require — fires when missing":
        "forbid — срабатывает, если нашлось; require — если не нашлось",
    "Original → translation": "Оригинал → перевод",
    "For every match in the original the translation must contain the answer: "
    "groups are substituted into it as \\1":
        "На каждое совпадение в оригинале в переводе обязан быть ответ: "
        "группы подставляются в него как \\1",
    "Paired characters": "Парные символы",
    "Two characters per pair: «» or (). Identical halves are counted for "
    "parity":
        "По два символа на пару: «» или (). Одинаковые половинки считаются "
        "на чётность",
    "Forbidden characters": "Запрещённые символы",
    "Every character listed is forbidden in the translation":
        "Каждый перечисленный символ в переводе запрещён",
    # правила
    "Empty translation": "Пустой перевод",
    "Status is «translated», but the translation is empty":
        "Статус «переведено», но перевод пуст",
    "Variables $…$": "Переменные $…$",
    "Variables $…$ do not match the original":
        "Переменные $…$ не совпадают с оригиналом",
    "Icons @…! and £…£": "Иконки @…! и £…£",
    "Icons do not match the original": "Иконки не совпадают с оригиналом",
    "Colour codes §…§!": "Цветовые коды §…§!",
    "Colour codes do not match the original":
        "Цветовые коды не совпадают с оригиналом",
    "Grammar tags and variants": "Грамматические теги и варианты",
    "A grammar tag or variant of the original was lost":
        "Потерян грамматический тег или вариант из оригинала",
    "Formatting tags #…": "Теги оформления #…",
    "The set of formatting tags differs from the original":
        "Набор тегов оформления отличается от оригинала",
    "Tags not closed": "Теги не закрыты",
    "Tags are closed in the original but not in the translation":
        "В оригинале теги закрыты, в переводе — нет",
    "Script references [ ]": "Скриптовые ссылки [ ]",
    "Script references [ ] differ from the original":
        "Скриптовые ссылки [ ] отличаются от оригинала",
    "The main source of noise: the translator wraps a substitution in "
    "Concept(…) to inflect it — that is a technique, not a mistake":
        "Главный источник шума: переводчик оборачивает подстановку в "
        "Concept(…) ради склонения — это приём, а не ошибка",
    "Line breaks": "Переносы строк",
    "The number of \\n breaks differs from the original":
        "Число переносов \\n отличается от оригинала",
    "Translation equals the original": "Перевод равен оригиналу",
    "The translation matches the original": "Перевод совпадает с оригиналом",
    "Normal for names and numbers — such rows are marked «Ignore»":
        "Для имён и чисел это норма — такие строки помечают «Игнорировать»",
    "Edge spaces": "Пробелы по краям",
    "Extra spaces at the beginning or the end":
        "Лишние пробелы в начале или в конце",
    "Double spaces": "Двойные пробелы",
    "Double spaces in the translation": "Двойные пробелы в переводе",
    "Unpaired quotes and brackets": "Непарные кавычки и скобки",
    "Unpaired quotes or brackets in the translation":
        "Непарные кавычки или скобки в переводе",
    "Missing space before a substitution": "Пропущен пробел перед подстановкой",
    "Missing space before a substitution — the words will stick together":
        "Пропущен пробел перед подстановкой — слова слипнутся",
    "A word of 3+ letters: one or two letters get a pronoun attached on "
    "purpose — «к н[X.GetHerHis]» yields «к нему»":
        "Слово из 3+ букв: за одну-две цепляют местоимение намеренно — "
        "«к н[X.GetHerHis]» даёт «к нему»",
    "Calque of an English copula": "Калька с английской связки",
    "A substitution after a copula verb: «склонны быть Верность». An "
    "appositive turn is needed — «склонны проявлять черту: …»":
        "Подстановка после глагола-связки: «склонны быть Верность». "
        "Нужен оборот с приложением — «склонны проявлять черту: …»",
    "CK3 names traits with nouns («Верность», «Отвага»), so «склонны быть "
    "[Trait]» unfolds into nonsense":
        "CK3 называет черты существительными («Верность», «Отвага»), "
        "поэтому «склонны быть [Trait]» разворачивается в бессмыслицу",
    "Same original translated differently": "Такой же оригинал переведён иначе",
    "The same original is translated differently in the project":
        "Такой же оригинал переведён в проекте иначе",
    "Not an error but a reason to check: one English word can be different "
    "things in different places":
        "Не ошибка, а повод свериться: одно английское слово бывает "
        "разными вещами в разных местах",
    "Suspicious length": "Подозрительная длина",
    "Suspicious length of the translation": "Подозрительная длина перевода",
    "A heuristic: noisier than it is useful, hence off":
        "Эвристика: шумит больше, чем помогает, поэтому выключена",
    # наборы
    "Strict": "Строгий",
    "%1 — recommended for this project":
        "%1 — рекомендуется для этого проекта",
    "Breakage only": "Только поломки",
    "Own": "Свой",
}

RU["UnitsTable"] = {
    "Key": "Ключ",
    "File": "Файл",
    "Status": "Статус",
    "Original": "Оригинал",
    "Translation": "Перевод",
    "Change to original": "Правка оригинала",
    "Issues": "Замечания",
    "C": "К",           # кастомный статус
    "I": "И",           # игнорировать
    "deleted": "удалён",
    "Validate (F10)": "Подтвердить (F10)",
    "Unvalidate (Shift+F10)": "Снять подтверждение (Shift+F10)",
    "Custom status (Ctrl+F10)": "Кастомный статус (Ctrl+F10)",
    "Ignore (Ctrl+Shift+F10)": "Игнорировать (Ctrl+Shift+F10)",
    "The original was edited cosmetically (punctuation, case, spaces)":
        "Оригинал правили косметически (пунктуация, регистр, пробелы)",
    "The original changed in meaning — check the translation":
        "Оригинал изменился по смыслу — перевод нужно проверить",
    "Sort by key": "Сортировать по ключу",
    "Sort by file": "Сортировать по файлу",
    "Sort by original text": "Сортировать по тексту оригинала",
    "Sort by translated text": "Сортировать по тексту перевода",
    "Sort by status — in working order, not alphabetically":
        "Сортировать по статусу — в порядке работы, а не по алфавиту",
    "Sort by kind of change to the original: meaningful first":
        "Сортировать по характеру правки оригинала: сначала смысловые",
    "Click — rows with issues on top. Click again — only those. Again — as it was":
        "Клик — строки с замечаниями наверх. Ещё клик — только они. Ещё — как было",
    "Click — ascending, again — descending, again — as it was":
        "Клик — по возрастанию, ещё — по убыванию, ещё — как было",
}

RU["Glossary"] = {
    "Glossary": "Глоссарий",
    "Terms": "Термины",
    "Candidates": "Кандидаты",
    "Original": "Оригинал",
    "Translation": "Перевод",
    "Note": "Примечание",
    "Confidence": "Уверенность",
    "Pairs": "Пар",
    "Search:": "Поиск:",
    "original": "оригинал",
    "translation": "перевод",
    "Add": "Добавить",
    "Delete selected": "Удалить выбранные",
    "Find terms": "Найти термины",
    "Stop": "Остановить",
    "Accept": "Принять",
    "Reject": "Отклонить",
    "A rejected term is not offered again on the next run":
        "Отклонённый термин не предлагается снова при следующем прогоне",
    "proper nouns only": "только имена собственные",
    "Offer only words written with a capital in the middle of a phrase — that "
    "is what tells a name apart from an ordinary word. Without it the list "
    "fills with correct but useless pairs like «Now → теперь».":
        "Предлагать только слова, написанные с заглавной посреди фразы, — это "
        "и отличает имя от обычного слова. Без него список наполняется верными, "
        "но бесполезными парами вроде «Now → теперь».",
    "Double click to edit. Accepted terms are highlighted in the original; "
    "hovering one shows its translation.":
        "Двойной клик — правка. Принятые термины подсвечиваются в оригинале, "
        "при наведении виден их перевод.",
    "Candidates are counted over the translation memory: the project's own "
    "plus every attached database. Statistics only suggests — nothing reaches "
    "the original until you accept it.":
        "Кандидаты считаются по памяти переводов: собственной памяти проекта и "
        "всем подключённым базам. Статистика только предлагает — в оригинал "
        "ничего не попадёт, пока вы не подтвердите.",
    "terms: %1 · waiting to be reviewed: %2":
        "терминов: %1 · ждут разбора: %2",
    "candidates: %1 · accepted: %2 · rejected: %3":
        "кандидатов: %1 · принято: %2 · отклонено: %3",
    "found: %1 · new: %2": "найдено: %1 · новых: %2",
    "counting failed: %1": "счёт не удался: %1",
    "Terms are still being counted. Interrupt and close the window?\n\n"
    "Candidates found so far will not be saved.":
        "Термины ещё считаются. Прервать и закрыть окно?\n\n"
        "Найденные к этому моменту кандидаты сохранены не будут.",
}

RU["Statuses"] = {
    "Not translated": "Не переведено",
    "Machine (unchecked)": "Машинный (не проверен)",
    "Auto (from memory)": "Авто (из памяти)",
    "Translated": "Переведено",
    "Reviewed": "Проверено",
    "Outdated": "Устарело",
    "Ignored": "Игнорировано",
    "Custom": "Кастомный",
}
