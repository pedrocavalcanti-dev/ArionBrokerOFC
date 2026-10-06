from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ══════════════════════════════════════════════════════════════
#  SEGURANÇA
# ══════════════════════════════════════════════════════════════
SECRET_KEY = config('SECRET_KEY')
DEBUG      = config('DEBUG', default=False, cast=bool)

# Utilizando o Csv() do decouple para ler a lista do .env corretamente
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS', 
    default='arionbroker.bicoai.com.br,127.0.0.1,localhost,*', 
    cast=Csv()
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Arion
    'aplicativos.autenticacao',
    'aplicativos.automacao',
    'aplicativos.automacao_embratel',   # ← novo
    'aplicativos.comunicacao',
    'aplicativos.core_broker',
    'aplicativos.painel',
    'aplicativos.chamados',
    'aplicativos.cancelamentos',
    'django_apscheduler',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # ← Serve estáticos sem DEBUG=True
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'arionbroker_projeto.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'arionbroker_projeto.wsgi.application'

# ══════════════════════════════════════════════════════════════
#  BANCO DE DADOS
# ══════════════════════════════════════════════════════════════
_db_host = config('DB_HOST', default='')

if _db_host:
    DATABASES = {
        'default': {
            'ENGINE':   config('DB_ENGINE', default='django.db.backends.mysql'),
            'NAME':     config('DB_NAME'),
            'USER':     config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST':     _db_host,
            'PORT':     config('DB_PORT', default='3306'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':   BASE_DIR / 'db.sqlite3',
        }
    }

# ══════════════════════════════════════════════════════════════
#  SENHAS
# ══════════════════════════════════════════════════════════════
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ══════════════════════════════════════════════════════════════
#  IDIOMA / FUSO
# ══════════════════════════════════════════════════════════════
LANGUAGE_CODE = 'pt-br'
TIME_ZONE     = 'America/Sao_Paulo'
USE_I18N      = True
USE_TZ        = True

# ══════════════════════════════════════════════════════════════
#  ESTÁTICOS E MÍDIA
# ══════════════════════════════════════════════════════════════
STATIC_URL       = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT      = BASE_DIR / 'staticfiles'

# Whitenoise — comprime e serve estáticos com DEBUG=False
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ══════════════════════════════════════════════════════════════
# E-MAIL / BREVO
# ══════════════════════════════════════════════════════════════

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = config(
    "EMAIL_HOST",
    default="smtp-relay.brevo.com",
)

EMAIL_PORT = config(
    "EMAIL_PORT",
    default=587,
    cast=int,
)

EMAIL_USE_TLS = config(
    "EMAIL_USE_TLS",
    default=True,
    cast=bool,
)

EMAIL_HOST_USER = config("EMAIL_HOST_USER")

EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD")

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="ARION BROKER <otrs.arionbroker@gmail.com>",
)

EMAIL_DESTINO_PADRAO = config(
    "EMAIL_DESTINO_PADRAO",
    default="arionbroker.otrs@gmail.com",
)

# Timeout evita ficar preso indefinidamente caso o SMTP não responda
EMAIL_TIMEOUT = 30

# ══════════════════════════════════════════════════════════════
#  SEGURANÇA
# ══════════════════════════════════════════════════════════════
X_FRAME_OPTIONS             = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY     = True
CSRF_COOKIE_HTTPONLY        = False

# Utilizando o Csv() do decouple para ler a lista do .env corretamente
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS', 
    default='https://arionbroker.bicoai.com.br', 
    cast=Csv()
)

# ══════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simples': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'arquivo': {
            'class':     'logging.FileHandler',
            'filename':  BASE_DIR / 'django.log',
            'formatter': 'simples',
        },
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'simples',
        },
    },
    'root': {
        'handlers': ['arquivo', 'console'],
        'level':    'INFO',
    },
}

# ══════════════════════════════════════════════════════════════
#  MISC
# ══════════════════════════════════════════════════════════════
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL          = '/auth/login/'