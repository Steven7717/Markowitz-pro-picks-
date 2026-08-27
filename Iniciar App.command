#!/bin/bash
cd "$(dirname "$0")" || exit 1

# macOS protege Descargas, Escritorio y Documentos. Si esta ventana no tiene
# permiso sobre la carpeta, el "cd" de arriba funciona igual (chdir no lee la
# carpeta), pero cualquier programa que arranquemos desde aqui se cae al pedir
# su directorio de trabajo. uv lo hace nada mas empezar y muere con
# "Current directory does not exist", que no le dice nada a nadie.
# /bin/pwd es un proceso hijo que llama a getcwd(): la misma prueba que uv,
# hecha antes de descargar 400 MB. El -x es por si acaso: si el binario no
# estuviera, la comprobacion se salta en vez de bloquear un arranque sano.
if [ -x /bin/pwd ] && ! /bin/pwd >/dev/null 2>&1; then
    echo
    echo 'macOS no deja que esta ventana de Terminal lea la carpeta donde esta'
    echo 'el programa. Tienes dos formas de arreglarlo:'
    echo
    echo '  A) Mueve la carpeta fuera de Descargas. Por ejemplo, arrastrala a tu'
    echo '     carpeta de usuario (la de la casita) y vuelve a abrir este archivo.'
    echo
    echo '  B) Dale permiso a Terminal: menu Apple > Preferencias del Sistema >'
    echo '     Seguridad y privacidad > Privacidad > Archivos y carpetas, busca'
    echo '     Terminal y marca la casilla de Descargas. Luego cierra Terminal'
    echo '     del todo (Cmd+Q) y vuelve a abrir este archivo.'
    echo
    read -r -n 1 -s -p 'Pulsa una tecla para cerrar.'
    exit 1
fi

# Si la carpeta es un clon, se trae lo nuevo antes de arrancar. Quien la
# descargo como ZIP no tiene .git y se salta esto entero: sigue funcionando,
# solo que sin actualizarse.
#
# --ff-only es la parte importante: avanza el puntero si se puede y no hace
# nada mas. Nunca fabrica un merge ni reescribe nada de quien haya tocado sus
# ficheros, asi que lo peor que puede pasar es quedarse en la version que ya
# tenia. Un fallo aqui no puede impedir abrir el programa: sin internet, en un
# avion, la app tiene que abrirse igual.
if [ -d .git ] && command -v git >/dev/null 2>&1; then
    echo
    echo 'Buscando actualizaciones...'
    # Sin las dos primeras, una red que acepta la conexion y luego no responde
    # deja el arranque colgado para siempre y sin explicacion; con ellas git
    # se rinde a los 10 s. La tercera evita que un repo que pida credenciales
    # se quede esperando un usuario que nadie va a escribir.
    export GIT_HTTP_LOW_SPEED_LIMIT=1000
    export GIT_HTTP_LOW_SPEED_TIME=10
    export GIT_TERMINAL_PROMPT=0
    ANTES=$(git rev-parse HEAD 2>/dev/null)
    if git pull --ff-only --quiet 2>/dev/null; then
        if [ "$(git rev-parse HEAD 2>/dev/null)" != "$ANTES" ]; then
            echo 'Actualizado a la ultima version.'
        else
            echo 'Ya tienes la ultima version.'
        fi
    else
        echo 'No se ha podido actualizar: puede que no haya conexion, o que'
        echo 'tengas cambios propios sin guardar. Se abre la version que ya'
        echo 'tienes, que funciona igual.'
    fi
fi

# El git pull de arriba se hace en la raiz, que es donde esta .git. Entrar en
# programa/ antes de esa comprobacion la haria fallar --alli no hay .git-- y el
# pull se saltaria en silencio: el programa arrancaria igual y nadie notaria que
# dejo de actualizarse.
#
# Tambien tiene que ir antes de la comprobacion del shebang del .venv, que mira
# .venv/bin/streamlit: ese .venv vive ahora dentro de programa/.
#
# Se guarda antes del cd: una tarea posterior lo necesita para apuntar un
# acceso directo del Escritorio a este lanzador, que se queda en la raiz.
RAIZ="$(/bin/pwd)"
if ! cd programa; then
    echo
    echo 'No se encuentra la carpeta "programa", que tiene que estar junto a'
    echo 'este archivo. Puede que la descarga se extrajera a medias, o que se'
    echo 'moviera solo el lanzador. Vuelve a descargar la carpeta entera.'
    echo
    read -r -n 1 -s -p 'Pulsa una tecla para cerrar.'
    exit 1
