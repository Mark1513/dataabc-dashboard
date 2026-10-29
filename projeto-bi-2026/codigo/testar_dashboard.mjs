// Teste da lógica JavaScript com DOM simulado. Não substitui revisão visual em navegador.
// Opcional: node codigo/testar_dashboard.mjs .
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const root=path.resolve(process.argv[2]||'.');
const text=fs.readFileSync(path.join(root,'dashboard.html'),'utf8');
const payload=text.match(/<script id="dataset" type="application\/json">([\s\S]*?)<\/script>/)[1];
const code=[...text.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
const data=JSON.parse(payload),elements=new Map(),logs=[];
let controls=[];let blob;
class Element{
 constructor(id){this.id=id;this.value='';this.textContent='';this.html='';this.classList={toggle(){}};this.dataset={}}
 set innerHTML(v){this.html=v;if(this.id==='filters'){
  for(const id of controls)elements.delete(id);controls=[];
  for(const match of v.matchAll(/<(select|input|button)\b[^>]*id="([^"]+)"[^>]*>/g)){
   const e=new Element(match[2]);e.value=match[0].match(/value="([^"]*)"/)?.[1]||'';elements.set(e.id,e);controls.push(e.id)
  }
 }}get innerHTML(){return this.html}
 querySelectorAll(){return controls.map(id=>elements.get(id))}addEventListener(){}click(){this.clicked=true}
}
for(const id of ['subtitle','dataset','filters','scope','alert','cards','charts','table-title','count','table','export'])elements.set(id,new Element(id));
elements.get('dataset').textContent=payload;
const buttons=['sales','clients','campaigns','inventory'].map(tab=>{const e=new Element(tab);e.dataset.tab=tab;return e});
const document={getElementById:id=>elements.get(id),querySelectorAll:()=>buttons,createElement:()=>new Element('a')};
const context=vm.createContext({document,Intl,console,Blob,URL:{createObjectURL:b=>{blob=b;return 'blob:test'},revokeObjectURL(){}},setTimeout:fn=>fn()});
vm.runInContext(code,context);
const run=s=>vm.runInContext(s,context), set=(id,value)=>{elements.get(id).value=value};
function check(name,condition){assert.ok(condition,name);logs.push({teste:name,aprovado:true})}
const sum=(r,k)=>r.reduce((a,x)=>a+x[k],0);
check('Total comercial inicial',elements.get('cards').innerHTML.includes('796.123.830,62'));
check('58 meses da base',run('visible.length')===58);
set('start','2025-01');set('end','2025-12');set('region','Sul');set('channel','App');set('category','Moda');run('render()');
let expected=data.sales.filter(r=>r.mes>='2025-01'&&r.mes<='2025-12'&&r.regiao==='Sul'&&r.canal==='App'&&r.categoria==='Moda');
check('Filtros combinados comerciais',Math.abs(run("visible.reduce((s,r)=>s+r.liquido,0)")-sum(expected,'liquido'))<.01);
set('start','2026-10');set('end','2025-01');run('render()');check('Intervalo invertido',run('visible.length')===0&&elements.get('table-title').textContent==='Intervalo inválido');
elements.get('reset').onclick();check('Limpar filtros',run('visible.length')===58);
set('start','2027-01');set('end','2027-12');run('render()');check('Sem dados mantém ausência de resultados',run('visible.length')===0&&!elements.get('cards').innerHTML.includes('NaN'));
buttons[1].onclick();set('region','Sem cadastro');set('segment','Valor a reativar');run('render()');
expected=data.clients.filter(r=>r.regiao==='Sem cadastro'&&r.segmento==='Valor a reativar');
check('Clientes com cadastro ausente preservados',run("visible.reduce((s,r)=>s+r.clientes,0)")===sum(expected,'clientes'));
check('RFM com janela fixa documentada',elements.get('scope').textContent.includes('365 dias'));
buttons[2].onclick();set('start','2025-01');set('end','2025-12');set('campaign','Reativação');set('medium','SMS');run('render()');
expected=data.campaigns.filter(r=>r.mes>='2025-01'&&r.mes<='2025-12'&&r.campanha==='Reativação'&&r.meio==='SMS');
check('Filtros combinados de marketing',Math.abs(run("visible.reduce((s,r)=>s+r.investimento,0)")-sum(expected,'investimento'))<.01);
check('Taxas de marketing sem divisão por zero',!elements.get('cards').innerHTML.includes('NaN')&&!elements.get('cards').innerHTML.includes('Infinity'));
buttons[3].onclick();set('risk','Cobertura abaixo de 30d');run('render()');check('48 SKUs com baixa cobertura',run('visible.length')===48);
check('Tabela de estoque ordenada',run('visible.every((r,i,a)=>!i||r.cobertura>=a[i-1].cobertura)'));
elements.get('export').onclick();let csv=await blob.text();check('CSV exporta todas as 48 linhas',csv.split('\r\n').length===49&&csv.includes('Cobertura · primeiro'));
set('category','Moda');run('render()');expected=data.inventory.filter(r=>r.risco==='Cobertura abaixo de 30d'&&r.categoria==='Moda');check('Filtros combinados de estoque',run('visible.length')===expected.length);
const output={status:'aprovado',tipo:'Teste de lógica com DOM simulado; não é teste visual de navegador',testes:logs};
fs.writeFileSync(path.join(root,'resultados','testes_logica_dashboard.json'),JSON.stringify(output,null,2));
console.log(`${logs.length} testes de lógica do dashboard aprovados.`);
