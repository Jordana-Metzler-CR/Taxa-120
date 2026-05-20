"""
Extração de dados dos PDFs da Barcellos.
...
"""

import re
import os
import shutil
from pathlib import Path
from PyPDF2 import PdfReader

from app.classes.boleto import Boleto
from app.utils.formatarCodigoBarras import linha_digitavel_para_codigo_barras
from app.imobiliarias.barcellos.config import PASTA_PROCESSADOS

# ---------------------------------------------------------------------------
# Padrões regex
# ---------------------------------------------------------------------------
_CNPJ             = r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}'
_VALOR            = r'R\$ ?\d{1,3}(?:\.\d{3})*(?:\d*)?,\d{2}'
_COMPETENCIA      = r'\b(0[1-9]|1[0-2])\/\d{4}\b'
_CODIGO_BARRAS    = r'\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d{1}\s+\d{14}'
_NOME_PREDIO      = r"\b\d{3,5}-([A-ZÁÉÍÓÚÂÊÔÃÕÇ .\-']+)\b"
_DOCUMENTOS       = r'(?:[\d\*]{3}\.[\d\*]{3}\.[\d\*]{3}-[\d\*]{2})|(?:[\d\*]{2}\.[\d\*]{3}\.[\d\*]{3}/[\d\*]{4}-[\d\*]{2})'
_NOME_COND_FAT    = r'Condômino\s*\n\s*(.+)'
_NOME_COND_REC    = r'Condomino\s*:\s*(.+?)\s*-\s*[\d\*\.\/-]+'
_VENCIMENTO       = r'\b(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[0-2])/\d{4}\b'
_ENDERECO_REC     = r'Endereço\s*:?\s*(.+)'
_COMPLEMENTO_REC  = r'Unidades\s*:?\s*(.*?)\s*S[ÉE]RIE'


def _safe_search(pattern, text, group=0):
    m = re.search(pattern, text)
    return m.group(group).strip() if m else None


# ---------------------------------------------------------------------------
# Normalização de nomes de taxas
# ---------------------------------------------------------------------------
_NORMALIZACOES_TAXA = [
    (lambda t: 'CONDOMINIO' in t or 'CONDOMÍNIO' in t,                                        'CONDOMINIO'),
    (lambda t: 'GÁS' in t or 'GAS' in t,                                                      'GAS'),
    (lambda t: 'ELEVADOR' in t and 'MELHORIAS' not in t and 'REFORMA' not in t,               'MANUTENCAO ELEVADOR'),
    (lambda t: ('FERIAS' in t or 'SALARIO' in t or 'SAL.' in t) and
               ('13' in t or 'FUNCIONARIO' in t or 'FUNC' in t),                              'FERIAS/13 SAL'),
    (lambda t: 'ENERGIA' in t or ('CONSUMO' in t and 'ENERGIA' in t),                         'ENERGIA ELETRICA'),
    (lambda t: 'COTA' in t and 'ALA' in t,                                                    'CONDOMINIO'),
    (lambda t: 'PORTARIA' in t,                                                                'PORTARIA'),
    (lambda t: 'AGUA' in t and 'PURIFICADOR' not in t,                                        'AGUA'),
    (lambda t: 'AGUA' in t and 'M' in t,                                                       'AGUA M³'),
    (lambda t: 'FUNDO' in t and 'OBRAS' in t,                                                 'FUNDO OBRAS'),
    (lambda t: 'FUNDO' in t and any(x in t for x in 
    ('MELHORIAS', 'LAZER', 'JANELA', 'ELETRIC')),                                              'FUNDO MELHORIAS'),
    (lambda t: 'OBRA' in t and 'FUNDO' not in t,                                              'OBRAS'),
    (lambda t: 'FUNDO' in t and 'RESERVA' in t,                                               'FUNDO RESERVA'),
    (lambda t: 'FDO.' in t and 'RESERVA' in t,                                               'FUNDO RESERVA'),
    (lambda t: 'FDO.' in t and 'LAZER' in t,                                               'FUNDO MELHORIAS'),
    (lambda t: 'PURIFICATTA' in t,                                                              'PURIFICATTA'),
    (lambda t: ('LAUDO' in t and 'PREDIAL' in t) or 'PPCI' in t,                              'LAUDO PPCI'),
    (lambda t: 'REFORMA' in t or 'MELHORIAS' in t and 'ELEVADOR' in t,                        'MELHORIAS ELEVADORES'),
    (lambda t: ('MANUT' in t and 'CONSERV' in t) or ('FECHO' in t and 'JANELA' in t)
               or ('FUNDO' in t and 'MANUTEN' in t),                                          'FUNDO MANUTENCAO'),
]


def _normalizar_taxa(taxa: str) -> str:                                 
    t = taxa.upper()
    for condicao, nome in _NORMALIZACOES_TAXA:
        if condicao(t):
            return nome
    return taxa.strip()