fi

# Recien instalado, uv queda en ~/.local/bin, que no esta en el PATH de esta
# ventana. Sin esta linea el primer arranque falla justo despues de una
# instalacion que acaba de decir que fue bien.
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo
    echo 'Este programa necesita "uv", una herramienta que instala Python y las'
    echo 'librerias necesarias por ti. Ahora mismo no lo tienes.'
    echo
    echo 'Se descargaria del sitio oficial: https://astral.sh/uv'
    echo
    read -r -p 'Quieres instalarlo ahora? (s/n): ' RESPUESTA
    case "$RESPUESTA" in
        s|S|si|Si|SI|y|Y)
            echo
            echo 'Instalando uv...'
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
            ;;
        *)
            echo
            echo 'De acuerdo, no se ha instalado nada. Puedes instalarlo tu mismo desde'
            echo 'https://docs.astral.sh/uv/getting-started/installation/'
            echo 'y volver a abrir este archivo.'
            echo
            read -r -n 1 -s -p 'Pulsa una tecla para cerrar.'
            exit 1
            ;;
    esac

    if ! command -v uv >/dev/null 2>&1; then
        echo
        echo 'La instalacion no ha salido bien. Instala uv a mano desde'
        echo 'https://docs.astral.sh/uv/getting-started/installation/'
        echo
        read -r -n 1 -s -p 'Pulsa una tecla para cerrar.'
        exit 1
    fi
fi

# Mismo razonamiento que en el .bat: el .command no puede llevar icono propio
# --en macOS vive en el resource fork, que git no guarda-- y un alias guardado
# en el repo dejaria de resolver al mover la carpeta. Se genera aqui, donde la
# ruta absoluta si es la correcta.
#
# Se pregunta porque crear un fichero en el Escritorio de alguien sin avisar es
# invasivo. Y se guarda la respuesta: comprobando solo si el atajo existe, a
# quien lo borre a proposito se le resucita en cada arranque.
MARCA="$HOME/.markowitz-pro-picks/atajo.txt"
if [ ! -f "$MARCA" ]; then
    echo
    read -r -p 'Quieres un acceso directo en el Escritorio? (s/n): ' QUIERE
    mkdir -p "$HOME/.markowitz-pro-picks"
    case "$QUIERE" in
        s|S|si|Si|SI|y|Y)
            # Con la extension y no sin ella: Finder decide con que abrir un
            # fichero por su extension, y un enlace sin ninguna es una apuesta.
            # La .command la oculta el propio Finder salvo que el usuario haya
            # pedido ver todas, asi que en el Escritorio se lee igual.
            ATAJO="$HOME/Desktop/Markowitz Pro Picks.command"
            # Un .command de dos lineas y no un enlace simbolico. Este lanzador
            # se orienta con cd "$(dirname "$0")", y bash no resuelve enlaces en
            # $0: si Finder le pasara a Terminal la ruta del enlace, dirname
            # daria el Escritorio, el cd a programa/ fallaria y el usuario leeria
            # "vuelve a descargar la carpeta entera", que seria mentira. Y como
            # la marca ya estaria escrita, no se le volveria a ofrecer nunca.
            # Con el envoltorio, $0 es siempre la ruta real, y ademas es el mismo
            # mecanismo que ya funciona aqui: un .command ejecutable.
            #
            # printf %q escapa la ruta antes de meterla dentro del fichero: un
            # apostrofo en el nombre de la cuenta rompe cualquier comilla que
            # pongamos a mano. Es el mismo fallo que se arreglo en Windows.
            if printf '#!/bin/bash\nexec %q\n' "$RAIZ/Iniciar App.command" > "$ATAJO" 2>/dev/null \
               && chmod +x "$ATAJO"; then
                echo si > "$MARCA"
                echo 'Acceso directo creado en el Escritorio.'

                # El icono es de mejor esfuerzo y NO esta verificado en un Mac.
                #
                # macOS guarda el icono de un fichero en su resource fork, que
                # git no almacena; por eso hay que ponerlo aqui y no traerlo
                # hecho. El .icns si viene en el repo, para no depender de que
                # sips sepa leer un .ico, que es lo que no consta.
                #
                # Se le pone al atajo directamente: ahora es un fichero propio y
                # no un enlace, asi que ya no hay que ponerselo al destino para
                # que Finder lo herede.
                #
                # Rez, DeRez y SetFile vienen con las herramientas de linea de
                # comandos de Xcode y pueden no estar instaladas. Cada paso va
                # con guarda: si algo falta o falla, el alias se queda con el
                # icono generico y el arranque continua. Nunca rompe nada.
                #
                # Si al probarlo en un Mac el icono no aparece, borra este
                # bloque entero en vez de dejarlo aparentando que hace algo.
                if command -v sips >/dev/null 2>&1 \
                   && command -v Rez >/dev/null 2>&1 \
                   && command -v DeRez >/dev/null 2>&1 \
                   && command -v SetFile >/dev/null 2>&1; then
                    ICNS="$HOME/.markowitz-pro-picks/icono.icns"
                    RSRC="$HOME/.markowitz-pro-picks/icono.rsrc"
                    if cp "$RAIZ/programa/icono.icns" "$ICNS" 2>/dev/null \
                       && sips -i "$ICNS" >/dev/null 2>&1 \
                       && DeRez -only icns "$ICNS" > "$RSRC" 2>/dev/null \
                       && Rez -append "$RSRC" -o "$ATAJO" 2>/dev/null; then
                        SetFile -a C "$ATAJO" 2>/dev/null
                    fi
                    rm -f "$RSRC"
                fi
            else
                echo
                echo 'No se ha podido crear el acceso directo. El programa se abre'
                echo 'igual con este mismo archivo, y se volvera a intentar la'
                echo 'proxima vez.'
            fi
            ;;
        *)
            echo no > "$MARCA"
            echo
            echo 'De acuerdo, no se crea nada. Si algun dia lo quieres, borra el'
            echo "fichero $MARCA y este lanzador volvera a preguntar."
            ;;
    esac
