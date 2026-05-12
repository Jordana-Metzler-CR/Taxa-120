"""
Serviço de DE-PARA: para cada PDF na pasta da imobiliária, extrai o boleto,
tenta encontrar o imóvel correspondente no banco e persiste o resultado.

Este arquivo não sabe nada sobre nenhuma imobiliária específica —
toda lógica particular fica em app/imobiliarias/<nome>/extrator.py e matcher.py.
"""

import psycopg2
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import pandas as pd
import os

from app.config import env
from app.imobiliarias import registry
from app.imobiliarias.barcellos.extrator import extrair_boleto
from app.utils.normalizacao import montar_periodo_competencia, normalizar_competencia


# ---------------------------------------------------------------------------
# Consulta ao banco do Imobiliar
# ---------------------------------------------------------------------------
def _extrair_tabela_imobiliar(cnpj: str, data_inicio: str, data_fim: str, competencia: str) -> pd.DataFrame:
    engine = create_engine(os.getenv("TABELA_CR"))
    query = text("""
        SELECT
            pc.codimovel,
            i.nomepredio,
            CONCAT(i.logradimo, ' ', i.numero) AS endereco,
            i.complementoimo AS complemento,
            p1.nome AS nome_locador,
            CAST(p1.cpf_cnpj AS VARCHAR) AS documento_locador,
            pc.datavenc
        FROM cpag_rec cr
            INNER JOIN pag_cond pc    ON cr.nrlancto   = pc.nrlancto
            INNER JOIN imovel i       ON pc.codimovel  = i.codimovel
            INNER JOIN fornecedor f   ON i.codfornecadmc = f.codfornec
            INNER JOIN contrato_adm ca ON i.codcontratoadm = ca.codcontrato
            INNER JOIN pessoa p1      ON p1.codpessoa  = ca.codpessoatit
            INNER JOIN aditivo_loc al ON i.codimovel   = al.codimovel
                AND i.codcontratoloc  = al.codcontrato
                AND al.seqcontrato    = 0
        WHERE f.cpf_cnpj = :cnpj
          AND pc.datavenc  >= :inicio
          AND pc.datavenc  <= :fim
          AND pc.competencia = :competencia
          AND i.ativo = 'S'
    """)
    try:
        return pd.read_sql_query(query, engine,
                                 params={"cnpj": cnpj, "inicio": data_inicio,
                                         "fim": data_fim, "competencia": competencia})
    except Exception as e:
        raise RuntimeError(f"Falha ao consultar tabela do Imobiliar: {e}") from e


def _buscar_id_administradora(cursor, cnpj: str):
    cursor.execute("SELECT id FROM taxa_120_administradoras WHERE cnpj = %s", (cnpj,))
    row = cursor.fetchone()
    return row[0] if row else None


def _inserir_boleto(cursor, nome_boleto: str, cod_imovel: float, competencia: str):
    cursor.execute(
        "INSERT INTO public.taxa_120_boletos (nome_boleto, cod_imovel, competencia) VALUES (%s, %s, %s)",
        (nome_boleto, cod_imovel, competencia)
    )


