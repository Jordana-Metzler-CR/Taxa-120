from dataclasses import dataclass
from enum import Enum

class Status(Enum):
    SUCESSO = "Sucesso"
    ALERTA = "Alerta"
    ERRO = "Erro"

@dataclass
class Log:
    status: Status
    fluxo: str
    mensagem: str