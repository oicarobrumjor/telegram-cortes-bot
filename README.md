# Bot Telegram para Cortes de YouTube

Projeto Python pronto para GitHub e Railway de um bot Telegram que baixa videos do YouTube, gera cortes com `ffmpeg`, baixa legenda automatica em portugues e envia a transcricao para o Gemini.

## Funcionalidades

- `/start`: mostra os comandos disponiveis.
- `/video LINK`: baixa o video do YouTube e salva um video atual por chat.
- `/corte NOME | INICIO FIM`: gera e envia um corte do video atual.
- `/limpar`: remove video, legenda e estado do chat.
- `/aut`: baixa a legenda automatica em portugues do video atual.
- `/legenda`: envia o arquivo `.srt` atual.
- `/maquina`: limpa o `.srt`, envia a transcricao para o Gemini e retorna a resposta no Telegram.

## Requisitos

- Python 3.11 ou superior
- `ffmpeg` instalado no sistema
- Token de bot do Telegram
- Opcional: `GEMINI_API_KEY` para usar `/maquina`

## Variaveis de ambiente

- `TELEGRAM_BOT_TOKEN`: obrigatoria
- `GEMINI_API_KEY`: opcional
- `GEMINI_MODEL`: opcional, padrao `gemini-1.5-flash`
- `LOG_LEVEL`: opcional, padrao `INFO`

## Como rodar localmente

1. Crie e ative um ambiente virtual:

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Instale as dependencias:

```bash
pip install -r requirements.txt
```

3. Garanta que o `ffmpeg` esta instalado e disponivel no `PATH`.

4. Defina as variaveis de ambiente:

```powershell
$env:TELEGRAM_BOT_TOKEN="SEU_TOKEN"
$env:GEMINI_API_KEY="SUA_CHAVE_OPCIONAL"
```

5. Inicie o bot:

```bash
python bot.py
```

## Uso no Telegram

### Baixar um video

```text
/video https://www.youtube.com/watch?v=EXEMPLO
```

### Gerar um corte

```text
/corte Hook inicial | 00:15 01:05
```

Tambem aceita `hh:mm:ss`. O corte tem limite de 20 minutos.

### Baixar legenda automatica

```text
/aut
```

O bot tenta `pt-BR`, depois `pt`, prioriza SRT e converte para `.srt` quando necessario.

### Enviar a legenda atual

```text
/legenda
```

### Analisar com Gemini

```text
/maquina
```

O bot remove numeracao e timestamps do `.srt`, envia a transcricao para o Gemini e responde com resumo e sugestoes de cortes.

## Estrutura do projeto

```text
.
|-- bot.py
|-- requirements.txt
|-- Procfile
|-- railway.json
|-- nixpacks.toml
|-- .gitignore
`-- README.md
```

## GitHub

1. Inicialize o repositório:

```bash
git init
git add .
git commit -m "feat: bot telegram para cortes"
```

2. Crie um repositório no GitHub e envie:

```bash
git remote add origin SEU_REPOSITORIO
git branch -M main
git push -u origin main
```

## Deploy no Railway

1. Suba este projeto para o GitHub.
2. No Railway, crie um novo projeto a partir do repositório.
3. Configure as variaveis:
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY` se quiser usar `/maquina`
4. O Railway usara:
   - `Procfile` com `worker: python bot.py`
   - `railway.json` com `startCommand` igual a `python bot.py`
   - `nixpacks.toml` para instalar `ffmpeg`

## Observacoes tecnicas

- O armazenamento e feito por chat em `data/chats/<chat_id>`.
- Ao trocar de video com `/video`, o bot remove arquivos antigos antes de salvar o novo.
- O estado guarda apenas o video e a legenda atuais, evitando reutilizacao de arquivos antigos.
- Erros de `yt-dlp`, `ffmpeg`, legenda e Gemini sao tratados com mensagens amigaveis no Telegram.
