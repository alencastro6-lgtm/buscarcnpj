@echo off
cd /d c:\Users\User\Downloads\BUSCAR_CNPJ

echo ===== FORÇA MÁXIMA: REFAZENDO TUDO DO ZERO =====

REM Remover diretório .git completamente
rmdir /s /q .git

echo ===== INICIALIZANDO GIT NOVO =====
"C:\Program Files\Git\bin\git.exe" init
"C:\Program Files\Git\bin\git.exe" config user.name "alencastro6-lgtm"
"C:\Program Files\Git\bin\git.exe" config user.email "user@example.com"

echo ===== REMOVENDO TODOS OS ARQUIVOS COM TOKENS =====
del /q push_github.bat push.sh cleanup_and_push.bat final_clean_push.bat 2>nul

echo ===== ADICIONANDO APENAS ARQUIVOS DO PROJETO =====
"C:\Program Files\Git\bin\git.exe" add -A

echo ===== COMMIT INICIAL LIMPO =====
"C:\Program Files\Git\bin\git.exe" commit -m "Initial commit: BUSCAR_CNPJ - Consulta de CNPJ com Interface Gráfica"

echo ===== BRANCH MAIN =====
"C:\Program Files\Git\bin\git.exe" branch -M main

echo ===== ADICIONAR REPOSITORIO REMOTO =====
REM Note: Remova o token! Use apenas a URL pública
"C:\Program Files\Git\bin\git.exe" remote add origin https://github.com/alencastro6-lgtm/buscarcnpj.git

echo ===== FAZENDO PUSH FORÇADO =====
"C:\Program Files\Git\bin\git.exe" push -u origin main --force

echo.
echo ✓ PUSH COMPLETO!
echo.
echo IMPORTANTE: Você será solicitado a autenticar via token no navegador
echo OU use o token regenerado (NÃO hardcode em arquivos!)
echo.
pause