fi

echo
echo 'Iniciando Markowitz Pro Picks...'
echo
echo 'La primera vez tarda unos minutos: hay que descargar Python y las'
echo 'librerias, varios cientos de MB. No cierres esta ventana.'
echo

# Un entorno virtual lleva su propia ruta grabada a fuego: los lanzadores de
# .venv/bin (streamlit entre ellos) empiezan por "#!/ruta/absoluta/.venv/bin/python".
# Si alguien mueve o copia la carpeta, esa ruta deja de existir y uv falla con
# "Failed to spawn: streamlit - No such file or directory", que suena a que
# falta instalar algo cuando en realidad solo hay que rehacer el entorno.
# Comparar el shebang con donde estamos ahora cuesta un "head" y lo detecta.
if [ -f .venv/pyvenv.cfg ] && [ -f .venv/bin/streamlit ]; then
    PY_ESPERADO="$(/bin/pwd)/.venv/bin/python"
    PY_GRABADO=$(sed -n '1s/^#!//p' .venv/bin/streamlit | awk '{print $1}')
    if [ "$PY_GRABADO" != "$PY_ESPERADO" ]; then
        echo 'La carpeta ha cambiado de sitio desde la ultima vez. Rehaciendo el'
        echo 'entorno (esta vez es rapido, las librerias ya estan descargadas)...'
        echo
        rm -rf .venv
    fi
fi

# La primera vez, streamlit se para a pedir un email por consola ("Welcome to
# Streamlit!") y se queda ahi esperando. Quien abre el .command ve la ventana
# colgada sin saber que tiene que pulsar Enter. Este fichero es la forma
# oficial de decir que no: se crea una sola vez y solo si no existe, para no
# pisar el de quien ya use streamlit para otra cosa.
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
    mkdir -p "$HOME/.streamlit" && printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

# Sin esto, si algo falla la ventana se cierra sola (el "; exit" que pone
# Terminal al abrir un .command) y el error se pierde antes de poder leerlo.
if ! uv run streamlit run app.py; then
    echo
    echo 'La app se ha cerrado con un error. El motivo esta en las lineas de'
    echo 'arriba: copialas si necesitas pedir ayuda.'
    echo
    read -r -n 1 -s -p 'Pulsa una tecla para cerrar.'
    exit 1
fi
