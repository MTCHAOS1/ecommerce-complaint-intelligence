# Malha das unidades federativas

`br_ufs.geojson` é a resposta original da API de malhas simplificadas do IBGE,
obtida em 28/10/2026, com 27 feições Polygon/MultiPolygon, incluindo DF.
A propriedade `codarea` contém o código IBGE de dois dígitos da UF.

- Fonte: https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?intrarregiao=UF&formato=application/vnd.geo%2Bjson&qualidade=minima
- Documentação: https://servicodados.ibge.gov.br/api/docs/malhas?versao=3
- Qualidade: mínima (visualização agregada por UF, sem precisão cadastral).
- A resposta não fixa um período cartográfico. A data acima é de obtenção, não do levantamento territorial.

O dashboard lê este arquivo local; não usa tiles externos ou token de mapas.
Preservar atribuição ao IBGE ao distribuir o mapa. Para atualização, substituir
somente após verificar as 27 UFs e executar os testes do dashboard.
