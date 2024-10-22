# Extrator de publicações do Diário Oficial da União 

## 💻 Descrição do Projeto
Este projeto, resultado da colaboração entre o Instituto de Computação (IComp) da Universidade Federal do Amazonas (UFAM) e a empresa JusBrasil, tem como objetivo o desenvolvimento de um extrator de publicações do Diário Oficial da União.

Isso ocorre através do uso da biblioteca [Selenium](https://www.selenium.dev/) na construção de um script capaz de, a partir de um link pertencente a uma seção do diário de determinado dia, acessar as publicações desse caderno e realizar a extração do texto.

🏁 Tabela de conteúdos
=================
<!--ts-->
   * 🔘 [Capturas de tela](#-capturas-de-tela)
   * 🔘 [Como usar](#-como-usar)
   * 🔘 [Experimentos e Resultados](#-experimentos-e-resultados)
<!--te-->

## 📸 Capturas de Tela

Publicação: 
<p align="center">
  <img src="./pub.png" />
</p>

Texto extraído:
<p align="center">
  <img src="./texto.png" />
</p>

## 📖 Como usar

Para poder utilizar a aplicação, você vai precisar ter instalado a biblioteca [Selenium](https://www.selenium.dev/).

```bash
# Clone este repositório
$ https://github.com/gioandrade7/ner_extension.git
```

1. No script `pub_extraction.py` altere a variável `url` para a url da seção do DOU de onde você deseja realizar a extração das publicações.
2. Execute o script `python pub_extraction.py`

## 🔬 Avaliação e Resultados

A avaliação desse método se deu através do cálculo das métricas de precisão, revocação e f1-score. 

As publicações extraídas foram comparadas com as publicações da tabela fornecida. As publicações foram extraídas das 3 seções do dia 02/09/2024.  

Os resultados obtidos foram:

- **Precisão:** 0.95
- **Revocação:** 0.77
- **F1-score:** 0.85

Os falsos positivos podem ser justificados pelo fato de que alguns caracteres das publicações extraídas podem diferir das publicações da tabela. Ex:

    Nº 12.275 != N° 12.275

Os falsos negativos podem ser justificados pelos seguintes motivos:

- Alguns coincidem com casos de falsos positivos;
- Publicações grandes são dividas em várias partes e são consideradas como publicações separadas na tabela. Nesse caso, este algorimto extrai a publicação por inteiro, e essas divisões não consideradas como FNs, pois não possuem uma publicação correspondente.

Análises mais aprofundadas são necessárias para a investigação de outras justificativas; 

## 📈 Melhorias

- O algorimto extrai o texto somente de tags <p> no html. Ou seja, informações contidas em outras *tags* (como de tabelas) não são recuperadas;  
- Texto bruto da página é recuperado, dependendo da finalidade, possíveis formatações serão necessárias;


 



