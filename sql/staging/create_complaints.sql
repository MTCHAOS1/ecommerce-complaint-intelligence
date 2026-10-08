DROP TABLE IF EXISTS staging.complaints;

CREATE TABLE staging.complaints (
    regiao VARCHAR(50),
    uf CHAR(2),
    cidade VARCHAR(150),
    sexo VARCHAR(30),
    faixa_etaria VARCHAR(100),

    data_finalizacao DATE,
    tempo_resposta NUMERIC,

    nome_fantasia VARCHAR(255),
    segmento_de_mercado VARCHAR(255),
    area VARCHAR(255),

    assunto TEXT,
    grupo_problema TEXT,
    problema TEXT,

    como_comprou_contratou VARCHAR(255),

    procurou_empresa BOOLEAN,
    respondida BOOLEAN,

    situacao VARCHAR(100),
    avaliacao_reclamacao VARCHAR(100),

    nota_do_consumidor NUMERIC
);