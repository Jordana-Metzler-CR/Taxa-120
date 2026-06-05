# ---------------------------------------------------------------------------
# Normalização de nomes de taxas
# ---------------------------------------------------------------------------
_NORMALIZACOES_TAXA = [
    (lambda t: 'CONDOMINIO' in t or 'CONDOMÍNIO' in t,                                         'CONDOMINIO'),
    (lambda t: 'GÁS' in t or 'GAS' in t,                                                       'GAS'),
    (lambda t: 'ELEVADOR' in t and 'MELHORIAS' not in t and 'REFORMA' not in t,                'MANUTENCAO ELEVADOR'),
    (lambda t: ('FERIAS' in t or 'SALARIO' in t or 'SAL.' in t) and
               ('13' in t or 'FUNCIONARIO' in t or 'FUNC' in t),                               'FERIAS/13 SAL'),
    (lambda t: 'ENERGIA' in t or ('CONSUMO' in t and 'ENERGIA' in t),                          'ENERGIA ELETRICA'),
    (lambda t: 'COTA' in t and 'ALA' in t and 'GERAL' not in t,                                'CONDOMINIO'),
    (lambda t: 'COTA' in t and 'GERAL' in t,                                                   'COTA ALA GERAL'),
    (lambda t: 'PORTARIA' in t,                                                                 'PORTARIA'),
    (lambda t: 'IMPERMEABILIZ' in t and 'AGUA' in t,                                           'IMPERMEABILIZACAO CX DAGUA'), 
    (lambda t: 'LIMPEZA' in t and ('CAIXA' in t or 'CX' in t),                                 'LIMPEZA CAIXA DAGUA'),
    (lambda t: 'AGUA' in t and ('M³' in t or 'M3' in t),                                       'AGUA M³'),
    (lambda t: 'AGUA' in t and 'PURIFICADOR' not in t
               and 'M³' not in t
               and 'IMPERMEABILIZ' not in t,                                                    'AGUA'),
    (lambda t: 'LAUDO' in t and 'TECNICO' in t or 'TÉCNICO' in t,                               'LAUDO TECNICO'),
    (lambda t: 'FUNDO' in t and 'OBRAS' in t,                                                  'FUNDO OBRAS'),
    (lambda t: 'FUNDO' in t and any(x in t for x in
    ('MELHORIAS', 'LAZER', 'JANELA', 'ELETRIC')),                                               'FUNDO MELHORIAS'),
    (lambda t: 'OBRA' in t and 'FUNDO' not in t,                                               'OBRAS'),
    (lambda t: 'RESERVA' in t and 'GERAL' in t,                                                'FUNDO RESERVA GERAL'),
    (lambda t: 'FUNDO' in t and 'RESERVA' in t and 'GERAL' not in t,                           'FUNDO RESERVA'),
    (lambda t: 'FDO.' in t and 'RESERVA' in t,                                                 'FUNDO RESERVA'),
    (lambda t: 'FDO.' in t and 'LAZER' in t,                                                   'FUNDO MELHORIAS'),
    (lambda t: 'PURIFICADOR' in t,                                                              'PURIFICADOR DE AGUA'),
    (lambda t: ('LAUDO' in t and 'PREDIAL' in t) or 'PPCI' in t,                               'LAUDO PPCI'),
    (lambda t: 'REFORMA' in t or ('MELHORIAS' in t and 'ELEVADOR' in t),                       'MELHORIAS ELEVADORES'),
    (lambda t: ('MANUT' in t and 'CONSERV' in t) or ('FECHO' in t and 'JANELA' in t)
               or ('FUNDO' in t and 'MANUTEN' in t),                                           'FUNDO MANUTENCAO'),
]