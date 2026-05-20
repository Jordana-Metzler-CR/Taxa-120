import datetime
import re

def linha_digitavel_para_codigo_barras(linha_digitavel):
    linha = linha_digitavel.replace(" ", "").replace(".", "").replace("-", "")
    if len(linha) != 47:
        raise ValueError(f"Linha digitável deve ter 47 dígitos. Recebido: {len(linha)}")
    if not linha.isdigit():
        raise ValueError("Linha digitável deve conter apenas números")
    codigo_barras = [''] * 44
    codigo_barras[0:4] = list(linha[0:4])
    codigo_barras[4] = linha[32]
    codigo_barras[5:19] = list(linha[33:47])
    codigo_barras[19:24] = list(linha[4:9])
    codigo_barras[24:34] = list(linha[10:20])
    codigo_barras[34:44] = list(linha[21:31])
    return ''.join(codigo_barras)

def extrai_valor_codigo_barras(codigo_barras):
    
    #print(f"Valor bruto extraído do código de barras: {codigo_barras}")
    
    #print(f"Código de barras limpo: {codigo_barras}")
    valor_str = codigo_barras[-10:]
    valor = int(valor_str) / 100
    return valor

def extrai_vencimento(codigo_barras):
    data_base = datetime.datetime(2022, 5, 29)
    vencimento_str = codigo_barras[-14: -10]
    vencimento_int = int(vencimento_str)
    vencimento_date = data_base + datetime.timedelta(days=vencimento_int)
    #print(f"Vencimento date: {vencimento_date}")
    return vencimento_date.strftime("%d/%m/%Y")