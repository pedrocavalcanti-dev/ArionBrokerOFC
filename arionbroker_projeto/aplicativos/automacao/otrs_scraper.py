"""
ARION PROJETOS — BROKER
aplicativos/automacao/otrs_scraper.py

Busca tickets no OTRS correspondentes às RECs enviadas por e-mail.
SESSÃO VIA COOKIES: O navegador é aberto e fechado a cada ciclo de forma limpa.
Os cookies são salvos em disco para pular o formulário de login do OTRS,
evitando bloqueios de segurança por múltiplas tentativas.
"""
import os
import re
import json
import logging
from datetime import timedelta
from urllib.parse import quote

from decouple import config
from django.conf import settings
from django.utils import timezone
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# ── CONFIGURAÇÕES ─────────────────────────────────────────────
OTRS_URL_LOGIN = 'https://suporte.grupoarion.com.br/otrs/index.pl'
OTRS_USUARIO = config('OTRS_USUARIO')
OTRS_SENHA   = config('OTRS_SENHA')

# Caminho absoluto para salvar a sessão do Playwright (cookies)
ARQUIVO_SESSAO_OTRS = os.path.join(settings.BASE_DIR, 'otrs_cookies.json')

JANELA_HORAS_ANTES          = 2
JANELA_HORAS_DEPOIS         = 72
JANELA_LIMITE_ABSOLUTO_DIAS = 3

ESTADOS_FECHADOS = frozenset({
    'fechado', 'closed', 'fechado com êxito', 'successful',
    'fechado sem êxito', 'merged', 'removido',
})

_RE_DATA_BR  = re.compile(r'(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})')
_RE_DATA_ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})')


# ── VALIDAÇÃO DO ARQUIVO DE SESSÃO (COOKIES) ──────────────────
def _sessao_valida(caminho: str) -> bool:
    """
    Verifica se o arquivo de storage_state existe, não está vazio
    e contém um JSON válido. Se estiver corrompido/vazio, remove o
    arquivo para forçar um login limpo na próxima tentativa.
    """
    if not os.path.exists(caminho):
        return False

    try:
        if os.path.getsize(caminho) == 0:
            logger.warning('[OTRS] [SESSAO] Arquivo de cookies vazio (0 bytes). Descartando: %s', caminho)
            _remover_sessao_corrompida(caminho)
            return False

        with open(caminho, 'r', encoding='utf-8') as f:
            conteudo = f.read().strip()

        if not conteudo:
            logger.warning('[OTRS] [SESSAO] Arquivo de cookies vazio (string vazia). Descartando: %s', caminho)
            _remover_sessao_corrompida(caminho)
            return False

        json.loads(conteudo)  # valida se é JSON legítimo
        return True

    except (json.JSONDecodeError, OSError) as e:
        logger.warning('[OTRS] [SESSAO] Arquivo de cookies corrompido (%s). Descartando: %s', e, caminho)
        _remover_sessao_corrompida(caminho)
        return False


def _remover_sessao_corrompida(caminho: str):
    try:
        os.remove(caminho)
        logger.info('[OTRS] [SESSAO] Arquivo corrompido removido: %s', caminho)
    except OSError as e:
        logger.error('[OTRS] [SESSAO] Não foi possível remover arquivo corrompido: %s', e)


# ── SCREENSHOT DE FALHA ───────────────────────────────────────
def _salvar_screenshot(page: Page, nome: str = 'otrs_falha.png'):
    try:
        falhas_dir = os.path.join(settings.BASE_DIR, 'aplicativos', 'autenticacao', 'falhasotrs')
        os.makedirs(falhas_dir, exist_ok=True)
        caminho = os.path.join(falhas_dir, nome)
        page.screenshot(path=caminho, full_page=True)
        logger.warning('[OTRS] [FALHA] Screenshot salvo: %s', caminho)
    except Exception as ex:
        logger.warning('[OTRS] [FALHA] Erro ao salvar screenshot: %s', ex)


