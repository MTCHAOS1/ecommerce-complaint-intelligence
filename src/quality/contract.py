"""Contrato versionado dos 19 campos de negócio, compartilhado pela pipeline."""
CONTRACT_VERSION = 1
SCORE_VALUES = (1, 2, 3, 4, 5)
VALID_UFS = frozenset('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())
RAW_COLUMN_MAPPING = {'Região': 'regiao',
 'UF': 'uf',
 'Cidade': 'cidade',
 'Sexo': 'sexo',
 'Faixa Etária': 'faixa_etaria',
 'Data Finalização': 'data_finalizacao',
 'Tempo Resposta': 'tempo_resposta',
 'Nome Fantasia': 'nome_fantasia',
 'Segmento de Mercado': 'segmento_de_mercado',
 'Área': 'area',
 'Assunto': 'assunto',
 'Grupo Problema': 'grupo_problema',
 'Problema': 'problema',
 'Como Comprou Contratou': 'como_comprou_contratou',
 'Procurou Empresa': 'procurou_empresa',
 'Respondida': 'respondida',
 'Situação': 'situacao',
 'Avaliação Reclamação': 'avaliacao_reclamacao',
 'Nota do Consumidor': 'nota_do_consumidor'}
COLUMNS = tuple(RAW_COLUMN_MAPPING.values())
