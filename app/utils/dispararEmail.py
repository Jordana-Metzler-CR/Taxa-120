import os
import smtplib
import mimetypes
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from email.message import EmailMessage
from datetime import datetime
from app.config import env

load_dotenv()

SMTP_HOST  = os.getenv("SMTP_HOST")
SMTP_PORT  = int(os.getenv("SMTP_PORT", 587))
SMTP_USER  = os.getenv("SMTP_USER")
SMTP_PASS  = os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("FROM_EMAIL")


def _corpo_texto(nome_imobiliaria: str) -> str:
    return f"""Olá,

Segue em anexo o relatório de execução da Taxa 120 – {nome_imobiliaria}

Em caso de erro na anexação da imagem, verifique os seguintes pontos:

1. Verifique o lançamento das taxas, pois pode haver alguma taxa ainda em Previsto;
2. Verifique se já existe algum lançamento gerado no Contas a Pagar para a taxa 120.

Isso ocorre porque o anexo da imagem é feito a partir do número do lançamento gerado no Contas a Pagar.
Dessa forma, caso alguma taxa ainda esteja em Previsto, o lançamento no Contas a Pagar não é gerado
e, consequentemente, não haverá o número necessário para anexar a imagem.

Atenciosamente,
Equipe RPA"""


def _montar_msg(assunto: str, destinatarios: list, nome_imobiliaria: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"]    = FROM_EMAIL
    msg["To"]      = destinatarios
    msg["Subject"] = assunto
    msg.set_content(_corpo_texto(nome_imobiliaria))
    return msg


def _anexar(msg: EmailMessage, caminho: str):
    with open(caminho, "rb") as f:
        dados = f.read()
    mime_type, _ = mimetypes.guess_type(caminho)
    mime_type = mime_type or "application/octet-stream"
    maintype, subtype = mime_type.split("/")
    msg.add_attachment(dados, maintype=maintype, subtype=subtype, filename=os.path.basename(caminho))


def _enviar(msg: EmailMessage):
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def enviarEmailRelatorio(nome_imobiliaria: str, arquivo_operacional: str) -> bool:
    ambiente        = os.getenv("ENV", "HML").upper()
    assunto         = f"Execução Taxa 120 - {nome_imobiliaria} ({datetime.now().strftime('%m/%Y')})"
    arquivo_tecnico = f"logs_taxa_120_{datetime.now().strftime('%Y%m%d')}.xlsx"

    conn = psycopg2.connect(
        host=env("DB_HOST"), port=env("DB_PORT"),
        database=env("DB_BANCO"), user=env("DB_USER"), password=env("DB_SENHA")
    )
    try:
        df = pd.read_sql(
           "SELECT * FROM logs_taxa_120 WHERE data_e_horario::date = CURRENT_DATE;", conn
        )
    finally:
        conn.close()
    df.to_excel(arquivo_tecnico, index=False)

    try:
        if ambiente == "HML":
            destinatarios_ti    = [e.strip() for e in env("EMAIL").split(",")       if e.strip()]

            msg_ti = _montar_msg(assunto, destinatarios_ti, nome_imobiliaria)
            _anexar(msg_ti, arquivo_tecnico)
            _anexar(msg_ti, arquivo_operacional)
            _enviar(msg_ti)


        else:  # PROD
            destinatarios_ti    = [e.strip() for e in env("EMAIL_TI").split(",")    if e.strip()]
            destinatarios_setor = [e.strip() for e in env("EMAIL_SETOR").split(",") if e.strip()]

            msg_ti = _montar_msg(assunto, destinatarios_ti, nome_imobiliaria)
            _anexar(msg_ti, arquivo_tecnico)
            _anexar(msg_ti, arquivo_operacional)
            _enviar(msg_ti)

            msg_setor = _montar_msg(assunto, destinatarios_setor, nome_imobiliaria)
            _anexar(msg_setor, arquivo_operacional)
            _enviar(msg_setor)

        return True

    except Exception as e:
        print(f"[ERRO] Falha ao enviar e-mail: {e}")
        return False

    finally:
        if os.path.exists(arquivo_tecnico):
            os.remove(arquivo_tecnico)