# ── EXTRAÇÃO DE TOKEN ─────────────────────────────────────────
def _extrair_token(page: Page) -> str:
    """Busca o ChallengeToken na interface do OTRS."""
    try:
        btn_logout = page.wait_for_selector('.LogoutButton', state='attached', timeout=5_000)
        if btn_logout:
            href = btn_logout.get_attribute('href') or ''
            m = re.search(r'ChallengeToken=([^;&\s]+)', href)
            if m:
                return m.group(1)
    except Exception:
        pass

    html = page.content()
    for pattern in [
        r'ChallengeToken=([^;&"\'\s]{10,})',
        r'name="ChallengeToken"\s+value="([^"]+)"',
    ]:
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return ''


# ── LOGIN ─────────────────────────────────────────────────────
def _salvar_sessao(page: Page):
    """Salva o storage_state com proteção contra escrita corrompida/vazia."""
    try:
        page.context.storage_state(path=ARQUIVO_SESSAO_OTRS)
        # confirma que gravou algo válido
        if not _sessao_valida(ARQUIVO_SESSAO_OTRS):
            logger.error('[OTRS] [SESSAO] Falha ao validar sessão recém-salva.')
    except Exception as e:
        logger.error('[OTRS] [SESSAO] Erro ao salvar cookies: %s', e)


def _fazer_login_otrs(page: Page) -> str:
    """Faz login no OTRS ou reaproveita a sessão injetada."""
    logger.info('[OTRS] [LOGIN] Acessando página inicial: %s', OTRS_URL_LOGIN)
    try:
        page.goto(OTRS_URL_LOGIN, wait_until='domcontentloaded', timeout=30_000)
        page.wait_for_timeout(2_000)
    except Exception as e:
        logger.error('[OTRS] [LOGIN] Falha ao acessar URL base: %s', e)

    titulo_atual = page.title()
    if 'Login' not in titulo_atual:
        logger.info('[OTRS] [LOGIN] Sessão reaproveitada via Cookies! Poupando OTRS de um novo login.')
        token = _extrair_token(page)
        if token:
            _salvar_sessao(page)
            return token

    for tentativa in range(1, 4):
        logger.info('[OTRS] [LOGIN] Tentativa manual %d/3...', tentativa)
        token = _tentar_login_uma_vez(page, tentativa)
        if token:
            logger.info('[OTRS] [LOGIN] Login bem-sucedido. Salvando cookies no disco.')
            _salvar_sessao(page)
            return token

        if tentativa < 3:
            logger.warning('[OTRS] [LOGIN] Tentativa %d falhou. Atualizando página...', tentativa)
            page.wait_for_timeout(5_000)
            try:
                page.goto(OTRS_URL_LOGIN, wait_until='domcontentloaded', timeout=30_000)
                page.wait_for_timeout(2_000)
            except Exception:
                pass

    logger.error('[OTRS] [LOGIN] Todas as tentativas falharam.')
    return ''


