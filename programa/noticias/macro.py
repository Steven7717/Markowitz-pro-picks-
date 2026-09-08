# noticias/macro.py
"""Quien publica los datos de mercado, no cuando los publica.

**Punteros y no fechas, y es la decision central del sub-proyecto.** Ni
yfinance ni EDGAR dan el calendario macro. Copiar las fechas al repo crearia
algo que caduca en silencio: un calendario viejo se lee igual que uno vigente.
Un enlace roto, en cambio, se ve roto. La autoridad se queda donde esta.

Por eso `Evento.cuando` es None aqui: de la Fed sabemos que publica y donde, no
cuando. Un `date` inventado seria exactamente el defecto que esta decision
existe para evitar.
"""

from noticias.agenda import Evento

PUNTEROS = (
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="Reuniones del FOMC — ocho al año. Deciden el tipo de interés.",
        url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    ),
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="IPC — mensual. La inflación que la Fed dice mirar.",
        url="https://www.bls.gov/schedule/news_release/",
    ),
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="Situación del empleo — mensual, normalmente el primer viernes.",
        url="https://www.bls.gov/schedule/news_release/",
    ),
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="PIB trimestral y PCE mensual — la medida de inflación preferida "
                "por la Fed.",
        url="https://www.bea.gov/news/schedule",
    ),
)