def _upsert_imovel(cursor, id_administradora, cod_imovel, boleto, match):
    cursor.execute("SELECT id FROM taxa_120_imoveis WHERE cod_imovel = %s", (cod_imovel,))
    if cursor.fetchone():
        cursor.execute(
            """UPDATE taxa_120_imoveis
               SET condominio = %s, endereco = %s, complemento = %s,
                   nome_locador = %s, documento_locador = %s
               WHERE cod_imovel = %s""",
            (boleto.nome_predio, boleto.endereco_imovel or "", boleto.complemento,
             boleto.nome_condomino, match['documento_locador'], cod_imovel)
        )
    else:
        cursor.execute(
            """INSERT INTO taxa_120_imoveis
               (id_administradora, cod_imovel, condominio, endereco, complemento, nome_locador, documento_locador)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (id_administradora, cod_imovel, boleto.nome_predio,
             boleto.endereco_imovel or "", boleto.complemento,
             boleto.nome_condomino, match['documento_locador'])
        )


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def registrar_relacao_de_para(cnpj: str, logger) -> list:
    """
    Para a imobiliária identificada pelo CNPJ:
      1. Busca os PDFs na pasta configurada
      2. Extrai cada boleto usando o extrator da imobiliária
      3. Usa a competência extraída do boleto
      4. Tenta encontrar o imóvel no banco
      5. Persiste e retorna a lista de boletos prontos para lançamento
    """

    imob      = registry.get(cnpj)
    cfg       = imob["config"]
    extrator  = imob["extrator"]
    matcher   = imob["matcher"]

    logger.sucesso("Processamento", f"Iniciando processamento da imobiliária {cfg.NOME}")

    arquivos = list(cfg.PASTA_PDFS.glob("*.pdf"))

    if not arquivos:
        logger.alerta("Processamento", f"Nenhum PDF encontrado para {cfg.NOME}")
        return []

    conn = psycopg2.connect(
        host=env("DB_HOST"),
        port=env("DB_PORT"),
        database=env("DB_BANCO"),
        user=env("DB_USER"),
        password=env("DB_SENHA")
    )

    boletos = []

    try:
        with conn:
            with conn.cursor() as cursor:
                id_adm = _buscar_id_administradora(cursor, cnpj)

                for arquivo in arquivos:
                    try:
                        boleto = extrator.extrair_boleto(arquivo, logger)
                    except Exception as e:
                        logger.erro("Extração de Boleto", f"Erro ao extrair '{arquivo.name}': {e}")
                        continue
                    print(f"[DEBUG] {boleto.nome_boleto} | competencia raw: {boleto.vencimento} | normalizada: {normalizar_competencia(boleto.vencimento)}")
                    competencia = normalizar_competencia(boleto.vencimento)

                    if not competencia:
                        logger.erro(
                            "Competência",
                            f"Competência inválida no boleto '{arquivo.name}'. Valor extraído: {boleto.vencimento}"
                        )
                        continue

                    primeiro_dia, ultimo_dia = montar_periodo_competencia(competencia)

                    tabela = _extrair_tabela_imobiliar(
                        cnpj,
                        primeiro_dia,
                        ultimo_dia,
                        competencia
                    )

                    # Verifica se já existe mapeamento no banco
                    cursor.execute(
                        """SELECT cod_imovel FROM taxa_120_imoveis
                           WHERE condominio = %s AND endereco = %s
                             AND complemento = %s AND nome_locador = %s
                             AND id_administradora = %s
                           LIMIT 1""",
                        (boleto.nome_predio, boleto.endereco_imovel,
                         boleto.complemento, boleto.nome_condomino, id_adm)
                    )
                    registro = cursor.fetchone()

                    if registro and registro[0] not in (None, 0, 0.0):
                        _inserir_boleto(cursor, arquivo.name, registro[0], competencia)
                        logger.sucesso("Boleto", f"Imóvel já mapeado ({registro[0]}). Pulando similaridade.")
                        boletos.append(boleto)
                        continue

                    # Calcula similaridade usando o matcher da imobiliária
                    match             = matcher.calcular_match(boleto, tabela)
                    media_principais  = matcher.media_campos_principais(match)
                    limiar            = cfg.LIMIAR_PONTUACAO
                    limiar_principais = cfg.LIMIAR_CAMPOS_PRINCIPAIS

                    if match['pontuacao_total'] < limiar:
                        if media_principais >= limiar_principais:
                            cod_imovel = float(match['codimovel'])
                            logger.alerta("Similaridade",
                                          f"Pontuação baixa ({match['pontuacao_total']}%) mas campos fortes. "
                                          f"Usando imóvel {cod_imovel}.")
                        else:
                            logger.alerta(
                                "Similaridade",
                                f"Similaridade baixa ({match['pontuacao_total']:.2f}%) para "
                                f"'{arquivo.name}'. Registrando com cod=0 para revisão manual."
                            )
                            cod_imovel = 0.0

                        _upsert_imovel(cursor, id_adm, cod_imovel, boleto, match)
                        _inserir_boleto(cursor, arquivo.name, cod_imovel, competencia)
                        boletos.append(boleto)
                        continue

                    cod_imovel = float(match['codimovel'])
                    _upsert_imovel(cursor, id_adm, cod_imovel, boleto, match)
                    _inserir_boleto(cursor, arquivo.name, cod_imovel, competencia)
                    logger.sucesso("Boleto", f"'{arquivo.name}' → imóvel {cod_imovel}")
                    boletos.append(boleto)

        logger.sucesso("Processamento", "Commit realizado com sucesso.")

    except Exception as e:
        logger.erro("Processamento", f"Erro inesperado: {e}")
        raise
    finally:
        conn.close()

    return boletos