def _tentar_login_uma_vez(page: Page, tentativa: int) -> str:
    try:
        page.wait_for_selector('#User', state='visible', timeout=15_000)
    except PlaywrightTimeoutError:
        logger.error('[OTRS] [LOGIN] Campo #User não encontrado (tentativa %d).', tentativa)
        _salvar_screenshot(page, f'otrs_sem_campo_user_t{tentativa}.png')
        return ''

    logger.info('[OTRS] [LOGIN] Preenchendo credenciais...')
    campo_user = page.locator('#User')
    campo_pass = page.locator('#Password')

    campo_user.click()
    page.wait_for_timeout(300)
    campo_user.fill('')
    page.wait_for_timeout(200)
    campo_user.type(OTRS_USUARIO, delay=80)
    page.wait_for_timeout(400)

    campo_pass.click()
    page.wait_for_timeout(300)
    campo_pass.fill('')
    page.wait_for_timeout(200)
    campo_pass.type(OTRS_SENHA, delay=80)
    page.wait_for_timeout(800)

    page.evaluate("""
        var btn = document.getElementById('LoginButton');
        if (btn) {
            btn.removeAttribute('disabled');
            btn.classList.remove('Disabled');
        }
    """)
    page.wait_for_timeout(500)

    logger.info('[OTRS] [LOGIN] Clicando no botão...')

    try:
        page.locator('#LoginButton').click(force=True)
        page.wait_for_timeout(4_000)
    except Exception as e:
        logger.warning('[OTRS] [LOGIN] Aviso durante o clique: %s', e)

    url_atual    = page.url
    titulo_atual = page.title()
    logger.info('[OTRS] [LOGIN] Pós-login: URL=%s | Título=%s', url_atual, titulo_atual)

    if 'Login' in titulo_atual:
        try:
            msg = page.locator('.MessageBox.Error, .ErrorMessage, #LoginError').inner_text(timeout=3_000)
            logger.error('[OTRS] [LOGIN] Erro reportado pelo OTRS: "%s"', msg.strip())
        except Exception:
            logger.error('[OTRS] [LOGIN] Login recusado sem mensagem de erro visível.')
        _salvar_screenshot(page, f'otrs_login_falha_t{tentativa}.png')
        return ''

    token = _extrair_token(page)
    if not token:
        logger.error('[OTRS] [TOKEN] ChallengeToken não encontrado. URL: %s', page.url)
        _salvar_screenshot(page, f'otrs_sem_token_t{tentativa}.png')
    return token


# ── HELPERS DE PARSE ──────────────────────────────────────────
def _parse_data_otrs(texto: str):
    from datetime import datetime

    m = _RE_DATA_BR.search(texto)
    if m:
        dia, mes, ano, hora, minuto = m.groups()
        try:
            dt = datetime(int(ano), int(mes), int(dia), int(hora), int(minuto))
            return timezone.make_aware(dt)
        except ValueError:
            pass

    m = _RE_DATA_ISO.search(texto)
    if m:
        ano, mes, dia, hora, minuto = m.groups()
        try:
            dt = datetime(int(ano), int(mes), int(dia), int(hora), int(minuto))
            return timezone.make_aware(dt)
        except ValueError:
            pass
    return None


def _analisar_linha(celulas: list) -> dict:
    info = {
        'ticket':       None,
        'is_projetos':  False,
        'is_broker':    False,
        'is_fechado':   False,
        'data_criacao': None,
    }
    for celula in celulas:
        try:
            txt_orig = celula.inner_text().strip()
            txt      = txt_orig.lower()
        except Exception:
            continue
        if re.match(r'^\d{14,}$', txt_orig):
            info['ticket'] = txt_orig
        if 'projetos' in txt:
            info['is_projetos'] = True
        if 'arionbroker' in txt or 'arion broker' in txt:
            info['is_broker'] = True
        if txt in ESTADOS_FECHADOS:
            info['is_fechado'] = True
        if info['data_criacao'] is None:
            dt = _parse_data_otrs(txt_orig)
            if dt:
                info['data_criacao'] = dt
    return info


def _dentro_da_janela(info: dict, data_envio_email) -> bool:
    if not data_envio_email or not info['data_criacao']:
        return False
    inicio = data_envio_email - timedelta(hours=JANELA_HORAS_ANTES)
    fim    = data_envio_email + timedelta(hours=JANELA_HORAS_DEPOIS)
    return inicio <= info['data_criacao'] <= fim


def _dentro_do_limite_absoluto(info: dict, data_referencia) -> bool:
    if not info['data_criacao']:
        return False
    ref    = data_referencia if data_referencia else timezone.now()
    limite = ref - timedelta(days=JANELA_LIMITE_ABSOLUTO_DIAS)
    return info['data_criacao'] >= limite


