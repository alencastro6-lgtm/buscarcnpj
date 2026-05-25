@echo off
REM Executa a versao simplificada: somente busca de clientes

setlocal
set "SCRIPT_DIR=%~dp0"

REM Inicia em modo GUI (sem janela de console) e sai do .bat.
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw "%SCRIPT_DIR%main.py"
    exit /b
)

where pyw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pyw -3 "%SCRIPT_DIR%main.py"
    exit /b
)

if exist "%LocalAppData%\Programs\Python\Python312\pythonw.exe" (
    start "" "%LocalAppData%\Programs\Python\Python312\pythonw.exe" "%SCRIPT_DIR%main.py"
    exit /b
)

REM Fallback: se nao houver pythonw/pyw, abre com console mesmo.
start "" py -3 "%SCRIPT_DIR%main.py"
exit /b

