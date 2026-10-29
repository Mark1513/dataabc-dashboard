"""Pipeline DataABC: leitura em lotes, SQLite em disco, auditoria e entregáveis.
Execute na pasta do projeto: python codigo/analisar.py --entrada dados_origem --saida .
O cadastro de produtos possui conflitos. As dimensões de primeiro/último registro
são cenários explícitos, sem inferir que um deles é o cadastro correto.
"""
import argparse, csv, hashlib, json, math, sqlite3
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

KEYS = {'clientes':'cliente_id','produtos':'produto_id','vendas':'pedido_id',
        'atendimento':'atendimento_id','marketing':'interacao_id','estoque':'movimento_id'}
NUMS = {'idade','renda_mensal','satisfacao_1a5','dias_desde_ultima_compra',
        'quantidade','preco_unitario','desconto_percentual','prazo_entrega_dias',
        'preco_lista','custo_estimado','estoque_cadastrado','satisfacao_atendimento',
        'impressoes','cliques','conversoes','investimento','compras_ultimos_30d',
        'duracao_minutos','recontatos'}
DOMAINS = {
 'regiao': {'Norte','Nordeste','Centro-Oeste','Sudeste','Sul'},
 'canal': {'App','E-commerce','Loja física','Marketplace'},
 'status_pedido': {'Concluído','Cancelado','Devolvido','Em processamento'},
 'status_cliente': {'Ativo','Inativo','Em risco'},
 'tipo_movimento': {'Entrada','Saída','Ajuste','Devolução'},
 'status_atendimento': {'Resolvido','Pendente','Escalado'}
}

def query(c,sql,args=()):
    return [dict(x) for x in c.execute(sql,args)]

def one(c,sql,args=()):
    return dict(c.execute(sql,args).fetchone())

def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def export_csv(c,sql,path):
    cur=c.execute(sql)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow([x[0] for x in cur.description])
        while rows:=cur.fetchmany(5000): w.writerows(rows)

def load(c,source):
    quality=[]; lineage=[]
    for table,key in KEYS.items():
        path=source/f'{table}.csv'
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f); cols=reader.fieldnames
            if any(not x.replace('_','').isalnum() for x in cols): raise ValueError('Coluna inválida')
            quoted=','.join('"'+x+'" TEXT' for x in cols)
            c.execute(f'CREATE TABLE {table} (_linha INTEGER PRIMARY KEY,{quoted})')
            insert=f'INSERT INTO {table} VALUES ({",".join("?" for _ in range(len(cols)+1))})'
            missing=Counter(); invalid=Counter(); examples={}; batch=[]; count=0
            for count,row in enumerate(reader,1):
                for k,v in row.items():
                    if v is None or not v.strip(): missing[k]+=1; continue
                    problem=None
                    if k in NUMS:
                        try:
                            num=Decimal(v)
                            if not num.is_finite() or num<0: problem='número negativo/inválido'
                            elif k in ('satisfacao_1a5','satisfacao_atendimento') and not 1<=num<=5: problem='escala 1 a 5'
                            elif k=='desconto_percentual' and num>1: problem='desconto maior que 1'
                            elif k=='quantidade' and (num<=0 or num!=int(num)): problem='quantidade não inteira/positiva'
                        except Exception: problem='número ilegível'
                    if k.startswith('data_'):
                        try: date.fromisoformat(v)
                        except ValueError: problem='data inválida'
                    if k in DOMAINS and v not in DOMAINS[k]: problem='fora do domínio'
                    if problem:
                        invalid[f'{k}: {problem}']+=1
                        examples.setdefault(f'{k}: {problem}',{'linha_csv':count+1,'valor':v})
                batch.append([count]+[row[x] for x in cols])
                if len(batch)==5000: c.executemany(insert,batch); batch=[]
            if batch: c.executemany(insert,batch)
        c.commit()
        duplicates=one(c,f'SELECT count(*) grupos,coalesce(sum(n-1),0) excedentes FROM (SELECT count(*) n FROM {table} GROUP BY {key} HAVING count(*)>1)')
        fields=','.join('"'+x+'"' for x in cols)
        exact=one(c,f'SELECT coalesce(sum(n-1),0) n FROM (SELECT count(*) n FROM {table} GROUP BY {fields} HAVING count(*)>1)')['n']
        quality.append({'tabela':table,'linhas':count,'colunas':len(cols),'chave':key,
                        'chaves_duplicadas':duplicates['grupos'],'linhas_excedentes':duplicates['excedentes'],
                        'duplicatas_exatas':exact,'ausencias':dict(missing),'invalidos':dict(invalid),'exemplos':examples})
        lineage.append({'arquivo':path.name,'linhas':count,'bytes':path.stat().st_size,'sha256':h.hexdigest()})
        print(f'Importado {table}: {count:,} linhas',flush=True)
    return quality,lineage

