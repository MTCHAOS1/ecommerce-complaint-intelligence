DROP TABLE IF EXISTS warehouse.fato_reclamacao;

DROP TABLE IF EXISTS warehouse.dim_classificacao;
DROP TABLE IF EXISTS warehouse.dim_tempo;
DROP TABLE IF EXISTS warehouse.dim_localidade;
DROP TABLE IF EXISTS warehouse.dim_empresa;

-- ============================================================
-- DIMENSÃO EMPRESA
-- ============================================================
CREATE TABLE warehouse.dim_empresa (
    empresa_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_fantasia VARCHAR(255) NOT NULL,
    segmento_de_mercado VARCHAR(255),
    CONSTRAINT uq_dim_empresa
        UNIQUE NULLS NOT DISTINCT (nome_fantasia, segmento_de_mercado)
);

-- ============================================================
-- DIMENSÃO LOCALIDADE
-- ============================================================
CREATE TABLE warehouse.dim_localidade (
    localidade_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    regiao VARCHAR(50),
    uf CHAR(2) NOT NULL,
    cidade VARCHAR(150) NOT NULL,
    CONSTRAINT uq_dim_localidade UNIQUE (uf, cidade)
);

-- ============================================================
-- DIMENSÃO TEMPO
-- ============================================================
CREATE TABLE warehouse.dim_tempo (
    data_id INTEGER PRIMARY KEY,
    data DATE NOT NULL UNIQUE,
    dia SMALLINT NOT NULL,
    mes SMALLINT NOT NULL,
    nome_mes VARCHAR(20) NOT NULL,
    trimestre SMALLINT NOT NULL,
    ano SMALLINT NOT NULL
);

-- ============================================================
-- DIMENSÃO CLASSIFICAÇÃO
-- ============================================================
CREATE TABLE warehouse.dim_classificacao (
    classificacao_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    area VARCHAR(255),
    assunto TEXT,
    grupo_problema TEXT,
    problema TEXT,
    CONSTRAINT uq_dim_classificacao
        UNIQUE NULLS NOT DISTINCT (area, assunto, grupo_problema, problema)
);

-- ============================================================
-- TABELA FATO
-- ============================================================
CREATE TABLE warehouse.fato_reclamacao (
    reclamacao_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empresa_id BIGINT NOT NULL,
    localidade_id BIGINT NOT NULL,
    data_id INTEGER NOT NULL,
    classificacao_id BIGINT NOT NULL,
    sexo VARCHAR(30),
    faixa_etaria VARCHAR(100),
    tempo_resposta NUMERIC,
    como_comprou_contratou VARCHAR(255),
    procurou_empresa BOOLEAN,
    respondida BOOLEAN,
    situacao VARCHAR(100),
    avaliacao_reclamacao VARCHAR(100),
    nota_do_consumidor NUMERIC,
    CONSTRAINT fk_fato_empresa FOREIGN KEY (empresa_id)
        REFERENCES warehouse.dim_empresa (empresa_id),
    CONSTRAINT fk_fato_localidade FOREIGN KEY (localidade_id)
        REFERENCES warehouse.dim_localidade (localidade_id),
    CONSTRAINT fk_fato_tempo FOREIGN KEY (data_id)
        REFERENCES warehouse.dim_tempo (data_id),
    CONSTRAINT fk_fato_classificacao FOREIGN KEY (classificacao_id)
        REFERENCES warehouse.dim_classificacao (classificacao_id)
);
