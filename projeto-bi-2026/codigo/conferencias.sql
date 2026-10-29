-- Consultas para o aluno executar no banco resultados/dataabc.sqlite.
SELECT status_pedido,COUNT(*) pedidos FROM vendas GROUP BY 1;
SELECT COUNT(*) linhas,COUNT(DISTINCT pedido_id) pedidos_unicos FROM vendas;
SELECT COUNT(*) linhas FROM fato_vendas;
SELECT SUM(bruto) bruto,SUM(desconto) desconto,SUM(liquido) liquido
 FROM fato_vendas WHERE status_pedido='Concluído';
SELECT mes,SUM(liquido) receita,SUM(pedidos) pedidos
 FROM comercial_mensal GROUP BY 1 ORDER BY 1;
SELECT produto_id,COUNT(*) versoes,COUNT(DISTINCT categoria) categorias,
 COUNT(DISTINCT custo_estimado) custos FROM produtos GROUP BY 1 HAVING COUNT(*)>1 LIMIT 20;
SELECT COUNT(*) vendas_sem_cliente FROM vendas v
 LEFT JOIN dim_clientes c USING(cliente_id) WHERE c.cliente_id IS NULL;
SELECT segmento,COUNT(*) clientes,SUM(monetario) receita_365d
 FROM clientes_rfm GROUP BY 1 ORDER BY receita_365d DESC;
SELECT campanha,SUM(investimento)/SUM(conversoes) cpa_declarado,
 SUM(funil_invalido) registros_incoerentes FROM marketing_mensal GROUP BY 1;
SELECT produto_id,estoque,estoque_ultimo,cobertura,cobertura_ultimo
 FROM estoque_produto ORDER BY cobertura LIMIT 20;
