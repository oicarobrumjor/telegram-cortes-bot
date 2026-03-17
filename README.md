# Bot Telegram para Cortes de YouTube

Projeto Python pronto para GitHub e Railway de um bot Telegram que baixa videos do YouTube, gera cortes com `ffmpeg`, baixa legenda automatica em portugues e envia a transcricao para o Gemini.

## Funcionalidades

- `/start`: mostra os comandos disponiveis.
- `/video LINK`: baixa o video do YouTube e salva um video atual por chat.
- `/drive`: lista os videos da pasta configurada no Google Drive.
- `/carregar NUMERO`: baixa um video da listagem do Google Drive e salva como video atual.
- `/corte NOME | INICIO FIM`: gera e envia um corte do video atual.
- `/cortes NOME | INICIO FIM ; NOME | INICIO FIM`: gera varios cortes em sequencia.
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
- `YOUTUBE_COOKIES_BASE64`: opcional, recomendado quando o YouTube exigir autenticacao anti-bot
- `YOUTUBE_COOKIES`: opcional, alternativa em texto puro ao arquivo de cookies
- `GOOGLE_DRIVE_FOLDER_ID`: opcional, obrigatoria para usar `/drive`
- `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`: opcional, recomendada para integrar com Google Drive
- `GOOGLE_SERVICE_ACCOUNT_JSON`: opcional, alternativa em texto puro ao JSON da service account
- `WEBHOOK_URL`: opcional, ativa modo webhook quando definida
- `WEBHOOK_PATH`: opcional, padrao `telegram`
- `WEBHOOK_SECRET_TOKEN`: opcional, recomendado para validar chamadas do Telegram
- `PORT`: opcional, padrao `8080` no webhook

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

Se precisar usar cookies do YouTube, voce pode carregar um `cookies.txt` local em Base64:

```powershell
$env:YOUTUBE_COOKIES_BASE64=[Convert]::ToBase64String([IO.File]::ReadAllBytes("cookies.txt"))
```

5. Inicie o bot:

```bash
python bot.py
```

Por padrao o bot sobe em `polling`. Se quiser testar `webhook`, defina tambem:

```powershell
$env:WEBHOOK_URL="https://seu-app.up.railway.app"
$env:WEBHOOK_PATH="telegram"
$env:WEBHOOK_SECRET_TOKEN="um-segredo-forte"
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

### Gerar varios cortes em sequencia

```text
/cortes Hook inicial | 00:15 01:05 ; CTA final | 05:10 05:40
```

### Listar videos do Google Drive

```text
/drive
```

O bot responde com a lista numerada da pasta configurada. Depois selecione um item:

```text
/carregar 2
```

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
   - `YOUTUBE_COOKIES_BASE64` se o YouTube bloquear downloads com mensagem de anti-bot
   - `GOOGLE_DRIVE_FOLDER_ID` se quiser listar videos da pasta do Drive
   - `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` para autenticar no Google Drive
   - `WEBHOOK_URL` se quiser reduzir uso continuo de polling
   - `WEBHOOK_SECRET_TOKEN` recomendado se ativar webhook
4. O Railway usara:
   - `Procfile` com `worker: python bot.py`
   - `railway.json` com `startCommand` igual a `python bot.py`
   - `nixpacks.toml` para instalar `ffmpeg`

### Modo webhook no Railway

Se quiser economizar e evitar polling continuo, configure:

- `WEBHOOK_URL`: URL publica do servico no Railway, por exemplo `https://seu-app.up.railway.app`
- `WEBHOOK_PATH`: opcional, padrao `telegram`
- `WEBHOOK_SECRET_TOKEN`: recomendado

Com isso, o bot passa a usar:

```text
https://seu-app.up.railway.app/telegram
```

Se `WEBHOOK_URL` nao estiver definida, o bot continua usando polling. Isso permite migracao segura sem quebrar o modo atual.

## Observacoes tecnicas

- O armazenamento e feito por chat em `data/chats/<chat_id>`.
- Ao trocar de video com `/video`, o bot remove arquivos antigos antes de salvar o novo.
- O estado guarda apenas o video e a legenda atuais, evitando reutilizacao de arquivos antigos.
- Erros de `yt-dlp`, `ffmpeg`, legenda e Gemini sao tratados com mensagens amigaveis no Telegram.
- Se `YOUTUBE_COOKIES_BASE64` ou `YOUTUBE_COOKIES` estiverem definidos, o bot grava um `cookies.txt` temporario por chat e o usa no `yt-dlp`.

## Cookies do YouTube

Se o bot retornar algo como `Sign in to confirm you’re not a bot`, exporte os cookies da sua sessao do YouTube e configure no ambiente.

Fluxo recomendado:

1. Exporte um arquivo `cookies.txt` da sua sessao do navegador.
2. Converta o arquivo para Base64 localmente.
3. Cole o resultado na variavel `YOUTUBE_COOKIES_BASE64` do Railway.

Exemplo no PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("cookies.txt"))
```

O bot vai decodificar essa variavel e usar o arquivo de cookies automaticamente nos downloads e nas legendas.

## Google Drive

Para usar `/drive` e `/carregar`, configure uma service account do Google com acesso de leitura a pasta do Drive.

Fluxo recomendado:

1. Crie uma service account no Google Cloud.
2. Gere a chave JSON da service account.
3. Compartilhe a pasta do Google Drive com o email da service account como leitor.
4. Pegue o ID da pasta no link do Drive.
5. Configure no ambiente:
   - `GOOGLE_DRIVE_FOLDER_ID`
   - `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`

Exemplo para converter o JSON da service account em Base64 no PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service-account.json"))
```

Depois:

1. Envie `/drive`
2. Escolha um item com `/carregar NUMERO`
3. Gere um corte com `/corte` ou varios de uma vez com `/cortes`

Observacao:

- `/aut` continua sendo exclusivo para videos carregados do YouTube
- Para videos do Drive, se voce quiser usar `/maquina`, sera preciso carregar uma legenda `.srt` por outro fluxo
