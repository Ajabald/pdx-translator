@echo off
rem Starts the application from the sources without a console window:
rem pythonw.exe is the windowed interpreter, and `start ""` hands the shell
rem back at once instead of holding it for as long as the program runs.
rem The portable build needs none of this — see pdx-translator.spec.
start "" "%~dp0.venv\Scripts\pythonw.exe" -m pdxloc
