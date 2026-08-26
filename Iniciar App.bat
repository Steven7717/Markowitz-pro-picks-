@echo off
cd /d "%~dp0"

rem Recien instalado, uv queda en %USERPROFILE%\.local\bin, que no esta en el
rem PATH de esta ventana. Sin esta linea el primer arranque falla justo
rem despues de una instalacion que acaba de decir que fue bien.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

rem uv instala las librerias creando enlaces duros desde su cache para ahorrar
rem espacio. Si la carpeta del programa esta en OneDrive -- y el Escritorio y
rem Documentos lo estan por defecto en muchos Windows -- el filtro de archivos
rem en la nube rechaza esos enlaces y la instalacion muere con "os error 396:
rem La operacion de nube no se puede realizar en un archivo con vinculos
rem permanentes incompatibles", que no le dice nada a nadie.
rem
rem Copiar en vez de enlazar siempre funciona. Cuesta algo mas de disco y unos
rem segundos mas la primera vez; a cambio, el programa arranca en cualquier
rem carpeta. Un lanzador que va lento es mejor que uno que falla con un error
rem incomprensible en la primera pantalla que ve el usuario.
set "UV_LINK_MODE=copy"

where uv >nul 2>&1
if not errorlevel 1 goto arrancar

echo.
echo Este programa necesita "uv", una herramienta que instala Python y las
echo librerias necesarias por ti. Ahora mismo no lo tienes.
echo.
echo Se descargaria del sitio oficial: https://astral.sh/uv
echo.
set /p RESPUESTA="Quieres instalarlo ahora? (s/n): "
if /i "%RESPUESTA%"=="s" goto instalar

echo.
echo De acuerdo, no se ha instalado nada. Puedes instalarlo tu mismo desde
echo https://docs.astral.sh/uv/getting-started/installation/
echo y volver a ejecutar este archivo.
echo.
pause
exit /b 1

:instalar
echo.
echo Instalando uv...
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>&1
if not errorlevel 1 goto arrancar
echo.
echo La instalacion no ha salido bien. Instala uv a mano desde
echo https://docs.astral.sh/uv/getting-started/installation/
echo y vuelve a ejecutar este archivo.
echo.
pause
exit /b 1

:arrancar
rem Si la carpeta es un clon, se trae lo nuevo antes de arrancar. Quien la
rem descargo como ZIP no tiene .git y se salta esto entero. --ff-only avanza
rem el puntero si se puede y no hace nada mas: nunca fabrica un merge ni pisa
rem los ficheros de nadie. Un fallo aqui no impide abrir el programa.
if not exist ".git" goto lanzar
where git >nul 2>&1
if errorlevel 1 goto lanzar
echo.
echo Buscando actualizaciones...
rem Sin las dos primeras, una red que acepta la conexion y luego no responde
rem deja el arranque colgado sin explicacion. La tercera evita quedarse
rem esperando unas credenciales que nadie va a escribir.
set "GIT_HTTP_LOW_SPEED_LIMIT=1000"
set "GIT_HTTP_LOW_SPEED_TIME=10"
set "GIT_TERMINAL_PROMPT=0"
git pull --ff-only --quiet
if errorlevel 1 (
  echo No se ha podido actualizar: puede que no haya conexion, o que tengas
  echo cambios propios sin guardar. Se abre la version que ya tienes.
) else (
  echo Al dia.
)

:lanzar
rem El git pull de arriba se hace en la raiz, que es donde esta .git. Entrar en
rem programa/ antes de esa comprobacion la haria fallar --alli no hay .git-- y
rem el pull se saltaria en silencio: el programa arrancaria igual y nadie
rem notaria que dejo de actualizarse.
cd /d "%~dp0programa" || exit /b 1

rem La primera vez, streamlit se para a pedir un email por consola y deja la
rem ventana colgada esperando un Enter que nadie sabe que hay que pulsar.
rem Este fichero es la forma oficial de declinar; solo se crea si no existe,
rem para no pisar el de quien ya use streamlit para otra cosa.
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
  > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
  >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo Iniciando Markowitz Pro Picks...
echo.
echo La primera vez tarda unos minutos: hay que descargar Python y las
echo librerias, varios cientos de MB. No cierres esta ventana.
echo.
uv run streamlit run app.py
pause
