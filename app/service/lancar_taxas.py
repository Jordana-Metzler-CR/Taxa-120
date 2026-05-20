"""
Serviço principal de lançamento de taxas.

Recebe o CNPJ da imobiliária e executa o fluxo completo:
  1. Lê o inbox do email (serviço na porta 5001)
  2. Separa os PDFs por página
  3. DE-PARA: extrai boletos e mapeia imóveis
  4. Lança taxas no Imobiliar (login → loop por boleto → logout)
  5. Abre o relatório operacional automaticamente
"""

import os
import pprint
import requests
import psycopg2
from datetime import datetime
from time import sleep
from urllib.parse import quote

from app.config import env
from app.core.logger_service import LoggerService
from app.repositories.db_logger import DBLogger
from app.imobiliarias import registry
from app.service.de_para import registrar_relacao_de_para
from app.utils.dispararEmail import enviarEmailRelatorio
from app.utils.normalizacao import normalizar_competencia, normalizar_valor_monetario
from app.utils.separarPdfs import processar_pdfs
from app.utils.relatorio import RelatorioOperacional
from app.utils.tunel import iniciar_tunel

URL = env("URL_IMOBILIAR")

_TAXAS_IGNORADAS = frozenset(['seguro conteudo', 'boleto registrado', 'porte'])
_DESCONTOS_ESPECIFICOS = {
    'DESCONTO - SINDICA.':   40,
    'DESCONTO - PAGTO PPCI': 750,
}


def _criar_logger():
    db_logger = DBLogger(
        host=env("DB_HOST"), port=env("DB_PORT"),
        dbname=env("DB_BANCO"), user=env("DB_USER"), password=env("DB_SENHA")
    )
    return LoggerService(db_logger)


