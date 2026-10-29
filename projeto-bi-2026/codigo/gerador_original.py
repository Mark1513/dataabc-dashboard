#!/usr/bin/env python3
"""Gera seis CSVs sintéticos relacionados para o projeto DataABC.
Uso: python gerar_base_dataabc.py --gb 0.2
Para 5 GB: python gerar_base_dataabc.py --gb 5
Somente biblioteca padrão; geração em streaming.
"""
import argparse,csv,random,string
from pathlib import Path
from datetime import date,timedelta
REG=["Norte","Nordeste","Centro-Oeste","Sudeste","Sul"]
CAN=["E-commerce","Loja física","Marketplace","App"]
CAT=["Eletrônicos","Moda","Casa","Beleza","Esportes","Alimentos","Livros"]
STATUS=["Concluído","Cancelado","Devolvido","Em processamento"]
MOT=["Atraso","Produto danificado","Troca","Reembolso","Dúvida","Elogio","Cobrança"]
CAMP=["Retenção","Conversão","Lançamento","Fidelidade","Reativação","Upsell"]
NOM=["Ana","Bruno","Carla","Daniel","Eduarda","Felipe","Gabriela","Heitor","Isabela","João","Karen","Lucas","Mariana","Nicolas","Olivia","Pedro"]
SOB=["Silva","Souza","Oliveira","Santos","Lima","Costa","Pereira","Almeida","Ferreira","Gomes","Ribeiro","Carvalho"]
def dt(r): return (date(2022,1,1)+timedelta(days=r.randint(0,1734))).isoformat()
def txt(r,n): return "".join(r.choice(string.ascii_letters+"     "+"áéíóúãõç") for _ in range(n)).strip()
def money(r,a=10,b=5000): return round(r.uniform(a,b),2)
def main():
 p=argparse.ArgumentParser(); p.add_argument("--gb",type=float,default=.2); p.add_argument("--saida",default="dataabc_dados"); p.add_argument("--seed",type=int,default=20261029); a=p.parse_args()
 if a.gb<=0: raise SystemExit("--gb deve ser maior que zero")
 r=random.Random(a.seed); out=Path(a.saida); out.mkdir(parents=True,exist_ok=True); target=int(a.gb*1_000_000_000)
 alloc={"clientes.csv":.08,"vendas.csv":.40,"produtos.csv":.04,"atendimento.csv":.16,"marketing.csv":.16,"estoque.csv":.16}
 nc,npd=100000,10000; cids=[f"C{i:07d}" for i in range(1,nc+1)]; pids=[f"P{i:06d}" for i in range(1,npd+1)]
 specs=[
 ("clientes.csv",["cliente_id","nome_ficticio","idade","renda_mensal","regiao","canal_preferido","data_cadastro","status_cliente","satisfacao_1a5","compras_ultimos_30d","dias_desde_ultima_compra","observacao"],lambda i:[cids[i%nc],f"{r.choice(NOM)} {r.choice(SOB)}",r.randint(18,85),round(max(1200,min(45000,r.lognormvariate(8.4,.55))),2),r.choice(REG),r.choice(CAN),dt(r),r.choice(["Ativo","Inativo","Em risco"]),r.randint(1,5),r.randint(0,30),r.randint(0,180),txt(r,100)]),
 ("vendas.csv",["pedido_id","cliente_id","produto_id","data_venda","canal","regiao","quantidade","preco_unitario","desconto_percentual","status_pedido","forma_pagamento","prazo_entrega_dias","observacao"],lambda i:[f"V{i+1:012d}",cids[r.randrange(nc)],pids[r.randrange(npd)],dt(r),r.choice(CAN),r.choice(REG),r.randint(1,12),money(r,5,2500),round(r.uniform(0,.35),3),r.choice(STATUS),r.choice(["Pix","Cartão","Boleto","Carteira digital"]),r.randint(0,20),txt(r,60)]),
 ("produtos.csv",["produto_id","nome_produto","categoria","faixa_preco","preco_lista","custo_estimado","estoque_cadastrado","produto_ativo","descricao"],lambda i:(lambda price:[pids[i%npd],f"Produto {pids[i%npd]}",r.choice(CAT),r.choice(["Premium","Intermediário","Econômico"]),price,round(price*r.uniform(.15,.65),2),r.randint(0,10000),r.choice(["Sim","Não"]),txt(r,80)])(money(r,8,8000))),
 ("atendimento.csv",["atendimento_id","cliente_id","data_atendimento","canal_atendimento","motivo","satisfacao_atendimento","duracao_minutos","status_atendimento","recontatos","comentario"],lambda i:[f"AT{i+1:011d}",cids[r.randrange(nc)],dt(r),r.choice(["Telefone","Chat","E-mail","Loja","Redes sociais"]),r.choice(MOT),r.randint(1,5),r.randint(1,240),r.choice(["Resolvido","Pendente","Escalado"]),r.randint(0,3),txt(r,140)]),
 ("marketing.csv",["interacao_id","cliente_id","data_interacao","campanha","meio","canal_venda","impressoes","cliques","conversoes","investimento","resultado","regiao"],lambda i:[f"MKT{i+1:011d}",cids[r.randrange(nc)],dt(r),r.choice(CAMP),r.choice(["E-mail","SMS","Push","Redes sociais","Busca paga","Display"]),r.choice(CAN),r.randint(100,200000),r.randint(0,10000),r.randint(0,1000),money(r,20,20000),r.choice(["Converteu","Não converteu","Abriu","Não abriu"]),r.choice(REG)]),
 ("estoque.csv",["movimento_id","produto_id","data_movimento","tipo_movimento","quantidade","deposito","motivo"],lambda i:[f"EST{i+1:011d}",pids[r.randrange(npd)],dt(r),r.choice(["Entrada","Saída","Ajuste","Devolução"]),r.randint(1,500),r.choice(["CD-01","CD-02","LOJA-01","LOJA-02","LOJA-03"]),r.choice(["Reposição","Venda","Avaria","Inventário","Transferência"])])]
 total=0
 for name,headers,factory in specs:
  path=out/name; count=0; goal=int(target*alloc[name])
  with path.open("w",newline="",encoding="utf-8-sig") as f:
   w=csv.writer(f); w.writerow(headers)
   while f.tell()<goal:
    w.writerow(factory(count)); count+=1
    if count%100000==0: f.flush(); print(name,count,"linhas")
  size=path.stat().st_size; total+=size; print(f"{name}: {count:,} linhas, {size/1e6:.1f} MB")
 with (out/"dicionario_dados.csv").open("w",newline="",encoding="utf-8-sig") as f:
  w=csv.writer(f); w.writerow(["arquivo","finalidade","chaves"])
  w.writerows([["clientes.csv","Perfil e comportamento","cliente_id"],["vendas.csv","Pedidos e itens","pedido_id; cliente_id; produto_id"],["produtos.csv","Cadastro de produtos","produto_id"],["atendimento.csv","Atendimentos e satisfação","atendimento_id; cliente_id"],["marketing.csv","Campanhas e conversões","interacao_id; cliente_id"],["estoque.csv","Movimentações de estoque","movimento_id; produto_id"]])
 print(f"Concluído: {total/1e9:.2f} GB aproximados. Pasta: {out.resolve()}")
if __name__=="__main__": main()
