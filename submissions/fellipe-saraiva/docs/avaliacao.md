# Avaliação do top 5 — revisão v6

**Resultado:** o plano padrão perdeu para maior preço em receita observada por vaga (−5,3%) e ganhos por vaga; superou maior idade em receita no agregado. Não demonstrou superioridade geral. A política não foi ajustada depois de ver estes resultados.

## Protocolo

- Cortes: 01/04, 01/05, 01/06 e 01/07/2017; horizonte fixo de 90 dias após cada corte. Em cada um, 30 vendedores × até 5 vagas; nesta base todos preencheram 5. Total: 600 seleções por política/cenário.
- População: oportunidades engajadas até o corte e ainda abertas ao fim dele. Prospecting não tem data de criação: não é possível saber quais existiam no passado. O preenchimento do plano com prospecção tem teste funcional, mas não validação de resultado.
- Snapshot: antes do fit e da seleção, status futuros viram Engaging, close_date futuro vira vazio e close_value futuro vira desconhecido. Preços de catálogo, vendedor e atributos estáticos são assumidos conhecidos no corte; não há histórico de alterações desses campos.
- Histórico rotulado: fechados até o corte (inclusive), disjuntos da população aberta. O fit padrão também usa abertos antigos como pseudo-negativos, inclusive IDs da avaliação: 2, 25, 84 e 153 nos quatro cortes. Esta é uma hipótese baseada em estado/idade no corte, não uso do desfecho futuro. A descrição anterior de fit apenas em fechados e integralmente disjunto era incorreta.
- Políticas: top5 chama exatamente monday_plan; maior_preco ordena preço decrescente e ID crescente; maior_idade ordena dias desde engajamento decrescentes e ID crescente. Não há dado de último contato: “tempo parado” aqui significa idade desde engajamento.
- Mesmo conjunto elegível e orçamento por vendedor dentro de cada cenário. No padrão, todas as políticas excluem antigos em revisão, evitando comparar pools diferentes. A terceira sensibilidade admite os antigos para todas.
- Só depois de escolher IDs são lidos os resultados registrados nos 90 dias seguintes. Isso é avaliação retrospectiva: desfechos posteriores são alvos, nunca entradas da seleção. Não extrapola além de 31/12/2017.

## Métricas

Cobertura = encerrados no horizonte / selecionados. Desconhecidos = sem desfecho registrado no horizonte (inclui quem encerrou depois dele); nunca recebem rótulo Lost na avaliação. Taxa entre resolvidos = Won / (Won + Lost) observados, sujeita a viés de seleção. Ganhos por vaga = Won observados / todas as vagas, rendimento observado e não probabilidade calibrada. Receita por vaga = soma de close_value de Won no horizonte / vagas; desconhecidos não acrescentam receita registrada, mas isso não afirma valor econômico zero.

Resultados são soma de seleções por corte, **não receita única da empresa**: o mesmo deal pode aparecer em mais de um corte. No cenário padrão, as 600 seleções correspondem a 420 IDs únicos no top5, 350 em preço e 438 em idade. Sem independência entre linhas, não há p-valor, intervalo de confiança ou afirmação de ganho causal.

## Resultado padrão

| Política | Vagas | Resolvidos | Desconhecidos | Cobertura | Ganhos | Taxa entre resolvidos | Ganhos/vaga | Receita observada/vaga |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top5 | 600 | 405 | 195 | 67.5% | 282 | 69.6% | 47.0% | $3,025.43 |
| maior_preco | 600 | 414 | 186 | 69.0% | 299 | 72.2% | 49.8% | $3,194.79 |
| maior_idade | 600 | 316 | 284 | 52.7% | 224 | 70.9% | 37.3% | $903.28 |

O top5 perde para preço em receita em abril, maio e junho; supera em julho. Em ganhos observados perde para preço nos quatro cortes. Em junho a maior idade tem mais ganhos observados (71 contra 61), embora menos receita. Portanto, nem a vantagem sobre idade vale para toda métrica/corte.