# ── SELEÇÃO DE TICKET NA TABELA ───────────────────────────────
def _ticket_do_zoom(page: Page, rec_id: str) -> str | None:
    try:
        h1 = page.locator('div.Headline h1').inner_text(timeout=5_000)
        m  = re.search(r'Ticket#(\d{14,})', h1)
        if m:
            ticket = m.group(1)
            logger.info('[OTRS] [SUCESSO] REC %s -> Zoom direto -> Ticket %s', rec_id, ticket)
            return ticket
    except Exception as e:
        logger.debug('[OTRS] Erro ao ler Zoom H1: %s', e)
    return None


def _ticket_da_tabela(page: Page, rec_id: str, data_envio_email) -> str | None:
    try:
        page.wait_for_selector(
            '.TicketList table tbody tr, #EmptyMessageSmall',
            state='attached', timeout=15_000,
        )
        if page.locator('#EmptyMessageSmall').is_visible():
            logger.info('[OTRS] [BUSCA] Sem resultados para REC %s.', rec_id)
            return None
    except Exception:
        pass

    try:
        linhas = page.locator('.TicketList table tbody tr').all()
        if not linhas:
            linhas = page.locator('table.TableSmall tbody tr').all()

        logger.info('[OTRS] [BUSCA] %d linha(s) para REC %s.', len(linhas), rec_id)
        p1 = p2 = p3 = p4 = p5 = p6 = None

        for linha in linhas:
            celulas = linha.locator('td').all()
            if not celulas:
                continue
            info = _analisar_linha(celulas)
            if not info['ticket']:
                continue

            # Verifica se está na janela, ou se não tem data na tabela (Idade).
            # Se não tem data, assumimos que pode estar na janela (True).
            tem_data_valida = info['data_criacao'] is not None
            na_janela = _dentro_da_janela(info, data_envio_email) if tem_data_valida else True
            no_limite_abs = _dentro_do_limite_absoluto(info, data_envio_email) if tem_data_valida else True

            aberto        = not info['is_fechado']
            projetos      = info['is_projetos']
            broker        = info['is_broker']

            if projetos and broker and aberto and na_janela and not p1:
                p1 = info['ticket']
                break
            if projetos and aberto and na_janela and not p2:
                p2 = info['ticket']
            if aberto and na_janela and not p3:
                p3 = info['ticket']
            if projetos and aberto and no_limite_abs and not p4:
                p4 = info['ticket']
            if aberto and no_limite_abs and not p5:
                p5 = info['ticket']
            if no_limite_abs and not p6:
                p6 = info['ticket']

        resultado = p1 or p2 or p3 or p4 or p5 or p6
        if resultado:
            origem = (
                'P1:Projetos+Broker+Aberto' if resultado == p1 else
                'P2:Projetos+Aberto'        if resultado == p2 else
                'P3:Aberto'                 if resultado == p3 else
                'P4:Projetos+Aberto(Lim)'   if resultado == p4 else
                'P5:Aberto(Lim)'            if resultado == p5 else
                'P6:LimiteAbs'
            )
            logger.info('[OTRS] [SUCESSO] REC %s -> Ticket %s (%s)', rec_id, resultado, origem)
            return resultado

        logger.warning('[OTRS] [AVISO] Nenhum ticket válido para REC %s. Filtros reprovaram %d resultado(s).', rec_id, len(linhas))
    except Exception as e:
        logger.error('[OTRS] [ERRO] Tabela para REC %s: %s', rec_id, e)
    return None


