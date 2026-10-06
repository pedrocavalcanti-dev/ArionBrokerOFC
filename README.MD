# ArionBroker

Sistema de gestão e automação de chamados (Broker), integrado com OTRS e painel da Claro.

## 🚀 Como configurar o ambiente de desenvolvimento local

Siga o passo a passo abaixo para rodar o projeto do zero em uma máquina nova.

### 1. Clone o repositório

Abra o terminal e baixe o código:

```powershell
git clone https://github.com/pedrocavalcanti-dev/ArionBroker.git
cd ArionBroker
```

### 2. Configure o Ambiente Virtual (venv)

Crie e ative o ambiente virtual para isolar as dependências:

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Instale as Dependências Python

Com o venv ativado, instale as bibliotecas listadas no projeto:

```powershell
pip install -r requirements.txt
```

### 4. Instale o Navegador do Playwright (Robô)

O scraper precisa do Chromium para rodar em segundo plano. Esse download é feito à parte, pois o Chromium não é uma biblioteca Python:

```powershell
playwright install chromium
```

### 5. Configure as Variáveis de Ambiente

O projeto usa um arquivo `.env` na raiz para guardar chaves, senhas e configurações — ele **não vai para o GitHub** por segurança (está no `.gitignore`).

Copie o modelo `.env.example` incluído no repositório e renomeie para `.env`:

```powershell
copy .env.example .env
```

Depois, abra o `.env` e preencha cada campo com os valores reais (peça ao responsável pelo projeto quem não tiver acesso):

```
# ── SEGURANÇA ─────────────────────────────────────────────────
SECRET_KEY=
DEBUG=False

# ── HOSTS ─────────────────────────────────────────────────────
# Dev: manter ['*']
# Prod: trocar por seus domínios oficiais
ALLOWED_HOSTS=

# ── PROTEÇÃO CSRF (CLOUDFLARE HTTPS) ──────────────────────────
# Obrigatório no Django 4+ para o login funcionar atrás do proxy da Cloudflare
CSRF_TRUSTED_ORIGINS=

# ── BANCO DE DADOS ────────────────────────────────────────────
DB_ENGINE=django.db.backends.mysql
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

# ── E-MAIL ─────────────────────────────────────────────────────
EMAIL_HOST=
EMAIL_PORT=
EMAIL_USE_TLS=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=
EMAIL_DESTINO_PADRAO=

# ── SCRAPER (Portal Claro) ────────────────────────────────────
SCRAPER_USUARIO=
SCRAPER_SENHA=

# ── OTRS (Portal Arion) ────────────────────────────────────────
OTRS_USUARIO=
OTRS_SENHA=

# ── Ligar e Desligar Robô ───────────────────────────────────────
RODA_AUTOMACAO=False  # Mude para True apenas no servidor de produção
```

> ⚠️ **Nunca** faça commit do arquivo `.env` preenchido com as credenciais reais. Apenas o `.env.example` (vazio) deve ir para o repositório.

### 6. Banco de Dados

Gere as tabelas e importe o seu backup de dados (se houver):

```powershell
python gerenciar.py migrate
# Se tiver um arquivo de backup, rode o comando abaixo:
# python -X utf8 gerenciar.py loaddata backup_dados_limpo.json
```

### 7. Rode o Servidor

```powershell
python gerenciar.py runserver
```

O sistema estará disponível em http://localhost:8000/.

## 📦 Dependências principais

- **Django** — framework web
- **Playwright** — automação do robô/scraper (Chromium instalado separadamente, veja passo 4)
- **django-apscheduler** — agendamento das tarefas do robô
- **mysqlclient** — conexão com o banco MySQL
- **python-decouple / python-dotenv** — leitura das variáveis do `.env`
- **certifi / urllib3** — resolvem os erros de certificado/SSL usados na integração com a Claro

## 🔒 Segurança

A automação (robô) só roda de fato quando a variável `RODA_AUTOMACAO=True` está definida no `.env`. Isso evita que o robô seja disparado acidentalmente em máquinas de desenvolvimento.
