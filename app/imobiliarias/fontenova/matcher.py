"""
Algoritmo de similaridade para matching de boletos da Fonte Nova.

Usa os mesmos 5 campos e pesos da Barcellos:
  Documento:    30%
  Complemento:  25%
  Endereço:     20%
  Nome prédio:  15%
  Nome locador: 10%

Quando o complemento está ausente em qualquer dos lados, os pesos são redistribuídos:
  Documento: 35%, Endereço: 30%, Nome prédio: 20%, Nome locador: 15%
"""

import pandas as pd
from rapidfuzz import fuzz
from app.utils.normalizacao import (
    normalizar_texto, normalizar_endereco, normalizar_nome_predio,
    normalizar_complemento, calcular_similaridade_documento, similaridade_complemento,
)


def calcular_match(boleto, tabela: pd.DataFrame) -> pd.Series:
    """
    Retorna a linha do DataFrame com maior pontuação de similaridade
    para o boleto informado.
    """
    nome_predio  = normalizar_nome_predio(boleto.nome_predio or "")
    documento    = boleto.documento_condomino or ""
    endereco     = normalizar_endereco(boleto.endereco_imovel or "")
    complemento  = normalizar_complemento(getattr(boleto, 'complemento', ''))
    nome_locador = normalizar_texto(boleto.nome_condomino or "")

    def _score(row):
        sim_predio = fuzz.token_set_ratio(nome_predio,  normalizar_nome_predio(row['nomepredio']))
        sim_end    = fuzz.token_set_ratio(endereco,     normalizar_endereco(row.get('endereco', '')))
        sim_comp   = similaridade_complemento(complemento, row.get('complemento', ''))
        sim_nome   = fuzz.token_set_ratio(nome_locador, normalizar_texto(row.get('nome_locador', '')))
        sim_doc    = calcular_similaridade_documento(documento, row.get('documento_locador', ''))

        tem_comp = bool(complemento and normalizar_complemento(row.get('complemento', '')))
        if tem_comp:
            total = sim_doc*0.30 + sim_comp*0.25 + sim_end*0.20 + sim_predio*0.15 + sim_nome*0.10
        else:
            total = sim_doc*0.35 + sim_end*0.30 + sim_predio*0.20 + sim_nome*0.15

        return pd.Series({
            'sim_nomepredio': sim_predio, 'sim_endereco': sim_end,
            'sim_complemento': sim_comp, 'sim_nome_locador': sim_nome,
            'sim_documento': sim_doc, 'pontuacao_total': round(total, 2),
        })

    sims = tabela.apply(_score, axis=1)
    return pd.concat([tabela, sims], axis=1).sort_values('pontuacao_total', ascending=False).iloc[0]


def media_campos_principais(match: pd.Series) -> float:
    """Média dos 3 campos com maior peso para decidir aceitar match de baixa pontuação."""
    return (match['sim_nomepredio'] + match['sim_endereco'] + match['sim_complemento']) / 3