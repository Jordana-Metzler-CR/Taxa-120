from pprint import pprint

from app.imobiliarias.barcellos.extrator import extrair_boleto
from app.utils.normalizacao import normalizar_competencia
from app.service.lancar_taxas import URL, _processar_boleto
from app.imobiliarias import registry
from app.config import env

import psycopg2
import requests


class LoggerFake:
    def sucesso(self, etapa, msg):
        print(f"[SUCESSO] {etapa} - {msg}")

    def erro(self, etapa, msg):
        print(f"[ERRO] {etapa} - {msg}")

    def alerta(self, etapa, msg):
        print(f"[ALERTA] {etapa} - {msg}")


class RelatorioFake:
    def registrar(self, **kwargs):
        pass


pdf_path = r"\\192.168.150.12\dados\CREDITO REAL\SETORES\CONTABILIDADE FISCAL\SETOR\Condomínios\Novas Locações\TAXA 120\PROCESSADOS\Boletos Barcellos 10_05_2026_pagina_21.pdf"

logger = LoggerFake()

boleto = extrair_boleto(pdf_path, logger)

print("\n=== RESULTADO ===")
print("Nome prédio:", boleto.nome_predio)
print("Endereço:", boleto.endereco_imovel)
print("Complemento:", boleto.complemento)
print("Condômino:", boleto.nome_condomino)
print("Documento:", boleto.documento_condomino)
print(f"Competência extraída: {boleto.competencia}")
print(f"Competência normalizada: {normalizar_competencia(boleto.vencimento)}")
print("Vencimento:", boleto.vencimento)
print("Valor total:", boleto.valor_total)
print("Código de barras:", boleto.codigo_barras)

print("\n=== TAXAS ===")
for taxa in boleto.taxas:
    print(taxa)


# =========================================================
# TESTE DA LISTA DE PREVISTOS
# =========================================================

cnpj = "92842921000110"  # ajuste se necessário

imob = registry.get(cnpj)

# LOGIN IMOBILIAR
login = requests.post(env("URL_IMOBILIAR"), json={
    "Header": {"Action": "LOGIN"},
    "Body": {
        "IMOB_ID": "CREDREAL",
        "USER_ID": env("USER_IMOBILIAR"),
        "USER_PASS": env("PASS_IMOBILIAR")
    }
}).json()
session_id = login['Header']['SessionId']

# CONEXÃO BANCO
conn = psycopg2.connect(
    host=env("DB_HOST"),
    port=env("DB_PORT"),
    database=env("DB_BANCO"),
    user=env("DB_USER"),
    password=env("DB_SENHA")
)

cursor = conn.cursor()

cursor.execute("""
    SELECT t.taxa_id, t.descricao_taxa
    FROM taxa_120_taxas t
    INNER JOIN taxa_120_administradoras a
        ON t.id_administradora = a.id
    WHERE a.cnpj = %s
""", (cnpj,))

tabela_taxas = cursor.fetchall()

cursor.execute(
    "SELECT id FROM taxa_120_administradoras WHERE cnpj = %s",
    (cnpj,)
)

row_adm = cursor.fetchone()
id_administradora = row_adm[0] if row_adm else None

competencia = normalizar_competencia(boleto.vencimento)

# ==========================================
# BUSCA COD_IMOVEL
# ==========================================

cursor.execute(
    """
    SELECT cod_imovel
    FROM taxa_120_imoveis
    WHERE condominio = %s
      AND endereco = %s
      AND complemento = %s
      AND nome_locador = %s
      AND id_administradora = %s
    LIMIT 1
    """,
    (
        boleto.nome_predio,
        boleto.endereco_imovel,
        boleto.complemento,
        boleto.nome_condomino,
        id_administradora
    )
)

row = cursor.fetchone()
cod_imovel = int(row[0]) if row else 0

print("\n=== COD IMÓVEL ===")
print(cod_imovel)



# ==========================================
# CONSULTA CONTRATO
# ==========================================

resp_contrato = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "LOCACAO_CONTRATO_IMOVEL_CONSULTAR"},
        "Body":   {"CodImovel": cod_imovel}
    }).json()

cod_contrato     = resp_contrato['Body']['CodContratoLoc']
#pprint(resp_contrato, width=200)
# ==========================================
# CONSULTA PREVISTOS
# ==========================================

payload_prev = {
    "Header": {
        "SessionId": session_id,
        "Action": "LOCACAO_LANCTO_COND_CONSULTAR"
    },
    "Body": {
        "CodImovel": cod_imovel,
        "Competencia": competencia,
        "CodContratoLoc": cod_contrato
    }
}

#print("\n=== PAYLOAD PREVISTOS ENVIADO ===")
#pprint(payload_prev, width=200)

resp_prev = requests.post(URL, json=payload_prev).json()

print("\n=== RESPOSTA PREVISTOS COMPLETA ===")
pprint(resp_prev, width=200)

lista_prev = resp_prev.get("Body", {}).get("Lista", [])

print("\n=== LISTA DE PREVISTOS ===")

if not lista_prev:
    print("Nenhum previsto encontrado.")
else:
    for i, item in enumerate(lista_prev, start=1):
        print(f"\n--- PREVISTO {i} ---")
        print("CodTaxa:", item.get("CodTaxa"))
        print("PrevisaoReal:", item.get("PrevisaoReal"))
        print("NumeroLanctoItem:", item.get("NumeroLanctoItem"))
        print("ValorPrevisao:", item.get("ValorPrevisao"))
        print("ValorReal:", item.get("ValorReal"))

        #print("\nOBJETO COMPLETO:")
        #pprint(item, width=200)
        
# ==========================================
# LOGOUT IMOBILIAR
# ==========================================
       
requests.post(env("URL_IMOBILIAR"), json={
    "Header": {"SessionId": session_id, "Action": "LOGOUT"},
    "Body": {}
})