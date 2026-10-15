# Process Log: como usei IA neste desafio

Usei três agentes de IA em sequência: Warp, Claude e Codex. Cada um revisou o trabalho do anterior. As decisões entre uma versão e outra foram minhas, e este log registra também os erros de cada um.

## Como decompus o problema
Usei a estrutura do Doug, o meu método de mentoria: **Verdade → Corte → Comando**.
- **Verdade:** o que os dados sustentam, não o que o brief sugere. Toda feature passa por um backtest temporal antes de entrar.
- **Corte:** o pedido literal é "um score". O problema real é o vendedor gastar agenda em deal que não fecha.
- **Comando:** cada deal sai com uma ação e um prazo.

Ao longo das versões aprendi um limite do método: **o comando tem que ser proporcional à evidência.** Esse aprendizado veio da revisão do Codex (v4).

---

## Sessão 1 — Warp (agente Oz): v1 e v2
1. Li o brief, o guia e o template antes do código.
2. O Kaggle exige login, então usei um espelho no GitHub com os 4 CSVs (8.800 deals) e conferi as contagens com o brief. A URL do espelho não foi guardada.
3. A EDA mostrou:
   - Grafias divergentes: `GTXPro` / `GTX Pro` e `technolgy` / `technology`.
   - 5 vendedores sem deals.
   - Contas vazias em deals abertos.
   - O dado que depois decidiu tudo: muitos deals abertos acima do maior ciclo de fechamento.
4. **v1:** modelo log-odds com vendedor, produto, setor, conta e idade. As explicações eram ótimas ("Vendedor neste produto: +7 pp").
5. Pedi um backtest temporal: AUC 0,51. A v1 explicava ruído com confiança.
6. **v2:** removi os fatores sem sinal e o score virou valor esperado, com triagem dos deals antigos.

**Erros da IA:**
- **Overfitting com cara de insight** na v1.
- **AUC exatamente 0,500** porque os deals de teste ainda carregavam Won/Lost. Desconfiei do número redondo demais.
- **Um teste que removia a idade**, e por isso media outra coisa.

## Sessão 2 — Claude: v3
1. **Auditoria da v2:** o score tinha correlação de ordem de 0,98 com o preço, ou seja, era a tabela de preço. E a curva de chance *subia* com a idade porque olhava só deals fechados (viés de sobrevivência).
2. **Hipótese:** contar os deals parados acima de 138 dias como perda. Com isso, a conversão vai a 53%, a chance cai com a idade e cada deal ganha um prazo.
3. **Vazamento encontrado:** setor aparecia com AUC 0,71. Era o campo de conta vazio: todo deal fechado tem conta.
4. **Interface por papel**, com o plano de segunda em cartões, contagem regressiva e detalhe por clique.

**Erros da IA (que só apareceram na revisão seguinte):**
- **A hipótese "parado = perda" foi apresentada como fato** ("conversão real", "previsão honesta de $746k").
- **A previsão de $746k era 76% prospecção**, com uma taxa de conversão que a base não permite validar.
- **No backtest, um deal fechado no próprio dia do corte caía no treino e no teste.**
- **Os deals com exatamente 138 dias eram tratados como parados**, mas existe uma venda fechada exatamente no dia 138.

## Sessão 3 — Codex: v4
Pedi ao Codex que revisasse e corrigisse a v3, com foco em linguagem proporcional à evidência.
- **Corrigiu a fronteira:** parado é *mais* de 138 dias, não 138 ou mais.
- **Corrigiu o backtest:** treino com fechados até o corte, teste com os abertos ao fim do dia, sem IDs em comum. Os que seguem abertos ficam fora da AUC e são contados à parte.
- **Removeu probabilidades e previsões**, e passou o score para uma regra fixa: 60% valor e 40% idade.
- **Escreveu 20 testes automatizados.**