def _extrair_erro(resp: dict) -> str:
    erros = resp.get('Body', {}).get('Erros', [])
    if isinstance(erros, list) and erros:
        return erros[0].get("Mensagem", "Erro desconhecido.")
    if isinstance(erros, dict):
        return erros.get("Mensagem", "Erro desconhecido.")
    return "Erro desconhecido."


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def lancar_taxas_imobiliar(cnpj: str):
    imob      = registry.get(cnpj)
    cfg       = imob["config"]
    logger    = _criar_logger()
    relatorio = RelatorioOperacional()

    processo_tunel = None
    conn           = None

    try:
        processo_tunel, url_publica = iniciar_tunel()

        # Aguarda o túnel estabilizar e valida antes de continuar
        sleep(10)
        for tentativa in range(5):
            try:
                r = requests.get(url_publica, timeout=5)
                logger.sucesso("Túnel", f"Túnel ativo: {url_publica}")
                break
            except Exception:
                logger.alerta("Túnel", f"Túnel ainda não disponível, tentativa {tentativa + 1}/5...")
                sleep(5)
        else:
            raise Exception("Túnel Cloudflare não ficou disponível após 5 tentativas.")

        # 1. Leitura do inbox
        resp = requests.get("http://localhost:5001/email/inbox/boletos@creditoreal.com.br/read")
        if resp.status_code == 200:
            logger.sucesso("Leitura de E-mail", "Inbox lida com sucesso.")
        else:
            logger.erro("Leitura de E-mail", f"Erro ao ler inbox. Status: {resp.status_code}")
            raise Exception("Falha na leitura do e-mail.")

        # 2. Separação dos PDFs
        pasta_origem = (
            rf"\\192.168.150.12\dados\CREDITO REAL\SETORES\INFORMATICA\RPA"
            rf"\boletoscreditoreal.com.br\{cfg.CAMINHO_IMOBILIAR}"
        )
        processar_pdfs(pasta_origem, cfg.PASTA_PDFS, logger)

        # 3. DE-PARA
        boletos = registrar_relacao_de_para(cnpj, logger)

        if not boletos:
            logger.alerta("Lançamento", "Nenhum boleto para lançar.")
            return

        # 4. Login no Imobiliar
        login = requests.post(URL, json={
            "Header": {"Action": "LOGIN"},
            "Body": {"IMOB_ID": "CREDREAL",
                     "USER_ID": env("USER_IMOBILIAR"),
                     "USER_PASS": env("PASS_IMOBILIAR")}
        }).json()

        if login['Header']['Status'] == 'Success' and not login['Header']['Error']:
            logger.sucesso("Login Imobiliar", "Login realizado com sucesso.")
        else:
            logger.erro("Login Imobiliar", "Falha no login.")
            raise Exception("Falha no login do Imobiliar.")

        session_id = login['Header']['SessionId']

        conn   = psycopg2.connect(
            host=env("DB_HOST"), port=env("DB_PORT"),
            database=env("DB_BANCO"), user=env("DB_USER"), password=env("DB_SENHA")
        )
        cursor = conn.cursor()

        cursor.execute("""
            SELECT t.taxa_id, t.descricao_taxa
            FROM taxa_120_taxas t
            INNER JOIN taxa_120_administradoras a ON t.id_administradora = a.id
            WHERE a.cnpj = %s
        """, (cnpj,))
        tabela_taxas = cursor.fetchall()

        cursor.execute(
            "SELECT id FROM taxa_120_administradoras WHERE cnpj = %s", (cnpj,)
        )
        row_adm = cursor.fetchone()
        id_administradora = row_adm[0] if row_adm else None

        for boleto in boletos:
            competencia = normalizar_competencia(boleto.vencimento)

            if not competencia:
                logger.erro(
                    "Lançamento",
                    f"Competência não encontrada no boleto {boleto.nome_boleto}. Pulando."
                )
                continue

            _processar_boleto(boleto, cursor, tabela_taxas, session_id,
                              competencia, url_publica, logger, relatorio, id_administradora)

        # 5. Logout
        logout = requests.post(URL, json={
            "Header": {"SessionId": session_id, "Action": "LOGOUT"}, "Body": {}
        }).json()
        if logout['Header']['Status'] == 'Success' and not logout['Header']['Error']:
            logger.sucesso("Logout Imobiliar", "Logout realizado com sucesso.")
        else:
            logger.erro("Logout Imobiliar", "Erro ao fazer logout.")

        cursor.close()
        conn.close()

        logger.sucesso("Lançamento", f"Fluxo finalizado com sucesso às {datetime.now()}")

        arquivo_operacional = f"relatorio_taxa120_{datetime.now().strftime('%Y%m%d')}.xlsx"
        relatorio.gerar_excel(arquivo_operacional)
        enviarEmailRelatorio(cfg.NOME, arquivo_operacional)

    finally:
        if processo_tunel:
            processo_tunel.terminate()


