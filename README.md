# Pipeline de Extração Semântica de Documentos Jurídicos

Projeto desenvolvido em colaboração entre o **IComp/UFAM** e o **JusBrasil**, com o objetivo de identificar e extrair automaticamente blocos semânticos de documentos oficiais — publicações do Diário Oficial da União (DOU) e leis federais.

---

## Visão Geral do Pipeline

```
┌──────────────────────┐     ┌────────────────────────────────────────┐
│  text_extraction/    │────▶│           semantic_seg/                │
│                      │     │                                        │
│  PDF  → Markdown     │     │  Identificador → Segmentador ⇄ Auditor │
│  RTF  → Texto        │     │  (padrão)        (blocos)    (correção)│
└──────────────────────┘     └────────────────────────────────────────┘
        Etapa 1                            Etapa 2
```

Cada módulo pode ser executado de forma independente. A segmentação é **puramente segmentação**: descobrir onde cada bloco começa e termina. Não há classificação em categorias pré-definidas nem arquivo de configuração por tipo de documento — o prompt é genérico e se especializa em tempo de execução.

> **Nota histórica:** um terceiro módulo, `scraper/`, coletava as publicações do DOU em in.gov.br e foi removido no commit `3781290`. Ele produzia o corpus de referência (`Pub_N.txt`, um arquivo por publicação) que o `avaliar.py` ainda espera como gabarito. Esse corpus não está no repositório — era ignorado pelo git — e não se encontra no disco. Ver [Limitações Conhecidas](#limitações-conhecidas).

---

## Estrutura do Projeto

```
.
├── README.md                    # Esta documentação
├── CLAUDE.md                    # Guia para o Claude Code
├── requirements.txt             # Dependências Python
│
├── text_extraction/             # Etapa 1 — Extração de texto
│   ├── download_pdfs.py         # Baixa edições completas do DOU (PDF)
│   ├── pdf_extract.py           # PDF → Markdown (camada de texto nativa)
│   └── rtf_txt.py               # RTF → Texto (leis em formato legado)
│
└── semantic_seg/                # Etapa 2 — Segmentação semântica
    ├── main.py                  # Ponto de entrada (CLI)
    ├── identificador.py         # Infere o padrão estrutural do documento
    ├── utils_llm.py             # Janela deslizante + chamadas ao LLM
    ├── corretor.py              # Auditoria dos blocos e correção iterativa
    ├── anchor.py                # Localização tolerante de âncoras
    ├── utils_files.py           # Carregamento e montagem de páginas
    ├── display.py               # Exibição no terminal
    └── avaliar.py               # Métricas (Precision/Recall/F1)
```

---

## Instalação

```bash
pip install -r requirements.txt
```

Crie um `.env` na raiz com a chave da OpenAI (não há `.env.example` no repositório):

```
OPENAI_API_KEY=sk-...
```

A chave é usada **apenas** pelo `semantic_seg/`. O `text_extraction/` não faz nenhuma chamada de API.

---

## Etapa 1 — Extração de Texto (`text_extraction/`)

### 1a. Baixar edições do DOU (`download_pdfs.py`)

Busca cada página de uma edição individualmente no `pesquisa.in.gov.br` (8 threads, 3 tentativas, validação dos magic bytes `%PDF`) e funde tudo num PDF único com PyMuPDF.

```bash
cd text_extraction/
python download_pdfs.py
```

> As edições são uma lista `EDITIONS` no início do arquivo: `(data, total_de_páginas, nome_de_saída)`.

**Saída:** `text_extraction/data/pdf/dou_secX_DD-MM.pdf`

### 1b. PDF → Markdown (`pdf_extract.py`)

Lê a **camada de texto nativa** do PDF — sem OCR, sem modelo de ML, sem chamada de API. Três estratégias, escolhidas no momento do import:

1. **pymupdf4llm** — preferencial; detecta colunas, listas e tabelas automaticamente.
2. **Blocos do PyMuPDF + ordenação por coluna** — fallback heurístico para layout multi-coluna.
3. **`get_text()` puro** — último recurso, na ordem do stream do PDF.

```bash
python pdf_extract.py -i arquivo.pdf -o saida/
python pdf_extract.py -i arquivo.pdf -o saida/ --workers 8   # paralelo
python pdf_extract.py -i arquivo.pdf -o saida/ --no-resume   # reprocessa do zero
python pdf_extract.py -i arquivo.pdf -o saida/ --no-final    # sem documento_final.md
python pdf_extract.py -i arquivo.pdf -o saida/ --chunk-size 4 # páginas por chunk
```

| Argumento | Descrição | Padrão |
|---|---|---|
| `-i` / `--input` | PDF de entrada | obrigatório |
| `-o` / `--output` | Diretório de saída | obrigatório |
| `-w` / `--workers` | Processos paralelos | metade dos CPUs |
| `--chunk-size` | Páginas por chunk de worker | automático |
| `--no-resume` | Reprocessa todas as páginas | desligado |
| `--no-final` | Não gera `documento_final.md` | desligado |

**Saída:** `page_NNNN.md` por página (0-indexado, 4 dígitos) e `documento_final.md`.

**Retomada automática:** páginas já processadas são detectadas e puladas. Páginas que extraem menos de 100 caracteres geram aviso — sinal de PDF escaneado, que precisaria de OCR.

Também usável como biblioteca:

```python
from text_extraction.pdf_extract import extract_pdf
resultados = extract_pdf("arquivo.pdf", "saida/", workers=4)
```

### 1c. RTF → Texto (`rtf_txt.py`)

Converte arquivos RTF (leis em formato legado) para texto plano via `striprtf`.

```bash
python rtf_txt.py
```

> Edite as variáveis `ano` e `rtf_path` no início do arquivo.

---

## Etapa 2 — Segmentação Semântica (`semantic_seg/`)

Três componentes, sendo dois deles um laço:

### Identificador — infere o padrão, uma vez

Antes de qualquer segmentação, lê uma **amostra do texto fonte**: `n` páginas contíguas do começo, `n` do meio e `n` do fim. Devolve a hierarquia do documento, o nível em que cortar os blocos e uma confiança.

A contiguidade é deliberada: para saber em que nível cortar, é preciso ver onde uma unidade termina e a próxima começa — uma página isolada mostra apenas o cabeçalho de uma unidade.

```json
{
  "tem_padrao": true,
  "modo": "hierarquico",
  "hierarquia": [
    {"nivel": 1, "nome": "Seção", "exemplo": "Section 3-02"},
    {"nivel": 2, "nome": "Subseção alfabética", "exemplo": "(b) Invitation for Bids."}
  ],
  "nivel_de_corte": 2,
  "justificativa_corte": "...",
  "confianca": "alta"
}
```

`modo` pode ser `hierarquico` (níveis encaixados), `sequencia_plana` (unidades independentes de mesmo nível — o caso do DOU, que é uma sucessão de publicações sem enumeração global) ou `topico` (sem padrão; delimitação só por mudança de assunto). `tem_padrao: false` é uma resposta legítima: o módulo não é obrigado a inventar uma hierarquia.

### Segmentador — janela deslizante

1. O documento é montado como um único string com marcadores `<!-- PÁGINA N -->`.
2. Uma janela de N páginas vai ao LLM, que identifica **apenas o primeiro bloco completo**.
3. O ponteiro de caracteres avança para além do fim do bloco, localizado pela âncora `offset_fim`.
4. Se o bloco termina na última página da janela, ele pode estar truncado: a janela dobra de tamanho e a chamada é repetida.

As âncoras são reencontradas no texto por `anchor.py`, em cinco camadas de tolerância (exata, parcial, normalizada, normalizada parcial e — só para o fim do bloco — por sufixo), porque o LLM promete copiar literalmente e na prática come marcação markdown, acentos e espaços.

### Auditor — correção iterativa

Recebe um **resumo** dos blocos (páginas, tamanho, título e as bordas: 250 caracteres iniciais e 120 finais) mais o padrão vindo do Identificador. Verifica se a segmentação respeita esse padrão e procura cinco problemas: granularidade desigual, bloco englobante, sobreposição, lacuna e falha de âncora.

Se reprovar, escreve diretrizes concretas que voltam ao prompt do Segmentador, e o documento é re-segmentado. O laço para quando o auditor aprova, quando não produz diretrizes novas, quando as diretrizes se repetem (o ciclo seguinte seria idêntico) ou no teto de `--max-ciclos`.

O Auditor **não deduz** o padrão dos blocos que está julgando — isso seria circular, já que os blocos são o objeto sob suspeita. Com `--sem-identificador` ele volta a deduzir, comportamento anterior mantido para comparação.

### Execução

```bash
cd semantic_seg/
python main.py \
    --diretorio ../text_extraction/ppb_rules_out/paginas \
    --saida resultados/ppb_rules.json \
    --janela-paginas 10
```

| Argumento | Descrição | Padrão |
|---|---|---|
| `--diretorio` | Pasta com os arquivos `.md` das páginas | obrigatório |
| `--extensao` | Extensão dos arquivos de página | `.md` |
| `--saida` | Arquivo JSON para salvar os blocos | nenhum |
| `--model` | Modelo OpenAI | `gpt-5.6-terra` |
| `--janela-paginas` | Páginas por janela de contexto | `10` |
| `--paginas-amostra` | Páginas por região (começo/meio/fim) enviadas ao Identificador | `2` |
| `--sem-identificador` | Não infere o padrão; o Auditor volta a deduzi-lo dos blocos | desligado |
| `--max-ciclos` | Teto de ciclos; `0` roda até o Auditor aprovar | `0` |
| `--sem-correcao` | Uma única passada, sem o Auditor | desligado |
| `--so-resultado` | Suprime os prompts no terminal | desligado |

**Saída:** `--saida` guarda **somente a lista de blocos**, que é o formato consumido pelo `avaliar.py`. Ao lado dele são escritos:

| Arquivo | Conteúdo |
|---|---|
| `{saida}_padrao.json` | O padrão identificado, com a procedência da amostra |
| `{saida}_cicloN.json` | A extração íntegra de cada ciclo |
| `{saida}_correcao.json` | O rastro da correção: diretrizes e veredito por ciclo |

Arquivos existentes **nunca são sobrescritos** — o sufixo `_v2`, `_v3` é acrescentado. Cada rodada custa chamadas de API e o último ciclo não é necessariamente o melhor, então as versões anteriores são material de comparação.

**Um bloco na saída:**

```json
{
  "titulo": "(b) Invitation for Bids",
  "pagina_inicio": 3,
  "pagina_fim": 5,
  "offset_inicio": "primeiros ~80 chars do bloco...",
  "offset_fim": "últimos ~80 chars do bloco...",
  "motivo": "Por que esse trecho forma uma unidade coesa",
  "texto": "Texto completo extraído do bloco..."
}
```

---

## Avaliação (`avaliar.py`)

Compara os blocos preditos com arquivos de referência (um arquivo por bloco esperado) via casamento guloso pelo maior `word_f1`, e calcula:

- **Detecção:** Precision, Recall e F1 — um bloco predito é TP se casa com alguma referência acima do `--threshold`.
- **Qualidade do texto:** `word_f1` e `char_f1` médios sobre os TPs.

```bash
python avaliar.py \
    --resultado resultados/X.json \
    --anotacoes <diretório de referência> \
    --threshold 0.5 \
    --relatorio resultados/X_relatorio.json

# Dataset de leis, com rótulo no nome do arquivo:
python avaliar.py --formato lei --resultado ... --anotacoes ...
```

Dois formatos de gabarito: DOU (`Pub_N.txt`, com `classes.json` opcional) e leis (`{seq}-{classe}-{pag_ini}-{pag_fim}.txt`).

> **Resultado histórico** (Precision 0.95 · Recall 0.77 · F1 0.85, DOU Seção 1): obtido com a versão anterior do pipeline, que usava configuração por tipo de documento e fazia classificação. Não é comparável à versão atual e não foi reproduzido desde então.

---

## Limitações Conhecidas

- **Não há dados de referência no repositório.** O `avaliar.py` precisa de anotações que não estão presentes em nenhum dos dois formatos — não há `Pub_*.txt`, `classes.json` nem o dataset de leis. Enquanto um corpus não for restaurado, o veredito do laço de correção e o padrão do Identificador só podem ser inspecionados à mão, não medidos.
- **Rodar o laço até `consistente=true` é um teste de auto-consistência, não de correção.** O Auditor compara a segmentação com uma especificação estrutural, não com o documento inteiro: uma segmentação uniformemente errada é um ponto fixo. A validação externa contra gabarito é a única saída dessa circularidade.
- **As métricas de classificação do `avaliar.py` estão órfãs.** Ele lê o campo `classificacao` de cada bloco, mas nenhum código o escreve — o prompt atual é só de segmentação. Com `--formato lei` o bloco de classificação roda e imprime `Accuracy: 0/N`.
- **O Identificador é um ponto único de falha.** O padrão que ele infere entra como critério estrutural nos prompts do Segmentador e do Auditor; se estiver errado, passa a ser fiscalizado fielmente e com mais autoridade do que antes. O `{saida}_padrao.json` existe para deixar isso auditável e a flag `--sem-identificador` para permitir comparação.
- O `pdf_extract.py` exige camada de texto nativa; PDFs escaneados precisariam de OCR (páginas com menos de 100 caracteres geram aviso).
- **`semantic_seg/lei.yaml` é vestigial** — seu único consumidor era o `anotar_classes.py`, removido no commit `3781290`. Nenhum código o lê.
- **`requirements.txt` está desatualizado**: ainda lista as dependências do scraper removido (`selenium`, `beautifulsoup4`, `lxml`, `requests`) e o `marker-pdf`, do pipeline de PDF que o `pdf_extract.py` substituiu. O ChromeDriver não é mais necessário.