# ---------------------------------------------------------------------------
# Extração de taxas — FATURA
# ---------------------------------------------------------------------------
def _extrair_taxas_fatura(texto):
    linhas     = texto.split('\n')
    taxas      = []
    lendo      = False
    valor_re   = re.compile(r'(\d{1,3}(?:\.\d{3})*,\d{2})')
    parcelas_re = re.compile(r'(\d{1,2})/(\d{1,2})$')

    for linha in linhas:
        linha = linha.strip()
        if not lendo:
            if re.search(r'Descrição\s+Valor', linha):
                lendo = True
            continue
        if re.match(r'^TOTAL', linha):
            break

        matches = list(valor_re.finditer(linha))
        if not matches:
            continue

        ultimo = matches[-1]
        valor  = ultimo.group(1)
        nome   = linha[:ultimo.start()].strip()

        parcela_atual = total_parcelas = 1
        pm = parcelas_re.search(nome)
        if pm:
            parcela_atual  = int(pm.group(1))
            total_parcelas = int(pm.group(2))
            nome = parcelas_re.sub('', nome).strip()

        taxas.append({
            'taxa': _normalizar_taxa(nome),                    
            'valor': valor,
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas


# ---------------------------------------------------------------------------
# Extração de taxas — RECIBO
# ---------------------------------------------------------------------------
def _extrair_taxas_recibo(texto):
    linhas      = texto.strip().split('\n')
    texto_taxas = ''
    lendo       = False
    parcelas_re = re.compile(r'(\d{1,2})\s*/\s*(\d{1,2})')

    for linha in linhas:
        linha = linha.strip()
        if linha.upper() == 'TAXAS':
            lendo = True
            continue
        if lendo and (linha.startswith('MENSAGENS') or linha.startswith('DEMONSTRATIVO')):
            break
        if lendo:
            texto_taxas += ' ' + linha

    texto_taxas = re.sub(r'\([^)]*\)', '', texto_taxas)
    taxas = []

    for nome, valor in re.findall(r'([A-ZÀ-Úa-zà-ú\s/0-9-]+?)\s+(\d+(?:[.,]\d{2}))', texto_taxas):
        nome = nome.strip().replace('FDO', 'FUNDO')
        nome = re.sub(r'\s+', ' ', nome)


        parcela_atual = total_parcelas = 1
        pm = parcelas_re.search(nome)
        if pm:
            parcela_atual  = int(pm.group(1))
            total_parcelas = int(pm.group(2))
            nome = parcelas_re.sub('', nome).strip()

        taxas.append({
            'taxa': _normalizar_taxa(nome),                                   
            'valor': valor.replace('.', ','),
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas

# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def extrair_boleto(caminho_pdf: Path, logger) -> Boleto:
    """
    Lê um PDF da Barcellos e retorna um Boleto com todos os campos extraídos.
    Move o arquivo para PASTA_PROCESSADOS ao final.
    """
    nome_arquivo = Path(caminho_pdf).name
    logger.sucesso("Extração dos Dados", f"Iniciando extração do boleto {nome_arquivo}")

    reader = PdfReader(caminho_pdf)
    texto  = "\n".join(page.extract_text() or "" for page in reader.pages)
    linhas = texto.split('\n')
    # Remove as primeiras 7 linhas (cabeçalho bancário que contém o CNPJ da Barcellos —
    # queremos o CNPJ do condômino, que aparece mais abaixo)
    subtexto = "\n".join(linhas[7:]) if len(linhas) > 7 else texto

    cnpj_imobiliaria = _safe_search(_CNPJ, texto)
    competencia      = _safe_search(_COMPETENCIA, texto) or "extra"
    codigo_barras    = linha_digitavel_para_codigo_barras(_safe_search(_CODIGO_BARRAS, texto))
    nome_predio      = _safe_search(_NOME_PREDIO, texto, 1)
    vencimento       = _safe_search(_VENCIMENTO, texto)

    endereco_imovel = complemento = taxas = valor_total = nome_condomino = documento_condomino = None

    texto_lower = texto.lower()

    if "recibo" in texto_lower:
        endereco_imovel     = _safe_search(_ENDERECO_REC, texto, 1)
        complemento         = _safe_search(_COMPLEMENTO_REC, texto, 1)
        taxas               = _extrair_taxas_recibo(texto)
        nome_condomino      = _safe_search(_NOME_COND_REC, texto, 1)
        documento_condomino = _safe_search(_DOCUMENTOS, subtexto)
        for linha in linhas:
            if "total" in linha.lower():
                m = re.search(r'\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}', linha)
                if m:
                    valor_total = m.group().replace('.', ',')
                break

    elif "fatura" in texto_lower:
        taxas               = _extrair_taxas_fatura(texto)
        valor_total         = _safe_search(_VALOR, texto)
        nome_condomino      = _safe_search(_NOME_COND_FAT, texto, 1)
        documento_condomino = _safe_search(_DOCUMENTOS, subtexto)
        for i, linha in enumerate(linhas):
            if "unidade" in linha.lower():
                if i + 1 < len(linhas): complemento     = linhas[i + 1].strip()
                if i + 3 < len(linhas): endereco_imovel = linhas[i + 3].strip()
                break

    else:
        logger.erro("Extração dos Dados", f"Tipo de boleto não identificado em '{nome_arquivo}'")

    # Loga campos faltando
    campos = {
        "CNPJ": cnpj_imobiliaria, "Competência": competencia,
        "Código de Barras": codigo_barras, "Nome do Prédio": nome_predio,
        "Vencimento": vencimento, "Endereço": endereco_imovel,
        "Complemento": complemento, "Nome Condômino": nome_condomino,
        "Documento Condômino": documento_condomino,
        "Valor Total": valor_total, "Taxas": taxas,
    }
    faltando = [c for c, v in campos.items() if not v]
    if faltando:
        logger.erro("Extração dos Dados",
                    f"'{nome_arquivo}' — campos faltando: {', '.join(faltando)}")
    else:
        logger.sucesso("Extração dos Dados", f"'{nome_arquivo}' extraído com sucesso.")

    # Move para processados
    shutil.move(str(caminho_pdf), str(PASTA_PROCESSADOS / nome_arquivo))

    return Boleto(nome_arquivo, cnpj_imobiliaria, endereco_imovel, complemento,
                  taxas, valor_total, competencia, codigo_barras,
                  nome_predio, nome_condomino, documento_condomino, vencimento)
