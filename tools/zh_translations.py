"""The Chinese translation of the interface: pairs «English original → 简体中文».

The file was **assembled by machine** and then proofread whole (2026-08-11). The
proofreading was not a translation anew: what was mended were the places where
the translation changed the meaning or collided with a neighbour —
«Machine-translate the row» without "machine", the Latin glyphs `C`/`I` in the
button columns, «Actualize» and «Validate» by the one word 确认, «Duplicate» and
«Copy» by the one word 复制. What the proofreading does **not** give: a check of
the terminology against what these things are called in the Chinese communities
of Paradox mods — that is for a native speaker.

`CHECKED` below lists the proofread contexts and the number of records in each at
the moment of the check. The number is a watchman: add a string, the count
diverges, and `tools/seed_ts.py` returns the `unfinished` mark to the whole
context. Better to ask once too often than to pass a machine string off as
checked. The run prints how many strings are waiting for an eye.

The originals are taken from `pdxloc_zh_CN.ts` as they are, not one of them typed
by hand: a typo in an English string would lose a translation silently. When
editing a string in the code, mend it here as well — `tools/seed_ts.py` complains
about a translation for which no original was found.

The top-level key is the translation context (the same `<context><name>` as in
the `.ts`).
"""
from __future__ import annotations

ZH: dict[str, dict[str, str]] = {}

# context -> how many records it held when it was proofread
#
# `Glossary` is **deliberately absent** here: the window is entirely new, and a
# proofreading mark on it would be untrue. Let the context stay `unfinished` —
# that is exactly the state it is in. The number for `DetailPane` (30→32) is
# raised: a couple of strings were added there, and they were read next to their
# neighbours, exactly as the mark demands.
#
# Six more contexts left the table in 0.1.2 — `Actions`, `Exporter`, `MainWindow`,
# `Relocate`, `RootDialog`, `StartScreen`. The translation folder stopped being
# obligatory, and each of them got new strings about it. The Chinese for those is
# written to match the words already used in the window, but no native speaker has
# read it, and raising the count would say otherwise.
CHECKED: dict[str, int] = {
    "Archive": 11,
    "Ask": 1,
    "Concordance": 9,
    "Db": 11,
    "DetailPane": 32,
    "Editor": 17,
    "Export": 34,
    "FileTree": 1,
    "Import": 16,
    "Languages": 16,
    "LanguagesDialog": 11,
    "LocImport": 9,
    "Mt": 12,
    "MtDialog": 27,
    "MtRun": 8,
    "ParadoxYaml": 3,
    "Prefs": 54,
    "Project": 6,
    "QaPanel": 17,
    # QaRules was proofread at 68 strings; a rule about the colour codes §…§! and
    # the preset «HOI4 · Русский» were added to it — five strings a human has not
    # seen. The mark is taken off whole: bringing it back is for whoever rereads
    # the context, not for whoever added the strings.
    # RulesWindow was proofread at 114 strings; in 0.1.2 the long-list field and
    # the explanation about the language layer were added to it. The mark is taken
    # off whole: bringing it back is for whoever rereads the context, not for
    # whoever added the strings.
    "ScanDialog": 30,
    "ScanStats": 14,
    "Scanner": 2,
    "Stats": 4,
    "StatusChips": 2,
    "Statuses": 8,
    "TextDiff": 4,
    "Theme": 2,
    "TmBuild": 40,
    "TmEntries": 23,
    "TmImport": 16,
    "TmSources": 18,
    "TmWindow": 6,
    "Toolbar": 6,
    "UnitsTable": 24,
    "Welcome": 17,
}


ZH["Actions"] = {
    "Projects…":
        "项目…",
    "Back to the project list":
        "返回项目列表",
    "Open project…":
        "打开项目…",
    "Save project as…":
        "项目另存为…",
    "Load translation from mod…":
        "从模组载入译文…",
    "Take translations from ready localization files — someone else's translation of this mod, or your own edits made directly in the files":
        "从现成的本地化文件中获取译文——他人对本模组的翻译，或你直接在文件中所做的修改",
    "Write translation to mod…":
        "将译文写入模组…",
    "Preferences…":
        "首选项…",
    "Quit":
        "退出",
    "Copy cell":
        "复制单元格",
    "Paste into translation":
        "粘贴到译文",
    "Copy key":
        "复制键",
    "Reset translation":
        "重置译文",
    "Save row translation":
        "保存本行译文",
    "Edits are saved anyway when you leave the row — this is just in case":
        "离开该行时修改本就会保存——这只是以防万一",
    "Undo last operation":
        "撤销上一次操作",
    "Rolls back the last batch of edits. In the translation field Ctrl+Z still undoes typing":
        "回滚最后一批修改。在译文输入框中 Ctrl+Z 仍然撤销输入",
    "Translation = Original":
        "译文 = 原文",
    "For names, numbers and anything untranslatable":
        "用于人名、数字以及一切无需翻译的内容",
    "Fill from translation memory":
        "从翻译记忆库填充",
    "Machine-translate the row":
        "机器翻译该行",
    "Sends the original to the service set up in «File → Preferences». The result is marked «Machine (unchecked)»":
        "把原文发送给在「文件 → 首选项」中配置的服务。结果会标记为「机器翻译（未校对）」",
    "Machine translation…":
        "机器翻译…",
    "Translate many rows at once through the service set up in «File → Preferences»":
        "通过在「文件 → 首选项」中配置的服务一次翻译多行",
    "Apply to all rows with the same original":
        "应用到原文相同的所有行",
    "Validate":
        "确认",
    "Mark the row as reviewed":
        "将该行标记为已校对",
    "Unvalidate":
        "取消确认",
    "Back to the «Translated» status":
        "退回「已翻译」状态",
    "Custom status":
        "自定义状态",
    "Ignore":
        "忽略",
    "Nothing to translate — a row of bare tags, say":
        "没有可翻译的内容——例如只有标签的行",
    "Next untranslated":
        "下一条未翻译",
    "Previous row":
        "上一行",
    "Next row":
        "下一行",
    "Save and go to next":
        "保存并转到下一行",
    "Find row…":
        "查找行…",
    "Puts the cursor in the search box":
        "将光标置于搜索框",
    "Only with issues":
        "仅有问题的行",
    "Show only rows the check has questions about":
        "只显示检查有疑问的行",
    "Show deleted":
        "显示已删除",
    "Rows whose keys are gone from the original":
        "键已从原文中消失的行",
    "Reset filters":
        "重置筛选",
    "Drops the status, file and search filters. The sort order stays":
        "清除状态、文件和搜索筛选。排序保持不变",
    "Toolbar":
        "工具栏",
    "File tree":
        "文件树",
    "Languages and databases in the header":
        "顶栏中的语言与数据库",
    "Scan":
        "扫描",
    "Re-read the original files and find changes":
        "重新读取原文文件并查找变化",
    "Actualize cosmetic edits…":
        "确认表面修改…",
    "Confirm translations of rows where the mod author only changed formatting":
        "确认模组作者仅改动了格式的那些行的译文",
    "Archive of old translations…":
        "旧译文存档…",
    "Change original folder…":
        "更改原文文件夹…",
    "If the mod was re-downloaded elsewhere, or the project came from another person":
        "如果模组重新下载到了别处，或项目来自他人",
    "Change translation folder…":
        "更改译文文件夹…",
    "Where the translation is read from and written to; may be empty until the first write":
        "译文从哪里读取、写入到哪里；首次写入之前可以为空",
    "Project languages…":
        "项目语言…",
    "Game folders (l_english) and the language the text is actually written in":
        "游戏文件夹（l_english）以及文本实际使用的语言",
    "Show original in Explorer":
        "在资源管理器中显示原文",
    "Check the whole project…":
        "检查整个项目…",
    "Configure checks…":
        "配置检查…",
    "Which rules are on, with what leniency, and how often they fire on this project":
        "哪些规则已启用、宽松程度如何，以及它们在本项目中触发的频率",
    "Marked «not an error»…":
        "标记为「不是错误」…",
    "Silenced issues — they can be put back into the check":
        "已屏蔽的问题——可以重新纳入检查",
    "Translation memory…":
        "翻译记忆库…",
    "Memory entries, attached databases and building new ones — in a single window":
        "记忆库条目、已挂载的数据库以及新建数据库——都在同一个窗口中",
    "Glossary…":
        "术语表…",
    "Terms and candidates for them: statistics suggests, you accept":
        "术语及其候选：统计给出建议，由你确认",
    "How was this translated before…":
        "以前是怎么翻译的…",
    "Search the memory for the selected piece of the original":
        "在记忆库中搜索选中的原文片段",
    "Open databases folder":
        "打开数据库文件夹",
    "Keyboard shortcuts":
        "快捷键",
    "About":
        "关于",
}

ZH["Archive"] = {
    "File":
        "文件",
    "Key":
        "键",
    "Translation":
        "译文",
    "Archived on":
        "存档时间",
    "Archive of old translations":
        "旧译文存档",
    "Translations of keys that are gone from the mod original: deleted rows and typos in keys.\nThey do not reach the write-to-mod step but are kept here.":
        "已从模组原文中消失的键的译文：被删除的行以及键中的笔误。\n它们不会写入模组，但保存在这里。",
    "Search:":
        "搜索：",
    "by key, file or translation text…":
        "按键、文件或译文内容…",
    "Copy the translation":
        "复制译文",
    "Copy everything (key + translation)":
        "复制全部（键 + 译文）",
    "entries: %1":
        "条目：%1",
}

ZH["Ask"] = {
    "Do not ask again":
        "不再询问",
}

ZH["Concordance"] = {
    "How was this translated before":
        "以前是怎么翻译的",
    "Fragment:":
        "片段：",
    "a word or a piece of a phrase from the original…":
        "原文中的一个词或一段短语…",
    "Original":
        "原文",
    "Translation":
        "译文",
    "Source":
        "来源",
    "Nothing found":
        "未找到",
    "Found: %1 · double click copies the translation":
        "找到：%1 · 双击复制译文",
    "Translation copied to the clipboard":
        "译文已复制到剪贴板",
}

ZH["Db"] = {
    "The database has schema version %1, the application expects %2. Please update the application.":
        "数据库结构版本为 %1，而应用程序需要 %2。请更新应用程序。",
    "Could not upgrade the database schema from version %1 to %2.":
        "无法将数据库结构从版本 %1 升级到 %2。",
    "Migration v1→v2: foreign keys violated: %1":
        "迁移 v1→v2：外键校验失败：%1",
    "Migration v2→v3: row count mismatch (was %1, became %2, orphaned %3)":
        "迁移 v2→v3：行数不一致（原为 %1，现为 %2，孤立 %3）",
    "Migration v2→v3: translation memory mismatch (unique before %1, after %2)":
        "迁移 v2→v3：翻译记忆库不一致（此前唯一条目 %1，此后 %2）",
    "Migration v2→v3: orphaned translations were not archived":
        "迁移 v2→v3：孤立的译文未被存档",
    "Migration v2→v3: foreign keys violated: %1":
        "迁移 v2→v3：外键校验失败：%1",
    "Migration v3→v4: mismatch (rows before %1, after %2; translations before %3, after %4)":
        "迁移 v3→v4：数据不一致（行此前 %1，此后 %2；译文此前 %3，此后 %4）",
    "Migration v3→v4: foreign keys violated: %1":
        "迁移 v3→v4：外键校验失败：%1",
    "Migration v5→v6: row count mismatch (was %1, became %2)":
        "迁移 v5→v6：行数不一致（原为 %1，现为 %2）",
    "Migration v5→v6: foreign keys violated: %1":
        "迁移 v5→v6：外键校验失败：%1",
}

