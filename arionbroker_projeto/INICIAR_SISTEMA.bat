@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM ARION PROJETOS - INICIALIZADOR GERAL
REM ============================================================
REM
REM JANELA AZUL:
REM   - Servidor Django com Waitress
REM   - Scheduler Broker/Claro
REM   - Robo Mestre
REM   - Atualizador de KPIs OTRS
REM
REM JANELA ROXA:
REM   - Robo Embratel
REM
REM ============================================================


REM ============================================================
REM CAMINHOS
REM ============================================================

set "BAT_ATUAL=%~f0"
set "PROJETO_DIR=%~dp0"
set "PYTHON_EXE=%PROJETO_DIR%..\venv\Scripts\python.exe"
set "GERENCIAR=%PROJETO_DIR%gerenciar.py"


REM ============================================================
REM CONFIGURACAO GLOBAL DE LOGS
REM ============================================================

REM Faz print() e logging aparecerem imediatamente no terminal
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"


REM ============================================================
REM AUTOMACOES DESLIGADAS POR PADRAO
REM
REM Somente a janela SERVIDOR vai alterar para True
REM ============================================================

set "RODA_AUTOMACAO=False"


REM ============================================================
REM MODOS INTERNOS
REM ============================================================

if /I "%~1"=="SERVIDOR" goto MODO_SERVIDOR
if /I "%~1"=="EMBRATEL" goto MODO_EMBRATEL


REM ============================================================
REM ============================================================
REM INICIALIZADOR PRINCIPAL
REM ============================================================
REM ============================================================

color 0E
title ARION PROJETOS - INICIALIZADOR

cls

echo.
echo ============================================================
echo               ARION PROJETOS - INICIALIZADOR
echo ============================================================
echo.
echo  Esta janela realiza as verificacoes iniciais.
echo.
echo  Serao abertas:
echo.
echo  [AZUL]  Django + Broker/Claro + Scheduler + KPI
echo  [ROXO]  Robo Embratel
echo.
echo ============================================================
echo.


REM ============================================================
REM VERIFICA PYTHON DA VENV
REM ============================================================

if not exist "%PYTHON_EXE%" (

    color 0C

    echo.
    echo ============================================================
    echo [ERRO] PYTHON DA VENV NAO ENCONTRADO
    echo ============================================================
    echo.
    echo Caminho procurado:
    echo %PYTHON_EXE%
    echo.

    pause
    exit /b 1
)


REM ============================================================
REM VERIFICA GERENCIAR.PY
REM ============================================================

if not exist "%GERENCIAR%" (

    color 0C

    echo.
    echo ============================================================
    echo [ERRO] GERENCIAR.PY NAO ENCONTRADO
    echo ============================================================
    echo.
    echo Caminho:
    echo %GERENCIAR%
    echo.

    pause
    exit /b 1
)


REM ============================================================
REM 1/4 - VERIFICA PORTA 8000
REM ============================================================

echo [1/4] Verificando porta 8000...
echo.

set "PID_PORTA="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    set "PID_PORTA=%%P"
)

if defined PID_PORTA (

    color 0C

    echo ============================================================
    echo [ERRO] JA EXISTE UM SERVIDOR NA PORTA 8000
    echo ============================================================
    echo.
    echo PID encontrado:
    echo.
    echo       !PID_PORTA!
    echo.
    echo Processo:
    echo.

    tasklist /FI "PID eq !PID_PORTA!"

    echo.
    echo O ARION nao vai iniciar uma segunda instancia.
    echo.
    echo Finalize o processo antigo antes de executar novamente.
    echo.

    pause
    exit /b 1
)

echo       Porta 8000 livre.
echo.


REM ============================================================
REM 2/4 - VERIFICA DJANGO E WAITRESS
REM ============================================================

echo [2/4] Verificando Django e Waitress...
echo.

"%PYTHON_EXE%" -c "import django; import waitress" >nul 2>&1

if errorlevel 1 (

    color 0C

    echo ============================================================
    echo [ERRO] DJANGO OU WAITRESS NAO ENCONTRADO
    echo ============================================================
    echo.
    echo Verifique a VENV do projeto.
    echo.

    pause
    exit /b 1
)

