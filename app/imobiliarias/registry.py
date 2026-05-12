"""
Registro central de imobiliárias.

Para adicionar uma nova:
  1. Crie a pasta app/imobiliarias/<nome>/ com config.py, extrator.py e matcher.py
  2. Importe e adicione a entrada no dict IMOBILIARIAS abaixo
  Nenhum outro arquivo precisa ser alterado.
"""

from app.imobiliarias.barcellos import config as cfg_barcellos
from app.imobiliarias.barcellos import extrator as ext_barcellos
from app.imobiliarias.barcellos import matcher as mtc_barcellos

from app.imobiliarias.fontenova import config as cfg_fontenova
from app.imobiliarias.fontenova import extrator as ext_fontenova
from app.imobiliarias.fontenova import matcher as mtc_fontenova

# Cada entrada expõe: config, extrator, matcher
IMOBILIARIAS = {
    cfg_barcellos.CNPJ: {
        "config":   cfg_barcellos,
        "extrator": ext_barcellos,
        "matcher":  mtc_barcellos,
    },
    cfg_fontenova.CNPJ: {
        "config":   cfg_fontenova,
        "extrator": ext_fontenova,
        "matcher":  mtc_fontenova,
    },
    # Pendentes — adicionar aqui quando implementar:
    # "73210825000104": { "config": cfg_lcd,   "extrator": ext_lcd,   "matcher": mtc_lcd   },
    # "40446119000107": { "config": cfg_tappe, "extrator": ext_tappe, "matcher": mtc_tappe },
    # "22488702000107": { "config": cfg_redoma,"extrator": ext_redoma,"matcher": mtc_redoma},
}


def get(cnpj: str) -> dict:
    """
    Retorna o dict {config, extrator, matcher} para o CNPJ informado.
    Lança ValueError com mensagem clara se o CNPJ não estiver registrado.
    """
    imob = IMOBILIARIAS.get(cnpj)
    if imob is None:
        conhecidos = ", ".join(IMOBILIARIAS.keys())
        raise ValueError(
            f"CNPJ '{cnpj}' não registrado. CNPJs conhecidos: {conhecidos}"
        )
    return imob