ZH["DetailPane"] = {
    "my translations":
        "我的译文",
    "import":
        "导入",
    "game database":
        "游戏数据库",
    "project export":
        "项目导出",
    "Entry original (%1 similarity):":
        "条目原文（相似度 %1）：",
    "Source: %1":
        "来源：%1",
    "Read only (attached database)":
        "只读（已挂载的数据库）",
    "Open translation memory…":
        "打开翻译记忆库…",
    "Insert into translation":
        "插入到译文",
    "Copy text":
        "复制文本",
    "Edit the memory entry…":
        "编辑记忆库条目…",
    "Delete from memory":
        "从记忆库中删除",
    "An entry from an attached database — read only":
        "来自已挂载数据库的条目——只读",
    "Edit memory entry":
        "编辑记忆库条目",
    "Translation in memory (suggestions for identical rows):":
        "记忆库中的译文（针对相同行的建议）：",
    "Remove this variant from the translation memory?\n\n%1\n\nThe translation of the current row stays in place.":
        "从翻译记忆库中删除该变体？\n\n%1\n\n当前行的译文保持不变。",
    "Original (EN):":
        "原文（EN）：",
    "highlight changes":
        "高亮变化",
    "Highlight in the original what was not in the previous revision":
        "在原文中高亮上一版本没有的内容",
    "highlight terms":
        "高亮术语",
    "Highlight glossary terms in the original; hover shows the accepted translation":
        "在原文中高亮术语表中的术语；悬停可查看已确认的译法",
    "Change of the original (was → became):":
        "原文的变化（原为 → 现为）：",
    "Actualize":
        "确认仍适用",
    "Confirm that the translation matches the new original":
        "确认译文与新原文相符",
    "Translation (RU):":
        "译文（RU）：",
    "Translation memory (double click — insert, right button — actions):":
        "翻译记忆库（双击——插入，右键——操作）：",
    "unsaved edits (Ctrl+S)":
        "有未保存的修改（Ctrl+S）",
    "saved":
        "已保存",
    "(no original — the key exists only in RU)":
        "（无原文——该键只存在于译文中）",
    " (cosmetic edit)":
        "（表面修改）",
    "The original changed%1 — was → became:":
        "原文已变化%1——原为 → 现为：",
    "Project":
        "项目",
}

ZH["Editor"] = {
    "Status:":
        "状态：",
    "All":
        "全部",
    "Search: key / EN / RU…  (Ctrl+F)":
        "搜索：键 / EN / RU…  (Ctrl+F)",
    "with issues":
        "有问题",
    "Show only rows the check has questions about":
        "只显示检查有疑问的行",
    "deleted":
        "已删除",
    "Rows selected: %1":
        "已选行数：%1",
    "Apply to all":
        "应用到全部",
    "There are no untranslated rows with the same EN text.":
        "没有原文相同且未翻译的行。",
    "Apply this translation to %1 rows with the same English text?":
        "将该译文应用到英文原文相同的 %1 行？",
    "Changed %1 of %2 (a status is not set without a translation)":
        "已修改 %1 / %2（没有译文则不设置状态）",
    "Reset translation":
        "重置译文",
    "Reset the translation of %1 rows?":
        "重置 %1 行的译文？",
    "No translation service is set up — «File → Preferences → Machine translation»":
        "尚未配置翻译服务——「文件 → 首选项 → 机器翻译」",
    "Translating…":
        "正在翻译…",
    "The translation lost a placeholder — check the row":
        "译文丢失了占位符——请检查该行",
    "Translated by the service — Ctrl+Z undoes it":
        "已由服务翻译——按 Ctrl+Z 可撤销",
}

ZH["Export"] = {
    "Writing the translation to mod files":
        "将译文写入模组文件",
    " · ignored: %1":
        " · 已忽略：%1",
    "Rows in total: %1, going to the mod: %2, without a translation: %3%4":
        "总行数：%1，写入模组：%2，无译文：%3%4",
    "Translated only (%1 rows)":
        "仅已翻译（%1 行）",
    "All rows — untranslated ones stay in English (%1 rows)":
        "全部行——未翻译的保留英文（%1 行）",
    "Include outdated translations (EN changed)":
        "包含已过时的译文（原文已变化）",
    "Include machine translations (nobody has checked them)":
        "包含机器翻译（尚无人校对）",
    "Include machine translations, %1 rows (nobody has checked them)":
        "包含机器翻译，共 %1 行（尚无人校对）",
    "Machine translation has been read by no one. In the game it can be wrong in meaning, break tooltips or lose icons.":
        "机器翻译无人阅读过。在游戏中它可能含义有误、破坏悬停提示或丢失图标。",
    "Back up the files being overwritten":
        "备份将被覆盖的文件",
    "Previous versions go into the backups folder — outside the localization tree, otherwise the game would read the copies as if they were real files":
        "旧版本会放入备份文件夹——位于本地化目录树之外，否则游戏会把副本当作正式文件读取",
    "Mod folder:":
        "模组文件夹：",
    "Browse…":
        "浏览…",
    "Choose a folder — the mod folder in Documents, say":
        "选择文件夹——例如「文档」中的模组文件夹",
    "Last write: %1":
        "上次写入：%1",
    "Write":
        "写入",
    "Mod folder":
        "模组文件夹",
    "Files are written for the game, for example:\n%1":
        "为游戏写入文件，例如：\n%1",
    "Files of the language «%1» are written for the game":
        "为游戏写入「%1」语言的文件",
    "This is the folder the translation was imported from: its files will be overwritten with the project content.":
        "译文正是从该文件夹导入的：其中的文件将被项目内容覆盖。",
    "Writing the translation":
        "正在写入译文",
    "Enter the mod folder.":
        "请填写模组文件夹。",
    "Previous versions will be kept in the backups folder.":
        "旧版本将保存在备份文件夹中。",
    "Backup is off — there will be nothing to restore the previous versions from.":
        "备份已关闭——将无法恢复旧版本。",
    "The folder already holds %1 translation files — they will be overwritten with the project content.\n\nThe project is the source of truth: rows it does not have will disappear from the files.\n%2\n\nContinue?":
        "该文件夹中已有 %1 个译文文件——它们将被项目内容覆盖。\n\n项目是唯一依据：项目中没有的行将从文件中消失。\n%2\n\n继续？",
    "Write error:\n%1":
        "写入错误：\n%1",
    "Files written: %1":
        "已写入文件：%1",
    "Files unchanged: %1":
        "未改动的文件：%1",
    "Rows written: %1":
        "已写入行数：%1",
    "Skipped (no translation): %1":
        "已跳过（无译文）：%1",
    "Left in English: %1":
        "保留英文：%1",
    "Previous versions: %1":
        "旧版本：%1",
    "rows":
        "行",
    " (skipped %1)":
        "（已跳过 %1）",
}

ZH["Exporter"] = {
    "Project id=%1 not found":
        "未找到 id=%1 的项目",
    "The project has no translation folder: choose where to write.":
        "项目尚未设置译文文件夹：请选择写入位置。",
}

ZH["FileTree"] = {
    "ALL":
        "全部",
}

ZH["Import"] = {
    "Load translation from mod":
        "从模组载入译文",
    "Take translations from a folder with ready localization files — someone else's translation of this mod, say, or your own edits made directly in the files.":
        "从含有现成本地化文件的文件夹获取译文——例如他人对本模组的翻译，或你直接在文件中所做的修改。",
    "Translation folder:":
        "译文文件夹：",
    "Browse…":
        "浏览…",
    "Overwrite existing translations":
        "覆盖已有译文",
    "Off — only rows that have no translation yet are taken":
        "关闭时——只取尚无译文的行",
    "Do not take rows where the translation equals the original":
        "不取译文与原文相同的行",
    "Take the translations":
        "获取译文",
    "Translation folder":
        "译文文件夹",
    "What will change (first rows):":
        "将会发生的变化（前几行）：",
    "(empty)":
        "（空）",
    "Parser warnings: %1":
        "解析器警告：%1",
    "Loading a translation":
        "正在载入译文",
    "Take %1 rows from the chosen folder?\n\nThe operation is recorded as a single batch — it can be undone as a whole via «Edit → Undo last operation» (Ctrl+Z).":
        "从所选文件夹获取 %1 行？\n\n该操作记为一个批次——可通过「编辑 → 撤销上一次操作」(Ctrl+Z) 整体撤销。",
    "Nothing was taken — the write failed:\n%1":
        "未导入任何内容——写入失败：\n%1",
    "\n\nDone. Undo it all with Ctrl+Z.":
        "\n\n完成。可用 Ctrl+Z 全部撤销。",
}

ZH["Languages"] = {
    "English":
        "英语",
    "French":
        "法语",
    "German":
        "德语",
    "Spanish":
        "西班牙语",
    "Russian":
        "俄语",
    "Simplified Chinese":
        "简体中文",
    "Korean":
        "韩语",
    "Japanese":
        "日语",
    "Brazilian Portuguese":
        "巴西葡萄牙语",
    "Polish":
        "波兰语",
    "Turkish":
        "土耳其语",
    "Chinese":
        "中文",
    "Portuguese":
        "葡萄牙语",
    "Italian":
        "意大利语",
    "Ukrainian":
        "乌克兰语",
    "Czech":
        "捷克语",
}

ZH["LanguagesDialog"] = {
    "Project languages":
        "项目语言",
    "Game:":
        "游戏：",
    "The game is now %1. The project file stays where it lies; moving it to the pen of the new game will be offered the next time the project is opened.":
        "游戏现在是 %1。项目文件仍留在原处；下次打开项目时会提示把它移到新游戏的目录中。",
    "The game folder decides the file names (*_l_english.yml) and the header inside them. The text language says what the text actually is — machine translation, memory database naming and language-specific checks go by it.":
        "游戏文件夹决定文件名（*_l_english.yml）及其内部的标头。文本语言说明文本实际所用的语言——机器翻译、记忆库命名以及与语言相关的检查都以它为准。",
    "Game folders:":
        "游戏文件夹：",
    "The text is in another language":
        "文本使用其他语言",
    "Turn on when translating into a language the game does not know: Portuguese in CK3, say, lives in l_english files":
        "当翻译成游戏不认识的语言时启用：例如 CK3 中的葡萄牙语存放在 l_english 文件中",
    "Text languages:":
        "文本语言：",
    "The folder of the original itself is changed in «Project → Change original folder…».":
        "原文文件夹本身在「项目 → 更改原文文件夹…」中更改。",
    "Apply":
        "应用",
    "Only %1 files out of %2 carry the label _l_%3.\n\nTranslations are not deleted: they stay in the archive and in the translation memory. Change the languages?":
        "%2 个文件中只有 %1 个带有 _l_%3 标记。\n\n译文不会被删除：它们保留在存档和翻译记忆库中。要更改语言吗？",
}

