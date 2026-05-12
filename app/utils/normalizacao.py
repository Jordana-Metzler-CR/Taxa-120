"""
Funções de normalização de texto usadas pelos matchers de todas as imobiliárias.
Extraídas do de_para.py original para evitar duplicação.
"""

import re
from rapidfuzz import fuzz
from datetime import datetime, timedelta
from decimal import Decimal

def normalizar_texto(texto: str) -> str:
    if not isinstance(texto, str):
        return ''
    texto = texto.lower()
    texto = re.sub(r'[^\w\s/]', '', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def normalizar_endereco(texto: str) -> str:
    if not texto:
        return ""
    texto = normalizar_texto(texto)
    texto = re.sub(r'^\b(r|r\.|av|av\.|tv|tv\.)\b\s*', '', texto)
    return texto


def normalizar_nome_predio(texto: str) -> str:
    texto = normalizar_texto(texto)
    texto = re.sub(r'\b(bl|bl\.|bloc|bloco)\b', 'bloco', texto)
    return texto


def normalizar_complemento(complemento: str) -> str:
    if not complemento:
        return ""
    complemento = str(complemento).upper()
    complemento = re.sub(r'[^A-Z0-9]', ' ', complemento)
    complemento = re.sub(r'\bBOX\b|\bBX\b', '', complemento)
    complemento = re.sub(r'\bC\b|\bC\/\b', '', complemento)
    complemento = re.sub(r'\s+', ' ', complemento).strip()
    return complemento


def calcular_similaridade_documento(censurado: str, completo: str) -> float:
    """Compara CPF/CNPJ censurado (com *) contra completo, posição a posição."""
    censurado = re.sub(r'[.\-/]', '', str(censurado)).strip()
    completo  = re.sub(r'[.\-/]', '', str(completo)).strip()
    censurado = censurado.zfill(len(completo))
    completo  = completo.zfill(len(censurado))

    total = acertos = 0
    for c, k in zip(censurado, completo):
        if c != '*':
            total += 1
            if c == k:
                acertos += 1
    return round((acertos / total) * 100, 2) if total > 0 else 0.0


def similaridade_complemento(comp1: str, comp2: str) -> float:
    comp1 = normalizar_complemento(comp1)
    comp2 = normalizar_complemento(comp2)
    if not comp1 or not comp2:
        return 0.0
    return fuzz.token_set_ratio(comp1, comp2)

def normalizar_competencia(compt: str | None) -> str | None:
    
    if not compt:
        return None
    try:
        dt = datetime.strptime(compt, "%d/%m/%Y")
        return dt.strftime("%Y%m")
    except ValueError:
        return None


def montar_periodo_competencia(competencia: str) -> tuple[str, str]:
    """
    Recebe competência no formato YYYYMM e retorna:
    - primeiro_dia (YYYY-MM-DD)
    - ultimo_dia   (YYYY-MM-DD)
    """

    ano = int(competencia[:4])
    mes = int(competencia[4:6])

    primeiro_dia = f"{ano}-{mes:02d}-01"

    if mes == 12:
        ultimo_dia = f"{ano}-12-31"
    else:
        proximo_mes = datetime(ano, mes + 1, 1)
        ultimo_dia = (proximo_mes - timedelta(days=1)).strftime("%Y-%m-%d")

    return primeiro_dia, ultimo_dia


def normalizar_valor_monetario(valor_extraido):
    """
    Transforma qualquer string de valor (OCR ou PDF) em formato decimal correto.
    Exemplos: 
    "43.835,00" -> "438,35" (Corrige o erro do seu OCR)
    "438.35"    -> "438,35"
    "241,89"    -> "241,89"
    """
    if not valor_extraido:
        return "0,00"

    # 1. Mantém apenas os números
    apenas_numeros = re.sub(r'\D', '', str(valor_extraido))
    
    if not apenas_numeros:
        return "0,00"

    # 2. Converte para float tratando os últimos 2 dígitos como centavos
    # Isso mata o problema do "." vs "," porque os separadores são descartados
    valor_float = float(apenas_numeros) / 100
    
    # 3. Retorna formatado para o seu sistema (ex: 438,35)
    return "{:.2f}".format(valor_float).replace('.', ',')