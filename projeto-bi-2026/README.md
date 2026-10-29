# Projeto individual DataABC - base gerada em Python

**[Abrir o dashboard interativo](https://mark1513.github.io/dataabc-dashboard/projeto-bi-2026/)**

Dados sintéticos gerados pelo script original com `--gb 0.2 --seed 20261029`: cerca de 200 MB nas seis fontes e 475.259 registros de vendas. Período de 01/01/2022 a 01/10/2026. A amostra de exemplo não integra estes resultados.

O painel tem quatro abas, filtros por área, gráficos e exportação de tabelas filtradas. A página carrega tabelas analíticas em arquivos JSON menores, sem carregar os CSVs brutos. Abra pelo endereço público; para visualizar esta versão localmente, sirva a pasta por HTTP.

- [Relatório final HTML](relatorio_final.html)
- [Relatório de qualidade](relatorio_qualidade.html)
- [Catálogo dos 22 KPIs](catalogo_kpis.csv)
- [Dicionário atualizado](dicionario_atualizado.csv)
- [Código Python e SQL](codigo/)
- [Guia de defesa e validação](guia_defesa_e_validacao.md)
- [Declaração de uso de IA](declaracao_uso_IA.md)

## Reproduzir

Com Python 3.10 ou superior, na pasta deste projeto:

```text
python -m pip install -r codigo/requirements.txt
python codigo/gerador_original.py --gb 0.2 --seed 20261029 --saida dados_origem
python codigo/analisar.py --entrada dados_origem --saida refeito
python codigo/validar.py --projeto refeito --entrada dados_origem
```

Os arquivos brutos e o banco SQLite são produzidos localmente pelos comandos acima. A publicação contém o painel, relatórios, código e documentação.

## Premissas

Receita considera somente pedidos concluídos após descontos. Categoria, custo e estoque têm conflitos de cadastro e são apresentados como cenários exploratórios. Conversões de marketing são declaradas, sem atribuição a pedidos. Estoque usa proxies de cobertura; o giro contábil está indisponível. Outubro de 2026 contém somente o dia 01. Segmentação RFM é descritiva, sem previsão de churn.

IA foi utilizada para programação, interpretação e redação, conforme a declaração. Verificações automáticas aprovadas: 29 de dados e 14 da lógica do painel. O aluno deve realizar e registrar a validação individual exigida pela atividade.
