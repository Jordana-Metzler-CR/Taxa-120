import os
from flask import Blueprint, jsonify, send_file, abort
from app.service.lancar_taxas import lancar_taxas_imobiliar
from app.imobiliarias import registry

taxa120_bp = Blueprint("taxa120_bp", __name__, url_prefix='/taxa-120')

PASTA_PROCESSADOS = (
    r"\\192.168.150.12\dados\CREDITO REAL\SETORES\CONTABILIDADE FISCAL"
    r"\SETOR\Condomínios\Novas Locações\TAXA 120\PROCESSADOS"
)

@taxa120_bp.route("/imobiliaria/<cnpj>", methods=["POST"])
def lancar_taxas(cnpj):
    try:
        lancar_taxas_imobiliar(cnpj)
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@taxa120_bp.route("/arquivo/<nome_arquivo>", methods=["GET"])
def servir_arquivo(nome_arquivo):
    caminho = os.path.join(PASTA_PROCESSADOS, nome_arquivo)
    if not os.path.exists(caminho):
        abort(404)
    return send_file(caminho, as_attachment=False)