ZH["LocImport"] = {
    "Translation files found: %1":
        "找到译文文件：%1",
    "Rows taken: %1":
        "已获取行数：%1",
    "Already the same: %1":
        "已经相同：%1",
    "Skipped (a translation already exists): %1":
        "已跳过（已有译文）：%1",
    "Skipped (translation equals the original): %1":
        "已跳过（译文与原文相同）：%1",
    "Skipped (the «needs translation» marker): %1":
        "已跳过（带「待翻译」标记）：%1",
    "Keys absent from the project: %1":
        "项目中不存在的键：%1",
    "Translation folder not found: %1":
        "未找到译文文件夹：%1",
    "Project id=%1 not found":
        "未找到 id=%1 的项目",
}

ZH["MainWindow"] = {
    "&File":
        "文件(&F)",
    "&Edit":
        "编辑(&E)",
    "&Translation":
        "翻译(&T)",
    "F&ilters":
        "筛选(&I)",
    "&View":
        "视图(&V)",
    "&Project":
        "项目(&P)",
    "&Check":
        "检查(&C)",
    "T&ools":
        "工具(&O)",
    "&Help":
        "帮助(&H)",
    "Project of another game":
        "属于其他游戏的项目",
    "The project «%1» belongs to %2, but lies in the folder of %3.\n\nMove it to %4?":
        "项目「%1」属于 %2，却放在 %3 的文件夹中。\n\n要把它移到 %4 吗？",
    "no game in particular":
        "不属于任何游戏",
    "Could not move the file:\n%1":
        "无法移动文件：\n%1",
    "Choose or create a project":
        "选择或创建项目",
    "Translation memory":
        "翻译记忆库",
    "There is not a single translation memory database.\n\nA database built from your copy of the game fills in strings the mod copied from it — often hundreds of them.\n\nBuild one now?":
        "目前没有任何翻译记忆库数据库。\n\n用你自己的游戏副本构建的数据库可以填充模组从游戏中复制的字符串——往往有数百条。\n\n现在就构建吗？",
    "All":
        "全部",
    "No sorting":
        "不排序",
    "Descending":
        "降序",
    "Show":
        "显示",
    "Sort":
        "排序",
    "Theme":
        "主题",
    "Rule preset":
        "规则预设",
    "Columns":
        "列",
    "Status buttons":
        "状态按钮",
    "Hides the toolbar button only — the command stays in the menu and its shortcut keeps working":
        "只隐藏工具栏按钮——命令仍留在菜单中，快捷键照常可用",
    "Check preset: %1":
        "检查预设：%1",
    "F2, double click":
        "F2、双击",
    "Edit the translation in the cell":
        "直接在单元格中编辑译文",
    "Keyboard shortcuts":
        "快捷键",
    "\n\nTranslations that will be lost: %1 of %2 rows.":
        "\n\n将丢失的译文：%2 行中的 %1 行。",
    "The file goes to the recycle bin":
        "文件将移入回收站",
    "The file will be deleted":
        "文件将被删除",
    "Delete project":
        "删除项目",
    "Delete the project «%1» together with its file?\n\n%2%3\n\n%4. Mod files and translation memory databases are untouched.":
        "连同文件一起删除项目「%1」？\n\n%2%3\n\n%4。模组文件和翻译记忆库数据库不受影响。",
    "Delete":
        "删除",
    "Cancel":
        "取消",
    "The recycle bin did not accept the file, so it was deleted permanently:\n%1\n\nUsually this means the file is larger than the bin allows.":
        "回收站未接收该文件，因此已被永久删除：\n%1\n\n通常这说明文件超出了回收站允许的大小。",
    "Delete the backups next to it as well":
        "同时删除旁边的备份",
    "Could not delete the file:\n%1\n\n%2\n\nMost likely it is open in another program.":
        "无法删除文件：\n%1\n\n%2\n\n很可能它正被其他程序打开。",
    "Project deleted: %1 (%2 files)":
        "已删除项目：%1（%2 个文件）",
    "Project":
        "项目",
    "Project file not found:\n%1":
        "未找到项目文件：\n%1",
    "Could not open the project:\n%1":
        "无法打开项目：\n%1",
    "%1 rows with no translatable text were marked as ignored (bare tags such as [GetName], empty values) — Ctrl+Z undoes it":
        "%1 行没有可翻译文本，已标记为忽略（例如仅有 [GetName] 之类标签、空值）——按 Ctrl+Z 可撤销",
    "auto-ignore of rows with nothing to translate":
        "自动忽略无可翻译内容的行",
    "Open project":
        "打开项目",
    "Translation project (*%1);;All files (*)":
        "翻译项目 (*%1);;所有文件 (*)",
    "Save project as":
        "项目另存为",
    "Translation project (*%1)":
        "翻译项目 (*%1)",
    "Saving":
        "正在保存",
    "Could not save:\n%1":
        "无法保存：\n%1",
    "Project saved:\n%1\n\nOpening the copy.":
        "项目已保存：\n%1\n\n正在打开该副本。",
    "Scan interrupted — changes were not saved":
        "扫描已中断——更改未保存",
    "Scanning":
        "正在扫描",
    "Error:\n%1":
        "错误：\n%1",
    "Rows selected: %1":
        "已选行数：%1",
    "Cosmetic edits":
        "表面修改",
    "There are no outdated rows with cosmetic edits.\n\nThose are changes of punctuation, case and spaces — when the meaning of the original did not change.":
        "没有仅含表面修改的过时行。\n\n表面修改指标点、大小写和空格的变动——即原文含义没有改变。",
    "Confirm translations of %1 rows where the original was edited cosmetically only?\n\nThe translations themselves do not change — the «Outdated» mark is removed. The operation can be undone (Ctrl+Z).":
        "确认原文仅有表面修改的 %1 行的译文？\n\n译文本身不会改变——只是移除「已过时」标记。该操作可以撤销（Ctrl+Z）。",
    "Rows actualized: %1":
        "已确认行数：%1",
    "Change of the original folder":
        "更改原文文件夹",
    "The folder has changed. Scan the project now?\n\nScanning re-reads the files: translations are kept, changed rows become «Outdated».":
        "文件夹已更改。现在扫描项目吗？\n\n扫描会重新读取文件：译文将保留，发生变化的行会变为「已过时」。",
    "Change of the translation folder":
        "更改译文文件夹",
    "The folder has changed. Scan the project now?\n\nScanning re-reads the files: the translation stays in the project, and what the new folder holds is picked up.":
        "文件夹已更改。现在扫描项目吗？\n\n扫描会重新读取文件：项目中的译文将保留，新文件夹中的内容会被读入。",
    "Project languages":
        "项目语言",
    "The language of the folders changed. Scan the project now?\n\nScanning re-reads the files under the new names.":
        "文件夹的语言已更改。现在扫描项目吗？\n\n扫描会按新的文件名重新读取文件。",
    "Undo":
        "撤销",
    "Nothing to undo.":
        "没有可撤销的操作。",
    "actualization":
        "确认表面修改",
    "status change":
        "状态更改",
    "translation edit":
        "译文修改",
    "bulk replace":
        "批量替换",
    "glossary rules":
        "术语表规则",
    "fill from memory":
        "从记忆库填充",
    "translation import":
        "译文导入",
    "machine translation":
        "机器翻译",
    "Undo operation":
        "撤销操作",
    "Undo the last operation (%1) and return %2 rows to their previous state?":
        "撤销上一次操作（%1）并将 %2 行恢复到先前状态？",
    "Rows reverted: %1":
        "已恢复行数：%1",
    "(no project open)":
        "（未打开项目）",
    "A translator's workbench for the localisation of Paradox game mods.<br>Format: Paradox pseudo-YAML (UTF-8 with BOM) and the older CSV.<br><br>":
        "用于 Paradox 游戏模组本地化的译者工作台。<br>格式：Paradox 伪 YAML（带 BOM 的 UTF-8）以及旧版 CSV。<br><br>",
    "This program comes with ABSOLUTELY NO WARRANTY. It is free software, and you are welcome to redistribute it under the terms of the GNU General Public License, version 3 or later — see the LICENSE file.<br><br>Uses Qt through PySide6 under the GNU LGPL v3.<br><br>":
        "本程序不提供任何担保。这是自由软件，欢迎你依照 GNU 通用公共许可证第 3 版或更新版本的条款重新分发它——参见 LICENSE 文件。<br><br>通过 PySide6 使用 Qt，依照 GNU LGPL v3 授权。<br><br>",
    "Project: %1<br>Memory databases: %2":
        "项目：%1<br>记忆库数据库：%2",
}

ZH["MtDialog"] = {
    "Machine translation":
        "机器翻译",
    "Translate":
        "翻译",
    "Through a web translator":
        "通过网页翻译器",
    "Interrupt":
        "中断",
    "Service: %1":
        "服务：%1",
    "No service is set up — choose one in «File → Preferences → Machine translation»":
        "尚未配置服务——请在「文件 → 首选项 → 机器翻译」中选择",
    "Which rows to translate:":
        "翻译哪些行：",
    "Selected rows":
        "选中的行",
    "Not translated":
        "未翻译",
    "Not translated and filled from memory":
        "未翻译以及从记忆库填充的",
    "The whole project":
        "整个项目",
    "Also re-translate outdated rows (their existing translation will be replaced)":
        "同时重新翻译已过时的行（其现有译文将被替换）",
    "Reviewed, custom and ignored rows are never touched, nor are rows with nothing to translate — a bare [GetName] costs money and returns nothing.":
        "已校对、自定义和已忽略的行永远不会被改动，没有可翻译内容的行也一样——只有 [GetName] 的行要花钱却毫无所得。",
    "Rows: %1 · characters: %2 · requests: %3 · roughly %4 minutes":
        "行数：%1 · 字符数：%2 · 请求数：%3 · 大约 %4 分钟",
    "%1 rows are longer than the service takes in one request and will be left untouched":
        "有 %1 行超过了服务单次请求可接受的长度，将保持不变",
    "Send %1 rows (%2 characters) to the service?\n\nThe result is written with the «Machine (unchecked)» status. The whole run is one batch — Ctrl+Z undoes it all.":
        "要把 %1 行（%2 个字符）发送给服务吗？\n\n结果将以「机器翻译（未校对）」状态写入。整次运行是一个批次——按 Ctrl+Z 可全部撤销。",
    "Translated %1 of %2":
        "已翻译 %1 / %2",
    "Interrupting…":
        "正在中断…",
    "Rows worth looking at:":
        "值得检查的行：",
    "… and %1 more":
        "……还有 %1 行",
    "Rows are taken by the same rules as on the «Translate» tab, and the result is written the same way — the only difference is that you carry the text to a translator yourself.":
        "取行规则与「翻译」选项卡相同，结果的写入方式也一样——区别只在于由你自己把文本带到翻译器中。",
    "Copy this into a web translator of your choice:":
        "把下面的内容复制到你选用的网页翻译器：",
    "Copy":
        "复制",
    "Paste the result here:":
        "把结果粘贴到这里：",
    "Take the result and go to the next batch":
        "采用结果并进入下一批",
    "Nothing left to translate.":
        "已没有需要翻译的内容。",
    "Batch %1 of %2 · %3 rows":
        "第 %1 / %2 批 · %3 行",
}

