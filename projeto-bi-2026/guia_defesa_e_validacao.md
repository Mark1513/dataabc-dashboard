# Guia de defesa e validação individual

## O que foi feito

O gerador original foi executado com tamanho de 0,2 GB e seed 20261029. A amostra de exemplo não foi usada nos resultados. A base cobre 2022-01-01 a 2026-10-01. O processamento lê lotes de 5.000 linhas e grava os dados no SQLite em disco.

## Apresentação sugerida: 7 a 10 minutos

1. Contexto e base gerada (1 minuto): explique o objetivo e o caráter sintético dos dados.
2. Qualidade e integração (2 minutos): mostre produtos conflitantes e clientes sem cadastro. Explique a dimensão de uma linha por produto e o cenário primeiro/último cadastro.
3. Dashboard e KPIs (2 minutos): filtre mês, região e canal em Comercial; mostre que os filtros de cada aba têm escopo próprio. Explique receita, desconto ponderado e margem de cenário.
4. Achados e ações (2 minutos): selecione três evidências quantificadas do relatório e a ação ligada a cada uma.
5. Método avançado e limites (1 a 2 minutos): explique a janela RFM, o grupo Valor a reativar, o teste de sensibilidade e por que isso não é previsão de churn.
6. Uso de IA: declare programação, interpretação e redação assistidas e descreva apenas as conferências que você realmente realizou.

## Conferência manual de um pedido

Pedido V000000000001, linha de dados 1 do CSV vendas.csv (linha física 2, contando o cabeçalho), status Concluído.

- Quantidade: 2.
- Preço unitário: R$ 1.029,91.
- Desconto: 18,2%.
- Bruto: 2 × 1029.91 = 2.059,82000 reais.
- Desconto em reais: bruto × 0.182 = 374,88724.
- Líquido: bruto − desconto = 1.684,93276 reais, exibido como R$ 1.684,93.

O cálculo mantém a precisão original por linha e arredonda somente a exibição final. Arredondar todas as linhas antes de somar pode produzir outro total. Margem depende de custo cadastral conflitante: não assuma que o primeiro registro é correto.

## Consultas para explicar e conferir

Abra resultados/dataabc.sqlite em um leitor SQLite e execute codigo/conferencias.sql. Consultas centrais:

```sql
SELECT status_pedido, COUNT(*) FROM vendas GROUP BY status_pedido;
SELECT SUM(liquido) FROM fato_vendas WHERE status_pedido='Concluído';
SELECT COUNT(*) FROM fato_vendas;
SELECT segmento,COUNT(*),SUM(monetario) FROM clientes_rfm GROUP BY segmento;
```

Explique que COUNT(*) é igual à contagem de pedidos nesta geração porque pedido_id é único. O pipeline interrompe a execução se aparecer repetição em uma chave de evento; uma base de itens exigiria item_id e contagem distinta de pedidos.

## Perguntas que você deve conseguir responder

- Receita líquida é lucro? Não: aqui significa valor após desconto dos pedidos concluídos, sem impostos, frete ou despesas.
- Por que não subtrair devolvidos mais uma vez? Eles já estão fora da receita elegível; sem histórico de status/estorno, não se deve descontar novamente.
- Por que LEFT JOIN? Para manter as vendas mesmo quando faltam cadastros. Para os produtos, a dimensão é primeiro reduzida a uma chave única de cenário.
- Por que não unir vendas, atendimento e marketing diretamente por cliente? Múltiplos eventos de cada fonte criam um produto cartesiano por cliente e repetem valores.
- Como foi validado? Receita recalculada diretamente no CSV por Decimal, cardinalidade antes/depois, reconciliação mensal e dos segmentos, e regras verificadas em codigo/validar.py.
- Recência cadastral é confiável? Não tem data de posição e diverge do histórico; a RFM usa compras concluídas na janela de 365 dias.
- Por que nem todos têm recência? Quem não comprou na janela tem recência nula e classe Sem compra na janela. Isso não significa que nunca comprou em todo o histórico.
- RFM prevê abandono? Não. São regras descritivas com parâmetros didáticos; a sensibilidade de 60/90/120 dias foi medida e não existe acurácia preditiva.
- Por que as notas de frequência têm pouca variação? Só um comprador tem 5 compras na janela. Os cortes precisam ser calibrados antes de uso operacional.
- Posso comparar outubro de 2026 com setembro? O extrato acaba em 01/10; a comparação de totais seria enganosa. O relatório compara janeiro-setembro entre anos.
- CPA é CAC? Não: conversão declarada não é necessariamente aquisição de um cliente novo.
- Por que o giro real está indisponível? Faltam CMV e estoque médio temporal confiáveis. Saídas/estoque cadastrado é uma proxy diferente.
- Devo comprar os produtos de baixa cobertura? Conferir primeiro posição datada, inventário e lead time, pois os cadastros são conflitantes.

## Registro de validação pessoal - preencher após executar

- [ ] Executei o pipeline e li o resultado do validador. Data: ______.
- [ ] Conferi o pedido demonstrado acima com calculadora. Resultado encontrado: ______.
- [ ] Conferi receita, contagens de status e junção no SQLite. Evidência/arquivo: ______.
- [ ] Testei filtros das quatro abas e um recorte sem dados. Observações: ______.
- [ ] Consigo explicar os blocos de analisar.py e as consultas de modelo.sql.
- [ ] Revisei os limites da margem, marketing, RFM e estoque.
- [ ] Completei a declaração de IA descrevendo somente validações que realizei.

As verificações automáticas já realizadas pela IA não foram marcadas como validações pessoais do aluno.
