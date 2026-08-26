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
