"""Documentos e dashboard a partir de métricas já conciliadas pelo pipeline."""
import csv, html, json, sys
from datetime import date,timedelta
from pathlib import Path

def n(x,d=0):
    return f'{x:,.{d}f}'.replace(',','@').replace('.',',').replace('@','.')
def brl(x): return 'R$ '+n(x,2)
def pct(x): return n(x*100,1)+'%'
def escape(x): return html.escape(str(x))

KPI=[
 ('K01','Receita bruta concluída','Σ(quantidade × preço unitário), status Concluído','vendas','Diária; fechamento mensal','Reais antes dos descontos. Não inclui cancelados, devolvidos ou processamento.'),
 ('K02','Receita líquida comercial','Σ[quantidade × preço × (1 − desconto)], status Concluído','vendas','Diária; fechamento mensal','Receita após desconto; impostos, frete, taxas e estornos financeiros não estão disponíveis.'),
 ('K03','Desconto ponderado','Σ desconto em R$ / receita bruta concluída','vendas','Mensal','Média ponderada pelo valor bruto. Não usar média simples dos percentuais.'),
 ('K04','Margem estimada do cenário','(Receita líquida − Σ quantidade × custo cadastral) / receita líquida','vendas + dim_produtos','Mensal','Primeiro cadastro é cenário. Custo conflitante e sem vigência. Não representa lucro líquido.'),
 ('K05','Ticket médio concluído','Receita líquida / pedidos distintos concluídos','vendas','Mensal','Pedido é único na base gerada; se surgir itemização, redefinir o contrato.'),
 ('K06','Taxa de conclusão','Pedidos Concluído / pedidos de todos os status','vendas','Mensal','Situação do extrato, sem acompanhamento da mudança de status no tempo.'),
 ('K07','Cancelados e devolvidos','(Pedidos Cancelado + Devolvido) / todos os pedidos','vendas','Mensal','Sinal operacional. Não é uma perda financeira comprovada ou taxa de coorte.'),
 ('K08','Frequência por comprador','Pedidos concluídos em 365 dias / clientes com ≥1 desses pedidos','vendas_cliente','Mensal; referência fixa nesta entrega','Descreve somente compradores na janela. Não usa compras_ultimos_30d do cadastro.'),
 ('K09','Recência média na janela','Média(data de referência − última compra concluída) dos compradores em 365 dias','clientes_rfm','Mensal; referência no último dia da base','Clientes sem compra na janela têm recência nula, não zero.'),
 ('K10','CSAT do atendimento','Atendimentos com nota 4 ou 5 / atendimentos com nota válida','atendimento','Mensal; histórico nesta entrega','Denominador é atendimento, não cliente único. Notas 1 a 5 validadas.'),
 ('K11','Reclamações por atendimento','Atendimentos por Atraso, Produto danificado, Reembolso ou Cobrança / atendimentos','atendimento','Mensal; histórico nesta entrega','Classificação de trabalho. Troca, Dúvida e Elogio ficam fora por não implicarem reclamação.'),
 ('K12','Atendimentos não resolvidos','Atendimentos Pendente ou Escalado / atendimentos','atendimento','Mensal; histórico nesta entrega','Sem data de encerramento, não mede atraso de SLA ou fila atual.'),
 ('K13','Investimento em marketing','Σ investimento dos registros','marketing','Mensal','Soma declarada. Não pressupõe que o gasto esteja ligado às vendas.'),
 ('K14','CTR declarado','Σ cliques / Σ impressões','marketing','Mensal','Razão agregada; há registros de funil incoerentes. Não garante validade do funil.'),
 ('K15','CVR declarado','Σ conversões / Σ cliques','marketing','Mensal','Conversões declaradas, sem deduplicação por pedido ou janela de atribuição.'),
 ('K16','CPA declarado','Σ investimento / Σ conversões','marketing','Mensal','Custo por conversão declarada. Não é CAC, ROI ou ROAS.'),
 ('K17','Funil incoerente','Registros com cliques > impressões OU conversões > cliques / registros de marketing','marketing','Por carga; mensal','União de condições; não somar os dois problemas, pois há sobreposição.'),
 ('K18','Cobertura de estoque - proxy','Estoque cadastrado / (saídas totais / dias do histórico)','estoque + dim_produtos','Por posição; cenário desta carga','Dias hipotéticos por SKU. Snapshot sem data; inclui motivos de saída diferentes de venda.'),
 ('K19','Intensidade de saídas - proxy','Saídas totais / estoque cadastrado','estoque + dim_produtos','Por carga; período integral','Razão no período integral, não anualizada. Não é o giro contábil.'),
 ('K20','Produtos com baixa cobertura','SKUs com cobertura <30 dias / SKUs com cobertura calculável','estoque_produto','Por posição; cenário desta carga','Limiar didático para conferência física, sem lead time ou nível de serviço.'),
 ('K21','Produtos com possível excesso','SKUs com cobertura >180 dias / SKUs com cobertura calculável','estoque_produto','Por posição; cenário desta carga','Sem obsolescência, sazonalidade ou data de posição; não comprova excesso.'),
 ('K22','Giro contábil do estoque','CMV do período / estoque médio ao custo no período','Não disponível','Mensal, quando houver insumos','Indisponível nesta base: faltam estoque médio temporal e CMV confiável. Não imputar zero.'),
]

DESCS={
 'cliente_id':'Identificador sintético do cliente. FK nos eventos; pode não existir no cadastro.',
 'produto_id':'Identificador sintético do produto. Repetido com atributos conflitantes no cadastro bruto.',
 'pedido_id':'Identificador do pedido; único nesta geração. Uma linha observada por pedido.',
 'interacao_id':'Identificador único do registro de marketing; contagens agregadas no registro.',
 'atendimento_id':'Identificador único do evento de atendimento.',
 'movimento_id':'Identificador único da movimentação de estoque.',
 'nome_ficticio':'Nome sintético, sem finalidade de identificação real.',
 'idade':'Idade declarada, em anos.', 'renda_mensal':'Renda mensal declarada, em reais.',
 'regiao':'Região do evento ou do cadastro, conforme tabela. Não substituir a região da venda pela do cliente.',
 'canal_preferido':'Canal preferido cadastral, não necessariamente o canal utilizado.',
 'data_cadastro':'Data declarada de cadastro; há eventos anteriores a ela.',
 'status_cliente':'Situação cadastral declarada, independente do segmento RFM.',
 'satisfacao_1a5':'Nota geral do cadastro, escala 1 a 5; distinta da satisfação do atendimento.',
 'compras_ultimos_30d':'Contagem declarada pelo gerador, sem data de posição; não usada para frequência calculada.',
 'dias_desde_ultima_compra':'Recência declarada sem data de referência. Diverge do histórico; preservada apenas para auditoria.',
 'observacao':'Texto sintético livre. Não utilizado em métricas.',
 'data_venda':'Data do pedido (ISO AAAA-MM-DD). Não há data de fechamento ou devolução.',
 'canal':'Canal efetivamente registrado no pedido.',
 'quantidade':'Quantidade de unidades no pedido ou movimento; positiva e inteira.',
 'preco_unitario':'Preço unitário transacional em reais, antes de desconto.',
 'desconto_percentual':'Fração de desconto: 0,182 significa 18,2%.',
 'status_pedido':'Concluído, Cancelado, Devolvido ou Em processamento. Receita somente de Concluído.',
 'forma_pagamento':'Meio de pagamento declarado. Sem valores de taxas.',
 'prazo_entrega_dias':'Prazo declarado em dias. Sem data de entrega real, não mede atraso.',
 'nome_produto':'Nome sintético do produto.', 'categoria':'Categoria cadastral; 9.999 SKUs têm mais de uma categoria.',
 'faixa_preco':'Faixa declarada pelo gerador; sem regra documentada.',
 'preco_lista':'Preço de lista cadastral em reais; não substitui o preço transacional.',
 'custo_estimado':'Custo unitário estimado em reais. Sem vigência e conflitante em todos os SKUs.',
 'estoque_cadastrado':'Unidades no cadastro, sem data ou depósito da posição. Usado somente em cenário.',
 'produto_ativo':'Indicador cadastral Sim/Não, gerado independentemente das vendas.',
 'descricao':'Texto sintético livre do produto.',
 'data_atendimento':'Data do evento de atendimento, sem data de encerramento.',
 'canal_atendimento':'Canal usado no atendimento.',
 'motivo':'Motivo do evento. Significado depende da fonte; não usar como sinal algébrico do estoque.',
 'satisfacao_atendimento':'Nota de 1 a 5 por atendimento; notas 4 e 5 compõem o CSAT.',
 'duracao_minutos':'Duração declarada em minutos, sem timestamps de início/fim.',
 'status_atendimento':'Resolvido, Pendente ou Escalado; fotografia declarada, sem evolução.',
 'recontatos':'Contagem declarada de recontatos; não equivale a clientes únicos.',
 'comentario':'Texto sintético livre do atendimento.',
 'data_interacao':'Data do registro de marketing.',
 'campanha':'Tipo de campanha declarado, sem identificador único de execução ou experimento.',
 'meio':'Meio de comunicação de marketing.',
 'canal_venda':'Canal de venda associado ao registro de marketing, sem vínculo com pedido.',
 'impressoes':'Contagem declarada de impressões no registro agregado.',
 'cliques':'Contagem declarada de cliques; pode superar impressões.',
 'conversoes':'Contagem declarada de conversões; pode superar cliques. Sem pedido vinculado.',
 'investimento':'Investimento declarado do registro em reais.',
 'resultado':'Rótulo declarado do resultado; pode contradizer a contagem de conversões.',
 'data_movimento':'Data do movimento de estoque.',
 'tipo_movimento':'Entrada, Saída, Ajuste ou Devolução. Ajustes/devoluções sem sinal inequívoco.',
 'deposito':'Identificador do depósito do movimento; não existe posição cadastral por depósito.',
}

