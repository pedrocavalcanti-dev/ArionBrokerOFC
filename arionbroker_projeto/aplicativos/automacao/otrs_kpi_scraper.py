"""
ARION PROJETOS — BROKER
aplicativos/automacao/otrs_kpi_scraper.py

Scraper de KPIs do OTRS.
Reutiliza a sessão/login do otrs_scraper.py existente.

Fluxo a cada ciclo (1 minuto):
  1. Abre o dashboard do OTRS e extrai o DataJSON inline
     (lista de todos os KPIs com seus IDs e títulos)
  2. Filtra APENAS os KPIs necessários para o Dashboard do Broker
  3. Para cada KPI do tipo "Numeric", acessa a URL de busca
     AgentKPISearch e conta quantos tickets aparecem
  4. Para o BRAD (profile 613_2), além de contar o total,
     lê o título de cada ticket:
       - "TELEFONICA" no título → VIVO
       - "TELMEX"     no título → CLARO
       - outros                → OUTROS
  5. Salva/atualiza o modelo KpiOtrs no banco
"""

import re
import json
import logging

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# ── CONSTANTES ────────────────────────────────────────────────

OTRS_BASE = 'https://suporte.grupoarion.com.br/otrs/index.pl'
DASHBOARD_URL = OTRS_BASE + '?Action=AgentDashboard'

# URL do dashboard KPI (página separada, mais leve)
KPI_WIDGET_URL = OTRS_BASE + '?Action=AgentKPIWidget'

# Perfis de busca que correspondem a cada KPI
# Formato: "NumericChart_{profile_id}_{group_id}" → profile = "{profile_id}_{group_id}"
_RE_NUMERIC_ID = re.compile(r'^(?:NumericChart|GaugeChart)_(\d+)_(\d+)$')

# KPI especial: BRAD — precisa classificar por operadora
BRAD_PROFILE = '613_2'

# Filtro rigoroso: Apenas os KPIs que interessam ao Broker
PERFIS_DESEJADOS = {
    '613_2', '640_2', '654_2', '643_2',
    '701_2', '655_2', '702_2', '682_2', '686_2', '251_2',
    '185_2', '723_2',
}

# Palavras-chave no TÍTULO do ticket para classificar BRAD
BRAD_VIVO   = 'TELEFONICA'
BRAD_CLARO  = 'TELMEX'

# Mapeamento de grupos (GroupingHeader h1) para nome amigável
# Extraído dinamicamente do HTML, mas fallback aqui
_GRUPOS_CONHECIDOS = {
    '2':  'PROJETOS',
    '4':  'POOL DE ATENDIMENTO',
    '17': 'SITES POP (PONTO DE PRESENÇA)',
    '38': 'CENTRAL DE SERVIÇOS',
    '45': 'SITES NÃO GEOGRÁFICOS',
    '58': 'CANCELAMENTOS',
    '81': 'CHAMADOS POR GESTORES +4D',
}


# ── EXTRAÇÃO DO DataJSON ──────────────────────────────────────

def _extrair_data_json(page: Page) -> list:
    """
    Extrai o array DataJSON que o OTRS embute inline no HTML do dashboard.
    Retorna lista de dicts: [{TypeKPI, ID, Title, Valid, ...}, ...]
    """
    html = page.content()
    m = re.search(r'var DataJSON\s*=\s*(\[.*?\]);', html, re.DOTALL)
    if not m:
        logger.warning('[KPI] DataJSON não encontrado no HTML.')
        return []
    try:
        data = json.loads(m.group(1))
        logger.info('[KPI] DataJSON extraído: %d itens', len(data))
        return data
    except json.JSONDecodeError as e:
        logger.error('[KPI] Erro ao parsear DataJSON: %s', e)
        return []


def _extrair_grupos_do_html(page: Page) -> dict:
    """
    Lê o HTML do dashboard e monta um dicionário group_id → nome_grupo.
    Usa os h1 de GroupingHeader associados aos NumericChart IDs dos filhos.
    """
    html = page.content()
    grupos = {}

    # Abordagem mais confiável: pegar group_id do ID do NumericChart
    # O sufixo "_GID" no ID já carrega o group_id
    for chart_id_full in re.findall(r'NumericChart_\d+_(\d+)', html):
        if chart_id_full not in grupos:
            grupos[chart_id_full] = _GRUPOS_CONHECIDOS.get(chart_id_full, f'GRUPO_{chart_id_full}')

    return grupos


# ── CONTAGEM DE TICKETS ───────────────────────────────────────