# ---------------------------------------------------------------------------
# Lançamento de um boleto
# ---------------------------------------------------------------------------
def _processar_boleto(boleto, cursor, tabela_taxas, session_id,
                      competencia, url_publica, logger, relatorio, id_administradora=None):

    tipo_boleto = "E" if boleto.competencia == "extra" else "N"

    cursor.execute(
        """SELECT cod_imovel FROM taxa_120_imoveis
           WHERE condominio = %s AND endereco = %s
             AND complemento = %s AND nome_locador = %s
             AND id_administradora = %s
           LIMIT 1""",
        (boleto.nome_predio, boleto.endereco_imovel,
         boleto.complemento, boleto.nome_condomino, id_administradora)
    )
    row        = cursor.fetchone()
    cod_imovel = int(row[0]) if row else 0

    if cod_imovel == 0:
        msg_nova = f"Necessário lançamento manual: não identificado o código de imóvel para {boleto.nome_boleto}."
        logger.alerta("Lançamento", f"Imóvel não mapeado para {boleto.nome_boleto}. Pulando.")
        relatorio.registrar(
            cod_imovel="NÃO MAPEADO",
            numero_taxa="",
            descricao_taxa=boleto.nome_boleto,
            valor="",
            status="Alerta",
            mensagem=msg_nova,
        )
        return

    taxas_boleto = sorted(
        boleto.taxas,
        key=lambda t: 0 if "condominio" in t.get("taxa", "").lower() else 1
    )

    if not taxas_boleto or taxas_boleto[0].get("taxa", "").lower() != 'condominio':
        msg_nova = f"Revisão manual: não foi encontrada taxa de condomínio para {boleto.nome_boleto}."
        logger.alerta("Lançamento", f"{boleto.nome_boleto} sem taxa de condomínio. Revisão manual.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="Condomínio",
            valor="",
            status="Alerta",
            mensagem=msg_nova,
        )
        return

    valor_total = normalizar_valor_monetario(boleto.valor_total)
    taxas_boleto[0]["valor"] = valor_total
    nomes = [t.get("taxa", "").lower() for t in taxas_boleto]

    if any("multa" in n for n in nomes):
        logger.alerta("Lançamento", f"{boleto.nome_boleto} contém multa. Revisão manual.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="Multa",
            valor="",
            status="Alerta",
            mensagem=f"Revisão manual: encontrada multa em {boleto.nome_boleto}.",
        )
        return

    if any("laudo pericial" in n for n in nomes):
        logger.alerta("Lançamento", f"{boleto.nome_boleto} contém LAUDO - PERICIAL. Revisão manual.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="LAUDO - PERICIAL",
            valor="",
            status="Alerta",
            mensagem=f"Revisão manual: encontrado laudo pericial em {boleto.nome_boleto}.",
        )
        return

    if any("desconto" in n for n in nomes):
        for desc in [t for t in taxas_boleto if "desconto" in t.get("taxa", "").lower()]:
            logger.alerta("Lançamento", f"{boleto.nome_boleto} contém taxa de desconto. Revisão manual.")
            relatorio.registrar(
                cod_imovel=cod_imovel,
                numero_taxa="",
                descricao_taxa=desc.get("taxa", ""),
                valor=desc.get("valor", ""),
                status="Alerta",
                mensagem=f"Revisão manual: encontrado desconto em {boleto.nome_boleto}.",
            )
        return

    # Consulta contrato do imóvel
    resp_contrato = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "LOCACAO_CONTRATO_IMOVEL_CONSULTAR"},
        "Body":   {"CodImovel": cod_imovel}
    }).json()

    if not (resp_contrato['Header']['Status'] == 'Success' and not resp_contrato['Header']['Error']):
        msg = f"Contrato não encontrado para o imóvel {cod_imovel}, boleto: {boleto.nome_boleto}."
        logger.erro("Lançamento", msg)
        relatorio.registrar(
            cod_imovel= cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            status="Erro",
            mensagem=msg,
        )
        return

    cod_contrato     = resp_contrato['Body']['CodContratoLoc']
    data_vig_inicial = resp_contrato['Body']['DataVigInicial']
    logger.sucesso("Lançamento", f"Contrato {cod_contrato} localizado para imóvel {cod_imovel}.")
    relatorio.registrar(
        cod_imovel=cod_imovel,
        numero_taxa="",
        descricao_taxa="",
        valor="",
        status="Sucesso",
        mensagem="Contrato localizado",
    )

    # -----------------------------------------------------------------------
    # PASSO 1: Lança todas as taxas do boleto
    # -----------------------------------------------------------------------
    for taxa in taxas_boleto:
        nome_taxa = taxa.get('taxa', '').lower()

        if nome_taxa in _TAXAS_IGNORADAS:
            logger.sucesso("Lançamento", f"Taxa '{taxa.get('taxa')}' ignorada por regra de negócio.")
            relatorio.registrar(
                cod_imovel=cod_imovel,
                numero_taxa="",
                descricao_taxa=taxa.get("taxa", ""),
                valor=taxa.get("valor", ""),
                status="Sucesso",
                mensagem="Taxa não lançada por regra de negócio.",
            )
            continue

        taxa["valor"] = float(
            str(taxa["valor"]).replace(".", "").replace(",", ".").replace("R$ ", "")
        )

        cod_taxa = next(
            (str(db[0]) for db in tabela_taxas if db[1].strip() == taxa.get("taxa", "").strip()),
            None
        )
        if not cod_taxa:
            msg_nova = f"Taxa '{taxa.get('taxa')}' não encontrada no banco de dados. Informe ao setor de TI."
            logger.erro("Lançamento", f"Taxa '{taxa.get('taxa')}' não encontrada na tabela.")
            relatorio.registrar(
                cod_imovel=cod_imovel,
                numero_taxa="",
                descricao_taxa=taxa.get("taxa", ""),
                valor=taxa["valor"],
                status="Erro",
                mensagem=msg_nova,
            )
            continue

        prop_loc = "L" if int(cod_taxa) <= 499 else "P"
        valor    = taxa["valor"]

        _incluir_lancamento(
            session_id, cod_taxa, cod_imovel, cod_contrato,
            competencia, tipo_boleto, taxa, valor, boleto, prop_loc, logger, relatorio
        )

    # -----------------------------------------------------------------------
    # PASSO 2: Consulta previstos APÓS lançar tudo e exclui os que sobraram
    # -----------------------------------------------------------------------
    resp_prev = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "LOCACAO_LANCTO_COND_CONSULTAR"},
        "Body":   {"CodImovel": cod_imovel, "Competencia": competencia,
                   "CodContratoLoc": cod_contrato}
    }).json()
    lista_prev = resp_prev['Body'].get('Lista', [])

    _excluir_previstos(
        session_id, lista_prev, resp_prev,
        cod_imovel, cod_contrato, competencia, tipo_boleto,
        boleto, logger
    )

    # -----------------------------------------------------------------------
    # PASSO 3: Associa a imagem do boleto ao lançamento
    # -----------------------------------------------------------------------
    _associar_imagem(session_id, cod_imovel, competencia, url_publica, boleto, logger, relatorio)


