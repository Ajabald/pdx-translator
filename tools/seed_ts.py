"""Разложить пары «оригинал → перевод» по контекстам `.ts`.

    .venv\\Scripts\\python.exe tools\\i18n.py update       # сперва вытащить строки
    .venv\\Scripts\\python.exe tools\\seed_ts.py           # затем заполнить русский
    .venv\\Scripts\\python.exe tools\\seed_ts.py zh_CN     # и китайский
    .venv\\Scripts\\python.exe tools\\i18n.py release      # и собрать .qm

Сверка идёт в обе стороны, и обе важны:

* **перевод без оригинала** — почти всегда опечатка в английской строке: её
  правили в коде, а здесь забыли. Молча пропустить значит потерять перевод;
* **оригинал без перевода** — просто ещё не дошли руки, это нормально, но
  число таких строк печатается, чтобы видеть остаток.

Китайский собран машинно, и пометка `unfinished` снимается только с **вычитанных
контекстов** — их перечисляет `zh_translations.CHECKED`. Пометка хранит число
записей на момент проверки: добавили строку — число разошлось, и контекст снова
ждёт взгляда. Лучше спросить лишний раз, чем выдать машинную строку за
проверенную. На сборку `.qm` пометка не влияет — `lrelease` пропускает только
пустые переводы, — зато в Qt Linguist сразу видно, что проверено, а что нет.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TS_DIR = ROOT / "src" / "pdxloc" / "gui" / "translations"

sys.path.insert(0, str(Path(__file__).resolve().parent))

# язык -> (модуль с парами, имя словаря, имя таблицы вычитанных контекстов)
#
# Третий элемент и есть пометка «проверено человеком». Пусто (`None`) — язык
# написан руками целиком, помечать нечего. Иначе `unfinished` снимается только
# с вычитанных контекстов: перевод, собранный машинно, не должен выдавать себя
# за проверенный, а Qt Linguist показывает эту пометку переводчику первым делом.
SOURCES: dict[str, tuple[str, str, str | None]] = {
    "ru": ("ru_translations", "RU", None),
    "zh_CN": ("zh_translations", "ZH", "CHECKED"),
}


def load(code: str) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
    module_name, table_name, checked_name = SOURCES[code]
    module = __import__(module_name)
    pairs = getattr(module, table_name)
    if checked_name is None:
        # весь язык считается вычитанным: столько записей, сколько есть
        return pairs, {ctx: len(table) for ctx, table in pairs.items()}
    return pairs, dict(getattr(module, checked_name, {}))


def main() -> int:
    # Консоль Windows отдаёт cp1251, и первая же строка со стрелкой роняла
    # отчёт целиком: сверка проходила, а увидеть её результат было нельзя.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    code = sys.argv[1] if len(sys.argv) > 1 else "ru"
    if code not in SOURCES:
        print(f"неизвестный язык {code}; есть: {', '.join(SOURCES)}")
        return 2

    ts = TS_DIR / f"pdxloc_{code}.ts"
    if not ts.is_file():
        print(f"нет файла {ts}; сперва: tools/i18n.py update")
        return 1

    pairs, checked = load(code)
    tree = ET.parse(ts)
    root = tree.getroot()

    filled = already = 0
    missing_translation: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    unchecked_contexts: list[str] = []

    for context in root.findall("context"):
        name = context.findtext("name") or ""
        table = pairs.get(name, {})
        # Пометка о вычитке хранит число записей на момент проверки. Добавили
        # строку — число разошлось, и контекст снова ждёт взгляда: лучше
        # спросить лишний раз, чем выдать машинную строку за проверенную.
        context_checked = table and checked.get(name) == len(table)
        if table and not context_checked:
            unchecked_contexts.append(name)
        for message in context.findall("message"):
            source = message.findtext("source") or ""
            seen.add((name, source))
            node = message.find("translation")
            if node is None:
                node = ET.SubElement(message, "translation")
            text = table.get(source)
            if text is None:
                if not (node.text or "").strip():
                    missing_translation.append((name, source))
                continue
            want_type = None if context_checked else "unfinished"
            # сравнение без strip(): у части строк краевой пробел значащий
            # (« · ignored: %1»), и со strip() они «заполнялись» каждый прогон
            if (node.text or "") == text and node.get("type") == want_type:
                already += 1
                continue
            node.text = text
            node.attrib.pop("type", None)
            if want_type:
                node.set("type", want_type)
            filled += 1

    orphans = [(ctx, src) for ctx, table in pairs.items()
               for src in table if (ctx, src) not in seen]

    tree.write(ts, encoding="utf-8", xml_declaration=True)
    print(f"{ts.name}: заполнено {filled}, уже было {already}, "
          f"без перевода {len(missing_translation)}")
    for ctx, src in missing_translation[:15]:
        print(f"  нет перевода  [{ctx}] {src[:70]}")
    if len(missing_translation) > 15:
        print(f"  … и ещё {len(missing_translation) - 15}")

    if unchecked_contexts:
        total = sum(len(pairs.get(c, {})) for c in unchecked_contexts)
        print(f"ждут вычитки: {total} строк в контекстах "
              f"{', '.join(sorted(unchecked_contexts))}")

    if orphans:
        print(f"\nПЕРЕВОД БЕЗ ОРИГИНАЛА — {len(orphans)}; "
              f"строку правили в коде, а здесь нет:")
        for ctx, src in orphans:
            print(f"  [{ctx}] {src[:70]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