def dictionary(out,source):
    rows=[]
    from analisar import KEYS,NUMS
    for table,key in KEYS.items():
        with (source/f'{table}.csv').open(encoding='utf-8-sig',newline='') as f:
            cols=next(csv.reader(f))
        for field in cols:
            typ='data ISO' if field.startswith('data_') else 'decimal/número' if field in NUMS else 'texto'
            role='chave de negócio' if field==key else 'FK' if field in ('cliente_id','produto_id') else 'atributo'
            rows.append([table,field,typ,role,DESCS.get(field,'Atributo declarado da fonte.'),'Não observados vazios nesta geração',table+'.csv'])
    derived=[
      ('dim_produtos','produto_id','texto','PK única','Primeiro registro físico por produto: cenário sem autoridade temporal.'),
      ('dim_produtos_ultimo','produto_id','texto','PK única','Último registro físico por produto: teste de sensibilidade, não cadastro vigente.'),
      ('fato_vendas','_linha','inteiro','PK técnica','Linha de origem, preservada sem multiplicação após LEFT JOINs.'),
      ('fato_vendas','bruto','real BRL','medida','quantidade × preço unitário.'),
      ('fato_vendas','desconto','real BRL','medida','bruto × desconto_percentual.'),
      ('fato_vendas','liquido','real BRL','medida','bruto − desconto. Receita agregada usa somente Concluído.'),
      ('fato_vendas','custo_primeiro','real BRL','medida de cenário','quantidade × custo unitário do primeiro registro.'),
      ('fato_vendas','custo_ultimo','real BRL','medida de cenário','quantidade × custo unitário do último registro.'),
      ('clientes_rfm','cliente_id','texto','PK única','União dos IDs observados em clientes, vendas, atendimento e marketing.'),
      ('clientes_rfm','frequencia','inteiro','medida','Pedidos concluídos em 365 dias, incluindo a data de referência.'),
      ('clientes_rfm','monetario','real BRL','medida','Receita líquida dos pedidos concluídos na janela de 365 dias.'),
      ('clientes_rfm','recencia','inteiro dias','medida','Data de referência menos última compra na janela. Nulo se não comprou na janela.'),
      ('clientes_rfm','r','inteiro 0 a 5','regra','R: 5 até 30d; 4 até 60d; 3 até 90d; 2 até 180d; 1 depois; 0 sem compra na janela.'),
      ('clientes_rfm','f','inteiro 0 a 5','regra','F: 5 para ≥8 pedidos; 4 para ≥5; 3 para ≥3; 2 para ≥2; 1 para 1; 0 para nenhum.'),
      ('clientes_rfm','m','inteiro 0 a 5','regra','Quintil monetário entre compradores usando CUME_DIST. Empates preservados; 0 sem compra.'),
      ('clientes_rfm','segmento','texto','classe descritiva','Regras sequenciais em modelo.sql. Não é previsão de churn.'),
      ('clientes_rfm','reclamacoes','inteiro','medida','Contagem de atendimentos por Atraso, Produto danificado, Reembolso e Cobrança em todo o histórico.'),
      ('estoque_produto','cobertura','real dias','proxy de cenário','Estoque do primeiro cadastro × dias de histórico / saídas totais.'),
      ('estoque_produto','cobertura_ultimo','real dias','proxy de cenário','Mesma fórmula, substituindo pelo último cadastro.'),
      ('estoque_produto','intensidade','real','proxy de cenário','Saídas totais / estoque do primeiro cadastro. Não é giro contábil.'),
      ('estoque_produto','risco','texto','hipótese','Faixas <30d, 30-180d, >180d ou sem saídas. Não confirma ruptura/excesso.'),
    ]
    for table,field,typ,role,desc in derived: rows.append([table,field,typ,role,desc,'Nulo quando o insumo/denominador não existir','modelo.sql'])
    with (out/'dicionario_atualizado.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['tabela','campo','tipo_logico','papel','definicao_regra','nulos','origem']);w.writerows(rows)
    with (out/'catalogo_kpis.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['id','kpi','formula','fonte','periodicidade','interpretacao_limitacao']);w.writerows(KPI)

def contents(d):
    s=d['stats'];m=d['marketing'];st=d['stock'];a=d['services'];co=d['controls']
    buyers=co['clientes_rfm_com_compra']; target=next(x for x in d['rfm'] if x['segmento']=='Valor a reativar')
    fk=next(x for x in d['fks'] if x['origem']=='vendas' and x['chave']=='cliente_id')
    near={x['ano']:x['liquido'] for x in d['semantic']['comparacao_jan_set']}
    growth=near['2026']/near['2025']-1
    start=(date.fromisoformat(s['fim'])-timedelta(days=364)).strftime('%d/%m/%Y')
    def P(t):return ('p',t)
    def H(t):return ('h',t)
    def T(head,rows,widths=None):return ('table',(head,rows,widths))
    pages=[]
    pages.append(('A receita é apurável; custos e estoque exigem saneamento',[
      P('Relatório final do projeto individual de Business Intelligence. Empresa e dados sintéticos, para fins didáticos. Base efetivamente gerada pelo programa fornecido, em substituição à amostra de exemplo.'),
      T(['Indicador','Resultado'],[
        ['Período analisado',f"{s['inicio']} a {s['fim']} ({n(s['meses'])} meses; último mês parcial)"],
        ['Registros nas seis fontes',n(sum(x['linhas'] for x in d['quality']))],
        ['Receita líquida comercial',brl(s['liquido'])],
        ['Pedidos concluídos',f"{n(s['pedidos'])} de {n(s['registros'])} ({pct(s['pedidos']/s['registros'])})"],
        ['Margem no cenário do primeiro cadastro',pct(s['margem']/s['liquido'])],
        ['Investimento declarado em marketing',brl(m['investimento'])]
      ],[.45,.55]),
      H('Achados que orientam a decisão'),
      P(f"1. Cancelados e devolvidos somam {n(s['cancelados']+s['devolvidos'])} pedidos, ou {pct((s['cancelados']+s['devolvidos'])/s['registros'])} do extrato. A situação final declarada pede investigação operacional; não comprova perda recuperável."),
      P(f"2. Há {n(m['funil_invalido'])} registros de marketing com funil incoerente ({pct(m['funil_invalido']/m['interacoes'])}). Campanhas não devem ser escaladas usando apenas conversões declaradas."),
      P(f"3. O segmento Valor a reativar contém {n(target['clientes'])} clientes e {pct(target['monetario']/co['receita_janela_rfm'])} da receita dos últimos 365 dias. É uma seleção para teste, sem previsão de retorno."),
      P(f"4. {n(st['risco30'])} SKUs apresentam cobertura hipotética abaixo de 30 dias, mas outro cadastro aponta {n(st['risco30_ultimo'])}. A verificação física e a data de posição são pré-requisitos para compra."),
      H('Decisão proposta'),
      P('Priorizar governança dos cadastros e rastreabilidade de marketing. Em paralelo, investigar motivos de cancelamento/devolução e realizar um teste controlado de reativação. Não converter margens de cenário ou coberturas hipotéticas em decisões automáticas.'),
      P('Geração: --gb 0.2 --seed 20261029. Pacote original e seu gerador foram preservados como referência; hashes e contagens estão em resultados/manifesto_fontes.json. Elaboração em 29/10/2026. Autoria individual deve ser preenchida pelo aluno.')
    ]))
    qrows=[[x['tabela'],n(x['linhas']),n(x['chaves_duplicadas']),n(x['linhas_excedentes']),n(sum(x['ausencias'].values()))] for x in d['quality']]
    pages.append(('Qualidade: falhas semânticas permanecem visíveis',[
      P('CSV em UTF-8 com BOM. Leitura por lotes de 5.000 linhas para SQLite em disco. Validação de datas ISO, números finitos e não negativos, quantidade inteira positiva, notas de 1 a 5, descontos entre 0 e 1 e domínios principais. Não foram observados vazios, duplicatas de linha completa ou valores inválidos nesses testes.'),
      T(['Fonte','Linhas','IDs repetidos','Excedentes','Vazios'],qrows,[.20,.20,.20,.20,.20]),
      H('Problemas de chave e de significado'),
      P(f"Produtos: {n(d['conflicts']['produtos'])} chaves e {n(next(x['linhas_excedentes'] for x in d['quality'] if x['tabela']=='produtos'))} linhas excedentes. Todos os produtos têm custos e saldos conflitantes; {n(d['conflicts']['categoria'])} têm categorias diferentes. Essas repetições não são cópias idênticas."),
      P(f"Vendas: {n(fk['linhas'])} eventos ({pct(fk['linhas']/s['registros'])}) referenciam {n(fk['chaves'])} clientes ausentes do cadastro. Os valores financeiros foram preservados; perfis desconhecidos recebem Sem cadastro."),
      T(['Relacionamento','Eventos sem dimensão'],[[x['origem']+' → '+x['destino'],n(x['linhas'])] for x in d['fks']],[.7,.3]),
      P(f"Cronologia: {n(d['semantic']['venda_antes_cadastro']['anteriores'])} vendas são anteriores ao cadastro entre {n(d['semantic']['venda_antes_cadastro']['comparaveis'])} vendas com cliente correspondente. Sem histórico cadastral, isso é inconsistência a investigar, sem descarte automático."),
      P(f"Recência: {n(d['recency']['divergentes'])} de {n(d['recency']['comparaveis'])} clientes comparáveis diferem mais de 30 dias entre cadastro e última compra concluída no histórico. A comparação usa o encerramento da base como referência assumida; a data do snapshot cadastral não foi fornecida."),
      P(f"Marketing: {n(d['semantic']['resultado_marketing']['contradicoes'])} registros contradizem o rótulo de conversão. Estoque: saldo inicial, data de posição e sinais de ajustes/devoluções não estão disponíveis. O relatório de qualidade HTML detalha as políticas de tratamento.")
    ]))
    pages.append(('Integração sem multiplicar os valores',[
      H('Grãos observados e relacionamentos'),
      T(['Objeto','Grão / regra'],[
        ['clientes e dim_clientes','Um cadastro por cliente nesta geração. IDs desconhecidos permanecem nos eventos.'],
        ['produtos bruto','Vários cadastros conflitantes por produto; sem data de vigência.'],
        ['dim_produtos e dim_produtos_ultimo','Uma linha por produto, escolhida pela primeira/última linha física. São cenários.'],
        ['vendas e fato_vendas','Um registro por pedido observado. PK técnica _linha preserva a rastreabilidade.'],
        ['atendimento','Um evento por atendimento_id, muitos para cada cliente.'],
        ['marketing','Um registro agregado por interacao_id; muitas contagens por cliente.'],
        ['estoque','Um movimento por movimento_id, muitos para cada produto/depósito.'],
        ['clientes_rfm','Uma linha por cliente após agregar cada fato separadamente.']
      ],[.32,.68]),
      H('Como o risco de duplicação foi evitado'),
      P('O modelo usa LEFT JOIN de vendas com dimensões de produto de chave única, sem unir vendas diretamente a atendimento ou marketing. Atendimento é agregado por cliente antes da junção com os resultados de compras. Compras, estoque e marketing mantêm medidas separadas.'),
      P(f"Uma junção ingênua das vendas ao cadastro bruto de produtos produziria {n(co['linhas_fanout_ingenuo'])} linhas ({n(co['linhas_fanout_ingenuo']/s['registros'],2)} vezes o original). O modelo entregue preservou exatamente {n(co['linhas_depois_join'])} linhas."),
      H('Conciliações executadas'),
      P(f"Receita calculada independentemente por Decimal e leitura streaming dos CSVs: {brl(float(co['receita_decimal']))}. Diferença para SQL: {n(abs(co['diferenca_reais']),6)} real. Soma mensal e total comercial coincidem com tolerância inferior a R$ 0,01. A receita dos segmentos RFM também confere com os pedidos da sua janela."),
      P('A região comercial vem do evento de venda. A região no painel de clientes vem do cadastro. Categoria, custo e saldo dependem do cenário cadastral. Não se atribui a receita total aos clientes que tiveram contato com uma campanha.'),
      P('Valores monetários não são arredondados em cada linha: os produtos são somados com a precisão original e exibidos em centavos no final. As verificações de receita usam Decimal para conferir o resultado analítico em ponto flutuante.')
    ]))
    for title,items in [('Catálogo de KPIs: comercial e clientes',KPI[:11]),('Catálogo de KPIs: atendimento, marketing e estoque',KPI[11:])]:
        rows=[[f'{k} · {name}',f'{formula}<br/><i>Fonte:</i> {source}<br/><i>Periodicidade:</i> {period}',interp] for k,name,formula,source,period,interp in items]
        pages.append((title,[P('Razões são calculadas pela divisão das somas, com nulo quando o denominador é zero. As periodicidades abaixo são propostas para acompanhamento; esta entrega representa uma carga estática.'),T(['KPI','Fórmula, fonte e periodicidade','Interpretação e limite'],rows,[.22,.42,.36])]))
    pages.append(('Comercial: comparar períodos equivalentes',[
      P(f"A receita líquida comercial foi de {brl(s['liquido'])}, após {brl(s['desconto'])} em descontos sobre {brl(s['bruto'])} de receita bruta dos pedidos concluídos. Desconto ponderado: {pct(s['desconto']/s['bruto'])}. Ticket médio: {brl(s['liquido']/s['pedidos'])}."),
      ('chart','monthly'),
      P(f"Em janeiro-setembro de 2026, a receita foi {brl(near['2026'])}, ante {brl(near['2025'])} em janeiro-setembro de 2025 ({pct(growth)} de variação). A comparação preserva o mesmo intervalo de calendário."),
      P('Outubro de 2026 contém apenas 01/10. A queda do total desse mês em relação a setembro é efeito da cobertura parcial e não demonstra deterioração do negócio. O gráfico destaca o último mês parcial.'),
      T(['Canal de venda','Receita líquida','Pedidos concluídos'],[[x['canal'],brl(x['liquido']),n(x['pedidos'])] for x in d['channels']],[.35,.40,.25]),
      P('Região e canal são campos transacionais, portanto independem da resolução dos cadastros de produtos. O dashboard permite comparar ambos por mês.'),
      P(f"No cenário de primeiro cadastro, o custo estimado é {brl(s['custo'])} e a margem {pct(s['margem']/s['liquido'])}. Com o último cadastro, a margem é {pct(s['margem_ultimo']/s['liquido'])}. A diferença de {n(abs(s['margem_ultimo']-s['margem'])/s['liquido']*100,2)} ponto percentual mede apenas a sensibilidade a duas escolhas arbitrárias, não a incerteza total."),
      P(f"{n(d['semantic']['pedidos_margem_negativa_cenario'])} pedidos concluídos têm margem negativa no primeiro cenário. O gerador sorteia preços de venda e custos de forma independente. Antes de recomendar reajustes, validar custo vigente e vínculo do preço ao SKU.")
    ]))
    pages.append(('Clientes: segmentação RFM para investigação',[
      P(f"Universo: {n(co['clientes_rfm'])} IDs distintos observados nas fontes de clientes e eventos. Janela RFM: {start} a {s['fim'].split('-')[2]}/{s['fim'].split('-')[1]}/{s['fim'].split('-')[0]} (365 dias). Há {n(buyers)} compradores e {brl(co['receita_janela_rfm'])} de receita nessa janela."),
      H('Método e regras'),
      P('R = 5 até 30 dias, 4 até 60, 3 até 90, 2 até 180 e 1 depois. F = 5 para ≥8 pedidos, 4 para ≥5, 3 para ≥3, 2 para ≥2 e 1 para 1. M = quintis da receita entre compradores, com CUME_DIST para preservar empates. Sem compra na janela recebe R/F/M = 0 e recência nula.'),
      P('Regras na ordem: sem compra; Valor a reativar (R≤2 e F≥4 ou M≥4); Recentes de alto valor (R≥4, F≥4 e M≥4); Recentes em desenvolvimento (R≥4); Intermediários (R=3); demais, Inativos de menor valor. O primeiro teste de reativação usa R≤2 E (F≥4 OU M≥4).'),
      T(['Segmento observado','Clientes','Receita em 365 dias'],[[x['segmento'],n(x['clientes']),brl(x['monetario'])] for x in d['rfm']],[.44,.16,.40]),
      P(f"Valor a reativar: {n(target['clientes'])} clientes ({pct(target['clientes']/buyers)} dos compradores) concentram {pct(target['monetario']/co['receita_janela_rfm'])} da receita na janela. A receita histórica não equivale a potencial recuperável."),
      H('Avaliação crítica e sensibilidade'),
      T(['Recência para reativar','Clientes selecionados','Receita histórica'],[[f">{x['corte']} dias",n(x['clientes']),brl(x['monetario'])] for x in d['sensitivity']],[.36,.24,.40]),
      P('O método é transparente e reproduzível, adequado a uma base sem rótulo futuro de abandono. Os limiares são hipóteses didáticas. Não houve treino, teste ou acurácia preditiva. A distribuição de frequência é baixa: só um comprador tem 5 pedidos na janela e nenhum chega a 8; a classe Recentes de alto valor não tem membros nesta carga. Recomenda-se calibrar os limiares antes de uso operacional.'),
      P(f"Atendimento no histórico: CSAT {pct(a['satisfeitos']/a['n'])}, reclamações por atendimento {pct(a['reclamacoes']/a['n'])} e não resolvidos {pct(a['abertos']/a['n'])}. A classificação de reclamações é explícita; não há vínculo a pedido ou prova de que a insatisfação causou inatividade.")
    ]))
    pages.append(('Marketing: custo declarado não demonstra retorno',[
      P(f"Investimento total: {brl(m['investimento'])}. Impressões: {n(m['impressoes'])}; cliques: {n(m['cliques'])}; conversões declaradas: {n(m['conversoes'])}. CTR agregado: {pct(m['cliques']/m['impressoes'])}; CVR: {pct(m['conversoes']/m['cliques'])}; CPA: {brl(m['investimento']/m['conversoes'])}."),
      T(['Campanha','Investimento','Conversões','CPA declarado'],[[x['campanha'],brl(x['investimento']),n(x['conversoes']),brl(x['investimento']/x['conversoes'])] for x in d['campaign_summary']],[.23,.32,.24,.21]),
      H('Problemas do funil'),
      P(f"Há {n(m['cliques_maiores_impressoes'])} registros com mais cliques que impressões e {n(m['conversoes_sem_clique'])} com mais conversões que cliques. A união tem {n(m['funil_invalido'])} registros ({pct(m['funil_invalido']/m['interacoes'])}), pois as condições podem se sobrepor. Além disso, {n(d['semantic']['resultado_marketing']['contradicoes'])} rótulos de resultado contradizem a contagem de conversões."),
      P('Os registros inconsistentes foram preservados nos totais e sinalizados no painel. Excluí-los silenciosamente poderia reduzir gastos ou alterar comparações. O CPA reportado descreve o arquivo; não valida a eficiência da campanha.'),
      H('Limites de atribuição'),
      P('cliente_id sozinho não liga uma conversão a um pedido. Faltam pedido_id, identificador único da conversão, carimbo de tempo detalhado, janela de atribuição, definição do evento de conversão e deduplicação entre meios. As conversões agregadas não são novos clientes nem compras comprovadas.'),
      P('Não foram calculados CAC, ROAS ou ROI, nem foi repartida a receita proporcionalmente aos cliques. Também não se assume causalidade entre exposição e compra: clientes podem ter múltiplos contatos e comprar sem influência da campanha.'),
      H('Recomendação sustentada'),
      P('Padronizar o evento de conversão e a ligação ao pedido. Corrigir o funil antes de ampliar investimento. Para testar uma campanha, usar grupo de controle e medir diferença de compras concluídas e margem com custo validado. As pequenas diferenças de CPA declarado entre campanhas não sustentam uma realocação de verba por si só.')
    ]))
    pages.append(('Estoque: sinais exploratórios, sem saldo conciliável',[
      P(f"Entre {st['inicio']} e {st['fim']} ({n(st['dias'])} dias), foram registradas {n(st['entradas'])} unidades de entrada, {n(st['saidas'])} de saída, {n(st['ajustes'])} em ajustes e {n(st['devolucoes'])} em devoluções. Não há saldo inicial, posição por depósito, sinal dos ajustes ou destino inequívoco das devoluções."),
      T(['Medida de cenário','Primeiro registro','Último registro'],[
       ['SKUs com cobertura <30 dias',n(st['risco30']),n(st['risco30_ultimo'])],
       ['SKUs com cobertura >180 dias',n(st['excesso180']),n(st['excesso180_ultimo'])],
       ['Total de SKUs analisados',n(st['produtos']),n(st['produtos'])]
      ],[.50,.25,.25]),
      H('Hipóteses da cobertura'),
      P('A cobertura proxy usa estoque cadastrado ÷ (saídas totais ÷ dias do histórico), por SKU. Pressupõe que o cadastro represente uma posição comparável ao fim do período e que a média histórica represente a demanda futura. Nenhuma dessas hipóteses é confirmada pelas fontes. Saídas incluem diferentes motivos, não somente venda.'),
      T(['SKU ilustrativo','Cobertura primeiro (dias)','Cobertura último (dias)'],[[x['produto_id'],n(x['cobertura'],2),n(x['cobertura_ultimo'],2)] for x in d['inventory'][:5]],[.26,.37,.37]),
      P('O mesmo produto pode passar de cobertura inferior a um dia para milhares de dias quando se troca apenas a linha cadastral escolhida. Isso torna a conferência do cadastro e do inventário mais urgente do que a reposição automática.'),
      H('Giro e reconciliação'),
      P('A razão saídas/estoque cadastrado é apresentada como intensidade de saídas no histórico integral. O giro contábil (CMV/estoque médio ao custo) fica indisponível. Não se soma Entrada − Saída + Ajuste + Devolução para fabricar saldo final: dois desses tipos não possuem sinal documentado e falta o saldo inicial.'),
      P('As vendas também não trazem depósito ou vínculo ao movimento. Diferenças entre unidades vendidas e saídas físicas não podem ser interpretadas como perdas sem identificar transferências, avarias, devoluções e movimentos associados ao pedido.'),
      P('Os limiares de 30 e 180 dias são escolhas didáticas para investigação. Para decisão operacional, incorporar lead time, estoque de segurança, sazonalidade, prazo de validade e posição física com data.')
    ]))
    actions=[
      ('P0 · Antes de usar margem/estoque','Sanear cadastro mestre de produtos',
       f"{n(d['conflicts']['custo'])} produtos com custo conflitante; risco de multiplicar as vendas em {n(co['linhas_fanout_ingenuo']/s['registros'],2)} vezes numa junção direta.",
       'Responsável proposto: dados/cadastro. Definir versão vigente por produto, custo datado e posição de estoque por depósito. Preservar histórico.',
       'Acompanhar IDs conflitantes e % de vendas com produto único. Critério proposto: zero conflitos sem regra e 100% de correspondência.',
       'Limite: primeiro/último registro físico não identifica o dado correto.'),
      ('P0 · Antes de ampliar campanhas','Instrumentar marketing e corrigir o funil',
       f"{n(m['funil_invalido'])} registros incoerentes ({pct(m['funil_invalido']/m['interacoes'])}); {n(d['semantic']['resultado_marketing']['contradicoes'])} rótulos contraditórios.",
       'Responsável proposto: marketing/engenharia. Documentar conversão, pedido vinculado, janela e deduplicação.',
       'Acompanhar K17 e % de conversões com pedido elegível. Meta proposta: zero violação inexplicada e vínculo auditável.',
       'Limite: cliques e conversões declarados não medem incremento de vendas.'),
      ('P1 · Após rastrear os motivos','Investigar cancelamento, devolução e atendimento',
       f"{pct((s['cancelados']+s['devolvidos'])/s['registros'])} dos pedidos cancelados/devolvidos; {pct(a['abertos']/a['n'])} dos atendimentos não resolvidos.",
       'Responsável proposto: operações/atendimento. Vincular atendimento ao pedido e medir motivos, tempo e coortes de fechamento.',
       'Acompanhar K07, K10 e K12. Definir meta de redução após medir a linha de base por coorte.',
       'Limite: status sorteados e sem evolução temporal não provam falha operacional real.'),
      ('P1 · Piloto após saneamento','Testar reativação com grupo de controle',
       f"{n(target['clientes'])} clientes concentram {pct(target['monetario']/co['receita_janela_rfm'])} da receita da janela RFM.",
       'Responsável proposto: CRM. Sortear elegíveis entre contato e controle, com a mesma janela futura de observação e custo de contato registrado.',
       'Acompanhar taxa de compra concluída incremental, receita por elegível e margem incremental após custo validado.',
       'Limite: RFM é descritivo; receita histórica não é retorno esperado. Limiares devem ser calibrados.'),
      ('P1 · Antes de comprar ou liquidar','Conferir inventário dos SKUs sinalizados',
       f"{n(st['risco30'])} SKUs abaixo de 30 dias e {n(st['excesso180'])} acima de 180 dias no primeiro cenário.",
       'Responsável proposto: estoque/compras. Contar fisicamente, datar posição, reconciliar sinais e registrar lead times.',
       'Acompanhar % de posições conciliadas e K18/K20/K21 após validação. Meta proposta: 100% dos SKUs priorizados conferidos.',
       'Limite: cobertura média de 1.735 dias de histórico pode ocultar sazonalidade; não é ruptura comprovada.')
    ]
    blocks=[P('Prioridades propostas, sem estimar ganhos financeiros não demonstrados. P0 corrige pré-requisitos; P1 depende dessas correções ou de vínculo transacional verificável.')]
    for priority,title,evidence,how,kpi,limit in actions:
        blocks += [H(priority+' · '+title),P('<b>Evidência:</b> '+evidence),P(how),P('<b>KPI e critério:</b> '+kpi),P('<b>Limitação:</b> '+limit)]
    pages.append(('Plano de ação: pré-requisitos e operação',blocks[:16]))
    pages.append(('Plano de ação: pilotos de CRM e inventário',[P('Continuação das ações propostas. A execução deve respeitar os pré-requisitos de qualidade e a medição de resultados.')]+blocks[16:]))
    pages.append(('Código, reprodutibilidade e validação',[
      H('Como repetir a análise'),
      P('Pré-requisitos: Python 3.10 ou superior e ReportLab 4.4.9 para recriar o PDF. SQLite, CSV e Decimal fazem parte da biblioteca padrão. A análise usa SQLite em disco, leitura por lotes e agregados para o navegador.'),
      ('code','python -m pip install -r codigo/requirements.txt\npython codigo/gerador_original.py --gb 0.2 --seed 20261029 --saida dados_regenerados\npython codigo/analisar.py --entrada dados_regenerados --saida refeito\npython codigo/validar.py --projeto refeito --entrada dados_regenerados'),
      P('Para usar os CSVs já entregues, substitua dados_regenerados por dados_origem. A execução recria somente resultados/dataabc.sqlite e os arquivos derivados na pasta de saída. Não modifica os CSVs. Para auditoria de bytes, comparar o manifesto; manter a versão do Python e o ambiente de geração registrados.'),
      H('Organização e explicação do código'),
      T(['Arquivo','Responsabilidade'],[
        ['gerador_original.py','Programa original recebido, sem alteração. Seed e tamanho controlam a geração.'],
        ['analisar.py','Importa em lotes, valida as fontes, executa SQL, reconcilia e exporta evidências.'],
        ['modelo.sql','Cria dimensões de cenários, fatos e agregados por seus grãos corretos.'],
        ['documentos.py','Produz catálogo, dicionário, relatório PDF/HTML e orientações a partir dos resultados.'],
        ['dashboard_template.html','Interface local com filtros por aba e exportação do recorte.'],
        ['validar.py','Confere hashes, receita diretamente nos CSVs, cardinalidade e regras RFM.']
      ],[.34,.66]),
      P('O banco analítico pode crescer além de 200 MB. Os CSVs não são carregados integralmente na memória; índices e resultados intermediários ficam no disco. A cache do SQLite foi limitada aproximadamente a 64 MiB e temporários configurados em arquivo. As únicas listas exportadas ao HTML são agregados e 10 mil produtos.'),
      H('Limitações gerais do experimento'),
      P('O gerador sorteia grande parte dos atributos independentemente: não incorpora uma história econômica causal. Seus padrões descrevem os dados sintéticos, sem generalização para o varejo real. O tamanho em bytes controla a quantidade de linhas por fonte e pode truncar o cadastro de clientes ou repetir o de produtos. Resultados observados refletem essas escolhas.'),
      P('Não foi treinado modelo preditivo: a segmentação RFM atende à análise adicional com regras auditáveis, avaliação de distribuição e sensibilidade. Não há rótulo futuro confiável para avaliar churn ou justificativa para projetar receitas com base nesses sorteios.')
    ]))
    pages.append(('Uso de IA e preparação para a defesa individual',[
      H('Declaração de uso efetivo'),
      P('Foi utilizado o Codex, assistente de IA da OpenAI, para apoiar a programação em Python e SQL, a construção do dashboard, a interpretação dos resultados e a redação dos relatórios. A IA executou o gerador fornecido, auxiliou a identificar problemas de qualidade e efetuou verificações automáticas de receita e de integração. Os dados são sintéticos, conforme o enunciado.'),
      P('As verificações automáticas descritas neste relatório foram executadas pelo assistente. Elas não substituem a validação individual exigida do aluno. Esta versão não declara que o aluno já conferiu os cálculos ou domina o código. A conclusão dessa etapa depende da execução e explicação pelo próprio aluno.'),
      H('Validação que o aluno deve concluir'),
      P('1. Reexecutar a análise e validar as contagens e o manifesto. 2. Conferir uma venda concluída com calculadora e o total do período com a consulta entregue. 3. Explicar por que cancelados e devolvidos não entram na receita. 4. Demonstrar que a junção não multiplicou linhas. 5. Testar os filtros do dashboard e explicar o escopo de cada aba. 6. Revisar as regras de RFM e os cenários de custo/estoque.'),
      H('Perguntas centrais para a defesa'),
      P('<b>Por que a margem é um cenário?</b> Todos os produtos têm custos cadastrais conflitantes e não existe vigência. Primeiro/último registro tornam o procedimento reproduzível, sem identificar o custo correto.'),
      P('<b>Por que não há ROAS?</b> Não existe ligação inequívoca entre conversão e pedido, definição do evento ou janela de atribuição. cliente_id não basta.'),
      P('<b>Como evitou duplicação?</b> Dimensões de chave única e agregação de fatos no mesmo grão antes de integrar. Conferência da quantidade de linhas e da receita antes/depois.'),
      P('<b>Por que RFM?</b> Regras simples que permitem investigação sem inventar rótulo futuro. Sensibilidade de 60/90/120 dias mostra dependência dos parâmetros.'),
      P('<b>O que os indicadores de estoque provam?</b> Apenas sinais condicionais às hipóteses declaradas. Faltam posições datadas, sinais e estoque médio para conciliar saldo ou giro real.'),
      P('O arquivo guia_defesa_e_validacao.md traz roteiro de apresentação, exercício numérico, consultas de conferência e campos para registrar o que foi validado pessoalmente. A declaração editável de IA está em declaracao_uso_IA.md; completar a seção de conferências somente depois de realizá-las.'),
      P('Fontes de evidência: os seis CSVs gerados e seu dicionário original; modelo.sql; resultados/analise.json, qualidade.json, validacao.json e os CSVs analíticos. Não foram usadas estatísticas externas ou dados reais para produzir as conclusões.')
    ]))
    return pages,actions

CSS='''body{font:16px/1.65 "Segoe UI",Arial,sans-serif;color:#19324b;background:#f2f5f8;margin:0}header{background:#132b45;color:white;padding:36px max(5vw,24px)}header h1{font-size:34px;max-width:1100px;margin:8px auto}header p{max-width:1100px;margin:auto;color:#d5e2ed}main{max-width:1100px;margin:25px auto;padding:0 20px}section{background:white;padding:28px;margin:22px 0;border:1px solid #dce4ec;border-radius:10px}h2{font-size:26px;line-height:1.3;color:#132b45}h3{font-size:18px;color:#087f82;margin-top:26px}table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}th,td{padding:10px;border-bottom:1px solid #dce4ec;text-align:left;vertical-align:top}th{background:#edf3f7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf3f7;padding:16px;font-size:13px}a{color:#087f82}svg{max-width:100%;height:auto}nav{max-width:1100px;margin:15px auto}nav a{margin-right:18px}footer{padding:20px;color:#52677d;font-size:13px}@media print{body{background:white}section{border:0;break-before:page;padding:0}nav{display:none}header{background:white;color:#132b45}}'''

def write_html(out,pages,d):
    sections=[]
    for i,(title,blocks) in enumerate(pages,1):
        text=[f'<section id="sec{i}"><h2>{i:02d}. {escape(title)}</h2>']
        for kind,v in blocks:
            if kind=='p':text.append('<p>'+v+'</p>')
            elif kind=='h':text.append('<h3>'+escape(v)+'</h3>')
            elif kind=='code':text.append('<pre>'+escape(v)+'</pre>')
            elif kind=='table':
                head,rows,w=v
                text.append('<div style="overflow:auto"><table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>')
            elif kind=='chart':text.append(svg_monthly(d))
        text.append('</section>');sections.append(''.join(text))
    (out/'relatorio_final.html').write_text('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DataABC · Relatório final</title><style>'+CSS+'</style><header><h1>DataABC · Da integração à decisão gerencial</h1><p>Base gerada em Python · Seed 20261029 · Projeto individual · 29/10/2026</p></header><main><nav><a href="dashboard.html">Abrir dashboard</a><a href="relatorio_qualidade.html">Qualidade dos dados</a><a href="relatorio_final.pdf">Versão PDF</a></nav>'+''.join(sections)+'<footer>Dados sintéticos. Conferência individual do aluno pendente.</footer></main></html>',encoding='utf-8')

def svg_monthly(d):
    rows=d['monthly'][-13:];maxy=max(r['liquido'] for r in rows)
    pts=' '.join(f'{80+i*62},{210-r["liquido"]/maxy*160}' for i,r in enumerate(rows))
    return '<svg viewBox="0 0 900 270" role="img" aria-label="Receita mensal, último mês parcial"><rect width="900" height="270" fill="#f2f5f8"/><text x="25" y="25" fill="#52677d" font-size="14">Receita líquida mensal (R$ milhões)</text>'+''.join(f'<line x1="80" y1="{210-f*160}" x2="825" y2="{210-f*160}" stroke="#dce4ec"/><text x="15" y="{215-f*160}" font-size="12">{n(maxy*f/1e6,1)}</text>' for f in [0,.5,1])+f'<polyline points="{pts}" fill="none" stroke="#087f82" stroke-width="3"/>'+''.join(f'<circle cx="{80+i*62}" cy="{210-r["liquido"]/maxy*160}" r="4" fill="'+('#b76512' if i==len(rows)-1 else '#087f82')+f'"/><text x="{80+i*62}" y="235" text-anchor="middle" font-size="10">{r["mes"][2:]}</text>' for i,r in enumerate(rows))+'<text x="620" y="260" font-size="12" fill="#b76512">Último mês: somente 01/10/2026</text></svg>'

def pdf(out,pages,d):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether,Preformatted
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.graphics.shapes import Drawing,Line,PolyLine,Circle,String,Rect
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    fonts=Path(reportlab.__file__).parent/'fonts'
    pdfmetrics.registerFont(TTFont('Vera',str(fonts/'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('VeraBold',str(fonts/'VeraBd.ttf')))
    pdfmetrics.registerFont(TTFont('VeraItalic',str(fonts/'VeraIt.ttf')))
    pdfmetrics.registerFontFamily('Vera',normal='Vera',bold='VeraBold',italic='VeraItalic',boldItalic='VeraBold')
    navy=colors.HexColor('#132b45');teal=colors.HexColor('#087f82');muted=colors.HexColor('#52677d')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleBI',fontName='VeraBold',fontSize=21,leading=26,textColor=navy,spaceAfter=17,keepWithNext=True))
    styles.add(ParagraphStyle(name='BodyBI',fontName='Vera',fontSize=9,leading=13,textColor=navy,spaceAfter=8))
    styles.add(ParagraphStyle(name='HeadBI',fontName='VeraBold',fontSize=11,leading=15,textColor=teal,spaceBefore=10,spaceAfter=7,keepWithNext=True))
    styles.add(ParagraphStyle(name='CellBI',fontName='Vera',fontSize=7.5,leading=10,textColor=navy))
    styles.add(ParagraphStyle(name='CellHeadBI',fontName='VeraBold',fontSize=7.5,leading=10,textColor=navy))
    styles.add(ParagraphStyle(name='CodeBI',fontName='Courier',fontSize=7,leading=11,textColor=navy,backColor=colors.HexColor('#edf3f7'),borderPadding=9,spaceAfter=12))
    doc=SimpleDocTemplate(str(out/'relatorio_final.pdf'),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=61,bottomMargin=45,title='DataABC - Relatório final de Business Intelligence',author='Projeto individual DataABC - apoio de IA declarado')
    width=A4[0]-84;story=[]
    def para(t,style='BodyBI'):
        # Vera não cobre todos os símbolos matemáticos: preservar fórmulas legíveis.
        for char,replacement in [('Σ','Soma'),('→','para'),('≥','&gt;='),('≤','&lt;='),('−','-')]:
            t=t.replace(char,replacement)
        return Paragraph(t,styles[style])
    for pi,(title,blocks) in enumerate(pages):
        if pi:story.append(PageBreak())
        story.append(para(f'{pi+1:02d} / {escape(title)}','TitleBI'))
        for kind,v in blocks:
            if kind=='p':story.append(para(v))
            elif kind=='h':story.append(para(escape(v),'HeadBI'))
            elif kind=='code':
                # Linhas longas do terminal quebradas explicitamente para caber no A4.
                import textwrap
                code='\n'.join('\n'.join(textwrap.wrap(line,95,subsequent_indent='  ',break_long_words=False)) for line in v.splitlines())
                story.append(Preformatted(code,styles['CodeBI']))
            elif kind=='table':
                head,rows,weights=v; weights=weights or [1/len(head)]*len(head)
                data=[[para(escape(h),'CellHeadBI') for h in head]]+[[para(str(cell),'CellBI') for cell in r] for r in rows]
                table=Table(data,colWidths=[width*w for w in weights],repeatRows=1,hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6eef4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#dce4ec'))]))
                story += [table,Spacer(1,10)]
            elif kind=='chart':
                rows=d['monthly'][-13:];maxy=max(r['liquido'] for r in rows);dr=Drawing(width,170)
                dr.add(Rect(0,0,width,170,fillColor=colors.HexColor('#f2f5f8'),strokeColor=None))
                dr.add(String(12,153,'Receita líquida mensal (R$ milhões)',fontName='Vera',fontSize=8,fillColor=muted))
                for fraction in [0,.5,1]:
                    y=35+fraction*100;dr.add(Line(43,y,width-12,y,strokeColor=colors.HexColor('#dce4ec'),strokeWidth=.5));dr.add(String(9,y-3,n(maxy*fraction/1e6,1),fontName='Vera',fontSize=7,fillColor=muted))
                pts=[]
                for i,r in enumerate(rows):
                    x=43+i*(width-60)/12;y=35+r['liquido']/maxy*100;pts.extend([x,y])
                    dr.add(String(x,22,r['mes'][2:],fontName='Vera',fontSize=6,textAnchor='middle',fillColor=muted))
                dr.add(PolyLine(pts,strokeColor=teal,strokeWidth=1.8))
                dr.add(Circle(pts[-2],pts[-1],3,fillColor=colors.HexColor('#b76512'),strokeWidth=0))
                dr.add(String(width-12,7,'Out/2026: somente dia 01',fontName='Vera',fontSize=7,textAnchor='end',fillColor=colors.HexColor('#b76512')))
                story += [dr,Spacer(1,9)]
    def frame(canvas,doc):
        canvas.saveState();canvas.setFillColor(navy);canvas.rect(0,A4[1]-35,A4[0],35,fill=1,stroke=0)
        canvas.setFont('VeraBold',9);canvas.setFillColor(colors.white);canvas.drawString(42,A4[1]-23,'DataABC / BUSINESS INTELLIGENCE')
        canvas.setFont('Vera',7);canvas.setFillColor(muted);canvas.drawString(42,25,'Dados sintéticos | Seed 20261029 | 29/10/2026');canvas.drawRightString(A4[0]-42,25,str(doc.page));canvas.restoreState()
    doc.build(story,onFirstPage=frame,onLaterPages=frame)

def quality_html(out,d):
    s=d['stats'];m=d['marketing'];co=d['controls']
    def table(head,rows):return '<table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'
    chunks=['<section><h2>Auditoria das fontes</h2><p>Testes aplicados aos CSVs gerados, sem confundir validade de formato com consistência de negócio. Os originais foram preservados. A amostra não participa dos resultados.</p>',table(['Fonte','Linhas','Colunas','Chaves duplicadas','Linhas excedentes','Duplicatas exatas','Vazios','Formato/domínio inválido'],[[x['tabela'],n(x['linhas']),x['colunas'],n(x['chaves_duplicadas']),n(x['linhas_excedentes']),x['duplicatas_exatas'],sum(x['ausencias'].values()),sum(x['invalidos'].values())] for x in d['quality']]),'</section>']
    chunks += ['<section><h2>Integridade referencial</h2>',table(['Origem','Chave','Dimensão','Eventos sem correspondência','IDs sem correspondência'],[[x['origem'],x['chave'],x['destino'],n(x['linhas']),n(x['chaves'])] for x in d['fks']]),'<p>LEFT JOIN e grupo Sem cadastro preservam os eventos órfãos; valores financeiros não foram descartados por ausência de perfil.</p></section>']
    issues=[
      ['Produtos conflitantes',f"{n(d['conflicts']['custo'])} custos; {n(d['conflicts']['estoque'])} saldos; {n(d['conflicts']['categoria'])} categorias",'Crítico','Primeiro registro físico e último registro físico são cenários; manter bruto e comparar sensibilidade. Não tratar como cadastro vigente.'],
      ['Fan-out evitado',f"{n(co['linhas_fanout_ingenuo'])} linhas numa junção ingênua contra {n(co['linhas_depois_join'])} no modelo",'Crítico','Criar dimensões de chave única e conferir quantidade de linhas e receita.'],
      ['Vendas antes do cadastro',n(d['semantic']['venda_antes_cadastro']['anteriores']),'Alto','Preservar como evento, registrar inconsistência temporal; pedir histórico de cadastro antes de análise de jornada.'],
      ['Recência divergente >30 dias',f"{n(d['recency']['divergentes'])}/{n(d['recency']['comparaveis'])}",'Alto','Recalcular pelo histórico na data de referência. Snapshot cadastral sem data, logo comparação depende dessa hipótese.'],
      ['Funil incoerente',f"{n(m['funil_invalido'])}/{n(m['interacoes'])}",'Alto','Preservar gasto e contagens; sinalizar razões como declaradas. Não usar para retorno financeiro.'],
      ['Cliques > impressões',n(m['cliques_maiores_impressoes']),'Alto','Registrar ocorrência e investigar definição do evento.'],
      ['Conversões > cliques',n(m['conversoes_sem_clique']),'Alto','Registrar ocorrência. As duas condições de funil podem se sobrepor.'],
      ['Rótulo de marketing contraditório',n(d['semantic']['resultado_marketing']['contradicoes']),'Alto','Não converteu com conversões >0 ou Converteu com conversões =0; não usar rótulo para medir vendas.'],
      ['Custo sem vigência','Presente em todos os SKUs','Crítico','Não chamar cenário de margem realizada; preço de venda é independente do custo no gerador.'],
      ['Estoque não conciliável','Sem saldo inicial, data de posição ou sinal de ajuste/devolução','Crítico','Não fabricar saldo final. Cobertura e intensidade são proxies condicionais. Giro contábil indisponível.'],
      ['Período parcial','Outubro/2026: apenas 01/10','Alto','Sinalizar no painel e comparar janeiro-setembro entre anos.'],
      ['Atribuição de marketing','Sem pedido_id ou conversao_id','Alto','Não calcular ROAS/ROI/CAC nem juntar receita ao marketing por cliente.']
    ]
    chunks += ['<section><h2>Registro de problemas e políticas</h2>',table(['Teste','Evidência','Severidade','Tratamento / impacto'],issues),'</section>']
    chunks += ['<section><h2>Controles executados</h2>',table(['Controle','Resultado'],[['Receita por leitura streaming e Decimal',brl(float(co['receita_decimal']))],['Receita via SQL',brl(co['receita_sql'])],['Diferença SQL versus Decimal (R$)',n(co['diferenca_reais'],8)],['Linhas antes/depois da junção',f"{n(co['linhas_antes_join'])} / {n(co['linhas_depois_join'])}"],['Soma da receita mensal',brl(co['receita_mensal'])],['Receita 365d versus segmentos RFM',f"{brl(co['receita_janela_rfm'])} / {brl(co['receita_segmentos_rfm'])}"]]),'<p>Validações de formato não atestam a veracidade das relações econômicas. Todos os atributos são sintéticos e muitos foram sorteados de forma independente.</p></section>']
    chunks += ['<section><h2>Rastreabilidade das fontes</h2>',table(['Arquivo','Linhas','Bytes','SHA-256'],[[x['arquivo'],n(x['linhas']),n(x['bytes']),x['sha256']] for x in d['lineage']]),'<p>Dados gerados com o script original, parâmetro --gb 0.2 e seed 20261029. O gerador para ao atingir a alocação em bytes de cada fonte; o cadastro de clientes pode ficar incompleto e o de produtos pode repetir IDs.</p></section>']
    (out/'relatorio_qualidade.html').write_text('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+CSS+'td{overflow-wrap:anywhere}</style><title>DataABC · Qualidade dos dados</title><header><h1>Qualidade dos dados</h1><p>Auditoria da base gerada de 200 MB</p></header><main><nav><a href="dashboard.html">Dashboard</a><a href="relatorio_final.html">Relatório final</a></nav>'+''.join(chunks)+'</main></html>',encoding='utf-8')

def guides(out,d):
    s=d['stats'];r=d['sample_sale'];bruto=float(r['quantidade'])*float(r['preco_unitario']);discount=bruto*float(r['desconto_percentual'])
    guide=f'''# Guia de defesa e validação individual

## O que foi feito

O gerador original foi executado com tamanho de 0,2 GB e seed 20261029. A amostra de exemplo não foi usada nos resultados. A base cobre {s['inicio']} a {s['fim']}. O processamento lê lotes de 5.000 linhas e grava os dados no SQLite em disco.

## Apresentação sugerida: 7 a 10 minutos

1. Contexto e base gerada (1 minuto): explique o objetivo e o caráter sintético dos dados.
2. Qualidade e integração (2 minutos): mostre produtos conflitantes e clientes sem cadastro. Explique a dimensão de uma linha por produto e o cenário primeiro/último cadastro.
3. Dashboard e KPIs (2 minutos): filtre mês, região e canal em Comercial; mostre que os filtros de cada aba têm escopo próprio. Explique receita, desconto ponderado e margem de cenário.
4. Achados e ações (2 minutos): selecione três evidências quantificadas do relatório e a ação ligada a cada uma.
5. Método avançado e limites (1 a 2 minutos): explique a janela RFM, o grupo Valor a reativar, o teste de sensibilidade e por que isso não é previsão de churn.
6. Uso de IA: declare programação, interpretação e redação assistidas e descreva apenas as conferências que você realmente realizou.

## Conferência manual de um pedido

Pedido {r['pedido_id']}, linha de dados {r['_linha']} do CSV vendas.csv (linha física {r['_linha']+1}, contando o cabeçalho), status {r['status_pedido']}.

- Quantidade: {r['quantidade']}.
- Preço unitário: {brl(float(r['preco_unitario']))}.
- Desconto: {pct(float(r['desconto_percentual']))}.
- Bruto: {r['quantidade']} × {r['preco_unitario']} = {n(bruto,5)} reais.
- Desconto em reais: bruto × {r['desconto_percentual']} = {n(discount,5)}.
- Líquido: bruto − desconto = {n(bruto-discount,5)} reais, exibido como {brl(bruto-discount)}.

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
'''
    (out/'guia_defesa_e_validacao.md').write_text(guide,encoding='utf-8')
    (out/'declaracao_uso_IA.md').write_text('''# Declaração de uso de inteligência artificial

Aluno(a): ____________________
Curso/turma: ____________________
Data: ____________________

Neste projeto utilizei o Codex, assistente de IA da OpenAI, para apoiar a programação em Python e SQL, a construção do dashboard, a interpretação dos dados e a redação dos relatórios e recomendações.

A IA executou o gerador Python fornecido no material da atividade, com --gb 0.2 e --seed 20261029. A análise utiliza essa base gerada, e não a amostra de exemplo. Os dados são sintéticos, para fins didáticos.

O apoio de IA incluiu a identificação de chaves e cadastros conflitantes, a definição de KPIs, a segmentação RFM, a documentação das limitações de atribuição de marketing e de estoque e verificações automáticas de receita, contagens e integração.

As verificações automáticas do assistente estão registradas no pacote. Minha validação individual deve ser descrita abaixo somente após ser realizada. Não declaro, nesta versão, que já executei essas conferências ou que elas foram realizadas por mim.

## Completar após a validação pessoal

Conferências que executei: ____________________

Cálculos conferidos manualmente e resultados: ____________________

Consultas/código que executei e consigo explicar: ____________________

Limitações que revisei e entendi: ____________________

Alterações que fiz após revisar a ajuda da IA: ____________________

Assinatura: ____________________
''',encoding='utf-8')
    (out/'LEIA-ME.md').write_text('''# Projeto DataABC

Abra **dashboard.html** no navegador, sem internet e sem instalar ferramentas. O relatório final está em **relatorio_final.pdf** e **relatorio_final.html**. O PDF e o HTML apresentam os mesmos argumentos. O dashboard tem filtros independentes em quatro abas e exporta a tabela do recorte para CSV.

## O que foi entregue

- dados_origem/: seis CSVs efetivamente gerados (aproximadamente 200 MB) e dicionário original.
- codigo/: gerador original, análise Python, modelo SQL, validador e construção dos documentos.
- resultados/: banco SQLite, métricas JSON, manifestos de hashes, controles e tabelas analíticas CSV.
- catalogo_kpis.csv: 22 KPIs com fórmula, fonte, periodicidade e interpretação.
- dicionario_atualizado.csv: campos originais, chaves e principais campos derivados.
- relatorio_qualidade.html: duplicidades, ausências, integridade referencial, inconsistências e tratamentos.
- guia_defesa_e_validacao.md e declaracao_uso_IA.md: orientações e campos de validação pessoal.

## Verificações desta entrega

Foram aprovadas 29 verificações de dados e 14 verificações da lógica do dashboard. A receita e os dados RFM foram conferidos diretamente nos CSVs. O PDF foi renderizado e revisado. A lógica de filtros e de exportação foi testada com DOM simulado; isso não constitui revisão visual no navegador. O controle do navegador foi encerrado automaticamente porque a ferramenta não conseguiu verificar o endereço da página com segurança. Confirme a aparência das quatro abas ao abrir dashboard.html.

## Repetir o projeto

Python 3.10+ é necessário para reprocessar, mas não para abrir os relatórios. ReportLab é necessário somente para recriar o PDF.

```text
python -m pip install -r codigo/requirements.txt
python codigo/analisar.py --entrada dados_origem --saida refeito
python codigo/validar.py --projeto refeito --entrada dados_origem
```

Para regenerar os dados em uma pasta separada:

```text
python codigo/gerador_original.py --gb 0.2 --seed 20261029 --saida dados_regenerados
```

Depois passe --entrada dados_regenerados ao pipeline. A base gerada depende do gerador, da seed, do tamanho e do ambiente Python; o manifesto permite comparar os arquivos de entrada. Os resultados/dataabc.sqlite e documentos derivados na pasta de saída são recriados; nunca aponte a saída para uma pasta com outro trabalho.

## Premissas indispensáveis

Receita: somente Concluído; após desconto; não é receita contábil completa ou lucro. Margem/categoria/estoque: cenários do primeiro registro por produto, com último registro para sensibilidade, sem afirmar qual é correto. Marketing: métricas declaradas, sem ROI/ROAS/CAC. Estoque: cobertura e intensidade proxies, giro contábil indisponível. Outubro/2026 contém somente o dia 01. RFM usa os últimos 365 dias até 01/10/2026 e não prevê churn.

Antes de entregar, preencha sua identificação, realize as conferências do guia e complete a declaração de IA. A validação pessoal exigida pela atividade não foi declarada como concluída pelo assistente.
''',encoding='utf-8')

def build(out,d,source):
    out=Path(out);source=Path(source);dictionary(out,source);pages,actions=contents(d)
    dashboard=(Path(__file__).parent/'dashboard_template.html').read_text(encoding='utf-8')
    # JSON estrito e sem fechamento acidental da tag script.
    payload=json.dumps(d,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    (out/'dashboard.html').write_text(dashboard.replace('__DATA__',payload),encoding='utf-8')
    write_html(out,pages,d);quality_html(out,d);guides(out,d);pdf(out,pages,d)

if __name__=='__main__':
    out=Path(sys.argv[1] if len(sys.argv)>1 else '.')
    d=json.loads((out/'resultados/analise.json').read_text(encoding='utf-8'))
    build(out,d,out/'dados_origem')