echo       Django OK.
echo       Waitress OK.
echo.


REM ============================================================
REM 3/4 - COLLECTSTATIC
REM ============================================================

echo [3/4] Atualizando arquivos estaticos...
echo.

REM ============================================================
REM IMPORTANTE
REM
REM collectstatic carrega o Django.
REM Ele NAO pode iniciar o Scheduler.
REM ============================================================

set "RODA_AUTOMACAO=False"

"%PYTHON_EXE%" -u "%GERENCIAR%" collectstatic --noinput

if errorlevel 1 (

    color 0C

    echo.
    echo ============================================================
    echo [ERRO] FALHA AO EXECUTAR COLLECTSTATIC
    echo ============================================================
    echo.

    pause
    exit /b 1
)

echo.
echo       Arquivos estaticos atualizados.
echo.


REM ============================================================
REM 4/4 - ABRE OS MOTORES
REM ============================================================

echo [4/4] Abrindo os motores...
echo.


REM ============================================================
REM ABRE SERVIDOR DJANGO + BROKER/CLARO
REM ============================================================

echo       Abrindo Django + Broker/Claro...

start "ARION - SERVIDOR E BROKER" cmd /k call "%BAT_ATUAL%" SERVIDOR


REM ============================================================
REM AGUARDA SOMENTE UM POUCO PARA SEPARAR AS INICIALIZACOES
REM
REM NAO esperamos a porta 8000 antes de abrir o Embratel.
REM O Scheduler pode executar tarefas antes do Waitress liberar
REM a porta.
REM ============================================================

timeout /t 2 /nobreak >nul


REM ============================================================
REM ABRE ROBO EMBRATEL
REM ============================================================

echo       Abrindo Robo Embratel...

start "ARION - ROBO EMBRATEL" cmd /k call "%BAT_ATUAL%" EMBRATEL


REM ============================================================
REM AGORA MONITORA O DJANGO SEM BLOQUEAR O EMBRATEL
REM ============================================================

echo.
echo       Motores iniciados.
echo       Aguardando Django ficar ONLINE...
echo.

set /a TENTATIVA_DJANGO=0


:AGUARDAR_DJANGO

set "PID_PORTA="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    set "PID_PORTA=%%P"
)

if defined PID_PORTA goto DJANGO_ONLINE


set /a TENTATIVA_DJANGO+=1

echo       Aguardando porta 8000... !TENTATIVA_DJANGO!/120

if !TENTATIVA_DJANGO! GEQ 120 goto DJANGO_TIMEOUT

timeout /t 1 /nobreak >nul

goto AGUARDAR_DJANGO



REM ============================================================
REM DJANGO ONLINE
REM ============================================================

:DJANGO_ONLINE

color 0A

echo.
echo ============================================================
echo                 SISTEMA INICIADO COM SUCESSO
echo ============================================================
echo.
echo  Django / Waitress..... ONLINE
echo  Porta................. 8000
echo  PID................... !PID_PORTA!
echo.
echo  [AZUL]
echo    Django
echo    Waitress
echo    Broker / Claro
echo    Scheduler
echo    Robo Mestre
echo    KPI OTRS
echo.
echo  [ROXO]
echo    Robo Embratel
echo.
echo ============================================================
echo.

timeout /t 5 /nobreak >nul

exit /b 0



REM ============================================================
REM DJANGO DEMOROU MAIS QUE 120 SEGUNDOS
REM ============================================================

:DJANGO_TIMEOUT

color 0E

echo.
echo ============================================================
echo               AVISO - DJANGO AINDA INICIALIZANDO
echo ============================================================
echo.
echo O servidor ainda nao abriu a porta 8000 apos 120 segundos.
echo.
echo As janelas AZUL e ROXA permanecem abertas.
echo.
echo Verifique os logs da janela AZUL.
echo.
echo O Robo Embratel ja foi iniciado separadamente.
echo.
echo ============================================================
echo.

pause