ZH["Mt"] = {
    "Off":
        "关闭",
    "The provider returned %1 rows instead of %2":
        "服务返回了 %1 行，而不是 %2 行",
    "Could not reach %1: %2":
        "无法连接到 %1：%2",
    "%1 refused: the request limit or the quota is exhausted.":
        "%1 拒绝了请求：请求次数或用量配额已用尽。",
    "%1 rejected the key. Check it in «File → Preferences → Machine translation».":
        "%1 不接受该密钥。请在「文件 → 首选项 → 机器翻译」中检查。",
    "%1 answered with an error (code %2).":
        "%1 返回了错误（代码 %2）。",
    "%1 returned an answer that could not be read.":
        "%1 返回的内容无法解析。",
    "%1 declined to translate this batch.":
        "%1 拒绝翻译这一批内容。",
    "%1 also needs a folder id — fill it in «File → Preferences → Machine translation».":
        "%1 还需要目录 ID——请在「文件 → 首选项 → 机器翻译」中填写。",
    "The answer has %1 separators instead of %2, or their order changed. Nothing from this batch was applied.":
        "回复中有 %1 个分隔符而不是 %2 个，或者顺序发生了变化。这一批内容一条也未应用。",
    "Manual — through a web translator":
        "手动——通过网页翻译器",
    "The manual mode is driven from its own tab, not from here.":
        "手动模式在它自己的选项卡中操作，而不是这里。",
}

ZH["MtRun"] = {
    "Rows translated: %1":
        "已翻译行数：%1",
    "Characters sent: %1":
        "已发送字符数：%1",
    "Requests made: %1":
        "已发出请求数：%1",
    "Rows where the translation lost a placeholder: %1 — they are written, but need fixing":
        "译文丢失占位符的行：%1 —— 这些行已写入，但需要修正",
    "Rows not translated: %1":
        "未翻译的行：%1",
    "Interrupted. What had been translated by then is kept — Ctrl+Z undoes the whole run.":
        "已中断。此前翻译的内容已保留——按 Ctrl+Z 可撤销整次运行。",
    "The row is longer than the service accepts in one request. It was left untouched.":
        "该行超过了服务单次请求可接受的长度，因此未做处理。",
    "The service returned nothing for this row.":
        "服务没有为该行返回任何内容。",
}

ZH["ParadoxYaml"] = {
    "%1:%2: an l_*: header was expected, found: %3":
        "%1:%2：应为 l_*: 标头，实际为：%3",
    "%1:%2: no closing quote for the key %3 — the text was taken to the end of the line":
        "%1:%2：键 %3 缺少右引号——文本按到行尾处理",
    "%1:%2: unrecognized line: %3":
        "%1:%2：无法识别的行：%3",
}

ZH["ParadoxCsv"] = {
    "%1:%2: a line without a «;» separator: %3":
        "%1:%2：缺少「;」分隔符的行：%3",
}

ZH["Prefs"] = {
    "Browse…":
        "浏览…",
    "Choose a folder":
        "选择文件夹",
    "Preferences":
        "首选项",
    "General":
        "常规",
    "Folders":
        "文件夹",
    "Editor":
        "编辑器",
    "Memory":
        "记忆库",
    "Interface language:":
        "界面语言：",
    "Colour theme:":
        "配色主题：",
    "Open the last project on startup":
        "启动时打开上次的项目",
    "Show hidden reminders again":
        "重新显示已隐藏的提示",
    "The interface language applies immediately. It is not related to the translation languages — those are set in the project itself.":
        "界面语言立即生效。它与翻译所用的语言无关——后者在项目中设置。",
    "Translation memory databases:":
        "翻译记忆库数据库：",
    "Projects:":
        "项目：",
    "Backups:":
        "备份：",
    "Snapshots of files overwritten when writing the translation to the mod.\n0 — do not keep any.":
        "将译文写入模组时被覆盖文件的快照。\n0——一律不保留。",
    "Keep copies per project:":
        "每个项目保留的副本数：",
    "Copies must not be put next to the localization: the game reads every *.yml from that folder and would load a backup file as if it were a real one.":
        "副本不能放在本地化文件旁边：游戏会读取该文件夹中的所有 *.yml，并把备份文件当作正式文件加载。",
    "Font of the original and translation fields:":
        "原文与译文输入框的字体：",
    "Font size:":
        "字号：",
    "Table row height:":
        "表格行高：",
    "Long rows are truncated in the cell — the full text is always visible in the editor pane and in the tooltip":
        "过长的行在单元格中会被截断——完整文本始终可在编辑面板和悬停提示中看到",
    "Truncate cell text after, characters:":
        "单元格文本截断长度（字符）：",
    "Show the table grid":
        "显示表格网格",
    "Highlight changes of the original":
        "高亮原文的变化",
    "Below this similarity, similar rows do not appear in the suggestions":
        "低于该相似度的相似行不会出现在建议中",
    "Suggestion similarity threshold:":
        "建议的相似度阈值：",
    "Suggestions to show:":
        "显示的建议数量：",
    "Exact matches are always shown and come first — the threshold applies to similar rows only.":
        "完全匹配始终显示且排在最前——阈值只对相似行生效。",
    "Machine translation":
        "机器翻译",
    "Service:":
        "服务：",
    "Access key:":
        "访问密钥：",
    "Show":
        "显示",
    "Check":
        "检查",
    "Checking…":
        "正在检查…",
    "The key works.":
        "密钥可用。",
    "Used %1 of %2 characters":
        "已使用 %2 个字符中的 %1 个",
    "The key is protected by Windows for your account. It is unreadable from another account, but a program running as you can read it.":
        "该密钥由 Windows 按你的账户加以保护。其他账户无法读取，但以你的身份运行的程序可以读取。",
    "The key is stored as plain text: this system cannot protect it.":
        "密钥以明文保存：本系统无法对其加以保护。",
    "Pro subscription (a different address, not a tariff)":
        "Pro 订阅（这是另一个地址，而不是资费档位）",
    "Model:":
        "模型：",
    "the service default":
        "服务默认值",
    "Extra instructions:":
        "额外说明：",
    "For example: formal tone, «you» in the plural, keep the names as in the glossary":
        "例如：正式语气、使用敬称、人名沿用术语表中的写法",
    "Folder id:":
        "目录 ID：",
    "Characters per request:":
        "每次请求的字符数：",
    "How many characters go into one request. Rows are never cut in half: one that does not fit is left untranslated":
        "一次请求中包含多少字符。行永远不会被切成两半：放不下的行将保持未翻译",
    "Pause between requests:":
        "请求之间的间隔：",
    "A pause between requests. Without it services start refusing halfway through a long run":
        "请求之间的停顿。没有它，服务会在长时间运行到一半时开始拒绝请求",
    "Retries after a refusal:":
        "被拒后的重试次数：",
    "Request timeout:":
        "请求超时：",
    "Machine translation is written with the «Machine (unchecked)» status. It does not go into the translation memory and is not written to the mod until you allow it in the export window.":
        "机器翻译以「机器翻译（未校对）」状态写入。它不会进入翻译记忆库，在你于写入窗口中允许之前也不会写入模组。",
    "Reminders you switched off with «Do not ask again»":
        "你用「不再询问」关闭的提示",
    "No reminders are hidden right now":
        "目前没有隐藏任何提示",
}

ZH["Project"] = {
    "game database":
        "游戏数据库",
    "project export":
        "项目导出",
    "import":
        "导入",
    "The project file already exists: %1":
        "项目文件已存在：%1",
    "(unnamed)":
        "（未命名）",
    "The file already exists: %1":
        "文件已存在：%1",
}

ZH["QaPanel"] = {
    "Key":
        "键",
    "File":
        "文件",
    "Issue":
        "问题",
    "Severity":
        "严重程度",
    "Error":
        "错误",
    "Warning":
        "警告",
    "Signal":
        "提示",
    "Project check":
        "项目检查",
    "Check":
        "检查",
    "Filter:":
        "筛选：",
    "All issues":
        "全部问题",
    "Not an error":
        "不是错误",
    "Mark the selected issue as false — do not show it again":
        "将选中的问题标记为误报——不再显示",
    "Configure this rule…":
        "配置该规则…",
    "Open the settings of the rule behind the selected issue":
        "打开选中问题所属规则的设置",
    "Close":
        "关闭",
    "issues: %1 (errors: %2)":
        "问题：%1（错误：%2）",
}