# ---------------------------------------------------------------------------
# Funções de lançamento
# ---------------------------------------------------------------------------
def _excluir_previstos(session_id, lista_prev, resp_prev,
                       cod_imovel, cod_contrato, competencia,
                       tipo_boleto, boleto, logger):
    """Exclui todos os itens que ainda estão como previstos (PrevisaoReal == 'P')."""
    for item in lista_prev:
        if item.get('PrevisaoReal') != 'P':
            continue

        resp = requests.post(URL, json={
            "Header": {"SessionId": session_id, "Action": "LOCACAO_LANCTO_COND_EXCLUIR"},
            "Body": {
                "NumeroLancto":     resp_prev['Body']['NumeroLancto'],
                "NumeroLanctoItem": item['NumeroLanctoItem'],
                "CodImovel":        cod_imovel,
                "Competencia":      competencia,
                "CodContratoLoc":   cod_contrato,
                "TipoBoleto":       tipo_boleto,
                "DataVencimento":   boleto.vencimento,
            }
        }).json()
        print(resp)

        cod_taxa_item = item.get('CodTaxa', item.get('NumeroLanctoItem', '?'))
        if resp['Header']['Status'] == 'Success' and not resp['Header']['Error']:
            logger.sucesso("Exclusão", f"Imóvel {cod_imovel} — previsão da taxa {cod_taxa_item} excluída.")
        else:
            logger.erro("Exclusão", f"Erro ao excluir previsão da taxa {cod_taxa_item}: {_extrair_erro(resp)}")


