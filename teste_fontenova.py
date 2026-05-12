from app.imobiliarias.fontenova.extrator import extrair_boleto
from app.utils.normalizacao import normalizar_competencia

class LoggerFake:
    def sucesso(self, etapa, msg):
        print(f"[SUCESSO] {etapa} - {msg}")

    def erro(self, etapa, msg):
        print(f"[ERRO] {etapa} - {msg}")


pdf_path = r"\\192.168.150.12\dados\CREDITO REAL\SETORES\CONTABILIDADE FISCAL\SETOR\Condomínios\Novas Locações\TAXA 120\PROCESSADOS\Boletos Fonte Nova 10_05_2026_pagina_24.pdf"

logger = LoggerFake()

boleto = extrair_boleto(pdf_path, logger)

print("\n=== RESULTADO ===")
print("Nome prédio:", boleto.nome_predio)
print("Endereço:", boleto.endereco_imovel)
print("Complemento:", boleto.complemento)
print("Condômino:", boleto.nome_condomino)
print("Documento:", boleto.documento_condomino)
print(f"Competência extraída: {boleto.competencia}")
print(f"Competência normalizada: {normalizar_competencia(boleto.competencia)}")
print("Vencimento:", boleto.vencimento)
print("Valor total:", boleto.valor_total)
print("Código de barras:", boleto.codigo_barras)

print("\n=== TAXAS ===")
for taxa in boleto.taxas:
    print(taxa)