ZH["QaRules"] = {
    "Every rule on, nothing forgiven. For the final read-through, when you would rather sift ten false alarms than miss one real fault.":
        "全部规则开启，不留任何宽容。适合定稿前的通读：宁可筛掉十条误报，也不放过一处真问题。",
    "What a CK3 translator does on purpose stops counting as a mistake: a reference wrapped so it can be inflected, an added #L, formatting flags. The helpers your language uses are added on their own.":
        "CK3 译者有意为之的写法不再算作错误：为变格而包裹的引用、补写的 #L、排版标记。你所用语言的助手会自动加入。",
    "HOI4 gives each language its own inflection helpers, and a translation swaps plain references for them. This set knows them, so a swap stops reading as a loss.":
        "HOI4 为每种语言提供各自的变格函数，译文会用它们替换普通引用。本规则集认得这些函数，替换便不再被读作丢失。",
    "CK2 translations inflect nearly everything and add forms of address the English has none of. That is expected here — a reference that went missing is still caught.":
        "CK2 的译文几乎处处变格，还会补上英文中没有的称呼。这些在此视为正常——真正丢失的引用仍会被抓出。",
    "Stellaris inflects names through a grammar system of its own, and many terms are meant to stay as they are in the original. Those stop shouting; anything that breaks the text still does.":
        "Stellaris 用自己的语法系统处理名称变格，许多术语本就应与原文保持一致。它们不再报警；而破坏文本的问题照旧报警。",
    "Only what breaks the text in the game: a lost variable or icon, an unclosed tag, an empty translation. Everything else keeps quiet.":
        "只报会在游戏里破坏文本的问题：丢失的变量或图标、未闭合的标签、空译文。其余一律不作声。",
    "The built-in values with nothing on top. Start here to set every rule by hand.":
        "仅使用内置数值，之上不加任何设置。想逐条手动调整规则，就从这里开始。",
    "A lost variable leaves a hole in the text in the game. A set that merely differs is a softer case, and «only_if_all_lost» keeps quiet about it":
        "变量丢失会在游戏文本里留下一个窟窿。仅仅是集合不同则要轻得多，「only_if_all_lost」对此不作声",
    "@gold! is the CK3 icon; the £gold£ form belongs to EU4, HOI4 and Stellaris. Both are checked, because a translator who has worked on another game types the icon they are used to":
        "@gold! 是 CK3 的图标写法；£gold£ 属于 EU4、HOI4 和 Stellaris。两者都要检查：做过另一款游戏的译者会顺手打出自己习惯的那种",
    "The colour of HOI4, EU4 and Stellaris: §Y…§!. A lost §! paints the rest of the line, and a swapped code can turn a warning green":
        "HOI4、EU4 和 Stellaris 的颜色写法：§Y…§!。丢掉 §! 会把整行后半段染色，写错代码则可能把警告变成绿色",
    "The Stellaris grammar system: «Empress&!fem,vowel» and «A $1$|||vowel:An $1$». Variants the translator adds for cases are fine; a lost tag is not — it changes the gender of a name everywhere it is substituted":
        "Stellaris 的语法系统：「Empress&!fem,vowel」与「A $1$|||vowel:An $1$」。译者为各种格补写的变体属于正常；丢失标签则不然——它会改变该名称在所有替换处的性别",
    "An edge space is often in the original too: that is how the game glues strings together. Compared against the source, the rule stays quiet about those":
        "边缘空格往往原文里就有：游戏正是靠它拼接字符串。与原文比对时，本规则对这些不作声",
    "The original is often unbalanced itself, and the translation has nothing to do with it — hence the check against the source":
        "原文本身常常就不成对，与译文无关——因此才要与原文比对",
    "A repetition inside a repeated group — on a long row the check can take minutes. Consider (?:…) or a stricter pattern.":
        "重复组内还有重复——在长文本上这项检查可能耗时数分钟。建议改用 (?:…) 或更严格的模式。",
    "Markup":
        "标记",
    "Formatting":
        "格式",
    "Typography":
        "排版",
    "Target language":
        "目标语言",
    "Consistency":
        "一致性",
    "Length":
        "长度",
    "Own rules":
        "自定义规则",
    "Same set of matches":
        "匹配集合一致",
    "What the expression finds in the original must be found in the translation — the same items and as many":
        "表达式在原文中找到的内容，译文中也必须找到——同样的内容，同样的数量",
    "Same number of matches":
        "匹配数量一致",
    "Only the count is compared, the items themselves may differ — for things that get translated":
        "只比较数量，内容本身可以不同——用于需要翻译的部分",
    "Expression in the translation":
        "译文中的表达式",
    "forbid — fires when found, require — fires when missing":
        "forbid——找到即报，require——找不到才报",
    "Original → translation":
        "原文 → 译文",
    "For every match in the original the translation must contain the answer: groups are substituted into it as \\1":
        "原文中每出现一次匹配，译文中就必须有对应内容：捕获组以 \\1 的形式代入",
    "Paired characters":
        "成对字符",
    "Two characters per pair: «» or (). Identical halves are counted for parity":
        "每对两个字符：«» 或 ()。两半相同的按奇偶计数",
    "Forbidden characters":
        "禁用字符",
    "Every character listed is forbidden in the translation":
        "所列出的每个字符都不允许出现在译文中",
    "Empty translation":
        "译文为空",
    "Status is «translated», but the translation is empty":
        "状态为「已翻译」，但译文为空",
    "Variables $…$":
        "变量 $…$",
    "Variables $…$ do not match the original":
        "变量 $…$ 与原文不一致",
    "Icons @…! and £…£":
        "图标 @…! 和 £…£",
    "Icons do not match the original":
        "图标与原文不一致",
    "Colour codes §…§!":
        "颜色代码 §…§!",
    "Colour codes do not match the original":
        "颜色代码与原文不一致",
    "Grammar tags and variants":
        "语法标记与变体",
    "A grammar tag or variant of the original was lost":
        "原文中的语法标记或变体丢失了",
    "Formatting tags #…":
        "格式标签 #…",
    "The set of formatting tags differs from the original":
        "格式标签的集合与原文不同",
    "Tags not closed":
        "标签未闭合",
    "Tags are closed in the original but not in the translation":
        "原文中标签已闭合，而译文中没有",
    "Script references [ ]":
        "脚本引用 [ ]",
    "Script references [ ] differ from the original":
        "脚本引用 [ ] 与原文不同",
    "The main source of noise: the translator wraps a substitution in Concept(…) to inflect it — that is a technique, not a mistake":
        "噪声的主要来源：译者用 Concept(…) 包裹替换项以便变格——这是一种技巧，而非错误",
    "Line breaks":
        "换行",
    "The number of \\n breaks differs from the original":
        "\\n 换行的数量与原文不同",
    "Translation equals the original":
        "译文与原文相同",
    "The translation matches the original":
        "译文与原文一致",
    "Normal for names and numbers — such rows are marked «Ignore»":
        "对人名和数字来说很正常——这类行应标记为「忽略」",
    "Edge spaces":
        "首尾空格",
    "Extra spaces at the beginning or the end":
        "开头或结尾有多余的空格",
    "Double spaces":
        "连续空格",
    "Double spaces in the translation":
        "译文中有连续空格",
    "Unpaired quotes and brackets":
        "引号和括号不成对",
    "Unpaired quotes or brackets in the translation":
        "译文中引号或括号不成对",
    "Missing space before a substitution":
        "替换项前缺少空格",
    "Missing space before a substitution — the words will stick together":
        "替换项前缺少空格——单词会粘连在一起",
    "A word of 3+ letters: one or two letters get a pronoun attached on purpose — «к н[X.GetHerHis]» yields «к нему»":
        "仅针对 3 个及以上字母的词：一两个字母的情况是有意与代词相连——«к н[X.GetHerHis]» 会得到 «к нему»",
    "Calque of an English copula":
        "英语系动词的直译",
    "A substitution after a copula verb: «склонны быть Верность». An appositive turn is needed — «склонны проявлять черту: …»":
        "系动词后接替换项：«склонны быть Верность»。需要改用同位语结构——«склонны проявлять черту: …»",
    "CK3 names traits with nouns («Верность», «Отвага»), so «склонны быть [Trait]» unfolds into nonsense":
        "CK3 用名词命名特质（«Верность»、«Отвага»），因此 «склонны быть [Trait]» 展开后不知所云",
    "Same original translated differently":
        "相同原文译法不一",
    "The same original is translated differently in the project":
        "项目中相同的原文有不同的译法",
    "Not an error but a reason to check: one English word can be different things in different places":
        "这不是错误，但值得核对：同一个英文词在不同位置可能含义不同",
    "Suspicious length":
        "长度可疑",
    "Suspicious length of the translation":
        "译文长度可疑",
    "A heuristic: noisier than it is useful, hence off":
        "一条启发式规则：噪声大于价值，因此默认关闭",
    "Strict":
        "严格",
    "%1 — recommended for this project":
        "%1 — 推荐用于本项目",
    "Breakage only":
        "仅致命问题",
    "Own":
        "自定义",
}

ZH["Relocate"] = {
    "Folder: %1":
        "文件夹：%1",
    "The project is left without a translation folder — it is asked for at the first write into the mod.":
        "项目将不设译文文件夹——首次写入模组时会询问。",
    "The folder does not exist yet — it is created at the first write.":
        "该文件夹尚不存在——首次写入时会创建。",
    "Translation files found: %1 of %2":
        "找到译文文件：%1 / %2",
    "No translation files for this project here — the folder is where the write will put them. Files known: %1":
        "此处没有本项目的译文文件——写入时会把它们放进这个文件夹。项目已知文件：%1",
    "This is a file, not a folder: %1":
        "这是文件，不是文件夹：%1",
    "%1 was chosen, but the localization files lie in %2 — that is what will be recorded.":
        "所选为 %1，但本地化文件位于 %2——将记录后者。",
    "Files matched: %1 out of the %2 the database knows.":
        "匹配到的文件：%1 / 数据库已知的 %2 个。",
    ", of them %1 with a translation will go to the archive.":
        "，其中 %1 个带译文的将转入存档。",
    "Files not found: %1 — %2":
        "未找到的文件：%1 — %2",
    "%1 rows will become deleted":
        "%1 行将变为已删除",
    "  … and %1 more":
        "  ……还有 %1 个",
    "New files: %1 — rows from them appear on the next scan.":
        "新文件：%1——其中的行将在下次扫描时出现。",
    "Not a single database file was found in this folder. Looks like another mod's folder was chosen: after the change the whole translation goes to the archive.":
        "该文件夹中没有找到任何数据库中的文件。看起来选中的是另一个模组的文件夹：更改之后整份译文都会转入存档。",
    "The file set matches completely — the translation is safe.":
        "文件集合完全一致——译文是安全的。",
    "After the folder change a scan (F5) is needed: it re-reads the files and shows what changed in the original.":
        "更改文件夹后需要扫描（F5）：它会重新读取文件并显示原文中的变化。",
    "Project id=%1 not found":
        "未找到 id=%1 的项目",
    "Folder not found: %1":
        "未找到文件夹：%1",
    "The folder has no localization files *%1*.yml:\n%2":
        "该文件夹中没有本地化文件 *%1*.yml：\n%2",
    "Only the text language changes — files and rows are not affected. Machine translation, memory database naming and language-specific checks will use the new value.":
        "只更改文本语言——文件和行不受影响。机器翻译、记忆库命名以及与语言相关的检查将使用新值。",
    "Files with the label _l_%1 in the original folder: %2 of the %3 the database knows.":
        "原文文件夹中带 _l_%1 标记的文件：%2 / 数据库已知的 %3 个。",
    "Not a single file was found. After the change the scan will consider every row deleted and the translations will go to the archive.":
        "没有找到任何文件。更改之后，扫描会把所有行都视为已删除，译文将转入存档。",
    "%1 rows will become deleted, of them %2 with a translation.":
        "%1 行将变为已删除，其中 %2 行带有译文。",
    "After the change a scan (F5) is needed: it re-reads the files under the new names.":
        "更改之后需要扫描（F5）：它会按新的文件名重新读取文件。",
}

ZH["RootDialog"] = {
    "Change the original folder":
        "更改原文文件夹",
    "Change the translation folder":
        "更改译文文件夹",
    "The folder the translation is read from at a scan and written into at a write. It may be left empty: the mod has no translation yet, and the folder is asked for at the first write.":
        "扫描时从中读取译文、写入时写入其中的文件夹。可以留空：模组尚无译文时，首次写入会询问该文件夹。",
    "Now: not chosen":
        "当前：未选择",
    "Translation folder":
        "译文文件夹",
    "Change of the translation folder":
        "更改译文文件夹",
    "The project will be left without a translation folder. Nothing is deleted: the translation stays in the project, and the folder is asked for at the first write. Continue?":
        "项目将不设译文文件夹。不会删除任何内容：译文仍保留在项目中，首次写入时会询问文件夹。要继续吗？",
    "The folder the original is read from. It needs changing if the mod was re-downloaded elsewhere, the game library was moved, or the project came from another person.":
        "读取原文的文件夹。如果模组重新下载到了别处、游戏库被移动，或项目来自他人，就需要更改它。",
    "Now: %1":
        "当前：%1",
    "New folder:":
        "新文件夹：",
    "Browse…":
        "浏览…",
    "Change the folder":
        "更改文件夹",
    "Original folder":
        "原文文件夹",
    "Could not read the folder:\n%1":
        "无法读取文件夹：\n%1",
    "\n\nRows that will become deleted: %1\nTranslations that go to the archive: %2":
        "\n\n将变为已删除的行：%1\n转入存档的译文：%2",
    "Change of the original folder":
        "更改原文文件夹",
    "The new folder holds %1 files out of the %2 the database knows.%3\n\nTranslations are not deleted: they stay in the archive and in the translation memory. Change the folder?":
        "新文件夹中包含数据库已知的 %2 个文件中的 %1 个。%3\n\n译文不会被删除：它们保留在存档和翻译记忆库中。要更改文件夹吗？",
}