def _incluir_lancamento(session_id, cod_taxa, cod_imovel, cod_contrato,
                        competencia, tipo_boleto, taxa, valor,
                        boleto, prop_loc, logger, relatorio):
    resp = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "LOCACAO_LANCTO_COND_INCLUIR"},
        "Body": {
            "TestaAditivoLocacao":          'N',
            "LancarContaCorrenteLocacao":   'S',
            "CompetenciaLocacao":           competencia,
            "TipoBoleto":                   tipo_boleto,
            "CodImovel":                    cod_imovel,
            "CodContratoLoc":               cod_contrato,
            "Competencia":                  competencia,
            "Complemento":                  boleto.complemento,
            "CodTaxa":                      cod_taxa,
            "CobrarLocatarioProprietario":  prop_loc,
            "TotalParcelas":                taxa.get("total_parcelas"),
            "NumeroParcela":                taxa.get("parcela_atual"),
            "ValorReal":                    valor,
            "DataVencimento":               boleto.vencimento,
            "CodBarras":                    boleto.codigo_barras,
        }
    }).json()

    if resp['Header']['Status'] == 'Success' and not resp['Header']['Error']:
        logger.sucesso("Lançamento", f"Imóvel {cod_imovel} — taxa {cod_taxa} lançada.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa=cod_taxa,
            descricao_taxa=taxa.get("taxa", ""),
            valor=valor,
            status="Sucesso",
            mensagem=f"Taxa {cod_taxa} lançada com sucesso.",
        )
    else:
        logger.erro("Lançamento", f"Erro ao lançar taxa {cod_taxa}: {_extrair_erro(resp)}")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa=cod_taxa,
            descricao_taxa=taxa.get("taxa", ""),
            valor=valor,
            status="Erro",
            mensagem=f"{_extrair_erro(resp)}.",
        )


def _associar_imagem(session_id, cod_imovel, competencia, url_publica, boleto, logger, relatorio):
    resp = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "CTAPAG_LANCAMENTO_PESQUISAR"},
        "Body": {"TipoPesquisa": "I", "CodImovel": cod_imovel,
                 "TipoPeriodo": "C", "Competencia": competencia, "PrevisaoReal": "R"}
    }).json()

    lancamentos    = resp.get("Body", {}).get("Lancamentos", [])
    num_lancto_120 = next((l["NumeroLancto"] for l in lancamentos if l.get("CodTaxa") == 120), None)

    if not num_lancto_120:
        msg_nova = f"Não foi possível associar imagem ao imóvel {cod_imovel}, confira o e-mail para mais informações."
        logger.erro("Imagem", f"Imóvel {cod_imovel} sem lançamento de taxa 120. Imagem não associada.")
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Erro",
            mensagem=msg_nova,
        )
        return

    nome_url   = quote(boleto.nome_boleto)
    url_imagem = f"{url_publica}/taxa-120/arquivo/{nome_url}"

    # Valida acesso ao arquivo sem estourar exceção
    try:
        acessivel = requests.get(url_imagem, timeout=10).status_code == 200
    except Exception:
        acessivel = False

    if not acessivel:
        msg = f"Arquivo não acessível: {boleto.nome_boleto}"
        logger.erro("Imagem", msg)
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Erro",
            mensagem=msg,
        )
        return

    resp_img = requests.post(URL, json={
        "Header": {"SessionId": session_id, "Action": "CTAPAG_LANCAMENTO_ADICIONAR_IMAGEM"},
        "Body": {"NumeroLancto": num_lancto_120, "UrlImagem": url_imagem}
    }).json()

    if resp_img['Header']['Status'] == 'Success' and not resp_img['Header']['Error']:
        msg = f"Boleto {boleto.nome_boleto} associado ao lançamento {num_lancto_120}."
        logger.sucesso("Imagem", msg)
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Sucesso",
            mensagem=msg,
        )
    else:
        msg = f"Erro ao associar imagem: {_extrair_erro(resp_img)}"
        logger.erro("Imagem", msg)
        relatorio.registrar(
            cod_imovel=cod_imovel,
            numero_taxa="",
            descricao_taxa="",
            valor="",
            processo="ASSOCIAÇÃO DE IMAGEM",
            status="Erro",
            mensagem=msg,
        )