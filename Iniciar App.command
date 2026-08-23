#!/bin/bash
cd "$(dirname "$0")" || exit 1

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
uv run streamlit run app.py