ZH["RulesWindow"] = {
    "One per line":
        "每行一个",
    "Values: %1":
        "条目数：%1",
    "The inflection helpers of the target language are added when a project is open — they come with its translation language.":
        "译文语言的变格函数在打开项目后才会加入——它们随项目的译文语言而来。",
    "all projects":
        "所有项目",
    "this project":
        "本项目",
    "Error":
        "错误",
    "Warning":
        "警告",
    "Signal":
        "提示",
    "Comma separated: Concept, Select_CString":
        "以逗号分隔：Concept, Select_CString",
    "Comma separated: #L, #P":
        "以逗号分隔：#L, #P",
    "Comma separated":
        "以逗号分隔",
    "Comma separated; fragments of a regular expression are allowed":
        "以逗号分隔；允许使用正则表达式片段",
    "multiset — with counts, set — composition only, count — the number only":
        "multiset——计入数量，set——只看组成，count——只看总数",
    "any — any discrepancy, fewer — lost ones only, more — extra ones only":
        "any——任何差异，fewer——只看缺少的，more——只看多出的",
    "Stay silent when a reference is replaced by a wrapper: one lost and one added is a swap, not a loss":
        "当引用被包裹取代时不作声：少了一个、多了一个，这是替换而非丢失",
    "Stay silent if the same space is in the original":
        "如果原文中也有同样的空格则不报",
    "Stay silent if the original itself is unbalanced":
        "如果原文本身就不配对则不报",
    "Stay silent if the double space is in the original":
        "如果原文中也有连续空格则不报",
    "Do not count formatting flags like |E as a discrepancy":
        "不把 |E 这类格式标志算作差异",
    "Count brackets after stripping the markup":
        "去除标记后再统计括号",
    "Complain only when not a single variable is left in the translation, and stay silent when the set merely differs":
        "只有当译文中一个变量都不剩时才报，集合仅仅不同则不报",
    "Preset:":
        "预设：",
    "Scope:":
        "范围：",
    "Where to record the setting: into a file next to the application or inside this project":
        "设置保存到何处：应用程序旁边的文件，还是本项目内部",
    "Reset…":
        "重置…",
    "Return built-in rules to the preset":
        "将内置规则恢复为预设",
    "The built-in rules already match the preset.":
        "内置规则已经与预设一致。",
    "Return %1 rules to the preset values? Own rules stay as they are.":
        "将 %1 条规则恢复为预设值？自定义规则保持不变。",
    "Delete all own rules":
        "删除全部自定义规则",
    "There are no own rules in this layer.":
        "该层中没有任何自定义规则。",
    "Delete %1 own rules? This cannot be undone.":
        "删除 %1 条自定义规则？此操作无法撤销。",
    "Return the rule to the preset":
        "将该规则恢复为预设",
    "Set by hand — differs from the preset":
        "已手动设置——与预设不同",
    "Built-in rules":
        "内置规则",
    "The check is written in the application: it can be switched on and off and made more lenient, but not rewritten or deleted":
        "检查由应用程序编写：可以开关、可以放宽，但无法改写或删除",
    "Rules of your own: they can be added, edited, duplicated and deleted":
        "你自己的规则：可以添加、编辑、复制和删除",
    "Other languages":
        "其他语言",
    "Rules of a language other than this project's: they stay silent, but can be switched on by hand":
        "并非本项目译文语言的规则：它们保持沉默，但可以手动启用",
    "Check":
        "检查",
    "Check · %1":
        "检查 · %1",
    "Setting":
        "设置",
    "🔒 Built-in rule: the check and its wording live in the application. It can be switched off and made more lenient, but not rewritten or deleted.":
        "🔒 内置规则：检查本身及其措辞都在应用程序中。可以关闭、可以放宽，但无法改写或删除。",
    "Duplicate":
        "创建副本",
    "A copy of your own rule to edit without losing the original. A built-in rule cannot be copied — its check is code, not an expression":
        "复制一份自定义规则，改动副本而不丢失原来的。内置规则无法复制——它的检查是代码，不是表达式",
    "%1 (copy)":
        "%1（副本）",
    "A regular expression; a match counts whole, brackets inside do not change that":
        "正则表达式；匹配整体计数，其中的括号不改变这一点",
    "A regular expression over the original":
        "针对原文的正则表达式",
    "What must be in the translation. Groups of the original are substituted as \\1":
        "译文中必须出现的内容。原文的捕获组以 \\1 的形式代入",
    "Treat the answer as a regular expression too. Off, the answer is searched as plain text — that is why $\\1$ works":
        "把答案也当作正则表达式。关闭时按纯文本查找——因此 $\\1$ 才有效",
    "forbid — fires when found, require — fires when missing":
        "forbid——找到即报，require——找不到才报",
    "Ignore the case":
        "忽略大小写",
    "Comma separated, two characters each: «», ()":
        "以逗号分隔，每对两个字符：«»、()",
    "In a row, without separators: …—":
        "连续写出，不加分隔符：…—",
    "How big a difference is still not an issue":
        "多大的差异仍然不算问题",
    "Own rule…":
        "自定义规则…",
    "A rule of your own: an expression instead of a built-in check":
        "自己写的规则：用表达式代替内置检查",
    "Own rule":
        "自定义规则",
    "Name:":
        "名称：",
    "Delete":
        "删除",
    "Message:":
        "提示语：",
    "same as the name":
        "与名称相同",
    "What the check will say about the row":
        "检查将如何描述该行",
    "Kind:":
        "类型：",
    "for example: No ellipsis as one character":
        "例如：不要用单字符省略号",
    "Delete the rule":
        "删除规则",
    "Delete the rule «%1»?":
        "删除规则「%1」？",
    "The rule is set for all projects — here it can only be switched off":
        "该规则设定于所有项目——在这里只能将其关闭",
    "Import…":
        "导入…",
    "Take the setting from a file — someone else's or your own from another machine":
        "从文件读取设置——别人的，或自己另一台机器上的",
    "Export…":
        "导出…",
    "Write the setting to a file to pass it on":
        "把设置写入文件以便传给他人",
    "Export check settings":
        "导出检查设置",
    "Import check settings":
        "导入检查设置",
    "Check settings (*%1)":
        "检查设置 (*%1)",
    "Check settings (*%1);;All files (*)":
        "检查设置 (*%1);;所有文件 (*)",
    "Written: %1":
        "已写入：%1",
    "The file cannot be read: %1":
        "无法读取文件：%1",
    "Preset: %1":
        "预设：%1",
    "Rules edited: %1":
        "有改动的规则：%1",
    "Own rules: %1":
        "自定义规则：%1",
    "Not understood and skipped: %1 (%2)":
        "无法识别已跳过：%1（%2）",
    "Replace the setting for «%1»?":
        "替换「%1」的设置？",
    "Rule":
        "规则",
    "Hits":
        "触发次数",
    "Severity":
        "严重程度",
    "How many times the rule fires on this project":
        "该规则在本项目中触发的次数",
    "Severity:":
        "严重程度：",
    "Leniency":
        "宽松度",
    "This rule has no settings.":
        "该规则没有可调设置。",
    "This rule has no self-check examples — try it on a pair above.":
        "该规则没有自检示例——请在上方的一对文本上试用它。",
    "Examples — the rule checks itself with them:":
        "示例——规则以此自检：",
    "Original":
        "原文",
    "Translation":
        "译文",
    "Expected":
        "预期",
    "Now":
        "当前",
    "Check on a pair":
        "在一对文本上检查",
    "original":
        "原文",
    "translation":
        "译文",
    "Take the current row":
        "取当前行",
    "Insert the pair from the row selected in the project table":
        "插入项目表格中选中行的原文与译文",
    "fires":
        "触发",
    "silent":
        "不触发",
    "No issues.":
        "没有问题。",
    "project-wide":
        "全项目",
    "The hit counter needs an open project.":
        "统计触发次数需要先打开项目。",
    "Counting the hits…":
        "正在统计触发次数…",
    "Hits counted on %1 translated rows of the project.":
        "已在项目的 %1 行已翻译内容上统计触发次数。",
    "Return to the check":
        "重新纳入检查",
    "Return all":
        "全部恢复",
    "Nothing has been silenced yet.\n\nThis is where issues go after the «Not an error» button in the check report (F6): a silenced issue stops showing up both in the report and in the «!» column of the table. From here it can be put back into the check.":
        "目前还没有屏蔽任何问题。\n\n"
        "在检查报告（F6）中按下「不是错误」后，问题就会来到这里：被屏蔽的问题"
        "不再出现在报告中，也不再出现在表格的「!」列中。可以从这里把它重新纳入检查。",
    "Nothing is marked «not an error».":
        "没有标记为「不是错误」的内容。",
    "Marked «not an error»: %1.":
        "标记为「不是错误」：%1。",
    "Return all %1 issues to the check?":
        "将全部 %1 个问题重新纳入检查？",
    "Check settings":
        "检查设置",
    "Rules":
        "规则",
    "Marked «not an error»":
        "标记为「不是错误」",
    "Apply and close":
        "应用并关闭",
}

ZH["ScanDialog"] = {
    "Scanning…":
        "正在扫描…",
    "Preparing…":
        "正在准备…",
    "Processed files:":
        "已处理文件：",
    "Interrupt":
        "中断",
    "File %1 of %2: %3":
        "第 %1 / %2 个文件：%3",
    "Interrupting — rolling back changes…":
        "正在中断——回滚更改…",
    "New rows":
        "新增行",
    "The original changed in meaning":
        "原文含义已变化",
    "The original was edited cosmetically":
        "原文仅有表面修改",
    "Filled from translation memory":
        "已从翻译记忆库填充",
    "Ignored (nothing to translate)":
        "已忽略（无需翻译）",
    "Deleted from the original":
        "已从原文中删除",
    "Moved to the archive":
        "已转入存档",
    "Unchanged":
        "未变化",
    "Scan results":
        "扫描结果",
    "Original files: %1 · translation files: %2":
        "原文文件：%1 · 译文文件：%2",
    "What":
        "内容",
    "How many":
        "数量",
    "Show":
        "显示",
    "Show details (%1)":
        "显示详情（%1）",
    "The discrepancies below were left as they are: the project has its own version. To take the version from the files use «Project → Load translation from mod…» with the «Overwrite existing translations» checkbox.":
        "以下差异保持原样：项目中另有自己的版本。若要采用文件中的版本，请使用「项目 → 从模组载入译文…」并勾选「覆盖已有译文」。",
    "Discrepancy with the file · %1: %2":
        "与文件的差异 · %1：%2",
    "      in project: %1":
        "　　　项目中：%1",
    "      in file:    %1":
        "　　　文件中：%1",
    "Duplicate key (original) · %1":
        "重复的键（原文）· %1",
    "Duplicate key (translation) · %1":
        "重复的键（译文）· %1",
    "Empty original · %1":
        "原文为空 · %1",
    "Translation file without a pair · %1":
        "没有对应原文的译文文件 · %1",
    "Parser · %1":
        "解析器 · %1",
    "Hide details":
        "隐藏详情",
}

