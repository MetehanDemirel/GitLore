@echo off
rem GitLore launcher (Windows). First run creates .venv and installs dependencies;
rem later runs start instantly. Close this window to stop GitLore.
setlocal
cd /d "%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"

where git >nul 2>nul || (
    echo [GitLore] Git is not installed or not on PATH. Install it from https://git-scm.com and try again.
    goto :fail
)

set "HAS_UV=0"
where uv >nul 2>nul && set "HAS_UV=1"

rem --- 1. Create the virtual environment (Python 3.11-3.13; 3.14 is not supported) ---
if exist "%VENV_PY%" goto :install
echo [GitLore] Creating virtual environment...
if "%HAS_UV%"=="1" (
    uv venv --python 3.12 .venv || goto :fail
    goto :install
)
for %%V in (3.12 3.13 3.11) do (
    py -%%V -c "" >nul 2>nul && (
        py -%%V -m venv .venv || goto :fail
        goto :install
    )
)
echo [GitLore] Could not find Python 3.11, 3.12 or 3.13, and uv is not installed.
echo           Easiest fix: install uv, then run this script again:
echo           powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
goto :fail

rem --- 2. Install dependencies only when requirements.txt changed ---
:install
if exist ".venv\requirements.stamp" (
    fc /b requirements.txt ".venv\requirements.stamp" >nul 2>nul && goto :run
)
echo [GitLore] Installing dependencies (first run takes a few minutes)...
if "%HAS_UV%"=="1" (
    uv pip install --python "%VENV_PY%" -r requirements.txt || goto :fail
) else (
    "%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt || goto :fail
)
"%VENV_PY%" -c "import llama_cpp" || (
    echo [GitLore] The LLM library was installed but cannot load on this system.
    goto :fail
)
copy /y requirements.txt ".venv\requirements.stamp" >nul

rem --- 3. Run ---
:run
echo [GitLore] Starting... a browser tab will open. Close it (or this window) to stop.
"%VENV_PY%" -m streamlit run app.py %*
exit /b %errorlevel%

:fail
echo.
echo [GitLore] Setup failed. See SETUP.md for troubleshooting.
pause
exit /b 1
