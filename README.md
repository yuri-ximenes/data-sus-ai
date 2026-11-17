# SRAG Report Agent

PoC da Indicium HealthCare Inc.: um agente de IA Generativa que consulta os dados de internações por
Síndrome Respiratória Aguda Grave (Open DATASUS / SIVEP-Gripe) e notícias em tempo real para gerar um
relatório com métricas, gráficos e uma análise contextualizada.

## Arquitetura

Diagrama conceitual: [docs/arquitetura.pdf](docs/arquitetura.pdf).

```
Pedido ─► [Guardrail de entrada] ─► Agente orquestrador (LangGraph) ◄─► LLM
                                          │
                                          ├─ get_srag_metrics ────┐
                                          ├─ get_srag_breakdowns ─┼─► marts agregados (Parquet)
                                          ├─ generate_srag_charts ┘
                                          └─ search_srag_news ─────► Google News RSS
                                          ▼
                                  [Guardrail de saída]
                                          ▼
                       Relatório Markdown (números calculados em código) + auditoria JSONL
```

### Ferramentas (tools) do agente

| Tool | O que faz | Fonte |
|---|---|---|
| `get_srag_metrics` | Calcula as 5 métricas (aumento de casos, variação vs. ano anterior, mortalidade, UTI, vacinação) | Marts |
| `get_srag_breakdowns` | Composição por agente etiológico e, na visão nacional, as UFs com mais casos e maior crescimento | Marts |
| `generate_srag_charts` | Gera os gráficos de casos diários (30 dias) e mensais (12 meses) | Marts |
| `search_srag_news` | Busca notícias recentes sobre SRAG, sanitizadas e marcadas como não confiáveis | Google News RSS |

O LLM (OpenAI por padrão; Claude, Gemini e Groq via `SRAG_PROVIDER`) decide quais tools chamar e
escreve a análise. Cada decisão, chamada de tool e resultado de guardrail é registrado na auditoria.

### Decisões de arquitetura

- **Orquestrador LangGraph com guardrails como nós.** Os guardrails ficam no fluxo de controle (não
  só no prompt), são determinísticos e podem devolver feedback ao LLM para nova tentativa (até 2x).
- **O LLM não calcula números.** Métricas e tabelas vêm de código testado; o LLM apenas escreve a
  análise, e o guardrail de saída rejeita qualquer percentual que não corresponda a um valor calculado.
- **Agente com tools, sem RAG ou banco vetorial.** O problema é de consulta e cálculo sobre dados
  estruturados e de notícias do momento, não de busca semântica em documentos; embeddings não
  agregariam precisão, só custo e complexidade.
- **DuckDB + Parquet em vez de um banco servidor.** 585 mil linhas cabem em memória, e o avaliador
  reproduz tudo clonando o repositório, sem credenciais nem infraestrutura. Os marts agregados fazem o
  papel do banco consultado pelo agente.
- **Notícias por Google News RSS.** Gratuito, em português e sem chave de API; os títulos entram como
  dado externo não confiável.
- **LLM configurável.** A mesma fiação funciona com 4 provedores, o que evitou o projeto ficar
  preso a limites de um único serviço.

### Métricas (janela de 30 dias terminando na última data de notificação)

| Métrica | Definição |
|---|---|
| Taxa de aumento de casos | Variação % dos casos dos últimos 30 dias vs. os 30 anteriores |
| Variação vs. ano anterior | Casos dos últimos 30 dias vs. a mesma janela 52 semanas antes (mesmos dias da semana), para separar sazonalidade de tendência |
| Taxa de mortalidade | Óbitos por SRAG / casos com desfecho conhecido |
| Taxa de ocupação de UTI | Internações que passaram por UTI / internações com informação de UTI (proxy; os dados não trazem capacidade de leitos) |
| Taxa de vacinação | Casos com vacina COVID-19 / casos com informação vacinal (proxy; não é cobertura populacional) |

Gráficos: casos diários (30 dias) e mensais (12 meses), por data de notificação.

Contexto adicional (também calculado em código, nunca pelo LLM):
- **Panorama por UF** (visão nacional): as 5 UFs com mais casos e as 5 com maior crescimento; só
  entram no ranking de crescimento UFs com pelo menos 100 casos no período, pois variações
  percentuais sobre poucos casos são instáveis.
- **Agente etiológico** (`CLASSI_FIN`): influenza, outro vírus respiratório, outro agente, não
  especificado e COVID-19. Os percentuais são sobre os casos já classificados; os recentes, ainda sem
  classificação final, são informados à parte.

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
- **Saída:** sem PII, percentuais ancorados nas métricas e tabelas calculadas, URLs apenas das
  fontes recuperadas e imagens removidas do texto do LLM.

## Tratamento de dados sensíveis
- Minimização: só 7 colunas úteis são mantidas (`DT_NOTIFIC`, `SG_UF_NOT`, `HOSPITAL`, `UTI`,
  `EVOLUCAO`, `VACINA_COV`, `CLASSI_FIN`). Colunas identificadoras (CPF, nome, endereço, data de
  nascimento etc.) estão numa lista de bloqueio e o SQL de qualquer camada que as referencie é recusado antes de rodar.
- Pseudonimização: a chave de deduplicação é um SHA-256 de campos não nominais (nº da notificação,
  município, sexo, idade etc.), calculado ao tipar o staging; os campos de origem não são gravados.
- As tools do agente leem somente os marts agregados; ao LLM chegam métricas e títulos de notícias,
  nunca registros individuais.