ZH["ScanStats"] = {
    "EN files: %1, RU: %2":
        "原文文件：%1，译文：%2",
    "New keys: %1":
        "新增键：%1",
    "Unchanged: %1":
        "未变化：%1",
    "The original changed: %1 (meaningful %2, cosmetic %3)":
        "原文已变化：%1（实质 %2，表面 %3）",
    "Deleted from EN: %1":
        "已从原文中删除：%1",
    "Restored: %1":
        "已恢复：%1",
    "Moved to the archive (absent from the original): %1":
        "已转入存档（原文中不存在）：%1",
    "Filled from translation memory: %1":
        "已从翻译记忆库填充：%1",
    "Ignored automatically (nothing to translate): %1":
        "自动忽略（无需翻译）：%1",
    "RU conflicts (the database wins): %1":
        "译文冲突（以数据库为准）：%1",
    "Duplicate keys (original): %1":
        "重复的键（原文）：%1",
    "Duplicate keys (translation): %1":
        "重复的键（译文）：%1",
    "Keys with an empty original: %1":
        "原文为空的键：%1",
    "Parser warnings: %1":
        "解析器警告：%1",
}

ZH["Scanner"] = {
    "Project id=%1 not found":
        "未找到 id=%1 的项目",
    "Original folder not found: %1":
        "未找到原文文件夹：%1",
}

ZH["StartScreen"] = {
    "New project":
        "新建项目",
    "Game not specified":
        "未指定游戏",
    "Game:":
        "游戏：",
    "Format is the same across the series. Of another game — type its name: it gets a pen of its own next to the rest":
        "整个系列的格式相同。其他游戏——直接填写它的名称：它会在旁边获得自己的专属目录",
    "Name:":
        "名称：",
    "Original folder:":
        "原文文件夹：",
    "Translation folder:":
        "译文文件夹：",
    "Browse…":
        "浏览…",
    "Choose a folder":
        "选择文件夹",
    "Game folders:":
        "游戏文件夹：",
    "The text is in another language":
        "文本使用其他语言",
    "Portuguese in CK3, say, lives in l_english files: the game has no folder of its own for it":
        "例如 CK3 中的葡萄牙语存放在 l_english 文件中：游戏没有为它单独设文件夹",
    "Text languages:":
        "文本语言：",
    "Choose where to put the project file":
        "选择项目文件的存放位置",
    "Project file:":
        "项目文件：",
    "The original folder is the one holding *_l_%1.yml (for example …\\localization\\english).\nThe translation folder is where *_l_%2.yml go. Leave it empty if the mod has no translation yet — it is asked for at the first write.\nThe project file is portable: put it anywhere.":
        "原文文件夹是存放 *_l_%1.yml 的文件夹（例如 …\\localization\\english）。\n译文文件夹用于存放 *_l_%2.yml。如果模组尚无译文，可以留空——首次写入时会询问。\n项目文件是可移动的：放在任何位置都可以。",
    "Project file":
        "项目文件",
    "Translation project (*%1)":
        "翻译项目 (*%1)",
    "Project":
        "项目",
    "Enter the project name.":
        "请填写项目名称。",
    "The original folder does not exist:\n%1":
        "原文文件夹不存在：\n%1",
    "Enter the project file.":
        "请填写项目文件。",
    "The file already exists:\n%1":
        "文件已存在：\n%1",
    "Translation projects":
        "翻译项目",
    "Create…":
        "新建…",
    "Open":
        "打开",
    "Open file…":
        "打开文件…",
    "Show in Explorer":
        "在资源管理器中显示",
    "Remove from the list":
        "从列表中移除",
    "Delete…":
        "删除…",
    "file not found":
        "未找到文件",
    "Could not create the project:\n%1":
        "无法创建项目：\n%1",
    "Project file not found:\n%1":
        "未找到项目文件：\n%1",
    "Open project":
        "打开项目",
    "Translation project (*%1);;All files (*)":
        "翻译项目 (*%1);;所有文件 (*)",
    "Remove the project from the recent list?\n\nThe file %1 itself stays on disk.":
        "从最近列表中移除该项目？\n\n文件 %1 本身仍保留在磁盘上。",
}

ZH["Stats"] = {
    "Translated %1 / %2 (%3%) · left %4":
        "已翻译 %1 / %2（%3%）· 剩余 %4",
    " · auto: %1":
        " · 自动：%1",
    " · outdated: %1":
        " · 已过时：%1",
    " · machine: %1":
        " · 机器翻译：%1",
}

ZH["StatusChips"] = {
    "%1 — click to filter":
        "%1 —— 点击以筛选",
    "Rows with issues among those loaded — click to keep only them":
        "已载入的行中有问题的行——点击只保留它们",
}

ZH["Statuses"] = {
    "Not translated":
        "未翻译",
    "Machine (unchecked)":
        "机器翻译（未校对）",
    "Auto (from memory)":
        "自动（来自记忆库）",
    "Translated":
        "已翻译",
    "Reviewed":
        "已校对",
    "Outdated":
        "已过时",
    "Ignored":
        "已忽略",
    "Custom":
        "自定义",
}

ZH["TextDiff"] = {
    "cosmetic edit":
        "表面修改",
    "the text changed":
        "文本已变化",
    "removed: %1":
        "删除：%1",
    "added: %1":
        "新增：%1",
}

ZH["Theme"] = {
    "Light":
        "浅色",
    "Dark":
        "深色",
}

ZH["TmBuild"] = {
    "Game:":
        "游戏：",
    "From localization folders":
        "从本地化文件夹",
    "From the current project translations":
        "从当前项目的译文",
    "An open project is needed":
        "需要先打开项目",
    "Create the database":
        "创建数据库",
    "Interrupt":
        "中断",
    "Database name:":
        "数据库名称：",
    "Original folder:":
        "原文文件夹：",
    "Translation folder:":
        "译文文件夹：",
    "Browse…":
        "浏览…",
    "Choose a folder":
        "选择文件夹",
    "Languages:":
        "语言：",
    "Game database (vanilla localization)":
        "游戏数据库（原版本地化）",
    "Import of someone else's translation":
        "导入他人的译文",
    "Database kind:":
        "数据库类型：",
    "For a game database point at the localization folders of the installed CK3, for example:\n…\\Crusader Kings III\\game\\localization\\english and …\\localization\\russian.\nThe finished database appears in the folder %1.":
        "构建游戏数据库时请指向已安装的 CK3 的本地化文件夹，例如：\n…\\Crusader Kings III\\game\\localization\\english 和 …\\localization\\russian。\n构建好的数据库会出现在文件夹 %1 中。",
    "Translated and reviewed rows of the project go into a separate database in the folder %1 — it can be attached to another project.":
        "项目中已翻译和已校对的行会写入文件夹 %1 中的独立数据库——它可以挂载到另一个项目。",
    "Export":
        "导出",
    " · took the nested translation folder: %1":
        " · 已采用嵌套的译文文件夹：%1",
    "(0 pairs)":
        "（0 对）",
    " · nested checked: %1":
        " · 已检查嵌套目录：%1",
    "Localization folder found: %1":
        "找到本地化文件夹：%1",
    "There are no localization files in the original folder":
        "原文文件夹中没有本地化文件",
    "Original files: %1, but none of them has a pair in the translation folder — check that the localization folders are the ones given":
        "原文文件：%1，但其中没有一个在译文文件夹中有对应文件——请确认填写的确实是本地化文件夹",
    "Original files: %1, of them with a pair: %2":
        "原文文件：%1，其中有对应文件的：%2",
    "The file already exists:\n%1\n\nOverwrite?":
        "文件已存在：\n%1\n\n要覆盖吗？",
    "Could not export:\n%1":
        "无法导出：\n%1",
    "Translation pairs exported: %1":
        "已导出译文对：%1",
    "Done: %1 translation pairs.\n\n%2":
        "完成：%1 对译文。\n\n%2",
    "Translation database":
        "翻译数据库",
    "Enter the database name and the original folder.":
        "请填写数据库名称和原文文件夹。",
    "— 0 pairs":
        "—— 0 对",
    "None of the %1 original files has a pair in the translation folder.\n\nFolders checked:\n%2\n\nUsually this means the game or mod root was given while localization folders are needed — for example:\n  …\\game\\localization\\%3\n  …\\game\\localization\\%4\n\nA translation mod keeps files in its own tree: for Russian translations that is usually …\\localization\\%4, and next to it lies …\\localization\\replace\\%4 — a replacement of vanilla strings, unrelated to the mod's own strings.":
        "%1 个原文文件中没有一个在译文文件夹中有对应文件。\n\n已检查的文件夹：\n%2\n\n通常这说明填写的是游戏或模组的根目录，而这里需要的是本地化文件夹——例如：\n  …\\game\\localization\\%3\n  …\\game\\localization\\%4\n\n翻译模组把文件放在自己的目录树中：俄语翻译通常位于 …\\localization\\%4，其旁边还有 …\\localization\\replace\\%4——那是对原版字符串的替换，与模组自身的字符串无关。",
    "%1 files will be processed — this may take about %2 seconds, and the database will take noticeable disk space.\n\nContinue?":
        "将处理 %1 个文件——大约需要 %2 秒，数据库也会占用可观的磁盘空间。\n\n继续？",
    "Interrupting…":
        "正在中断…",
    "Build interrupted — the database file was not created":
        "构建已中断——未创建数据库文件",
    "Done":
        "完成",
    "File: %1":
        "文件：%1",
    "Parser warnings:":
        "解析器警告：",
    "Could not create the database:\n%1":
        "无法创建数据库：\n%1",
}

ZH["TmEntries"] = {
    "Original":
        "原文",
    "Translation":
        "译文",
    "Source":
        "来源",
    "Key":
        "键",
    "Changed":
        "修改时间",
    "Click — ascending, again — descending, again — as the database returns it":
        "单击——升序，再次——降序，再次——按数据库返回的顺序",
    "Search:":
        "搜索：",
    "by original, translation or key…":
        "按原文、译文或键…",
    "my entries only":
        "仅我的条目",
    "Hide entries of attached databases — they are read only":
        "隐藏已挂载数据库的条目——它们是只读的",
    "Double click on a translation to edit it. Entries of attached databases are dimmed: their files are open read only.":
        "双击译文即可编辑。已挂载数据库的条目显示为灰色：它们的文件以只读方式打开。",
    "Delete selected":
        "删除选中",
    "Clear my memory…":
        "清空我的记忆库…",
    " · from attached databases: %1":
        " · 来自已挂载的数据库：%1",
    " (first ones shown — refine the search)":
        "（仅显示开头部分——请细化搜索）",
    "shown: %1%2 · my entries: %3%4":
        "显示：%1%2 · 我的条目：%3%4",
    "Translation memory":
        "翻译记忆库",
    "Only entries of attached databases are selected — they are read only.\nA database can be detached on the «Databases» tab.":
        "选中的都是已挂载数据库的条目——它们是只读的。\n可以在「数据库」选项卡中卸载数据库。",
    "\n\nEntries of attached databases (%1) will not be touched.":
        "\n\n已挂载数据库的条目（%1）不会被改动。",
    "Deletion":
        "删除",
    "Delete %1 entries from the translation memory?%2\n\nThe translations of the project rows themselves do not change.":
        "从翻译记忆库中删除 %1 个条目？%2\n\n项目各行的译文本身不会改变。",
    "Clear the memory":
        "清空记忆库",
    "Delete all %1 entries of my translation memory?\n\nThe translations of the project rows stay in place — the memory fills up again on the next scan.":
        "删除我的翻译记忆库中全部 %1 个条目？\n\n项目各行的译文保持不变——下次扫描时记忆库会重新填充。",
}