def _contar_tickets_kpi(page: Page, profile: str, token: str) -> int:
    """
    Acessa a URL de busca KPI e retorna o total de tickets listados.
    Lê o texto "X-Y de Z" para pegar Z sem precisar iterar todas as páginas.
    """
    url = (
        f'{OTRS_BASE}?Action=AgentKPISearch;Subaction=Search'
        f';TakeLastSearch=1;Profile={profile}'
        f';ChallengeToken={token}'
    )
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=20_000)
        page.wait_for_timeout(800)

        # Tenta ler o texto de paginação "1-25 de 47"
        try:
            pag_text = page.locator('.Pagination').inner_text(timeout=4_000).strip()
            m = re.search(r'de\s+(\d+)', pag_text)
            if m:
                total = int(m.group(1))
                logger.debug('[KPI] Profile=%s → %d tickets (paginação)', profile, total)
                return total
        except Exception:
            pass

        # Fallback: conta as linhas da tabela
        linhas = page.locator('table.TableSmall tbody tr').count()
        # Verifica se existe mensagem de "nenhum resultado"
        if linhas == 0:
            return 0

        # Se tem uma linha com "EmptyMessageSmall", é zero
        try:
            empty = page.locator('#EmptyMessageSmall').is_visible()
            if empty:
                return 0
        except Exception:
            pass

        logger.debug('[KPI] Profile=%s → %d tickets (contagem de linhas)', profile, linhas)
        return linhas

    except PlaywrightTimeoutError:
        logger.warning('[KPI] Timeout na busca do profile=%s', profile)
        return -1
    except Exception as e:
        logger.error('[KPI] Erro ao contar tickets do profile=%s: %s', profile, e)
        return -1


def _classificar_brad(page: Page, token: str) -> dict:
    """
    Acessa a busca BRAD (profile 613_2), lê os títulos dos tickets
    e classifica por operadora: CLARO (TELMEX) / VIVO (TELEFONICA) / OUTROS.
    Retorna dict: {'CLARO': N, 'VIVO': N, 'OUTROS': N, 'total': N}
    """
    url = (
        f'{OTRS_BASE}?Action=AgentKPISearch;Subaction=Search'
        f';TakeLastSearch=1;Profile={BRAD_PROFILE}'
        f';ChallengeToken={token}'
    )
    resultado = {'CLARO': 0, 'VIVO': 0, 'OUTROS': 0, 'total': 0}

    try:
        page.goto(url, wait_until='domcontentloaded', timeout=20_000)
        page.wait_for_timeout(800)

        # Paginação — precisa navegar todas as páginas para classificar 100%
        pagina = 1
        while True:
            linhas = page.locator('table.TableSmall tbody tr').all()
            for linha in linhas:
                try:
                    # O título fica no atributo title do link MasterActionLink
                    link = linha.locator('a.MasterActionLink')
                    titulo = link.get_attribute('title') or ''
                    titulo_upper = titulo.upper()

                    if BRAD_CLARO in titulo_upper:
                        resultado['CLARO'] += 1
                    elif BRAD_VIVO in titulo_upper:
                        resultado['VIVO'] += 1
                    else:
                        resultado['OUTROS'] += 1

                    resultado['total'] += 1
                except Exception:
                    continue

            # Verifica se existe próxima página
            try:
                prox = page.locator('a[title="Próxima Página"], a[title="Next Page"]')
                if prox.count() > 0 and prox.is_visible():
                    prox.click()
                    page.wait_for_timeout(800)
                    pagina += 1
                    if pagina > 20:  # Segurança
                        break
                else:
                    break
            except Exception:
                break

        logger.info(
            '[KPI] BRAD classificado: CLARO=%d VIVO=%d OUTROS=%d total=%d',
            resultado['CLARO'], resultado['VIVO'], resultado['OUTROS'], resultado['total']
        )

    except Exception as e:
        logger.error('[KPI] Erro ao classificar BRAD: %s', e)

    return resultado


# ── ENTRADA PÚBLICA ───────────────────────────────────────────

