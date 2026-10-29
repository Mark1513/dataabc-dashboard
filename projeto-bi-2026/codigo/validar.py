"""Conferências independentes a partir dos CSVs originais. Biblioteca padrão."""
import argparse,csv,hashlib,json,sqlite3,sys,platform
from collections import defaultdict
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--projeto',default='.');p.add_argument('--entrada',default='dados_origem');a=p.parse_args()
    root=Path(a.projeto);source=Path(a.entrada);result=root/'resultados'
    d=json.loads((result/'analise.json').read_text(encoding='utf-8'));c=sqlite3.connect(result/'dataabc.sqlite');c.row_factory=sqlite3.Row
    checks=[]
    def check(name,ok,detail):
        checks.append({'teste':name,'aprovado':bool(ok),'detalhe':detail})
        if not ok:raise AssertionError(name+': '+str(detail))
    # Arquivos conferidos pelos bytes, não somente pelo nome.
    for m in d['lineage']:
        h=hashlib.sha256()
        with (source/m['arquivo']).open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        check('SHA256 '+m['arquivo'],h.hexdigest()==m['sha256'],h.hexdigest())
    total=Decimal(0);gross=Decimal(0);disc=Decimal(0);counts=defaultdict(int)
    ref=date.fromisoformat(d['stats']['fim']);start=ref-timedelta(days=364)
    rfm=defaultdict(lambda:{'n':0,'v':Decimal(0),'last':date.min})
    with (source/'vendas.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            counts[row['status_pedido']]+=1
            if row['status_pedido']!='Concluído':continue
            b=Decimal(row['quantidade'])*Decimal(row['preco_unitario']);discount=b*Decimal(row['desconto_percentual'])
            gross+=b;disc+=discount;total+=b-discount
            dt=date.fromisoformat(row['data_venda'])
            if start<=dt<=ref:
                cl=rfm[row['cliente_id']];cl['n']+=1;cl['v']+=b-discount;cl['last']=max(cl['last'],dt)
    sqlnet=c.execute("SELECT sum(liquido) FROM fato_vendas WHERE status_pedido='Concluído'").fetchone()[0]
    check('Receita: CSV Decimal versus SQL',abs(total-Decimal(str(sqlnet)))<Decimal('.01'),{'csv':str(total),'sql':sqlnet})
    check('Bruto e desconto independentes',abs(gross-Decimal(str(d['stats']['bruto'])))<Decimal('.01') and abs(disc-Decimal(str(d['stats']['desconto'])))<Decimal('.01'),{'bruto':str(gross),'desconto':str(disc)})
    check('Contagem de status',counts=={r['status_pedido']:r['n'] for r in c.execute('SELECT status_pedido,count(*) n FROM vendas GROUP BY 1')},dict(counts))
    check('Cardinalidade preservada',sum(counts.values())==c.execute('SELECT count(*) FROM fato_vendas').fetchone()[0],sum(counts.values()))
    for table,key in [('dim_clientes','cliente_id'),('dim_produtos','produto_id'),('dim_produtos_ultimo','produto_id'),('clientes_rfm','cliente_id')]:
        row=c.execute(f'SELECT count(*),count(distinct {key}) FROM {table}').fetchone()
        check('Unicidade '+table,row[0]==row[1],row[0])
    mismatch=0;segments=defaultdict(int)
    for row in c.execute('SELECT * FROM clientes_rfm'):
        raw=rfm.get(row['cliente_id']);freq=raw['n'] if raw else 0;mon=raw['v'] if raw else Decimal(0)
        rec=(ref-raw['last']).days if raw else None
        mismatch+=row['frequencia']!=freq or abs(Decimal(str(row['monetario']))-mon)>Decimal('.01') or row['recencia']!=rec
        if not freq:expected='Sem compra na janela'
        elif rec>90 and (freq>=5 or row['m']>=4):expected='Valor a reativar'
        elif rec<=60 and freq>=5 and row['m']>=4:expected='Recentes de alto valor'
        elif rec<=60:expected='Recentes em desenvolvimento'
        elif rec<=90:expected='Intermediários'
        else:expected='Inativos de menor valor'
        mismatch+=expected!=row['segmento'];segments[expected]+=1
    check('RFM: pedidos, receita, recência e classe de todos os clientes',mismatch==0,{'divergencias':mismatch,'classes':dict(segments)})
    check('Compradores RFM não perdidos',len(rfm)==d['controls']['clientes_rfm_com_compra'],len(rfm))
    # Verifica os quintis e seus limites preservando empates de receita.
    ordered=list(c.execute('SELECT monetario,m FROM clientes_rfm WHERE frequencia>0 ORDER BY monetario'))
    m_errors=0;end=0
    while end<len(ordered):
        first=end;amount=ordered[end]['monetario']
        while end<len(ordered) and ordered[end]['monetario']==amount:end+=1
        pos=end/len(ordered);expected=next((i for i,cut in enumerate([.2,.4,.6,.8,1],1) if pos<=cut),5)
        m_errors+=sum(row['m']!=expected for row in ordered[first:end])
    check('Quintis monetários e empates',m_errors==0,m_errors)
    invalid=0;spend=Decimal(0);conversions=0;clicks=0;impressions=0
    with (source/'marketing.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            invalid+=int(row['cliques'])>int(row['impressoes']) or int(row['conversoes'])>int(row['cliques'])
            spend+=Decimal(row['investimento']);conversions+=int(row['conversoes']);clicks+=int(row['cliques']);impressions+=int(row['impressoes'])
    check('Marketing: gasto e contagens preservados',abs(spend-Decimal(str(d['marketing']['investimento'])))<Decimal('.01') and conversions==d['marketing']['conversoes'] and clicks==d['marketing']['cliques'] and impressions==d['marketing']['impressoes'],{'gasto':str(spend),'conversoes':conversions})
    check('União dos problemas de funil',invalid==d['marketing']['funil_invalido'],invalid)
    stock_errors=0
    for row in c.execute('SELECT * FROM estoque_produto'):
        expected=row['estoque']*d['stock']['dias']/row['saidas'] if row['saidas'] else None
        stock_errors+=expected is not None and abs(expected-row['cobertura'])>1e-8
        stock_errors+=row['saidas']<=0
    check('Cobertura por SKU e denominadores',stock_errors==0,stock_errors)
    check('Integridade SQLite',c.execute('PRAGMA integrity_check').fetchone()[0]=='ok','ok')
    for filename in ['dashboard.html','relatorio_final.pdf','relatorio_final.html','relatorio_qualidade.html','catalogo_kpis.csv','dicionario_atualizado.csv','guia_defesa_e_validacao.md','declaracao_uso_IA.md']:
        check('Entregável '+filename,(root/filename).exists() and (root/filename).stat().st_size>0,(root/filename).stat().st_size)
    output={'status':'aprovado','testes':checks,'ambiente':{'python':sys.version,'plataforma':platform.platform()},'nota':'Testes executados automaticamente pela IA. Validação pessoal do aluno pendente.'}
    (result/'testes_automatizados.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(checks)} verificações aprovadas. Conferência de receita e RFM feita diretamente nos CSVs.');c.close()

if __name__=='__main__':main()
