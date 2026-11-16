# SRAG Report Agent

PoC da Indicium HealthCare Inc.: um agente de IA Generativa que consulta os dados de internações por
Síndrome Respiratória Aguda Grave (Open DATASUS / SIVEP-Gripe) e notícias em tempo real para gerar um
relatório com métricas, gráficos e uma análise contextualizada.

## Arquitetura

Diagrama conceitual: [docs/arquitetura.pdf](docs/arquitetura.pdf).

```
Pedido ─► [Guardrail de entrada] ─► Agente (LangGraph + LLM) ◄─► Tools
                                          │                          ├─ get_srag_metrics ─► DuckDB (CSV)
                                          ▼                          ├─ generate_srag_charts
                                  [Guardrail de saída]               └─ search_srag_news ─► Google News RSS
                                          ▼
                       Relatório Markdown (números calculados em código) + auditoria JSONL
```

**Por que um grafo LangGraph com guardrails como nós?** Os guardrails ficam no fluxo de controle (não
só no prompt), são determinísticos e podem devolver feedback ao LLM para nova tentativa (até 2x).

**Por que o LLM não calcula números?** Métricas e tabelas vêm de código testado. O LLM apenas escreve a
análise, e o guardrail de saída rejeita qualquer percentual que não corresponda a uma métrica calculada.

### Métricas (janela de 30 dias terminando na última data de notificação)

| Métrica | Definição |
|---|---|
| Taxa de aumento de casos | Variação % dos casos dos últimos 30 dias vs. os 30 anteriores |
| Taxa de mortalidade | Óbitos por SRAG / casos com desfecho conhecido |
| Taxa de ocupação de UTI | Internações que passaram por UTI / internações com informação de UTI (proxy; os dados não trazem capacidade de leitos) |
| Taxa de vacinação | Casos com vacina COVID-19 / casos com informação vacinal (proxy; não é cobertura populacional) |

Gráficos: casos diários (30 dias) e mensais (12 meses), por data de notificação.

## Governança e transparência
- **Auditoria** (`logs/audit.jsonl`): registra pedido, qualidade dos dados, cada decisão do LLM (tools
  e argumentos, uso de tokens), cada chamada de tool, resultados dos guardrails e hash do relatório.
  Os registros são encadeados por hash; `srag_agent.audit.verify` detecta adulteração.
- Cada métrica no relatório mostra numerador, denominador e definição.

## Guardrails
- **Entrada:** tamanho, escopo (somente SRAG), prompt injection e PII no pedido.
- **Tools:** argumentos validados com Pydantic (UF válida, termos de busca restritos).
- **Conteúdo externo:** notícias são sanitizadas, descartadas se parecerem instruções e marcadas como
  não confiáveis; XML parseado com `defusedxml`.
- **Saída:** sem PII, percentuais ancorados nas métricas, URLs apenas das fontes recuperadas.

## Tratamento de dados sensíveis
- Minimização: só 6 colunas são lidas do CSV (`DT_NOTIFIC`, `SG_UF_NOT`, `HOSPITAL`, `UTI`,
  `EVOLUCAO`, `VACINA_COV`). Colunas identificadoras (CPF, nome, endereço etc.) estão numa lista de
  bloqueio e nunca são carregadas.
- Ao LLM chegam apenas métricas agregadas e títulos de notícias; nenhum registro individual.
- Redação automática de CPF, e-mail e telefone em entradas, notícias e saídas.
- Chave de API só via variável de ambiente; `.env` e dados brutos estão no `.gitignore`.

## Tratamento dos dados
Valores fora do domínio (ex.: `9 = ignorado`) viram nulo e saem do denominador; datas inválidas, antes
de 2019 ou futuras são descartadas; UF inválida vira nula. Os descartes aparecem no relatório.
Limitação conhecida: casos recentes sofrem atraso de notificação, então a taxa de aumento e a
mortalidade dos últimos dias tendem a ser subestimadas.

## Como executar
```bash
uv sync
# 1. Baixe INFLUD25*.csv e INFLUD26*.csv de https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026
#    e salve em data/raw/ (o nome deve começar com INFLUD).
# 2. cp env.example .env   e preencha GOOGLE_API_KEY (grátis em https://aistudio.google.com/apikey)
#    Provedor padrão: Gemini (free tier). Alternativas: SRAG_PROVIDER=groq ou anthropic (ver env.example).
uv run srag-report                # Brasil
uv run srag-report --uf SP        # por UF
uv run srag-report --no-llm       # sem LLM (apenas métricas, gráficos e notícias)
uv run pytest                     # testes
```
O relatório é salvo em `reports/relatorio_<data>.md`, com os gráficos ao lado.
Um exemplo real gerado pelo agente está em [docs/exemplo/](docs/exemplo/relatorio_2026-11-15.md).
O dicionário de dados usado como referência está em `docs/dicionario-de-dados-2019-a-2025.pdf`.
Um exemplo real gerado pelo agente está em [docs/exemplo/](docs/exemplo/relatorio_2026-11-15.md).
O dicionário de dados usado como referência está em `docs/dicionario-de-dados-2019-a-2025.pdf`.
