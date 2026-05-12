import os
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "HML")

def env(nome, default=None, required=True):
    valor = os.getenv(f"{nome}_{ENV}", default)

    if required and valor is None:
        raise RuntimeError(f"Variável {nome}_{ENV} não definida")

    return valor

class Config:
    SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False