# ── BUSCA INDIVIDUAL ──────────────────────────────────────────
def _buscar_ticket_por_rec(page: Page, rec, token: str) -> str | None:
    rec_id     = str(rec.rec_id)
    data_envio = getattr(rec, 'data_envio', None)
    url = (
        'https://suporte.grupoarion.com.br/otrs/index.pl'
        '?Action=AgentTicketSearch;Subaction=Search;SearchTemplate=Procurar'
        f';CheckTicketNumberAndRedirect=1;ChallengeToken={token}'
        f';Fulltext={quote(rec_id)}'
    )
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=25_000)
        page.wait_for_timeout(1_500)

        if 'AgentTicketZoom' in page.url:
            ticket = _ticket_do_zoom(page, rec_id)
            if ticket and data_envio:
                try:
                    criado_txt = page.locator('label:has-text("Criado:") + p').inner_text(timeout=3_000)
                    dt_criado  = _parse_data_otrs(criado_txt)
                    if dt_criado:
                        limite = data_envio - timedelta(days=JANELA_LIMITE_ABSOLUTO_DIAS)
                        fim    = data_envio + timedelta(hours=JANELA_HORAS_DEPOIS)
                        if not (limite <= dt_criado <= fim):
                            logger.warning('[OTRS] Ticket %s no Zoom fora do limite. Descartando.', ticket)
                            return None
                except Exception:
                    pass
            return ticket
        return _ticket_da_tabela(page, rec_id, data_envio)
    except PlaywrightTimeoutError:
        logger.warning('[OTRS] Timeout na busca da REC %s.', rec_id)
    except Exception as e:
        logger.error('[OTRS] Erro na busca da REC %s: %s', rec_id, e)
    return None


# ── ENTRADA PÚBLICA ───────────────────────────────────────────
def buscar_tickets_otrs(recs_pendentes: list) -> dict:
    if not recs_pendentes:
        return {}

    rec_ids = [str(r.rec_id) for r in recs_pendentes]
    logger.info('[OTRS] [START] Pipeline para %d REC(s): %s', len(rec_ids), rec_ids)
    encontrados: dict[str, str] = {}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )

            context_args = {
                'viewport': {'width': 1366, 'height': 900},
                'locale': 'pt-BR',
                'user_agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/123.0.0.0 Safari/537.36'
                )
            }

            # Injeta os cookies SOMENTE se o arquivo existir e for um JSON válido.
            # Isso evita o JSONDecodeError quando o arquivo está vazio/corrompido.
            if _sessao_valida(ARQUIVO_SESSAO_OTRS):
                context_args['storage_state'] = ARQUIVO_SESSAO_OTRS
                logger.info('[OTRS] [SESSAO] Cookies válidos encontrados. Reaproveitando sessão.')
            else:
                logger.info('[OTRS] [SESSAO] Nenhuma sessão válida encontrada. Login será feito do zero.')

            try:
                context = browser.new_context(**context_args)
            except Exception as e:
                # Proteção extra: se mesmo assim o storage_state falhar ao ser
                # carregado pelo Playwright, descarta o arquivo e tenta de novo
                # sem sessão, em vez de derrubar o ciclo inteiro.
                logger.error('[OTRS] [SESSAO] Falha ao criar contexto com storage_state (%s). '
                              'Descartando cookies e tentando sem sessão.', e)
                _remover_sessao_corrompida(ARQUIVO_SESSAO_OTRS)
                context_args.pop('storage_state', None)
                context = browser.new_context(**context_args)

            page = context.new_page()

            token = _fazer_login_otrs(page)

            if not token:
                logger.error('[OTRS] [FALHA FATAL] Não foi possível obter sessão válida. Abortando.')
            else:
                for rec in recs_pendentes:
                    ticket = _buscar_ticket_por_rec(page, rec, token)
                    if ticket:
                        encontrados[str(rec.rec_id)] = ticket

            context.close()
            browser.close()

    except Exception as e:
        logger.error('[OTRS] Erro na execução do Playwright: %s', e, exc_info=True)

    logger.info(
        '[OTRS] [RESUMO] Ciclo concluído — REC(s) registradas: %d / %d | Resultado: %s',
        len(encontrados), len(rec_ids), encontrados,
    )
    return encontrados


# ── CLEANUP (MANTIDO APENAS PARA COMPATIBILIDADE) ─────────────
def fechar_sessao_otrs():
    """Função vazia mantida para não quebrar o atexit do apps.py."""
    pass