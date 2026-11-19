@echo off
setlocal
REM Rebuild Prism Ark (PC) Ruah Route non-destructive mod from PS2 Awake ISO + PC game folder.
REM Usage:
REM   rebuild_pc_mod.bat "C:\path\to\Prism Ark - Awake (Japan).iso" "C:\path\to\p_ark201"
REM If omitted, defaults are read from PRISM_ARK_ISO / PRISM_ARK_PC_DIR or repo defaults.

set SCRIPT_DIR=%~dp0
if not "%~1"=="" set PRISM_ARK_ISO=%~1
if not "%~2"=="" set PRISM_ARK_PC_DIR=%~2

python "%SCRIPT_DIR%src\pc_port\build_mod.py" --all --verify
exit /b %ERRORLEVEL%
