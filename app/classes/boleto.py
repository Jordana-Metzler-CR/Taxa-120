from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Boleto:
    nome_boleto: str = ""
    cnpj_imobiliaria: str = ""
    endereco_imovel: str = ""
    complemento: str = ""
    taxas: List[Dict[str, float]] = field(default_factory=list)
    valor_total: float = 0.0
    competencia: str = ""
    codigo_barras: str = ""
    nome_predio: str = ""
    nome_condomino: str = ""
    documento_condomino: str = ""
    vencimento: str = ""