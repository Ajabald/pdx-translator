"""PDX Translator — рабочее место переводчика модов Paradox.

Copyright (C) 2026 Ajabald

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Уведомление стоит здесь, а не в шапке каждого из 83 модулей: GPL советует
второе, но считает достаточным «прикрепить к программе», а восемьдесят три
одинаковых шапки в проекте на одного автора — шум, который перестают читать
на третьем файле. Точка входа пакета видна и человеку, и сборщику.

Интерфейсная часть повторяет уведомление в окне «О программе» — этого просит
то же приложение к лицензии: «for a GUI interface, you would use an about box».
"""

__version__ = "0.1.1"

# Для окна «О программе» и любого другого места, где эти строки понадобятся:
# держать их в одном месте дешевле, чем сверять копии.
COPYRIGHT = "Copyright (C) 2026 Ajabald"
LICENCE = "GNU GPL v3 or later"
