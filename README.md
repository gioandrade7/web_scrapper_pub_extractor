# Pipeline de Extração Semântica de Documentos Jurídicos

Projeto desenvolvido em colaboração entre o **IComp/UFAM** e o **JusBrasil**, com o objetivo de identificar e extrair automaticamente blocos semânticos de publicações do Diário Oficial da União (DOU).

---

## Visão Geral do Pipeline

```
┌─────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│      scraper/       │────▶│  text_extraction/    │────▶│   semantic_seg/      │
│                     │     │                      │     │                      │
│  Scraping do DOU    │     │  PDF → Markdown      │     │  Identificação de    │
│  → texto das pubs.  │     │  RTF → Texto         │     │  blocos semânticos   │
└─────────────────────┘     └──────────────────────┘     └──────────────────────┘
       Etapa 1                      Etapa 2                      Etapa 3
```

Cada módulo pode ser executado de forma independente ou como parte do pipeline completo.

---

## Estrutura do Projeto

```
.
├── README.md                    # Esta documentação
├── requirements.txt             # Dependências Python unificadas
├── .env.example                 # Template de variáveis de ambiente
├── .gitignore
│
├── scraper/                     # Módulo 1 — Coleta de publicações
│   ├── pub_scrapper.py          # Scraper principal do DOU (async + Selenium)
│   └── dou_html_parser.py       # Parser HTML das páginas do DOU
│
├── text_extraction/             # Módulo 2 — Extração de texto
│   ├── marker_test.py           # Pipeline PDF → Markdown (Marker + GPT-4o)
│   └── rtf_txt.py               # Conversor RTF → Texto (leis em RTF)
│
└── semantic_seg/                # Módulo 3 — Segmentação semântica
    ├── main.py                  # Ponto de entrada (CLI)
    ├── utils_llm.py             # Pipeline de janela deslizante + chamadas LLM
    ├── utils_files.py           # Carregamento e montagem de páginas
    └── avaliar.py               # Avaliação com métricas (Precision/Recall/F1)
```

---

## Instalação

**1. Clone o repositório e instale as dependências:**

```bash
pip install -r requirements.txt
```

**2. Configure as variáveis de ambiente:**

```bash
cp .env.example .env
# Edite .env com suas chaves de API
```

**3. Instale o ChromeDriver** (necessário para o módulo `scraper/`):

O ChromeDriver deve ser compatível com a versão do Chrome instalada. Uma forma simples é usar o `webdriver-manager`:

```bash
pip install webdriver-manager
```

---

## Etapa 1 — Scraping do DOU (`scraper/`)

Coleta todas as publicações de uma edição do DOU e salva cada uma como um arquivo `.txt`.

**Como funciona:**
1. Um driver Selenium abre a página do DOU, clica na árvore de publicações e coleta todos os links.
2. Os cookies de sessão são capturados e repassados a um cliente `httpx` assíncrono.
3. Até 20 publicações são baixadas simultaneamente via HTTP (sem overhead de browser).
4. URLs que retornam 403 persistente são processadas por um pool de drivers Selenium como fallback.

**Execução:**

```bash
cd scraper/
python pub_scrapper.py
```

> Altere a variável `url` na função `main()` de `pub_scrapper.py` para a edição desejada:
> `https://in.gov.br/leiturajornal?data=DD-MM-AAAA&secao=do1`

**Saída:** Arquivos `Pub_000.txt`, `Pub_001.txt`, ... em `scraper/pubs_extracted/dou_secX_DD-MM/`.

---

## Etapa 2 — Extração de Texto (`text_extraction/`)

Converte documentos PDF ou RTF em texto estruturado (Markdown).

### 2a. PDF → Markdown (`marker_test.py`)

Processa um PDF página a página, usando o modelo local **Marker** para extração inicial e **GPT-4o** para correção das conversões.

**Configuração** (via `.env`):

| Variável | Descrição | Padrão |
|---|---|---|
| `OPENAI_API_KEY` | Chave da OpenAI | obrigatório |
| `DOC_NAME` | Nome do documento (sem extensão) | `dou_sec1_13-01` |
| `INPUT_PDF` | Pasta base dos PDFs | `data/pdf/` |
| `OUTPUT_DIR` | Pasta de saída dos Markdowns | `text_extraction/out/` |
| `REPAIR_MODEL` | Modelo OpenAI para correção | `gpt-4o` |
| `START_PAGE` | Página inicial (sobrescreve checkpoint) | auto-detectado |