- Detecção de CPF, e-mail e telefone: o pedido com PII é bloqueado, as notícias têm o PII removido
  e uma análise do LLM com PII é rejeitada.
- Chave de API só via variável de ambiente; `.env` e dados brutos estão no `.gitignore`.

## Tratamento dos dados

O CSV tem **194 colunas** e centenas de milhares de linhas reais, com campos ignorados (`9`),
ausentes e inconsistentes. O fluxo é `staging (CSV) → tratamento em memória → marts`
(DuckDB, SQL em [src/srag_agent/pipeline/sql/](src/srag_agent/pipeline/sql)):

| Etapa | O que faz | Arquivo SQL |
|---|---|---|
| **staging** | CSVs originais do Open DATASUS, intocados, em `data/staging/` | n/a |
| **tipagem** | Das 194 colunas, mantém 7 úteis (`DT_NOTIFIC`, `SG_UF_NOT`, `HOSPITAL`, `UTI`, `EVOLUCAO`, `VACINA_COV`, `CLASSI_FIN`); converte datas (ISO ou dd/mm/aaaa) e códigos para tipos corretos | `typed_srag_cases.sql` |
| **tratamento** | Aplica as 6 regras de qualidade abaixo, só em memória | `clean_srag_cases.sql` |
| **marts** | Grava em Parquet só contagens agregadas por data e UF (`data/marts/`), que são o que o agente lê | `mart_srag_*_summary.sql` |

Nenhum dado individual vai para o disco: só os marts (~150 KB) e o `quality_report.json`.

### Regras de tratamento e efeito real

Contagens da execução com os CSVs de 2025 e 2026 (585.334 notificações); o relatório gerado
repete essa tabela em "Qualidade dos dados".

| # | Regra | Por quê | Efeito real |
|---|---|---|---|
| 1 | Data de notificação ausente, anterior a 2019 ou futura: linha descartada | Todas as métricas são por janela de datas | 0 linhas |
| 2 | Duplicatas (mesma chave pseudonimizada): mantém a que tem desfecho conhecido | O "banco vivo" é regravado e pode repetir notificações | 0 linhas |
| 3 | UF fora das 27 siglas vira nulo; o caso segue no total nacional | Não distorce o ranking por UF | 0 inválidas (36 ausentes) |
| 4 | Passou por UTI implica internado (`HOSPITAL` = 1) | Sem isso, esses casos de UTI sairiam do cálculo da taxa de UTI, que só considera internados | **1.418 casos** corrigidos |
| 5 | Código fora do domínio (`9` = ignorado) vira nulo | O `9` não é "sim" nem "não" e distorceria as taxas | **24.169 valores**: 781 internação, 5.409 UTI, 11.442 evolução, 6.537 vacina |
| 6 | Ausentes ficam nulos e saem do denominador da taxa, sem imputação | Não inventar valores em dado de saúde | **62.365** sem UTI, **55.181** sem desfecho, **6.600** sem vacina, **26.428** sem classificação final |

Três das seis regras não encontraram nada neste recorte. Foram mantidas de propósito: protegem
contra o que o "banco vivo" pode trazer em atualizações futuras, e os testes
([tests/test_pipeline.py](tests/test_pipeline.py)) exercitam cada uma com dados sintéticos.

Dois cuidados nas métricas, já nos marts: a taxa de UTI só considera internados com UTI informada,
e a mortalidade só considera casos com desfecho conhecido.

Exemplo ilustrativo, com valores fictícios, do que o tratamento faz com uma linha:

| Campo | Antes (staging) | Depois (tratamento) | Regra |
|---|---|---|---|
| `DT_NOTIFIC` | `2026-11-02T00:00:00.000Z` | `2026-11-02` | tipagem |
| `HOSPITAL` | `9` (ignorado) | `1` (internado) | 4 |
| `UTI` | `1` | `1` | n/a |
| `EVOLUCAO` | `9` (ignorado) | nulo (fora do denominador) | 5 e 6 |
| `VACINA_COV` | `9` (ignorado) | nulo (fora do denominador) | 5 e 6 |
| `SG_UF_NOT` | `XX` | nulo (segue no total nacional) | 3 |

A pipeline roda automaticamente na primeira execução e quando os CSVs mudam; `--rebuild` força.
Limitação conhecida: casos recentes sofrem atraso de notificação, então a taxa de aumento e a
mortalidade dos últimos dias tendem a ser subestimadas.

## Como executar
```bash
uv sync
# 1. Baixe INFLUD25*.csv e INFLUD26*.csv de https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026
#    e salve em data/staging/ (o nome deve começar com INFLUD).
# 2. cp env.example .env   e preencha OPENAI_API_KEY (https://platform.openai.com/api-keys)
#    Provedor padrão: OpenAI. Alternativas: SRAG_PROVIDER=anthropic, gemini ou groq (ver env.example).
uv run srag-report                # Brasil
uv run srag-report --uf SP        # por UF
uv run srag-report --no-llm       # sem LLM (apenas métricas, gráficos e notícias)
uv run srag-report --rebuild      # reexecuta a pipeline de dados (staging -> marts)
uv run pytest                     # testes
```
O relatório é salvo em `reports/relatorio_<data>.md`, com os gráficos ao lado.
Um exemplo real gerado pelo agente está em [docs/exemplo/](docs/exemplo/relatorio_2026-11-15.md).
O dicionário de dados usado como referência está em `docs/dicionario-de-dados-2019-a-2025.pdf`.
