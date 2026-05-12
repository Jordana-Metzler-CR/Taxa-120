from pathlib import Path

CNPJ             = "92842921000110"
NOME             = "Barcellos"
CAMINHO_IMOBILIAR = "barcellos.com.br"   # subdomínio usado na URL do Imobiliar

# Pasta de onde os PDFs fragmentados são lidos para extração
PASTA_PDFS = Path(
    r"\\192.168.150.12\dados\CREDITO REAL\SETORES"
    r"\CONTABILIDADE FISCAL\SETOR\Condomínios\Novas Locações\TAXA 120"
)

# Pasta para onde cada PDF é movido após ser extraído com sucesso
PASTA_PROCESSADOS = Path(
    r"\\192.168.150.12\dados\CREDITO REAL\SETORES"
    r"\CONTABILIDADE FISCAL\SETOR\Condomínios\Novas Locações\TAXA 120\PROCESSADOS"
)

# Limiares do algoritmo de similaridade
LIMIAR_PONTUACAO        = 85   # pontuação geral mínima para aceitar um match
LIMIAR_CAMPOS_PRINCIPAIS = 90  # média mínima dos campos principais quando a pontuação geral é baixa
