@echo off
REM Sobe o painel do ciclo-br e abre o navegador quando ele estiver de pe.
REM
REM Na primeira execucao cria o ambiente virtual e instala as dependencias; nas
REM seguintes so sobe. O servidor fica na janela minimizada que este script
REM abre: fechar aquela janela derruba o painel.

setlocal enabledelayedexpansion
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    call :achar_python
    if not defined PY goto :sem_python

    echo Primeira execucao: criando o ambiente virtual...
    "!PY!" -m venv .venv || goto :falhou
    echo Instalando dependencias ^(isso leva alguns minutos^)...
    .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt || goto :falhou
)

echo Subindo o painel em http://localhost:8501 ...
start "ciclo-br - painel" /min .venv\Scripts\python.exe -m streamlit run app.py

REM O Streamlit leva alguns segundos para responder na primeira carga, entao o
REM navegador so abre depois que a porta comeca a responder.
powershell -NoProfile -Command ^
  "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -Uri 'http://localhost:8501' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"

if errorlevel 1 (
    echo O painel nao respondeu a tempo. Veja a janela "ciclo-br - painel".
    pause
    exit /b 1
)

start "" http://localhost:8501
exit /b 0


REM ------------------------------------------------------------------------
REM Acha um Python de verdade.
REM
REM `python` no PATH do Windows costuma ser o atalho da Microsoft Store, que
REM nao executa nada e ainda devolve codigo de sucesso enganoso — por isso a
REM busca comeca pelas instalacoes reais e so depois cai no PATH.
:achar_python
set "PY="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
if defined PY exit /b 0
for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
if defined PY exit /b 0
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3" && exit /b 0
where python >nul 2>&1 && python -c "import sys" >nul 2>&1 && set "PY=python"
exit /b 0

:sem_python
echo.
echo Nao encontrei uma instalacao do Python neste computador.
echo Instale o Python 3.12 em https://www.python.org/downloads/ e rode de novo.
pause
exit /b 1

:falhou
echo.
echo Nao consegui preparar o ambiente. Rode os comandos da secao
echo "Como rodar" do README para ver a mensagem de erro completa.
pause
exit /b 1
