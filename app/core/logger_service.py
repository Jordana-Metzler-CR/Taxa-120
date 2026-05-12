from app.classes.log import Log, Status
from app.repositories.db_logger import DBLogger

class LoggerService:
    def __init__(self, db_logger: DBLogger):
        self.db_logger = db_logger

    def _criar_log(self, status: Status, fluxo: str, mensagem: str) -> Log:
        return Log(
            status=status,
            fluxo=fluxo,
            mensagem=mensagem
        )

    def sucesso(self, fluxo: str, mensagem: str):
        log = self._criar_log(Status.SUCESSO, fluxo, mensagem)
        self.db_logger.registrar(log)
        return log

    def alerta(self, fluxo: str, mensagem: str):
        log = self._criar_log(Status.ALERTA, fluxo, mensagem)
        self.db_logger.registrar(log)
        return log

    def erro(self, fluxo: str, mensagem: str):
        log = self._criar_log(Status.ERRO, fluxo, mensagem)
        self.db_logger.registrar(log)
        return log