| Corte | Top5 receita/vaga | Preço receita/vaga | Idade receita/vaga |
|---|---:|---:|---:|
| 2017-04-01 | $3,391.27 | $3,458.59 | $849.08 |
| 2017-05-01 | $2,835.50 | $3,262.77 | $934.48 |
| 2017-06-01 | $3,008.23 | $3,288.61 | $1,327.33 |
| 2017-07-01 | $2,866.75 | $2,769.20 | $502.23 |

## Sensibilidade aos abertos antigos

1. **padrao:** curva com pseudo-perdas e antigos fora da seleção, em revisão.
2. **sem_pseudo_perdas:** curva só dos encerrados; mantém antigos em revisão. Isola a hipótese no fit.
3. **antigos_elegiveis:** curva só dos encerrados e antigos voltam ao conjunto elegível. Para idades fora do suporte histórico, o top5 usa a taxa média dos encerrados como proxy explícita, não evidência de conversão; baselines não usam taxa. Isola a regra de exclusão em relação ao cenário 2.

| Cenário | Política | Cobertura | Desconhecidos | Ganhos/vaga | Receita/vaga |
|---|---|---:|---:|---:|---:|
| padrao | top5 | 67.5% | 195 | 47.0% | $3,025.43 |
| padrao | maior_preco | 69.0% | 186 | 49.8% | $3,194.79 |
| padrao | maior_idade | 52.7% | 284 | 37.3% | $903.28 |
| sem_pseudo_perdas | top5 | 68.5% | 189 | 47.7% | $3,041.54 |
| sem_pseudo_perdas | maior_preco | 69.0% | 186 | 49.8% | $3,194.79 |
| sem_pseudo_perdas | maior_idade | 52.7% | 284 | 37.3% | $903.28 |
| antigos_elegiveis | top5 | 68.2% | 191 | 47.3% | $3,026.88 |
| antigos_elegiveis | maior_preco | 68.2% | 191 | 49.2% | $3,126.87 |
| antigos_elegiveis | maior_idade | 48.7% | 308 | 34.0% | $816.37 |

Maior preço continua acima do top5 em receita e ganhos observados nos três cenários. Remover a hipótese de pseudo-perdas pouco muda a receita do plano neste conjunto; isso não valida a hipótese. Admitir antigos aumenta a fração desconhecida do baseline por idade: a cobertura cai de 52,7% para 48,7%. A idade sem atividade registrada não sustenta encerramento automático.

## Reprodução e limites

```bash
cd submissions/fellipe-saraiva/solution
python -m unittest discover -s . -p 'test_*.py'
python scoring.py
python evaluation.py
```

- [baselines.csv](baselines.csv): 36 linhas, métricas/contagens por corte, cenário e política.
- [baseline-selections.csv](baseline-selections.csv): 5.400 seleções com IDs para auditoria.
- [validacao-v6.txt](../process-log/validacao-v6.txt): comandos, versões e saídas.
- A AUC em scoring.py mantém a avaliação de discriminação entre encerrados até 31/12; tem horizonte diferente e não substitui estas métricas top5.
- Não há log de ações, esforço/custo ou contrafactual. A receita observada não foi causada pelo app. Margem, tempo poupado e efeito comercial precisam de piloto prospectivo.
- A base tem 500 prospecções no snapshot final, sem conversão observável nem data de criação. Nenhum resultado acima valida a proxy dessas prospecções.
- O máximo histórico pode refletir a coleta ou a geração da base. O cenário sem histórico ordena por preço; sem vitórias a taxa/valor/score são zero. Não há garantia de transferência a outro CRM.
- Decisão desta revisão: manter a proposta enxuta e o plano como heurística operacional, explicitar sua desvantagem contra preço e testar políticas num piloto antes de alegar melhoria.
