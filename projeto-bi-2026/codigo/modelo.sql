-- SQLite 3.25+. Nunca unir diretamente as tabelas de eventos entre si.
-- Primeiro cadastro é um CENÁRIO, sem garantia temporal ou de autoridade.
CREATE INDEX idx_clientes_key ON clientes(cliente_id);
CREATE INDEX idx_produtos_key ON produtos(produto_id);
CREATE INDEX idx_vendas_cliente ON vendas(cliente_id);
CREATE INDEX idx_vendas_produto ON vendas(produto_id);
CREATE INDEX idx_atendimento_cliente ON atendimento(cliente_id);
CREATE INDEX idx_marketing_cliente ON marketing(cliente_id);
CREATE INDEX idx_estoque_produto ON estoque(produto_id);

CREATE TABLE dim_clientes AS
 SELECT * FROM clientes WHERE _linha IN (SELECT min(_linha) FROM clientes GROUP BY cliente_id);
CREATE UNIQUE INDEX pk_dim_clientes ON dim_clientes(cliente_id);
CREATE TABLE dim_produtos AS
 SELECT * FROM produtos WHERE _linha IN (SELECT min(_linha) FROM produtos GROUP BY produto_id);
CREATE UNIQUE INDEX pk_dim_produtos ON dim_produtos(produto_id);
CREATE TABLE dim_produtos_ultimo AS
 SELECT * FROM produtos WHERE _linha IN (SELECT max(_linha) FROM produtos GROUP BY produto_id);
CREATE UNIQUE INDEX pk_dim_produtos_ultimo ON dim_produtos_ultimo(produto_id);

CREATE TABLE fato_vendas AS
 SELECT v._linha, v.pedido_id, v.cliente_id, v.produto_id, v.data_venda,
 substr(v.data_venda,1,7) mes, v.regiao, v.canal, v.status_pedido,
 coalesce(p.categoria,'Sem cadastro') categoria,
 CAST(v.quantidade AS INTEGER) quantidade,
 CAST(v.quantidade AS REAL)*CAST(v.preco_unitario AS REAL) bruto,
 CAST(v.quantidade AS REAL)*CAST(v.preco_unitario AS REAL)*CAST(v.desconto_percentual AS REAL) desconto,
 CAST(v.quantidade AS REAL)*CAST(v.preco_unitario AS REAL)*(1-CAST(v.desconto_percentual AS REAL)) liquido,
 CAST(v.quantidade AS REAL)*CAST(p.custo_estimado AS REAL) custo_primeiro,
 CAST(v.quantidade AS REAL)*CAST(u.custo_estimado AS REAL) custo_ultimo
 FROM vendas v
 LEFT JOIN dim_produtos p USING(produto_id)
 LEFT JOIN dim_produtos_ultimo u USING(produto_id);
CREATE INDEX idx_fato_cliente ON fato_vendas(cliente_id);
CREATE INDEX idx_fato_status_data ON fato_vendas(status_pedido,data_venda);

-- Uma linha por combinação de mês e dimensões comerciais. Pedido é único nesta base.
CREATE TABLE comercial_mensal AS
 SELECT mes,regiao,canal,categoria,count(*) registros,
 sum(status_pedido='Concluído') pedidos,
 sum(status_pedido='Cancelado') cancelados,
 sum(status_pedido='Devolvido') devolvidos,
 sum(status_pedido='Em processamento') processamento,
 sum(CASE WHEN status_pedido='Concluído' THEN quantidade ELSE 0 END) unidades,
 sum(CASE WHEN status_pedido='Concluído' THEN bruto ELSE 0 END) bruto,
 sum(CASE WHEN status_pedido='Concluído' THEN desconto ELSE 0 END) desconto,
 sum(CASE WHEN status_pedido='Concluído' THEN liquido ELSE 0 END) liquido,
 sum(CASE WHEN status_pedido='Concluído' THEN custo_primeiro ELSE 0 END) custo,
 sum(CASE WHEN status_pedido='Concluído' THEN custo_ultimo ELSE 0 END) custo_ultimo
 FROM fato_vendas GROUP BY 1,2,3,4;

CREATE TABLE marketing_mensal AS
 SELECT substr(data_interacao,1,7) mes,campanha,meio, count(*) interacoes,
 sum(CAST(investimento AS REAL)) investimento,
 sum(CAST(impressoes AS INTEGER)) impressoes,
 sum(CAST(cliques AS INTEGER)) cliques,
 sum(CAST(conversoes AS INTEGER)) conversoes,
 sum(CAST(cliques AS INTEGER)>CAST(impressoes AS INTEGER)
     OR CAST(conversoes AS INTEGER)>CAST(cliques AS INTEGER)) funil_invalido
 FROM marketing GROUP BY 1,2,3;

-- Atendimentos e compras agregados separadamente no nível do cliente.
CREATE TABLE atendimento_cliente AS
 SELECT cliente_id, count(*) atendimentos,
 sum(motivo IN ('Atraso','Produto danificado','Reembolso','Cobrança')) reclamacoes,
 sum(status_atendimento!='Resolvido') abertos,
 sum(CAST(satisfacao_atendimento AS REAL)) soma_satisfacao,
 sum(CAST(satisfacao_atendimento AS INTEGER)>=4) satisfeitos
 FROM atendimento GROUP BY 1;

