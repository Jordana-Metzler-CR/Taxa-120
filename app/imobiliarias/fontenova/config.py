from pathlib import Path

CNPJ              = "92551738000165"
NOME              = "Fonte Nova"
CAMINHO_IMOBILIAR = "fontenova.com.br"

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
# Menores que Barcellos porque o PDF da Fonte Nova não tem endereço completo,
# o que reduz a pontuação máxima atingível
LIMIAR_PONTUACAO         = 85
LIMIAR_CAMPOS_PRINCIPAIS = 90
