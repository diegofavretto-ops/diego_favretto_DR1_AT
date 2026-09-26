# Brasil nas Copas do Mundo - Sport Analytics

Assessment de Desenvolvimento Front-End com Python utilizando Streamlit, StatsBombPy e mplsoccer.

## Pergunta do projeto

**Como o desempenho coletivo da Seleção Brasileira varia entre as Copas do Mundo disponíveis no StatsBomb Open Data e o que os eventos de cada partida mostram sobre passes, chutes e ações defensivas?**

O projeto utiliza apenas as edições e partidas realmente disponíveis no StatsBomb Open Data. O foco é a Seleção Brasileira como equipe; jogadores aparecem somente como filtros auxiliares.

## Estrutura

```text
diego_favretto_DR1_AT/
├── app.py
├── requirements.txt
├── README.md


## Criar o ambiente virtual

No PowerShell, dentro da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Para validar o Streamlit instalado:

```powershell
streamlit hello
```

## Executar o projeto

```powershell
streamlit run app.py
```

## Recursos utilizados

- Streamlit: layout, páginas, sidebar, tabs, containers, forms, métricas, download, upload, progress, spinner, cache e Session State;
- StatsBombPy: competições, temporadas, partidas e eventos;
- Pandas: tratamento e filtros;
- mplsoccer: mapa de passes, chutes e calor;
- Matplotlib e Seaborn: comparação estatística;
- Altair: heatmap temporal de eventos;
- Plotly: gráficos interativos e subplots;
- PyDeck: mapa contextual das sedes das Copas disponíveis;
- streamlit-extras: estilização dos cartões de métricas.

## Git e GitHub

Depois de criar um repositório vazio no GitHub, execute:

```powershell
git init
git add .
git commit -m "Assessment Streamlit Sport Analytics"
git branch -M main
git remote add origin https://github.com/diegofavretto/diego_favretto_DR1_AT.git
git push -u origin main
```

## Streamlit Community Cloud

Após enviar o projeto ao GitHub:

1. Acesse o Streamlit Community Cloud.
2. Escolha o repositório `diego_favretto_DR1_AT`.
3. Selecione a branch `main`.
4. Informe `app.py` como arquivo principal.
5. Faça o deploy e teste todas as páginas.

**Link do GitHub:** preencher após a publicação.  
**Link do Streamlit:** preencher após o deploy.

## Fonte dos dados

StatsBomb Open Data: https://github.com/statsbomb/open-data