**Execução:**

```bash
cd text_extraction/
python marker_test.py
```

**Saída:** Para cada documento, uma pasta em `out/<DOC_NAME>/` contendo:
- `page_NNNN.md` — Markdown final corrigido por página
- `md_raw_page_NNNN.md` — Markdown bruto do Marker (para depuração)
- `documento_final.md` — Documento completo concatenado

**Retomada automática:** Se o processo for interrompido, basta rodar novamente — as páginas já processadas são detectadas e puladas.

### 2b. RTF → Texto (`rtf_txt.py`)

Converte arquivos RTF (leis em formato legado) para texto plano.

```bash
cd text_extraction/
python rtf_txt.py
```

> Edite as variáveis `ano` e `rtf_path` no início do arquivo conforme necessário.

---

## Etapa 3 — Segmentação Semântica (`semantic_seg/`)

Percorre o documento (em Markdown paginado) e identifica todos os blocos semânticos via estratégia de **janela deslizante com LLM**.

**Como funciona:**
1. O texto do documento é montado como um único string com marcadores `<!-- PÁGINA N -->`.
2. Uma janela de N páginas é enviada ao LLM, que identifica o primeiro bloco semântico completo.
3. O ponteiro avança para além do fim do bloco e o processo se repete.
4. Se o bloco parece truncado (termina na última página da janela), a janela é expandida automaticamente.

**Arquivo de configuração JSON:**

```json
{
  "tipo_documento": "Diário Oficial da União — Seção 1",
  "descricao_geral": "Descrição do tipo de documento...",
  "segmentos": [
    {
      "nome": "Atos Normativos Primários",
      "descricao": "Leis, decretos e medidas provisórias..."
    }
  ]
}
```

**Execução:**

```bash
cd semantic_seg/
python main.py \
    --config configs/dou_sec1.json \
    --diretorio ../text_extraction/out/dou_sec1_06-01 \
    --saida resultados/dou_sec1_06-01.json \
    --model gpt-4o \
    --janela-paginas 10
```

**Argumentos:**

| Argumento | Descrição | Padrão |
|---|---|---|
| `--config` | Caminho para o JSON de configuração | obrigatório |
| `--diretorio` | Pasta com os arquivos `.md` das páginas | obrigatório |
| `--extensao` | Extensão dos arquivos de página | `.md` |
| `--saida` | Arquivo JSON para salvar os blocos | nenhum |
| `--model` | Modelo OpenAI | `gpt-4o` |
| `--janela-paginas` | Páginas por janela de contexto | `10` |
| `--so-resultado` | Suprime prompts no terminal | `False` |

**Saída JSON** (um objeto por bloco):

```json
{
  "classificacao": "Atos Normativos Primários",
  "titulo": "Portaria nº 123/2025",
  "pagina_inicio": 3,
  "pagina_fim": 5,
  "offset_inicio": "primeiros ~80 chars do bloco...",
  "offset_fim": "últimos ~80 chars do bloco...",
  "motivo": "Justificativa da classificação",
  "texto": "Texto completo extraído do bloco..."
}
```

### Avaliação (`avaliar.py`)

Compara os blocos preditos com publicações de referência (gabarito) e calcula métricas de detecção e qualidade de texto.

```bash
cd semantic_seg/
python avaliar.py \
    --resultado resultados/dou_sec1_06-01.json \
    --anotacoes ../scraper/pubs_extracted/dou_sec1_06-01 \
    --threshold 0.5 \
    --relatorio resultados/dou_sec1_06-01_relatorio.json
```

**Métricas calculadas:**
- **Detecção:** Precision, Recall e F1 (nível de publicação, threshold = word_F1)
- **Qualidade do texto:** word_F1 e char_F1 médios dos blocos corretamente detectados

**Resultados obtidos** (DOU Seção 1): Precision 0.95 · Recall 0.77 · F1 0.85

---

## Limitações Conhecidas

- O scraper extrai apenas texto de tags `<p>` — tabelas HTML não são capturadas.
- O pipeline de segmentação depende de um arquivo de configuração JSON com as categorias de blocos específicas do tipo de documento processado.
- O modelo local Marker pode apresentar erros em documentos com layout complexo (multi-coluna, tabelas densas); o GPT-4o corrige a maioria desses casos.