CREATE TABLE vendas_cliente AS
 SELECT cliente_id,count(*) frequencia, sum(liquido) monetario,
 max(data_venda) ultima_compra
 FROM fato_vendas
 WHERE status_pedido='Concluído'
 AND data_venda>=date((SELECT max(data_venda) FROM vendas),'-364 days')
 GROUP BY 1;

CREATE TABLE clientes_rfm AS
 WITH universo AS (
   SELECT cliente_id FROM clientes UNION SELECT cliente_id FROM vendas
   UNION SELECT cliente_id FROM atendimento UNION SELECT cliente_id FROM marketing
 ), base AS (
   SELECT u.cliente_id,coalesce(c.regiao,'Sem cadastro') regiao,
   coalesce(c.status_cliente,'Sem cadastro') status_cliente,
   CAST(c.satisfacao_1a5 AS REAL) satisfacao_cadastro,
   CAST(c.dias_desde_ultima_compra AS INTEGER) recencia_cadastro,
   coalesce(v.frequencia,0) frequencia,coalesce(v.monetario,0) monetario,
   v.ultima_compra,
   CAST(julianday((SELECT max(data_venda) FROM vendas))-julianday(v.ultima_compra) AS INTEGER) recencia,
   coalesce(a.atendimentos,0) atendimentos,coalesce(a.reclamacoes,0) reclamacoes,
   coalesce(a.abertos,0) abertos, coalesce(a.soma_satisfacao,0) soma_satisfacao,
   coalesce(a.satisfeitos,0) satisfeitos
   FROM universo u LEFT JOIN dim_clientes c USING(cliente_id)
   LEFT JOIN vendas_cliente v USING(cliente_id)
   LEFT JOIN atendimento_cliente a USING(cliente_id)
 ), quantis AS (
   SELECT cliente_id,cume_dist() OVER(ORDER BY monetario) posicao
   FROM base WHERE frequencia>0
 ), notas AS (
   SELECT b.*,
   CASE WHEN recencia<=30 THEN 5 WHEN recencia<=60 THEN 4 WHEN recencia<=90 THEN 3
        WHEN recencia<=180 THEN 2 WHEN recencia IS NOT NULL THEN 1 ELSE 0 END r,
   CASE WHEN frequencia>=8 THEN 5 WHEN frequencia>=5 THEN 4 WHEN frequencia>=3 THEN 3
        WHEN frequencia>=2 THEN 2 WHEN frequencia=1 THEN 1 ELSE 0 END f,
   CASE WHEN q.posicao<=.2 THEN 1 WHEN q.posicao<=.4 THEN 2 WHEN q.posicao<=.6 THEN 3
        WHEN q.posicao<=.8 THEN 4 WHEN q.posicao IS NOT NULL THEN 5 ELSE 0 END m
   FROM base b LEFT JOIN quantis q USING(cliente_id)
 ) SELECT *, CASE
   WHEN frequencia=0 THEN 'Sem compra na janela'
   WHEN r<=2 AND (f>=4 OR m>=4) THEN 'Valor a reativar'
   WHEN r>=4 AND f>=4 AND m>=4 THEN 'Recentes de alto valor'
   WHEN r>=4 THEN 'Recentes em desenvolvimento'
   WHEN r=3 THEN 'Intermediários'
   ELSE 'Inativos de menor valor' END segmento
 FROM notas;

CREATE TABLE estoque_produto AS
 WITH mov AS (
 SELECT produto_id,
 sum(CASE WHEN tipo_movimento='Entrada' THEN CAST(quantidade AS INTEGER) ELSE 0 END) entradas,
 sum(CASE WHEN tipo_movimento='Saída' THEN CAST(quantidade AS INTEGER) ELSE 0 END) saidas,
 sum(CASE WHEN tipo_movimento='Ajuste' THEN CAST(quantidade AS INTEGER) ELSE 0 END) ajustes,
 sum(CASE WHEN tipo_movimento='Devolução' THEN CAST(quantidade AS INTEGER) ELSE 0 END) devolucoes
 FROM estoque GROUP BY 1
 ), duracao AS (
 SELECT julianday(max(data_movimento))-julianday(min(data_movimento))+1 dias FROM estoque
 ), base AS (
 SELECT p.produto_id,p.categoria,p.nome_produto,CAST(p.estoque_cadastrado AS INTEGER) estoque,
 CAST(u.estoque_cadastrado AS INTEGER) estoque_ultimo,
 CAST(p.custo_estimado AS REAL) custo_unitario,
 coalesce(v.entradas,0) entradas,coalesce(v.saidas,0) saidas,
 coalesce(v.ajustes,0) ajustes,coalesce(v.devolucoes,0) devolucoes,
 CAST(p.estoque_cadastrado AS REAL)*d.dias/NULLIF(v.saidas,0) cobertura,
 CAST(u.estoque_cadastrado AS REAL)*d.dias/NULLIF(v.saidas,0) cobertura_ultimo,
 v.saidas/NULLIF(CAST(p.estoque_cadastrado AS REAL),0) intensidade
 FROM dim_produtos p LEFT JOIN mov v USING(produto_id)
 LEFT JOIN dim_produtos_ultimo u USING(produto_id) CROSS JOIN duracao d
 ) SELECT *,CASE WHEN cobertura IS NULL THEN 'Sem saídas'
 WHEN cobertura<30 THEN 'Cobertura abaixo de 30d'
 WHEN cobertura>180 THEN 'Cobertura acima de 180d' ELSE 'Entre 30 e 180d' END risco
 FROM base;