exit /b 0



REM ============================================================
REM ============================================================
REM MODO SERVIDOR
REM ============================================================
REM ============================================================

:MODO_SERVIDOR

color 0B
title ARION - SERVIDOR + ROBO BROKER CLARO

cls

cd /d "%PROJETO_DIR%"


REM ============================================================
REM CONFERE NOVAMENTE SE JA EXISTE SERVIDOR
REM ============================================================

set "PID_PORTA="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    set "PID_PORTA=%%P"
)

if defined PID_PORTA (

    color 0C

    echo.
    echo ============================================================
    echo               SERVIDOR JA ESTA RODANDO
    echo ============================================================
    echo.
    echo Porta 8000 ocupada.
    echo.
    echo PID: !PID_PORTA!
    echo.
    echo Uma segunda instancia foi bloqueada.
    echo.

    pause
    exit /b 1
)


REM ============================================================
REM SOMENTE ESTA JANELA PODE RODAR AUTOMACOES
REM ============================================================

set "RODA_AUTOMACAO=True"


REM ============================================================
REM LOGS SEM BUFFER
REM ============================================================

set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"


REM ============================================================
REM CABECALHO
REM ============================================================

cls

echo.
echo ============================================================
echo            SERVIDOR DJANGO + ROBO BROKER/CLARO
echo ============================================================
echo.
echo  Django................ ATIVO
echo  Waitress.............. ATIVO
echo  Broker / Claro........ ATIVO
echo  Scheduler............. ATIVO
echo  Robo Mestre........... ATIVO
echo  KPI OTRS.............. ATIVO
echo.
echo  IP.................... 127.0.0.1
echo  Porta................. 8000
echo  Threads............... 8
echo.
echo  RODA_AUTOMACAO........ %RODA_AUTOMACAO%
echo.
echo ============================================================
echo                    LOGS DO SISTEMA
echo ============================================================
echo.


REM ============================================================
REM INICIA WAITRESS
REM
REM -u = PYTHON SEM BUFFER
REM
REM Seu settings.py possui StreamHandler no console.
REM Todos os logger.info(), warning(), error(), exception()
REM e print() devem aparecer nesta janela.
REM ============================================================

"%PYTHON_EXE%" -u -m waitress ^
    --listen=127.0.0.1:8000 ^
    --threads=8 ^
    arionbroker_projeto.wsgi:application


REM ============================================================
REM SERVIDOR ENCERRADO
REM ============================================================

echo.
echo.

color 0C

echo ============================================================
echo.
echo              SERVIDOR DJANGO ENCERRADO
echo.
echo ============================================================
echo.

pause

exit /b 0



REM ============================================================
REM ============================================================
REM MODO EMBRATEL
REM ============================================================
REM ============================================================

:MODO_EMBRATEL

color 0D
title ARION - ROBO EMBRATEL

cls

cd /d "%PROJETO_DIR%"


REM ============================================================
REM EMBRATEL NUNCA PODE RODAR O SCHEDULER BROKER/CLARO
REM ============================================================

set "RODA_AUTOMACAO=False"


REM ============================================================
REM LOGS SEM BUFFER
REM ============================================================

set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"


REM ============================================================
REM CABECALHO
REM ============================================================

echo.
echo ============================================================
echo                     ROBO EMBRATEL
echo ============================================================
echo.
echo  Robo Embratel......... ATIVO
echo  Scheduler Broker...... DESABILITADO
echo.
echo  RODA_AUTOMACAO........ %RODA_AUTOMACAO%
echo.
echo ============================================================
echo                    LOGS EMBRATEL
echo ============================================================
echo.


REM ============================================================
REM EXECUTA EMBRATEL
REM ============================================================

"%PYTHON_EXE%" -u "%GERENCIAR%" rodar_robo_embratel


REM ============================================================
REM EMBRATEL ENCERRADO
REM ============================================================

echo.
echo.

color 0C

echo ============================================================
echo.
echo                 ROBO EMBRATEL ENCERRADO
echo.
echo ============================================================
echo.

pause

exit /b 0