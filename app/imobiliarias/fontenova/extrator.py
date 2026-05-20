"""
Extração de dados dos PDFs da Fonte Nova.

A Fonte Nova gera PDFs em dois layouts distintos:

  LAYOUT ANTIGO (virtualimobi): tabela de duas colunas lado a lado
    - Cabeçalho: "Histórico Valor Histórico Valor"
    - Taxas intercaladas em duas colunas na mesma linha

  LAYOUT NOVO (recibo): coluna única, uma taxa por linha
    - Cabeçalho: "RECIBO DO PAGADOR"
    - Cada linha: NOME_TAXA [parcela] valor

A função extrair_boleto() detecta o layout automaticamente e
despacha para o parser correto.
"""

import re
import shutil
from pathlib import Path

import pdfplumber
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from app.classes.boleto import Boleto
from app.imobiliarias.fontenova.config import PASTA_PROCESSADOS
from app.utils.formatarCodigoBarras import extrai_valor_codigo_barras, extrai_vencimento, linha_digitavel_para_codigo_barras

# ---------------------------------------------------------------------------
# Normalização de nomes de taxas
# ---------------------------------------------------------------------------
_NORMALIZACOES_TAXA = [
    (lambda t: 'CONDOMINIO' in t or 'CONDOMÍNIO' in t,                                       'CONDOMINIO'),
    (lambda t: 'GÁS' in t or 'GAS' in t,                                                     'GÁS'),
    (lambda t: 'DMAE' in t,                                                                   'DMAE'),
    (lambda t: 'SEG.' in t and 'INCENDIO' in t,                                               'SEGURO INCENDIO'),
    (lambda t: 'SEGURO' in t,                                                                 'SEGURO INCENDIO'),
    (lambda t: 'FUNDO' in t and 'OBRAS' in t and 'JANELAS' not in t,                         'FUNDO OBRAS'),
    (lambda t: 'FUNDO' in t and 'MANUTEN' in t,                                              'FUNDO MANUTENÇAO'),
    (lambda t: ('FERIAS' in t or 'SALARIO' in t or 'SAL.' in t) and
               ('13' in t or 'FUNCIONARIO' in t or 'FUNC' in t),                             'FERIAS/13 SAL'),
    (lambda t: 'REVITALIZ' in t and 'PRED' in t,                                              'REVITALIZACAO'),
    (lambda t: 'REFORMA' in t and 'FACHADA' in t,                                            'FACHADA - SERVIÇOS DE REPAROS'),
    (lambda t: 'BOX' in t,                                                                    'BOX'),
    (lambda t: 'DESCONTO' in t and 'SINDICA' not in t and 'PPCI' not in t,                   'DESCONTO'),
    (lambda t: 'RESTAURA' in t,                                                               'OBRAS'),
    (lambda t: 'RECUP' in t and ('SALDO' in t or 'DEVEDOR' in t),                            'RECUPERACAO'),
    (lambda t: 'REC' in t and ('SALDO' in t or 'DEVEDOR' in t),                              'RECUPERACAO'),
    (lambda t: 'RECUP' in t and 'PISO' in t,                                                 'OBRAS'),
    (lambda t: 'REC' in t and 'PISO' in t,                                                   'OBRAS'),
    (lambda t: 'RECUPERAÇAO' in t and 'FUNDO' in t,                                          'RECUPERACAO'),
    (lambda t: 'PORTARIA' in t,                                                               'PORTARIA -/ FAXINA'),
    (lambda t: 'VIGILANCIA' in t,                                                             'VIGILANCIA DE RUA'),
    (lambda t: 'FUNDO' in t and 'PINTURA' in t,                                              'FUNDO PINTURA'),
    (lambda t: 'PINTURA' in t and 'FACHADA' in t,                                            'FUNDO PINTURA'),
    (lambda t: 'SINDICO' in t,                                                                'SINDICO PROFISSIONAL'),
    (lambda t: 'FUNDO' in t and 'RESERVA' in t,                                              'FUNDO RESERVA'),
    (lambda t: 'AGUA' in t and 'ESGOTO' in t,                                                'AGUA E ESGOTO'),
    (lambda t: 'MODER.' in t and 'ELEVADOR' in t,                                            'MELHORIAS ELEVADORES'),
    (lambda t: 'FUNDO' in t and 'MELHORIAS' in t,                                            'FUNDO MELHORIAS'),
    (lambda t: 'JANELAS' in t,                                                                'FUNDO MELHORIAS'),
    (lambda t: 'MELHORIAS' in t,                                                              'FUNDO MELHORIAS'),
    (lambda t: 'SERVIÇO' in t and 'LIXEIRAS' in t,                                           'OBRAS'),
    (lambda t: 'REFORMA' in t and 'FRENTE' in t,                                             'FACHADA - SERVIÇOS DE REPAROS'),
    (lambda t: 'SERVIÇOS' in t and 'FACHADA' in t,                                           'FACHADA - SERVIÇOS DE REPAROS'),
    (lambda t: 'IMPERMEABILI' in t,                                                           'IMPERMEABILIZACAO'),
    (lambda t: 'PINTURA' in t and 'FUNDO' not in t and 'FACHADA' not in t,                   'PINTURA'),
    (lambda t: 'RESCIS' in t and 'FUNC' in t,                                                 'RECISAO FUNCIONARIO'),
]