def coletar_kpis_otrs(page: Page, token: str) -> list:
    """
    Função principal chamada pelo scheduler.
    Recebe uma página já autenticada e o ChallengeToken.

    Retorna lista de dicts prontos para salvar no banco:
    [
        {
            'kpi_id': '613_2',
            'titulo': 'BRAD',
            'grupo': 'PROJETOS',
            'valor': 5,
            'brad_por_operadora': {'CLARO': 2, 'VIVO': 3, 'OUTROS': 0},
        },
        ...
    ]
    """
    logger.info('[KPI] Iniciando coleta de KPIs...')

    # 1. Acessa o dashboard para extrair DataJSON
    try:
        page.goto(DASHBOARD_URL, wait_until='domcontentloaded', timeout=25_000)
        page.wait_for_timeout(1_500)
    except Exception as e:
        logger.error('[KPI] Falha ao acessar dashboard: %s', e)
        return []

    data_json = _extrair_data_json(page)
    if not data_json:
        logger.error('[KPI] Sem DataJSON, abortando coleta de KPIs.')
        return []

    grupos_map = _extrair_grupos_do_html(page)

    # 2. Para cada KPI do tipo Numeric, acessa e conta
    resultados = []
    for item in data_json:
        if not item.get('Valid', 0):
            continue

        tipo = item.get('TypeKPI', '')
        chart_id = item.get('ID', '')
        titulo = item.get('Title', '')

        # Extrai profile da busca a partir do ID do chart
        m = _RE_NUMERIC_ID.match(chart_id)
        if not m:
            continue

        profile_num = m.group(1)
        group_num   = m.group(2)
        profile     = f'{profile_num}_{group_num}'
        
        # 🛑 REGRA NOVA: Ignora os KPIs de outras filas/projetos não listados
        if profile not in PERFIS_DESEJADOS:
            continue

        grupo = grupos_map.get(group_num, _GRUPOS_CONHECIDOS.get(group_num, f'GRUPO_{group_num}'))

        logger.info('[KPI] Coletando: %s (profile=%s, grupo=%s)', titulo, profile, grupo)

        # Caso especial: BRAD — classificar por operadora
        if profile == BRAD_PROFILE:
            brad_result = _classificar_brad(page, token)
            resultados.append({
                'kpi_id':             profile,
                'titulo':             titulo,
                'grupo':              grupo,
                'valor':              brad_result['total'],
                'brad_por_operadora': brad_result,
                'coletado_ok':        brad_result['total'] >= 0,
            })
        else:
            # KPI normal — só conta
            if tipo == 'Graphic':
                # GaugeChart: pula por enquanto (precisa de lógica diferente)
                continue

            total = _contar_tickets_kpi(page, profile, token)
            resultados.append({
                'kpi_id':             profile,
                'titulo':             titulo,
                'grupo':              grupo,
                'valor':              max(total, 0),
                'brad_por_operadora': {},
                'coletado_ok':        total >= 0,
            })

    logger.info('[KPI] Coleta concluída: %d KPIs processados', len(resultados))
    return resultados


def rodar_pipeline_kpi():
    """
    Pipeline completo de KPIs: abre browser → login → coleta → salva.
    Chamado diretamente pelo scheduler (job_atualizar_kpis).
    Reutiliza os cookies do otrs_scraper.py (otrs_cookies.json).
    """
    import os
    from playwright.sync_api import sync_playwright

    # Import tardio para evitar circular import
    from aplicativos.automacao.otrs_scraper import (
        ARQUIVO_SESSAO_OTRS,
        _fazer_login_otrs,
    )

    logger.info('[KPI PIPELINE] Iniciando...')

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
                ),
            }

            if os.path.exists(ARQUIVO_SESSAO_OTRS):
                context_args['storage_state'] = ARQUIVO_SESSAO_OTRS

            context = browser.new_context(**context_args)
            page    = context.new_page()

            token = _fazer_login_otrs(page)

            if not token:
                logger.error('[KPI PIPELINE] Sem token. Abortando.')
                context.close()
                browser.close()
                return

            resultados = coletar_kpis_otrs(page, token)

            context.close()
            browser.close()

        if resultados:
            salvos = salvar_kpis(resultados)
            logger.info('[KPI PIPELINE] Concluído: %d KPIs salvos.', salvos)
        else:
            logger.warning('[KPI PIPELINE] Nenhum KPI coletado.')

    except Exception as e:
        logger.error('[KPI PIPELINE] Erro crítico: %s', e, exc_info=True)


def salvar_kpis(resultados: list) -> int:
    """
    Salva/atualiza os KPIs no banco.
    Importa o model aqui para não criar dependência circular no topo do arquivo.
    Retorna quantidade de registros salvos.
    """
    # Import tardio para evitar problema com Django não configurado
    from aplicativos.chamados.models import KpiOtrs

    salvos = 0
    for item in resultados:
        try:
            obj, criado = KpiOtrs.objects.update_or_create(
                kpi_id=item['kpi_id'],
                defaults={
                    'titulo':             item['titulo'],
                    'grupo':              item['grupo'],
                    'valor':              item['valor'],
                    'brad_por_operadora': item.get('brad_por_operadora', {}),
                    'coletado_ok':        item.get('coletado_ok', True),
                }
            )
            salvos += 1
            acao = 'CRIADO' if criado else 'ATUALIZADO'
            logger.debug('[KPI] %s: %s = %d', acao, item['titulo'], item['valor'])
        except Exception as e:
            logger.error('[KPI] Erro ao salvar KPI %s: %s', item.get('titulo'), e)

    logger.info('[KPI] %d/%d KPIs salvos no banco.', salvos, len(resultados))
    return salvos