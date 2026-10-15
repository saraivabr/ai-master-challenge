# Process log: como usei IA neste desafio

**Como ler este registro:** as sessões 1 e 2 preservam a narrativa já existente sobre o trabalho no Warp e no Claude. São o relato das versões anteriores, não evidência de que essas sessões foram reexecutadas ou de que suas conclusões continuam válidas. A sessão 3 registra a revisão com Codex. A implementação e a apresentação atuais correspondem à v4.

## Decomposição inicial do problema

O relato original descreve o uso da estrutura do Doug, meu método de mentoria: **Verdade → Corte → Comando**.

- **Verdade:** investigar o que os dados sustentam antes de escolher features.
- **Corte:** transformar o pedido de um score em uma decisão de agenda para o vendedor.
- **Comando:** acompanhar cada oportunidade com uma ação compreensível.

Na formulação inicial, isso também incluía mostrar um custo em dinheiro e impor prazo e consequência a cada ação. A v4 revê essa parte: preço de catálogo e idade, sozinhos, não demonstram receita futura nem autorizam prazo de compra ou encerramento automático.

## Sessão 1 — Warp, agente Oz: v1 e v2

Esta seção resume o relato original de Fellipe.

1. Li o brief, o guia de submissão e o template antes de começar o código.
2. O relato registra que, diante da exigência de login no Kaggle, usei um espelho no GitHub com os quatro CSVs e 8.800 oportunidades. **A URL desse espelho não foi preservada.** A fonte indicada pelo desafio é [CRM Sales Predictive Analytics](https://www.kaggle.com/datasets/agungpambudi/crm-sales-predictive-analytics); a revisão atual trabalha com os CSVs presentes na pasta e não comprova o download original.
3. A exploração apontou diferenças de grafia (`GTXPro`/`GTX Pro` e `technolgy`/`technology`), cinco vendedores sem oportunidades e contas vazias em Engaging e Prospecting. Também identificou 1.301 negócios abertos com idade **maior ou igual a 138 dias**. A redação anterior dizia “tinham passado”; a distinção importa, porque dez deles têm exatamente 138 dias.
4. **v1:** modelo log-odds com shrinkage para vendedor, produto, setor, conta, vendedor × produto e idade. Gerou explicações como “Vendedor neste produto: +7 pp”.
5. Pedi um backtest temporal. O relato registra AUC de aproximadamente 0,51, insuficiente para sustentar a confiança das explicações.
6. Testei carga do vendedor e histórico prévio da conta. Os resultados relatados também ficaram próximos de 0,5.
7. **v2:** retirei os fatores sem evidência suficiente no teste. O score passou a usar valor esperado, com triagem de oportunidades antigas e uma visão para a gestão.

**Erros e correções registrados nessa sessão:**

- A primeira solução produziu explicações convincentes antes de demonstrar discriminação fora da amostra. O backtest motivou a simplificação.
- Os negócios do teste ainda carregavam estágio Won/Lost, gerando AUC exatamente 0,500. O relato registra a correção desse problema.
- Um teste retirava a idade (`engage_date=NaT`), mudando a pergunta que estava sendo avaliada. Foi substituído por uma tentativa de reconstruir o pipeline nas datas de corte.

## Sessão 2 — Claude: v3

Esta seção preserva o relato original e marca as conclusões posteriormente revistas.

Pedi ao Claude uma auditoria da v2 e a aplicação do método Doug aos pontos fracos. O relato registra acesso aos arquivos desse método.

1. **Auditoria da v2:** o Claude executou `scoring.py`, abriu o app em navegador headless e comparou números com o README. Apontou correlação de ordem de 0,98 entre score e preço, ações dependentes do produto e um desempate por preço em vez de valor esperado. Reproduzir os números demonstrava consistência da implementação, mas não validava a premissa estatística.
2. **Investigação das coortes:** a equipe observou taxas diferentes entre coortes e recalculou o denominador incluindo oportunidades antigas como perdas. Daí vieram os números apresentados na v3 como “conversão real de 53%” e uma curva que diminuía com a idade. **Correção da v4:** esses resultados dependiam de rotular negócios ainda abertos como perdas. Eram resultados de uma hipótese, não observações do desfecho. A v4 remove essa classificação e essas probabilidades.
3. **Backtest da v3:** passou a usar o resultado conhecido em 31/12, ainda com perdas presumidas para os antigos. A documentação o chamou de corrigido. **Correção da v4:** além do problema de rótulo, os fechamentos no próprio dia do corte pertenciam ao treino e ao teste, porque os dois filtros usavam fronteiras diferentes.
4. **Campo de conta:** o relato descreve uma AUC de 0,71 para setor, seguida da identificação de que o campo vazio influenciava o resultado. Restringir a análise a contas preenchidas reduziu a métrica. O relato registra que nenhum negócio ganho estava sem conta. Isso pode refletir o preenchimento exigido no fechamento; sem snapshots do cadastro, não prova capacidade preditiva disponível antes da venda.
5. **Outros sinais:** o relato registra testes de porte da conta, recorrência e calendário sem evidência suficiente de discriminação. A conclusão atual é limitada a esses testes; não significa que esses atributos nunca possam ser úteis.
6. **Interface da v3:** passou a mostrar uma comparação entre receita calculada com a taxa dos encerrados e uma estimativa de US$ 746 mil; criou “Última chamada”, prazo no dia 138, Plano de segunda e visão da gestão. **Correção da v4:** os rótulos “previsão honesta” e “ponto sem volta” excediam a evidência. O app atual mantém o plano de ação, elimina o forecast e usa a idade como critério de acompanhamento ou revisão.
7. **Verificação relatada:** execução de `scoring.py`, testes com `streamlit.testing`, filtros por vendedor e screenshots no navegador. Esses testes pertenciam à v3. As asserções sobre probabilidades e perdas validavam a lógica programada, não a sua adequação ao problema.

**Aprendizados registrados nessa sessão:**

- Uma curva calculada apenas com negócios encerrados pode responder a uma pergunta diferente da chance de um negócio ainda aberto. Incluir perdas presumidas também não resolve essa limitação por si só.
- Um campo vazio pode carregar informação do processo de fechamento, em vez de um sinal disponível no momento da decisão.
- Houve correções de apresentação: o caractere `$` foi interpretado como LaTeX no Streamlit, o cache ocultou uma alteração e um exemplo numérico do README precisou ser recalculado.

## Sessão 3 — Codex: v4

A revisão partiu dos arquivos presentes na pasta. Fellipe pediu a correção do código e da apresentação com SARAIVA · PNL e SARAIVA · Conversão BR, seguida de nova validação para preparar a submissão. Também confirmou o perfil [linkedin.com/in/saraivaai](https://www.linkedin.com/in/saraivaai/).

**O que a análise encontrou:**

- Os 1.301 negócios antigos incluíam dez exatamente no dia 138, e existe um ganho registrado com ciclo de 138 dias. O limite anterior excluía esse caso de fronteira.
- A taxa apresentada como “real” vinha de atribuir perda a oportunidades que continuavam abertas.
- A estimativa financeira era dominada pela prospecção, usando uma taxa de progressão que a base não permite validar.
- O treino incluía fechamentos até a data do corte; o teste excluía somente os anteriores ao corte. Havia sobreposição de IDs.
- Texto e interface transformavam limite histórico em prazo comercial e hipótese em resultado confirmado.

**Decisões da revisão:**

1. **Prioridade como heurística explícita.** Combinar valor de catálogo normalizado (60%) e idade relativa (40%) para ordenar as negociações. Esses pesos são uma escolha de produto, não uma probabilidade individual estimada.
2. **Revisão sem perda presumida.** Mais de 138 dias direciona a oportunidade para confirmação de situação. Exatamente 138 dias permanece dentro da referência histórica. O CRM deve ser atualizado com base na resposta do cliente ou em outra evidência de desfecho.
3. **Uma agenda executável.** O Plano de segunda distribui até cinco posições entre revisão e negociação, completando vagas com prospecção e depois com os itens restantes das filas quando necessário. O próximo passo informa o que confirmar, sem criar urgência de compra.
4. **Fronteira temporal consistente.** Histórico com fechamento até o corte; teste com fechamento posterior ao corte e resultado conhecido até a referência. Os casos ainda abertos são reportados como desconhecidos. A avaliação compara score e preço e informa quantos casos têm resultado conhecido ou permanecem abertos.
5. **Linguagem proporcional à evidência.** A revisão com PNL separa observação e interpretação; Conversão BR liga o benefício ao mecanismo entregue e à prova disponível. A promessa é organizar o trabalho do vendedor. Ganho de vendas depende de validação em uso real.
6. **Documentação de envio.** Preencher o LinkedIn confirmado, atualizar setup e evidências e remover data de envio e itens de chat export que não correspondiam a arquivos presentes. A narrativa escrita é um formato aceito pelo guia.

**Validação da v4 em 14/10/2026:** passaram 20 testes automatizados — 16 de scoring e quatro de interface com AppTest — e as verificações Ruff e Black. No navegador desktop de 1440 × 1100, o app carregou sem erros de JavaScript. O layout também foi conferido em 390 × 844, sem rolagem horizontal da página. Ao selecionar Vicki, a interface mostrou 24 negociações, 80 revisões e nenhuma prospecção; o download real da fila produziu um CSV com 24 linhas somente dessa vendedora, incluindo prioridade, observação, critério e próximo passo. A [saída dos testes e do backtest](validacao.txt) foi preservada.

A validação reproduzível da v4 está nos comandos do [README principal](../README.md). O backtest responde sobre ordenação na parcela com desfecho conhecido; testes de código e interface respondem sobre funcionamento. Nenhum desses resultados, sozinho, demonstra aumento de conversão comercial.

## Julgamento humano e iterações

O relato original destaca que Fellipe pediu testes quando as explicações pareciam mais fortes que a evidência e trouxe a decisão de agenda para o centro do produto. Nesta revisão, o pedido explícito foi corrigir os problemas encontrados e preparar a pasta para envio, preservando esse foco prático.

| Versão | Decisão principal | Limitação que motivou a próxima revisão |
|---|---|---|
| v1 | Modelo com múltiplos atributos e explicações por fator | Backtest relatado próximo do acaso |
| v2 | Simplificação para valor esperado | Forte dependência de preço e interpretação inadequada da curva |
| v3 | Antigos tratados como perdas, previsão e prazo por oportunidade | Desfechos presumidos, certeza excessiva e fronteira temporal sobreposta |
| v4 | Prioridade heurística, revisão de situação e avaliação com desconhecidos separados | Utilidade comercial ainda depende de validação no fluxo real do time |

## Evidências disponíveis

- [Código, testes e CSVs](../solution/).
- [Screenshots do app](../docs/).
- [Saída da validação automatizada](validacao.txt).
- Esta narrativa e o [README da submissão](../README.md).

Os exports de chat mencionados na versão anterior não estão anexados. A evidência de processo entregue aqui é a narrativa, com as conclusões anteriores e suas correções identificadas.