## Sessão 4 — Claude: v5 (a versão entregue)
Pedi ao Claude para validar o que estava de pé. Ele rodou a v4 do zero: 20/20 testes com as versões fixadas, app sem erros e números batendo com o README. Mas apontou três problemas de produto:
1. **O plano de segunda mandava começar pelo pior deal.** O item nº 1 da Vicki era um MG Special de **$55 parado há 379 dias**, porque a fila de revisão estava ordenada por idade.
2. **O score premiava idade.** Com 40% de peso, quanto mais velho, mais prioridade, inclusive na beira dos 138 dias, onde nenhuma venda fechou depois. E o backtest da própria v4 mostrava o score sem vantagem sobre o preço.
3. **A interface voltou a ser texto e tabela**, e o diagnóstico mais forte da base tinha sumido.

**Decisão:** juntar o melhor das duas versões.
- **Fica da v4:** a fronteira em mais de 138 dias, o backtest sem sobreposição e com os desconhecidos separados, a validação de entradas e a disciplina de testes.
- **Volta da v3:** a interface por papel, o plano por valor esperado com prazo e a curva por idade. Mas agora a curva é **declarada como hipótese**, com a evidência ao lado (0 de 6.711 fechadas passaram de 138 dias).
- **O topo da tela passou a ser um fato observado**, não uma previsão: "64% do valor aberto está em deals mais velhos que qualquer venda já fechada".
- **A "previsão honesta" saiu.** Era dominada pela prospecção.
- **Deal parado nunca entra no plano de 5.** Vira uma tarefa de limpeza à parte.

**Verificação:**
- **23 testes** (20 de scoring e 3 de interface), rodando tanto com as versões fixadas (pandas 2.3.3, Streamlit 1.50) quanto com as mais novas (pandas 3, Streamlit 1.66).
- **Os testes de interface** abrem o app como cada um dos 27 vendedores com deals abertos, testam a visão do gerente com os filtros em cascata e um filtro vazio que se recupera.
- **Screenshots com Playwright**, sem erros no console.

**Auditoria independente:** um segundo agente, que não escreveu a v5, conferiu cada número dos READMEs contra o código e os dados. Todos bateram, exceto um: eram 27 vendedores com deals abertos, não 30. Ele também apontou exageros, todos corrigidos:
- **"AUC ≈ 0,5" virou "nada separa de forma estável".** A idade oscila entre 0,43 e 0,55 e muda de direção.
- **O gráfico agora diz que a queda vem da hipótese.**
- **"Metade das perdas até o dia 14" vale só para as perdas registradas** e saiu do argumento central.
- **Um deal em "Baixa prioridade" recebia "conversa em 48h".** Corrigido.
- **A Última chamada do plano precisa ter pelo menos 1 dia de prazo.**
- **Entrou um aviso de que o limite de 138 dias pode ser artefato de base sintética.**

**Erros nessa sessão:**
- **O teste de interface do Streamlit 1.50 quebra com `segmented_control`** (bug do próprio framework de teste). Troquei por `radio`.
- **Um teste de filtro vazio era pulado em silêncio** porque o cenário não existia por escritório. Reescrevi usando um manager sem o produto, e agora ele roda.
- **Uma explicação de texto quebrava** quando não havia histórico (data vazia). Coberto por teste.

---

## O que eu adicionei que as IAs sozinhas não fariam
- **Desconfiei duas vezes de resultados bonitos:** a v1 com explicações perfeitas e a AUC 0,71 de setor. Nos dois casos era ruído ou vazamento.
- **Coloquei as IAs para revisar umas às outras** e decidi o que cada revisão acertou. O Codex estava certo sobre rigor. O Claude estava certo sobre o plano de segunda e a interface.
- **Mantive o foco no vendedor na segunda de manhã.** A pergunta não é "qual modelo é mais correto", e sim "o que ele faz primeiro". Um deal de $55 parado há um ano não pode ser a resposta.

## Evidências
- Código, testes e dados: [`../solution/`](../solution/)
- Saída dos testes e do backtest: [`validacao.txt`](validacao.txt)
- Screenshots: [`../docs/`](../docs/)
