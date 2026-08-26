---
name: dou-secao1
description: Segmenta edições da Seção 1 do Diário Oficial da União em blocos semânticos por ato publicado. Deve ser usada quando o documento reúne leis, decretos, portarias, despachos, retificações e demais publicações oficiais federais com possível mistura de conteúdo editorial e atos normativos ou administrativos.
---

# Diário Oficial da União - Seção 1

Segmenta documentos do tipo **Diário Oficial da União - Seção 1** em blocos semânticos,
classificando cada bloco em uma das categorias definidas em
`assets/config.yaml`.

Esta skill foi gerada automaticamente pelo `skill_generator/` a partir de uma
amostra do documento e das classes de segmento fornecidas pelo usuário. A
lógica de segmentação (janela deslizante, matching de âncoras) é a mesma do
pipeline principal em `semantic_seg/`; apenas a configuração é específica
deste tipo de documento.

## Uso

```bash
python scripts/segmentar.py \
    --diretorio <diretório com as páginas .md do documento> \
    --saida resultado.json
```

Parâmetros adicionais (`--model`, `--janela-paginas`, `--extensao`,
`--so-resultado`) — ver `python scripts/segmentar.py --help`.

## Arquivos

- `assets/config.yaml`: definição do tipo de documento, regras de
  granularidade (inclui a definição de bloco) e classes de segmento.
- `scripts/segmentar.py`: wrapper que carrega `assets/config.yaml` e invoca
  o pipeline de segmentação de `semantic_seg/`.