def main():
    p=argparse.ArgumentParser(); p.add_argument('--entrada',default='dados_origem'); p.add_argument('--saida',default='.')
    p.add_argument('--somente-analise',action='store_true',help='Não gerar documentos e dashboard')
    args=p.parse_args(); source=Path(args.entrada).resolve(); out=Path(args.saida).resolve()
    out.mkdir(parents=True,exist_ok=True); result=out/'resultados'; result.mkdir(exist_ok=True)
    db=result/'dataabc.sqlite'
    if db.exists(): db.unlink()  # Somente o banco derivado, nunca os CSVs originais.
    c=sqlite3.connect(db); c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=OFF'); c.execute('PRAGMA synchronous=OFF')
    c.execute('PRAGMA temp_store=FILE'); c.execute('PRAGMA cache_size=-64000')
    quality,lineage=load(c,source)
    # Sem uma chave de item, pedidos repetidos exigiriam outro contrato de entrada.
    if any(q['linhas_excedentes'] for q in quality if q['tabela'] not in ('clientes','produtos')):
        dump(result/'qualidade.json',quality); raise ValueError('Chave de evento repetida. Investigar antes de agregar.')
    if any(q['invalidos'] or q['ausencias'] for q in quality):
        dump(result/'qualidade.json',quality); raise ValueError('Ausências/valores inválidos: corrigir ou definir política antes de calcular.')
    c.executescript((Path(__file__).parent/'modelo.sql').read_text(encoding='utf-8'))
    fks=[]
    for fact,key,dim in [('vendas','cliente_id','dim_clientes'),('vendas','produto_id','dim_produtos'),
                        ('atendimento','cliente_id','dim_clientes'),('marketing','cliente_id','dim_clientes'),
                        ('estoque','produto_id','dim_produtos')]:
        fks.append({'origem':fact,'chave':key,'destino':dim,**one(c,f'SELECT count(*) linhas,count(distinct f.{key}) chaves FROM {fact} f LEFT JOIN {dim} d USING({key}) WHERE d.{key} IS NULL')})
    # Os conflitos são medidos por atributo, sem chamar todas as repetições de cópias idênticas.
    conflicts=query(c,"SELECT count(*) produtos, sum(ncat>1) categoria, sum(ncusto>1) custo, sum(nsaldo>1) estoque FROM (SELECT produto_id,count(distinct categoria) ncat,count(distinct custo_estimado) ncusto,count(distinct estoque_cadastrado) nsaldo FROM produtos GROUP BY 1)")[0]
    stats=one(c,"SELECT min(data_venda) inicio,max(data_venda) fim,count(*) registros,sum(status_pedido='Concluído') pedidos,sum(status_pedido='Cancelado') cancelados,sum(status_pedido='Devolvido') devolvidos,sum(status_pedido='Em processamento') processamento FROM vendas")
    stats.update(one(c,"SELECT sum(bruto) bruto,sum(desconto) desconto,sum(liquido) liquido,sum(custo_primeiro) custo,sum(custo_ultimo) custo_ultimo,sum(quantidade) unidades FROM fato_vendas WHERE status_pedido='Concluído'"))
    stats['margem']=stats['liquido']-stats['custo']; stats['margem_ultimo']=stats['liquido']-stats['custo_ultimo']
    stats['meses']=one(c,'SELECT count(distinct mes) n FROM fato_vendas')['n']
    marketing=one(c,'SELECT sum(investimento) investimento,sum(impressoes) impressoes,sum(cliques) cliques,sum(conversoes) conversoes,sum(funil_invalido) funil_invalido,sum(interacoes) interacoes FROM marketing_mensal')
    marketing['conversoes_sem_clique']=one(c,'SELECT count(*) n FROM marketing WHERE CAST(conversoes AS INTEGER)>CAST(cliques AS INTEGER)')['n']
    marketing['cliques_maiores_impressoes']=one(c,'SELECT count(*) n FROM marketing WHERE CAST(cliques AS INTEGER)>CAST(impressoes AS INTEGER)')['n']
    services=one(c,"SELECT count(*) n,sum(CAST(satisfacao_atendimento AS REAL)) soma_satisfacao,sum(CAST(satisfacao_atendimento AS INTEGER)>=4) satisfeitos,sum(motivo IN ('Atraso','Produto danificado','Reembolso','Cobrança')) reclamacoes,sum(status_atendimento!='Resolvido') abertos FROM atendimento")
    recency=one(c,"SELECT count(*) comparaveis,sum(abs(CAST(c.dias_desde_ultima_compra AS INTEGER)-(julianday((SELECT max(data_venda) FROM vendas))-julianday(v.ultima)))>30) divergentes FROM dim_clientes c JOIN (SELECT cliente_id,max(data_venda) ultima FROM fato_vendas WHERE status_pedido='Concluído' GROUP BY 1) v USING(cliente_id)")
    stock=one(c,"SELECT count(*) produtos,sum(estoque) estoque,sum(estoque*custo_unitario) valor_cenario,sum(cobertura<30) risco30,sum(cobertura>180) excesso180,sum(cobertura_ultimo<30) risco30_ultimo,sum(cobertura_ultimo>180) excesso180_ultimo,sum(saidas) saidas,sum(entradas) entradas,sum(ajustes) ajustes,sum(devolucoes) devolucoes FROM estoque_produto")
    stock.update(one(c,"SELECT min(data_movimento) inicio,max(data_movimento) fim,julianday(max(data_movimento))-julianday(min(data_movimento))+1 dias FROM estoque"))
    rfm=query(c,"SELECT segmento,count(*) clientes,sum(monetario) monetario,sum(atendimentos) atendimentos,sum(reclamacoes) reclamacoes,sum(abertos) abertos FROM clientes_rfm GROUP BY 1 ORDER BY monetario DESC")
    sensitivity=query(c,"SELECT 60 corte,count(*) clientes,sum(monetario) monetario FROM clientes_rfm WHERE recencia>60 AND (f>=4 OR m>=4) UNION ALL SELECT 90,count(*),sum(monetario) FROM clientes_rfm WHERE recencia>90 AND (f>=4 OR m>=4) UNION ALL SELECT 120,count(*),sum(monetario) FROM clientes_rfm WHERE recencia>120 AND (f>=4 OR m>=4)")
    # Receita independente com Decimal e leitura streaming, sem repetir o cálculo SQL.
    decimal_bruto=Decimal(0); decimal_desconto=Decimal(0); complete=0
    with (source/'vendas.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['status_pedido']=='Concluído':
                b=Decimal(row['quantidade'])*Decimal(row['preco_unitario'])
                decimal_bruto+=b; decimal_desconto+=b*Decimal(row['desconto_percentual']); complete+=1
    controls={
        'receita_decimal':str(decimal_bruto-decimal_desconto),
        'receita_sql':stats['liquido'],'diferenca_reais':float(decimal_bruto-decimal_desconto)-stats['liquido'],
        'pedidos_decimal':complete,'linhas_antes_join':stats['registros'],
        'linhas_depois_join':one(c,'SELECT count(*) n FROM fato_vendas')['n'],
        'receita_mensal':one(c,'SELECT sum(liquido) n FROM comercial_mensal')['n'],
        'clientes_rfm':one(c,'SELECT count(*) n FROM clientes_rfm')['n'],
        'clientes_rfm_com_compra':one(c,'SELECT count(*) n FROM clientes_rfm WHERE frequencia>0')['n'],
        'receita_janela_rfm':one(c,'SELECT sum(monetario) n FROM vendas_cliente')['n'],
        'receita_segmentos_rfm':sum(x['monetario'] for x in rfm),
        'linhas_fanout_ingenuo':one(c,'SELECT sum(v.n*p.n) n FROM (SELECT produto_id,count(*) n FROM vendas GROUP BY 1) v JOIN (SELECT produto_id,count(*) n FROM produtos GROUP BY 1) p USING(produto_id)')['n']
    }
    semantic={
        'venda_antes_cadastro':one(c,'SELECT count(*) comparaveis,sum(v.data_venda<c.data_cadastro) anteriores FROM vendas v JOIN dim_clientes c USING(cliente_id)'),
        'resultado_marketing':one(c,"SELECT sum((resultado='Não converteu' AND CAST(conversoes AS INTEGER)>0) OR (resultado='Converteu' AND CAST(conversoes AS INTEGER)=0)) contradicoes FROM marketing"),
        'pedidos_margem_negativa_cenario':one(c,"SELECT count(*) n FROM fato_vendas WHERE status_pedido='Concluído' AND liquido<custo_primeiro")['n'],
        'frequencias_rfm':query(c,'SELECT frequencia,count(*) clientes FROM clientes_rfm GROUP BY 1'),
        'comparacao_jan_set':query(c,"SELECT substr(data_venda,1,4) ano,sum(liquido) liquido,count(*) pedidos FROM fato_vendas WHERE status_pedido='Concluído' AND substr(data_venda,6,5) BETWEEN '01-01' AND '09-30' GROUP BY 1 ORDER BY 1"),
        'anos':query(c,'SELECT substr(mes,1,4) ano,sum(liquido) liquido,sum(pedidos) pedidos FROM comercial_mensal GROUP BY 1 ORDER BY 1')
    }
    assert abs(controls['diferenca_reais'])<.01
    assert controls['linhas_antes_join']==controls['linhas_depois_join']
    assert complete==stats['pedidos']
    assert math.isclose(controls['receita_mensal'],stats['liquido'],abs_tol=.01)
    assert math.isclose(controls['receita_janela_rfm'],controls['receita_segmentos_rfm'],abs_tol=.01)
    # Exportações analíticas pequenas. Não levar os eventos brutos ao navegador.
    tables=['comercial_mensal','marketing_mensal','clientes_rfm','estoque_produto']
    for t in tables: export_csv(c,f'SELECT * FROM {t}',result/f'{t}.csv')
    client_dashboard=query(c,"SELECT regiao,segmento,status_cliente,count(*) clientes,sum(monetario) monetario,sum(frequencia) pedidos,sum(atendimentos) atendimentos,sum(reclamacoes) reclamacoes,sum(abertos) abertos,sum(soma_satisfacao) soma_satisfacao,sum(satisfeitos) satisfeitos,sum(CASE WHEN frequencia>0 THEN recencia ELSE 0 END) soma_recencia,sum(frequencia>0) compradores FROM clientes_rfm GROUP BY 1,2,3")
    dataset={
      'stats':stats,'marketing':marketing,'services':services,'stock':stock,'recency':recency,
      'rfm':rfm,'sensitivity':sensitivity,'quality':quality,'fks':fks,'conflicts':conflicts,
      'controls':controls,'lineage':lineage,'semantic':semantic,
      'sales':query(c,'SELECT * FROM comercial_mensal ORDER BY mes'),
      'campaigns':query(c,'SELECT * FROM marketing_mensal ORDER BY mes'),
      'clients':client_dashboard,'inventory':query(c,'SELECT * FROM estoque_produto ORDER BY cobertura'),
      'monthly':query(c,'SELECT mes,sum(liquido) liquido,sum(bruto) bruto,sum(desconto) desconto,sum(custo) custo,sum(pedidos) pedidos FROM comercial_mensal GROUP BY 1 ORDER BY 1'),
      'categories':query(c,'SELECT categoria,sum(liquido) liquido,sum(custo) custo,sum(pedidos) pedidos FROM comercial_mensal GROUP BY 1 ORDER BY liquido DESC'),
      'channels':query(c,'SELECT canal,sum(liquido) liquido,sum(pedidos) pedidos FROM comercial_mensal GROUP BY 1 ORDER BY liquido DESC'),
      'regions':query(c,'SELECT regiao,sum(liquido) liquido,sum(pedidos) pedidos FROM comercial_mensal GROUP BY 1 ORDER BY liquido DESC'),
      'campaign_summary':query(c,'SELECT campanha,sum(investimento) investimento,sum(conversoes) conversoes,sum(cliques) cliques,sum(impressoes) impressoes FROM marketing_mensal GROUP BY 1 ORDER BY sum(investimento)*1.0/sum(conversoes)'),
      'movements':query(c,'SELECT tipo_movimento,sum(CAST(quantidade AS INTEGER)) unidades,count(*) registros FROM estoque GROUP BY 1'),
      'sample_sale':one(c,"SELECT * FROM vendas WHERE status_pedido='Concluído' ORDER BY _linha LIMIT 1")
    }
    dump(result/'analise.json',dataset)
    dump(result/'qualidade.json',{'fontes':quality,'relacionamentos':fks,'conflitos_produtos':conflicts,'recencia':recency})
    dump(result/'validacao.json',controls); dump(result/'manifesto_fontes.json',lineage)
    if not args.somente_analise:
        from documentos import build
        build(out,dataset,source)
    c.close(); print('Entregáveis concluídos em '+str(out),flush=True)

if __name__=='__main__': main()