def _safe_search(pattern, text, group=1, flags=re.IGNORECASE | re.MULTILINE):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def _normalizar_taxa(taxa: str) -> str:
    t = taxa.upper()
    for condicao, nome in _NORMALIZACOES_TAXA:
        if condicao(t):
            return nome
    return taxa.strip()


def _limpar_documento(documento: str) -> str | None:
    if not documento:
        return None
    # Remove só separadores de formatação, preserva dígitos e asteriscos
    doc = re.sub(r'[.\-/\s]', '', documento)
    if not doc:
        return None
    return doc


# ---------------------------------------------------------------------------
# layout ANTIGO — duas colunas (virtualimobi)
# ---------------------------------------------------------------------------
def _extrair_taxas_layout_antigo(texto: str) -> list:
    """
    Isola o bloco entre 'Histórico Valor Histórico Valor' e 'Total até o vencimento',
    lineariza as duas colunas e consome token a token.
    """
    inicio = re.search(r'Histórico\s+Valor\s+Histórico\s+Valor', texto, re.IGNORECASE)
    fim    = re.search(r'Total\s+até\s+o\s+vencimento', texto, re.IGNORECASE)
    if not inicio or not fim:
        return []

    linha = texto[inicio.end():fim.start()].replace('\n', ' ')

    # Normaliza CONDOMINIO
    linha = re.sub(
        r'(CONDOM[IÍ]NIO)\s*(?:[-–—]\s*)?(?:(?:BLOCO\s+)?[A-Z\.])?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        r'CONDOMINIO \2',
        linha, flags=re.IGNORECASE
    )
    # GÁS com CONDOMINIO embutido
    linha = re.sub(
        r'G[ÁA]S\s*[-–—]?\s*Leituras:.*?Dt\.?ant:\d{2}/\d{2}/\d{2}\s*'
        r'CONDOM[IÍ]NIO\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*'
        r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*atual:\d{2}/\d{2}/\d{2}',
        r'CONDOMINIO \1 GÁS \2',
        linha, flags=re.IGNORECASE
    )
    # GÁS
    linha = re.sub(
        r'G[ÁA]S\s*[-–—]?\s*Leituras:.*?atual:\d{2}/\d{2}/\d{2}\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        r'GÁS \1',
        linha, flags=re.IGNORECASE
    )
    # Valores negativos: (-)100,00 → -100,00
    linha = re.sub(r'\(-\)\s*(\d{1,3}(?:\.\d{3})*,\d{2})', r'-\1', linha)

    tokens     = linha.split()
    valor_re   = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}$')
    parcela_re = re.compile(r'^(\d{1,2})/(\d{1,2})$')
    taxas          = []
    nome_atual     = ""
    valor_atual    = None
    parcela_atual  = 1
    total_parcelas = 1
    extraiu        = False

    for token in tokens:
        if not nome_atual:
            nome_atual = token
            continue
        if valor_re.match(token):
            valor_atual = token
            extraiu     = True
            continue
        if parcela_re.match(token):
            pm = parcela_re.match(token)
            if not valor_atual:
                parcela_atual, total_parcelas = int(pm.group(1)), int(pm.group(2))
                extraiu = True
            else:
                parcela_atual, total_parcelas = int(pm.group(1)), int(pm.group(2))
                taxas.append({
                    'taxa': _normalizar_taxa(nome_atual.strip()),
                    'valor': valor_atual.strip(),
                    'parcela_atual': parcela_atual,
                    'total_parcelas': total_parcelas,
                })
                nome_atual = ""; valor_atual = None
                parcela_atual = total_parcelas = 1; extraiu = False
            continue
        if extraiu and valor_atual:
            taxas.append({
                'taxa': _normalizar_taxa(nome_atual.strip()),
                'valor': valor_atual.strip(),
                'parcela_atual': parcela_atual,
                'total_parcelas': total_parcelas,
            })
            nome_atual = token; valor_atual = None
            parcela_atual = total_parcelas = 1; extraiu = False
            continue
        if not extraiu:
            nome_atual += " " + token

    if nome_atual and valor_atual:
        taxas.append({
            'taxa': _normalizar_taxa(nome_atual.strip()),
            'valor': valor_atual.strip(),
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas


# ---------------------------------------------------------------------------
# layout NOVO — coluna única, uma taxa por linha
# ---------------------------------------------------------------------------
def _extrair_taxas_layout_novo(texto: str) -> list:
    """
    Lê linha a linha entre 'Demonstrativo da cobrança' e 'Total até o vencimento'.
    Cada linha tem: NOME_TAXA [parcela] valor
    O GÁS ocupa uma linha inteira com a descrição de leitura.
    """
    inicio = re.search(r'Demonstrativo da cobran', texto, re.IGNORECASE)
    fim    = re.search(r'Total\s+até\s+o\s+vencimento', texto, re.IGNORECASE)
    if not inicio or not fim:
        return []

    bloco  = texto[inicio.end():fim.start()]
    linhas = [l.strip() for l in bloco.split('\n') if l.strip()]

    valor_re   = re.compile(r'(\d{1,3}(?:\.\d{3})*,\d{2})$')
    parcela_re = re.compile(r'(\d{1,2})/(\d{1,2})')
    gas_re     = re.compile(
        r'G[ÁA]S\s*[-–]?\s*Leituras:.*?atual:\s*\d{2}/\d{2}/\d{2}\s+(\d{1,3}(?:\.\d{3})*,\d{2})',
        re.IGNORECASE
    )

    taxas = []
    for linha in linhas:
        # GÁS com descrição longa
        m_gas = gas_re.search(linha)
        if m_gas:
            taxas.append({
                'taxa': 'GÁS',
                'valor': m_gas.group(1),
                'parcela_atual': 1,
                'total_parcelas': 1,
            })
            continue

        # Linha normal: termina com valor numérico
        m_val = valor_re.search(linha)
        if not m_val:
            continue

        valor = m_val.group(1)
        nome  = linha[:m_val.start()].strip()

        # Parcela embutida no nome (ex: "SEG. INCENDIO 05/6" ou "REFORMA FACHADA 1/60")
        parcela_atual = total_parcelas = 1
        m_par = parcela_re.search(nome)
        if m_par:
            parcela_atual  = int(m_par.group(1))
            total_parcelas = int(m_par.group(2))
            nome = nome[:m_par.start()].strip()

        if not nome:
            continue
        taxas.append({
            'taxa': _normalizar_taxa(nome),
            'valor': valor,
            'parcela_atual': parcela_atual,
            'total_parcelas': total_parcelas,
        })
    return taxas


# ---------------------------------------------------------------------------
# Extração de campos por layout
# ---------------------------------------------------------------------------
def _detectar_layout(texto: str) -> str:
    if re.search(r'RECIBO DO PAGADOR', texto, re.IGNORECASE):
        return 'novo'
    return 'antigo'


def _extrair_campos_layout_antigo(texto: str) -> dict:
    nome_predio = _safe_search(r'CONDOM[IÍ]NIO\s*[:\-]?\s*\d+\s*-\s*([A-Z.\s]+?)\s*(?:\n|$)', texto)
    endereco    = _safe_search(r'CONDOM[IÍ]NIO[^\r\n]*[\r\n]+([A-ZÁÉÍÓÚÃÕÇ\s,.]+?,\s*\d+)', texto)
    nome_cond   = _safe_search(r'COND[ÔO]MINO\s*[:\-]?\s*[\r\n]*([A-ZÁÉÍÓÚÃÕÇ.\s\/\-]+?)\s*(?:UNIDADE|COMPETÊNCIA|$)', texto)
    complemento = _safe_search(r'UNIDADE\s*:\s*[\r\n]*([A-Z0-9.\s\-]+?)\s*(?:COMPETÊNCIA|$)', texto)
    competencia = _safe_search(r'Compet[eê]ncia\s*[:\-]?\s*(\d{2}\/\d{4})', texto) or 'extra'
    vencimento  = _safe_search(r'Vencimento:\s*(\d{2}/\d{2}/\d{4})', texto)
    documento   = _limpar_documento(_safe_search(r'CPF\/?CNPJ\s*[:\-]?\s*([0-9\s.\-\/\*]+)', texto))
    return dict(nome_predio=nome_predio, endereco=endereco, nome_cond=nome_cond,
                complemento=complemento, competencia=competencia,
                vencimento=vencimento, documento=documento)


def _extrair_campos_layout_novo(texto: str) -> dict:
    # nome_predio: para antes de VENCIMENTO ou V E N C I M E N T O ou \n
    nome_predio = _safe_search(
        r'Condom[íi]nio\s*:\s*\d+\s*-\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç.\s]+?)'
        r'(?:\s+V(?:\s+E\s+N\s+C\s+I\s+M\s+E\s+N\s+T\s+O|ENCIMENTO)|\n)',
        texto)
    endereco    = _safe_search(
        r'Condom[íi]nio\s*:[^\n]+\n([A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç\s,.]+?,\s*\d+)',
        texto)
    # Condômino: pega tudo após o ":" até fim de linha (sem exigir data na mesma linha)
    nome_cond   = _safe_search(
        r'Cond[oô]mino\s*:\s*(.+?)(?:\s+\d{2}/\d{2}/\d{4})?\s*$',
        texto, flags=re.IGNORECASE | re.MULTILINE)
    complemento = _safe_search(r'Unidade\s*:?\s*([a-zA-Z0-9 ]+?)\s*\W*CPF', texto)
    competencia = _safe_search(r'Compet[êe]ncia\s*:\s*(\d{2}/\d{4})', texto) or 'extra'
    # Vencimento: tenta na linha do pagamento, depois na Unidade, depois em qualquer linha após Condômino
    vencimento  = _safe_search(r'PAGAMENTO EM[^\n]+\n(\d{2}/\d{2}/\d{4})', texto)
    if not vencimento:
        vencimento = _safe_search(r'Unidade\s*:[^\n]+(\d{2}/\d{2}/\d{4})', texto)
    if not vencimento:
        vencimento = _safe_search(r'Cond[oô]mino\s*:[^\n]+(\d{2}/\d{2}/\d{4})', texto)
    # Documento vem no rodapé: "NOME CPF/CNPJ:xxx"
    documento   = _limpar_documento(_safe_search(r'CPF/CNPJ:\s*([0-9\*\.\-\/]+)', texto))
    return dict(nome_predio=nome_predio, endereco=endereco, nome_cond=nome_cond,
                complemento=complemento, competencia=competencia,
                vencimento=vencimento, documento=documento)


def _extrair_texto_pdf(caminho: Path, logger) -> str:
    """
    Tenta extrair texto via pdfplumber. Se o texto for vazio ou muito curto
    (PDF vetorial sem texto extraível), renderiza a página como imagem usando
    o próprio pdfplumber e aplica OCR com Tesseract.
    Não depende de Poppler — apenas pdfplumber + pytesseract.
    """
    with pdfplumber.open(caminho) as pdf:
        texto = "\n".join(page.extract_text() or "" for page in pdf.pages)

        if len(texto.strip()) > 100:
            return texto

        logger.sucesso("Extração dos Dados", "PDF sem texto — aplicando OCR.")
        paginas_ocr = []
        for page in pdf.pages:
            pil_img = page.to_image(resolution=200).original
            paginas_ocr.append(pytesseract.image_to_string(pil_img, lang='por'))
        return "\n".join(paginas_ocr)


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def extrair_boleto(caminho_pdf: Path, logger) -> Boleto:
    """
    Lê um PDF da Fonte Nova, detecta o layout automaticamente e
    retorna um Boleto com todos os campos extraídos.
    Se o PDF for escaneado (sem texto), aplica OCR automaticamente.
    Move o arquivo para PASTA_PROCESSADOS ao final.
    """
    caminho_pdf  = Path(caminho_pdf)
    nome_arquivo = caminho_pdf.name
    logger.sucesso("Extração dos Dados", f"Iniciando extração do boleto {nome_arquivo}")

    texto  = _extrair_texto_pdf(caminho_pdf, logger)
    layout = _detectar_layout(texto)
    logger.sucesso("Extração dos Dados", f"Layout detectado: {layout}")

    if layout == 'novo':
        campos = _extrair_campos_layout_novo(texto)
        taxas  = _extrair_taxas_layout_novo(texto)
    else:
        campos = _extrair_campos_layout_antigo(texto)
        taxas  = _extrair_taxas_layout_antigo(texto)

    cnpj_imob = _safe_search(
        r'FONTE\s+NOV\s*A\s+IMOVEIS\s+(?:L\s*TDA|LTDA)\s*(?:CNPJ\s*:)?\s*[-–]?\s*'
        r'(\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2})',
        texto)
    if cnpj_imob:
        cnpj_imob = re.sub(r'\D', '', cnpj_imob)

    # Tenta código de barras direto (47 dígitos) — layout antigo
    codigo_barras = _safe_search(r'(\d{47})', texto)
    # Tenta linha digitável — layout novo
    linha_dig = _safe_search(
        r'(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d{1}\s+\d{14})',
        texto)
    if linha_dig:
        compt = extrai_vencimento(linha_dig)
        #print(f"Competência extraída: {compt}")
        clean_codigo = re.sub(r'\D', '', linha_dig)
        valor_bruto = extrai_valor_codigo_barras(clean_codigo)
        #print(f"Codigo de barras normal: {valor_bruto}")
        try:
            codigo_barras = linha_digitavel_para_codigo_barras(linha_dig)
        except Exception:
            codigo_barras = None

    valor_total   =  valor_bruto
    if taxas:
        for t in taxas:
            t['taxa'] = _normalizar_taxa(t['taxa']) 
            logger.sucesso("Extração dos Dados", f"Taxa encontrada: {t.get('taxa')} — Valor: {t.get('valor')}")
    else:
        logger.erro("Extração dos Dados", "Nenhuma taxa encontrada no boleto Fonte Nova.")

    campos_validacao = {
        "CNPJ": cnpj_imob, "Competência": compt,
        "Código de Barras": codigo_barras, "Nome do Prédio": campos['nome_predio'],
        "Vencimento": compt, "Complemento": campos['complemento'],
        "Nome Condômino": campos['nome_cond'], "Documento Condômino": campos['documento'],
        "Valor Total": valor_total, "Taxas": taxas,
    }
    faltando = [c for c, v in campos_validacao.items() if not v]
    if faltando:
        logger.erro("Extração dos Dados",
                    f"'{nome_arquivo}' — campos faltando: {', '.join(faltando)}")
    else:
        logger.sucesso("Extração dos Dados", f"'{nome_arquivo}' extraído com sucesso.")

    shutil.move(str(caminho_pdf), str(PASTA_PROCESSADOS / nome_arquivo))

    return Boleto(nome_arquivo, cnpj_imob, campos['endereco'], campos['complemento'],
                  taxas, valor_total, compt, codigo_barras,
                  campos['nome_predio'], campos['nome_cond'], campos['documento'],
                  compt)