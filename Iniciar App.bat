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
cd /d "%~dp0programa"
if errorlevel 1 (
  echo.
  echo No se encuentra la carpeta "programa", que tiene que estar junto a este
  echo archivo. Puede que la descarga se extrajera a medias, o que se moviera
  echo solo el lanzador. Vuelve a descargar la carpeta entera.
  echo.
  pause
  exit /b 1
)

rem Un .bat no puede llevar icono propio --lo pone la asociacion del sistema
rem para la extension-- y un .lnk guardado en el repo tampoco sirve: al mover
rem la carpeta deja de resolver, y cada usuario la extrae en un sitio distinto.
rem Generarlo aqui es lo que hace que la ruta absoluta sea la correcta.
rem
rem Se pregunta porque crear un fichero en el Escritorio de alguien sin avisar
rem es invasivo, y este lanzador ya pregunta antes de instalar uv. Y se guarda
rem la respuesta: comprobando solo si el atajo existe, a quien lo borre a
rem proposito se le resucita en cada arranque.
set "MARCA=%USERPROFILE%\.markowitz-pro-picks\atajo.txt"
if exist "%MARCA%" goto sin_atajo
echo.
rem Se limpia la variable antes de preguntar y se le quitan las comillas a la
rem respuesta: una comilla suelta dentro del if rompe la sintaxis y cmd cierra
rem la ventana de golpe, sin que de tiempo a leer nada. El "if defined" hace
rem falta porque si contesta con un Enter a secas la variable no existe y la
rem linea de abajo tampoco se puede escribir.
set "QUIERE="
set /p QUIERE="Quieres un acceso directo en el Escritorio? (s/n): "
if defined QUIERE set "QUIERE=%QUIERE:"=%"
if not exist "%USERPROFILE%\.markowitz-pro-picks" mkdir "%USERPROFILE%\.markowitz-pro-picks"
rem A un "(s/n)" mucha gente contesta "si", no "s". Aceptar solo "s" convertiria
rem ese "si" en un no definitivo y silencioso, porque la respuesta se guarda y
rem no se vuelve a preguntar. Es la misma lista que acepta el lanzador de Mac.
if /i "%QUIERE%"=="s"  goto crear_atajo
if /i "%QUIERE%"=="si" goto crear_atajo
if /i "%QUIERE%"=="y"  goto crear_atajo
> "%MARCA%" echo no
echo.
echo De acuerdo, no se crea nada. Si algun dia lo quieres, borra el fichero
echo %MARCA% y este lanzador volvera a preguntar.
goto sin_atajo

:crear_atajo
rem La ruta viaja por variable de entorno en vez de incrustada en el comando:
rem dentro de las comillas simples de PowerShell, un apostrofo en la ruta
rem --C:\Users\O'Brien\...-- cierra la cadena antes de tiempo y el comando ni
rem llega a ejecutarse. Como la ruta suele llevar el nombre de la cuenta, no es
rem un caso tan raro.
set "RAIZ=%~dp0"
rem GetFolderPath y no %USERPROFILE%\Desktop: con OneDrive el Escritorio real
rem puede estar redirigido, y el atajo acabaria en una carpeta que el usuario
rem no ve.
rem
rem El 2>nul se traga el volcado de error de PowerShell a proposito: es un muro
rem de texto para alguien que no lo puede interpretar, y justo debajo va nuestro
rem mensaje con lo unico que necesita saber.
powershell -NoProfile -Command "$r=$env:RAIZ; $d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'Markowitz Pro Picks.lnk')); $s.TargetPath=(Join-Path $r 'Iniciar App.bat'); $s.WorkingDirectory=$r; $s.IconLocation=(Join-Path $r 'programa\icono.ico'); $s.Description='Markowitz Pro Picks'; $s.Save()" 2>nul
rem Sin esta comprobacion se anunciaba un atajo que no existe y ademas se
rem guardaba la marca: no se reintentaba nunca mas. No escribir la marca cuando
rem falla es lo que deja la puerta abierta al proximo arranque.
if errorlevel 1 (
  echo.
  echo No se ha podido crear el acceso directo. El programa se abre igual con
  echo este mismo archivo, y se volvera a intentar la proxima vez.
  goto sin_atajo
)
> "%MARCA%" echo si
echo Acceso directo creado en el Escritorio.
:sin_atajo

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
