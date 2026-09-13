@echo off
REM Sobe o painel do ciclo-br e abre o navegador quando ele estiver de pe.
REM
REM Na primeira execucao, cria o ambiente virtual e instala as dependencias;
REM nas seguintes, so sobe. O servidor fica na janela minimizada que este script
REM abre: fechar aquela janela derruba o painel.

setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Primeira execucao: criando o ambiente virtual...
    python -m venv .venv || goto :falhou
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

:falhou
echo.
echo Nao consegui preparar o ambiente. Confira se o Python esta instalado
echo e rode os comandos da secao "Como rodar" do README.
pause
exit /b 1
