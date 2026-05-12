import PyPDF2
from pathlib import Path


def processar_pdfs(pasta_entrada, pasta_fragmentados, logger):
    """
    Lê cada PDF da pasta_entrada e salva cada página como arquivo individual
    na pasta_fragmentados. Renomeia o original com "PROCESSADO - " após concluir.
    """
    pasta_entrada      = Path(pasta_entrada)
    pasta_fragmentados = Path(pasta_fragmentados)
    pasta_fragmentados.mkdir(parents=True, exist_ok=True)

    logger.sucesso("Processamento PDF", f"Iniciando: {pasta_entrada}")

    try:
        for arquivo in pasta_entrada.iterdir():
            if not arquivo.is_file() or arquivo.suffix.lower() != ".pdf":
                continue
            if "PROCESSADO" in arquivo.name.upper():
                continue
            try:
                with open(arquivo, "rb") as f:
                    leitor = PyPDF2.PdfReader(f)
                    for i, pagina in enumerate(leitor.pages):
                        escritor = PyPDF2.PdfWriter()
                        escritor.add_page(pagina)
                        destino = pasta_fragmentados / f"{arquivo.stem}_pagina_{i+1}.pdf"
                        with open(destino, "wb") as fout:
                            escritor.write(fout)
                arquivo.rename(pasta_entrada / f"PROCESSADO - {arquivo.name}")
            except Exception as e:
                logger.erro("Processamento PDF", f"Erro ao processar '{arquivo.name}': {e}")

        logger.sucesso("Processamento PDF", "Finalizado com sucesso.")
    except Exception as e:
        logger.erro("Processamento PDF", f"Falha inesperada: {e}")
        raise