ZH["TmImport"] = {
    "This SQLite build has no FTS5 — similarity search is unavailable":
        "该 SQLite 版本不含 FTS5——无法进行相似度搜索",
    "building the index…":
        "正在构建索引…",
    "compacting…":
        "正在压缩…",
    "Files processed: %1":
        "已处理文件：%1",
    "Translation pairs: %1":
        "译文对：%1",
    "Skipped (no translation): %1":
        "已跳过（无译文）：%1",
    "Parser warnings: %1":
        "解析器警告：%1",
    "Original folder not found: %1":
        "未找到原文文件夹：%1",
    "No translation folder found next to %1 (…/%2 was expected)":
        "在 %1 旁边没有找到译文文件夹（应为 …/%2）",
    "Translation folder not found: %1":
        "未找到译文文件夹：%1",
    "The folder %1 has no localization files of the language «%2» (names like *_l_%2.yml were expected)":
        "文件夹 %1 中没有语言「%2」的本地化文件（应为 *_l_%2.yml 这样的文件名）",
    " · pairs: %1":
        " · 对数：%1",
    "saving the database…":
        "正在保存数据库…",
    "building the similar-rows index…":
        "正在构建相似行索引…",
    "Not a single «original — translation» pair was found.\n\nOriginal files checked: %1, of them with a pair in the translation folder: %2.\nUsually the reason is that the game or mod root was given instead of the localization folders (…\\game\\localization\\%3 and …\\localization\\%4, say).":
        "没有找到任何「原文——译文」对。\n\n已检查的原文文件：%1，其中在译文文件夹中有对应文件的：%2。\n通常原因是填写了游戏或模组的根目录，而不是本地化文件夹（例如 …\\game\\localization\\%3 和 …\\localization\\%4）。",
    "Could not replace the database file: %1\n\nMost likely it is attached to the current project — detach it in «Tools → Translation memory…» and try again.":
        "无法替换数据库文件：%1\n\n很可能它已挂载到当前项目——请在「工具 → 翻译记忆库…」中卸载后重试。",
}

ZH["TmSources"] = {
    "The database is of another game — %1":
        "该数据库属于其他游戏——%1",
    "Checked databases provide suggestions and autofill (%1 → %2). Changes apply immediately.":
        "勾选的数据库会提供建议和自动填充（%1 → %2）。更改立即生效。",
    "Refresh the list":
        "刷新列表",
    "Build the similar-rows index":
        "构建相似行索引",
    "Without an index the database answers exact matches only.\nBuilding takes seconds and adds about 20% to the file size.":
        "没有索引时数据库只能给出完全匹配的结果。\n构建只需几秒，文件体积约增加 20%。",
    "No databases yet. Build one from localization folders on the «Build a database» tab.":
        "目前还没有数据库。请在「构建数据库」选项卡中从本地化文件夹构建一个。",
    "(file not found in the Bdd folder)":
        "（在 Bdd 文件夹中未找到该文件）",
    "entries":
        "条目",
    "with a similarity index":
        "有相似度索引",
    "without a similarity index":
        "无相似度索引",
    "The database languages do not match the project languages":
        "数据库的语言与项目的语言不一致",
    "databases in the folder: %1 · attached: %2":
        "文件夹中的数据库：%1 · 已挂载：%2",
    " · entries: %1":
        " · 条目：%1",
    "Index":
        "索引",
    "Choose a database in the list.":
        "请在列表中选择一个数据库。",
    "Database file not found:\n%1":
        "未找到数据库文件：\n%1",
    "Could not build the index:\n%1":
        "无法构建索引：\n%1",
    "Index built: %1 entries.\n\nThe database now suggests not only exact matches but similar rows too.":
        "索引已构建：%1 个条目。\n\n数据库现在不仅能给出完全匹配，还能给出相似的行。",
}

ZH["TmWindow"] = {
    "Translation memory":
        "翻译记忆库",
    "Entries":
        "条目",
    "Databases":
        "数据库",
    "Build a database":
        "构建数据库",
    "Building a database":
        "正在构建数据库",
    "The database is still being built. Interrupt it and close the window?\n\nAn unfinished database file will not be created.":
        "数据库仍在构建中。要中断并关闭窗口吗？\n\n不会生成未完成的数据库文件。",
}

ZH["Toolbar"] = {
    "Toolbar":
        "工具栏",
    "Project languages: original → translation":
        "项目语言：原文 → 译文",
    "Attached translation memory databases — they can be switched on and off right here":
        "已挂载的翻译记忆库数据库——可以直接在这里开关",
    "Memory databases":
        "记忆库数据库",
    "entries":
        "条目",
    "No databases yet":
        "目前还没有数据库",
}

ZH["UnitsTable"] = {
    "Key":
        "键",
    "File":
        "文件",
    "Status":
        "状态",
    "C":
        "自",
    "I":
        "忽",
    "Validate (F10)":
        "确认 (F10)",
    "Unvalidate (Shift+F10)":
        "取消确认 (Shift+F10)",
    "Custom status (Ctrl+F10)":
        "自定义状态 (Ctrl+F10)",
    "Ignore (Ctrl+Shift+F10)":
        "忽略 (Ctrl+Shift+F10)",
    "The original was edited cosmetically (punctuation, case, spaces)":
        "原文只有表面修改（标点、大小写、空格）",
    "The original changed in meaning — check the translation":
        "原文含义已变化——请核对译文",
    "Sort by key":
        "按键排序",
    "Sort by file":
        "按文件排序",
    "Sort by original text":
        "按原文排序",
    "Sort by translated text":
        "按译文排序",
    "Sort by status — in working order, not alphabetically":
        "按状态排序——按工作顺序，而非字母顺序",
    "Sort by kind of change to the original: meaningful first":
        "按原文变化的类型排序：实质变化在前",
    "Click — rows with issues on top. Click again — only those. Again — as it was":
        "单击——有问题的行置顶。再次单击——只显示这些行。再次——恢复原样",
    "Click — ascending, again — descending, again — as it was":
        "单击——升序，再次——降序，再次——恢复原样",
    "Original":
        "原文",
    "Translation":
        "译文",
    "Change to original":
        "原文变化",
    "Issues":
        "问题",
    "deleted":
        "已删除",
}

ZH["Welcome"] = {
    "Getting started":
        "快速上手",
    "Skip":
        "跳过",
    "Back":
        "上一步",
    "Next":
        "下一步",
    "Choose the language of the interface. It can be changed at any time in «File → Preferences».":
        "请选择界面语言。之后随时可以在「文件 → 首选项」中更改。",
    "The interface language has nothing to do with the languages you translate between — those belong to the project.":
        "界面语言与你翻译时使用的语言无关——后者属于项目设置。",
    "Build a database…":
        "构建数据库…",
    "A project holds everything: rows, statuses, translation memory and the history of the original. It is a single file you can copy or hand to another person.":
        "项目中保存着一切：行、状态、翻译记忆库以及原文的历史。它就是一个文件，可以复制，也可以交给别人。",
    "Create a project…":
        "创建项目…",
    "Open a project…":
        "打开项目…",
    "Translation memory databases found: %1. They fill in strings the mod copied from the game and prompt you with how similar lines were translated before.":
        "找到翻译记忆库数据库：%1 个。它们会填充模组从游戏中复制的字符串，并提示相似的行以前是怎么翻译的。",
    "Build one more…":
        "再构建一个…",
    "There are no translation memory databases yet. A database built from your copy of the game fills in strings the mod copied from it — often hundreds of them — and prompts you with how similar lines were translated before.\n\nBuilding takes seconds and needs nothing but the game localization folders.":
        "目前还没有翻译记忆库数据库。用你自己的游戏副本构建的数据库可以填充模组从游戏中复制的字符串——往往有数百条——并提示相似的行以前是怎么翻译的。\n\n构建只需几秒，只需要游戏的本地化文件夹。",
    "Interface language":
        "界面语言",
    "Translation memory":
        "翻译记忆库",
    "First project":
        "第一个项目",
    "Done":
        "完成",
}

ZH["Glossary"] = {
    "Glossary":
        "术语表",
    "Terms":
        "术语",
    "Candidates":
        "候选",
    "Original":
        "原文",
    "Translation":
        "译文",
    "Note":
        "备注",
    "Confidence":
        "置信度",
    "Pairs":
        "对数",
    "Search:":
        "搜索：",
    "original":
        "原文",
    "translation":
        "译文",
    "Add":
        "添加",
    "Delete selected":
        "删除所选",
    "Find terms":
        "查找术语",
    "Stop":
        "停止",
    "Accept":
        "接受",
    "Reject":
        "拒绝",
    "A rejected term is not offered again on the next run":
        "被拒绝的术语在下次运行时不会再次出现",
    "proper nouns only":
        "仅限专有名词",
    "Offer only words written with a capital in the middle of a phrase — that is what tells a name apart from an ordinary word. Without it the list fills with correct but useless pairs like «Now → теперь».":
        "只提供在句子中间以大写字母开头的词——正是这一点把名称与普通词区分开来。没有它，列表就会塞满「Now → теперь」这类正确但无用的词对。",
    "Double click to edit. Accepted terms are highlighted in the original; hovering one shows its translation.":
        "双击可编辑。已接受的术语会在原文中高亮显示，悬停即可查看其译法。",
    "Candidates are counted over the translation memory: the project's own plus every attached database. Statistics only suggests — nothing reaches the original until you accept it.":
        "候选是基于翻译记忆库统计得出的：包括项目自身的记忆库和所有已挂载的数据库。统计只负责建议——在你接受之前，原文不会受到任何影响。",
    "terms: %1 · waiting to be reviewed: %2":
        "术语：%1 · 待审阅：%2",
    "candidates: %1 · accepted: %2 · rejected: %3":
        "候选：%1 · 已接受：%2 · 已拒绝：%3",
    "found: %1 · new: %2":
        "找到：%1 · 新增：%2",
    "counting failed: %1":
        "统计失败：%1",
    "Terms are still being counted. Interrupt and close the window?\n\nCandidates found so far will not be saved.":
        "术语仍在统计中。是否中断并关闭窗口？\n\n目前找到的候选将不会保存。",
}
