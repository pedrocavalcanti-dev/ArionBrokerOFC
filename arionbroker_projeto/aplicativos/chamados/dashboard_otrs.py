"""Leitura do ATACADO com a sessão existente, sem login ou persistência.

O AJAX real do widget é a fonte preferencial. AgentKPISearch é o fallback
quando o widget não está habilitado para a sessão; também fornece TicketIDs
para deduplicar operadoras e os títulos usados pela regra existente de BRAD.
"""
import logging
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, parse_qs

from aplicativos.automacao.otrs_kpi_scraper import (
    OTRS_BASE, DASHBOARD_URL, BRAD_CLARO, BRAD_VIVO,
)

logger = logging.getLogger(__name__)

OTRS_ATACADO_KPIS = {
    'atacado_diversos': ('ATACADO DIVERSOS', '686_2'),
    'brad': ('BRAD', '613_2'),
    'correios': ('CORREIOS', '640_2'),
    'fust': ('FUST', '731_2'),
    'lan_to_lan': ('LAN-TO-LAN', '654_2'),
    'mc_donalds': ('MC DONALDS', '643_2'),
    'monitoramento_rreip': ('Monitoramento RREIP', '723_2'),
    'noc_atacado': ('NOC - ATACADO', '251_2'),
    'projeto_algar': ('PROJETO ALGAR', '701_2'),
    'projeto_bb': ('PROJETO BB', '655_2'),
    'projeto_carrefour': ('PROJETO CARREFOUR', '702_2'),
    'projeto_cef': ('PROJETO CEF', '682_2'),
    'reincidentes_30_dias': ('REINCIDENTES (30 dias)', '724_2'),
}

# Associações já presentes em views.py; BRAD é dividido pelo título do ticket.
PROJETOS = {
    'claro': [('brad_claro', 'Bradesco', 'brad'),
              ('correios', 'Correios', 'correios'),
              ('cef_claro', 'Caixa Econômica', 'projeto_cef'),
              ('bb_claro', 'Banco do Brasil', 'projeto_bb'),
              ('carrefour', 'Carrefour', 'projeto_carrefour'),
              ('div_claro', 'Diversos', 'atacado_diversos'),
              ('fust_claro', 'FUST', 'fust')],
    'vivo': [('brad_vivo', 'Bradesco', 'brad'),
             ('mcdonalds', "McDonald's", 'mc_donalds'),
             ('l2l', 'L2L (LAN-to-LAN)', 'lan_to_lan'),
             ('div_vivo', 'Diversos', None),
             ('fust_vivo', 'FUST', 'fust')],
    'algar': [('escolas', 'Escolas Conectadas', 'projeto_algar')],
}


def parse_ajax(payload):
    """Aceita somente Numeric/ID/Total, sem converter ausência em zero."""
    items = payload.get('JSON', []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return {}
    result = {}
    for item in items:
        if not isinstance(item, dict) or item.get('TypeKPI') != 'Numeric':
            continue
        value = item.get('Total')
        if isinstance(value, str) and re.fullmatch(r'\d+', value.strip()):
            value = int(value)
        if type(value) is int and value >= 0:
            result[item.get('ID')] = value
    return result


def _buscar_tickets(page, profile, token, incluir_cliente=False):
    """Só retorna uma busca completa; falha/página parcial nunca equivale a 0."""
    url = (f'{OTRS_BASE}?Action=AgentKPISearch;Subaction=Search'
           f';TakeLastSearch=1;Profile={profile};ChallengeToken={token}')
    tickets, visited = {}, set()
    expected = None
    for _ in range(100):
        if url in visited:
            raise ValueError('Paginação repetida')
        visited.add(url)
        response = page.goto(url, wait_until='domcontentloaded', timeout=20_000)
        if not response or response.status != 200 or page.locator('#User').count():
            raise ValueError('Busca indisponível')
        # OTRS redireciona buscas com exatamente um resultado para o ticket.
        destination = urlsplit(page.url.replace(';', '&'))
        params = parse_qs(destination.query)
        if params.get('Action') == ['AgentTicketZoom']:
            ticket_id = params.get('TicketID', [''])[0]
            if tickets or not ticket_id.isdigit() or destination.hostname != urlsplit(OTRS_BASE).hostname:
                raise ValueError('Redirecionamento de busca inválido')
            heading = page.locator('.Headline h1')
            if heading.count() != 1:
                raise ValueError('Título do resultado único ausente')
            title = heading.inner_text()
            if incluir_cliente:
                customer_id = page.locator('fieldset.TableLike label').evaluate_all("""(labels) => {
                    const label = labels.find(n => /^ID do Cliente:$/i.test(n.innerText.trim()));
                    return label?.nextElementSibling?.textContent.trim() || '';
                }""")
                return {ticket_id: {'titulo': title, 'cliente_id': customer_id}}
            return {ticket_id: title}
        pagination = ' '.join(page.locator('.Pagination').all_inner_texts())
        match = re.search(r'(?:de|of)\s+([\d.]+)', pagination, re.I)
        if match:
            count = int(match.group(1).replace('.', ''))
            if expected is not None and expected != count:
                raise ValueError('Total mudou durante paginação')
            expected = count
        if page.locator('#EmptyMessageSmall').count() and expected == 0:
            return {}
        if not page.locator('table.TableSmall').count():
            raise ValueError('Tabela ausente')
        for link in page.locator('table.TableSmall tbody a.MasterActionLink').all():
            href = link.get_attribute('href') or ''
            match = re.search(r'(?:[?;&])TicketID=(\d+)', href)
            if match:
                title = link.get_attribute('title') or link.inner_text()
                if incluir_cliente:
                    customer_id = link.evaluate("""(link) => {
                        const row = link.closest('tr');
                        const headers = Array.from(row.closest('table').querySelectorAll('thead th'));
                        const index = headers.findIndex(h => h.classList.contains('CustomerID')
                            || h.innerText.trim().toUpperCase() === 'ID DO CLIENTE');
                        return index >= 0 ? (row.cells[index]?.textContent.trim() || '') : '';
                    }""")
                    tickets[match.group(1)] = {'titulo': title, 'cliente_id': customer_id}
                else:
                    tickets[match.group(1)] = title
        next_link = page.locator('a[title="Próxima Página"], a[title="Next Page"]')
        if next_link.count() and next_link.first.is_visible():
            href = next_link.first.get_attribute('href')
            if not href:
                raise ValueError('Próxima página sem URL')
            next_url = urljoin(OTRS_BASE, href)
            if not next_url.startswith(OTRS_BASE + '?'):
                raise ValueError('Destino de paginação inválido')
            url = next_url
        else:
            if expected is None or len(tickets) != expected:
                raise ValueError('Busca incompleta ou sem total verificável')
            return tickets
    raise ValueError('Limite de paginação')


def coletar_atacado(page):
    response = page.goto(DASHBOARD_URL, wait_until='domcontentloaded', timeout=25_000)
    if not response or response.status != 200 or page.locator('#User').count():
        raise ValueError('Sessão OTRS expirada ou dashboard indisponível')
    logout = page.locator('.LogoutButton').first.get_attribute('href') or ''
    token_match = re.search(r'ChallengeToken=([^;&\s]+)', logout)
    if not token_match:
        raise ValueError('Sessão OTRS sem token disponível')
    token = token_match.group(1)
    logger.info('[OTRS DASHBOARD] Sessão reutilizada')
    logger.info('[OTRS DASHBOARD] Dashboard carregado')

    values = {}
    try:
        response = page.context.request.post(
            OTRS_BASE, form={'Action': 'KPIWidgetAJAXHandler', 'ChallengeToken': token},
            timeout=20_000,
        )
        if response.status == 200:
            values = parse_ajax(response.json())
    except Exception:
        logger.warning('[OTRS DASHBOARD] AJAX indisponível; usando buscas existentes')

    result = {}
    project_keys = {key for projects in PROJETOS.values() for _, _, key in projects if key}
    for key, (title, profile) in OTRS_ATACADO_KPIS.items():
        chart_id = 'NumericChart_' + profile
        value = values.get(chart_id)
        source = 'ajax' if value is not None else None
        tickets = None
        # Títulos e IDs são necessários para BRAD e totais sem sobreposição.
        if value is None or key in project_keys:
            try:
                if key == 'fust':
                    tickets = _buscar_tickets(page, profile, token, incluir_cliente=True)
                else:
                    tickets = _buscar_tickets(page, profile, token)
                if value is None:
                    value, source = len(tickets), 'busca'
                elif len(tickets) != value:
                    tickets = None  # snapshot mudou; não classificar uma parte do KPI
            except Exception as exc:
                # Exceções do Playwright podem conter URLs com ChallengeToken.
                logger.warning('[OTRS DASHBOARD] Busca não validada: %s (%s)',
                               title, type(exc).__name__)
        result[key] = {'id': key, 'nome': title, 'kpi_id': profile,
                       'chart_id': chart_id, 'valor': value,
                       'coletado_ok': value is not None, 'fonte': source,
                       'tickets': tickets}
        if value is None:
            logger.warning('[OTRS DASHBOARD] KPI não encontrado: %s', title)
        else:
            logger.info('[OTRS DASHBOARD] KPI encontrado: %s = %d', title, value)
    logger.info('[OTRS DASHBOARD] %d/%d KPIs ATACADO processados',
                sum(item['coletado_ok'] for item in result.values()),
                len(OTRS_ATACADO_KPIS))
    return result


def _operadora_fust(ticket):
    """CustomerID observado no OTRS tem prioridade; título é fallback.

    TELMEX/TELEFONICA preservam os padrões já comprovados em BRAD.
    CLARO/VIVO são marcas explícitas; conflito ou ausência fica em OUTROS.
    """
    if isinstance(ticket, str):
        ticket = {'titulo': ticket}
    for field in ('cliente_id', 'titulo'):
        text = unicodedata.normalize('NFKD', ticket.get(field) or '')
        text = ''.join(char for char in text if not unicodedata.combining(char)).upper()
        claro = bool(re.search(r'\b(?:CLARO|TELMEX)\b', text))
        vivo = bool(re.search(r'\b(?:VIVO|TELEFONICA)\b', text))
        if claro or vivo:
            return 'OUTROS' if claro and vivo else ('CLARO' if claro else 'VIVO')
    return 'OUTROS'


def normalizar_atacado(kpis):
    """Contrato público: não entrega títulos de tickets nem tokens ao frontend."""
    result = {}
    fust = kpis.get('fust', {})
    fust_tickets = fust.get('tickets')
    fust_ids = None
    if fust_tickets is not None and len(fust_tickets) == fust.get('valor'):
        fust_ids = {'CLARO': set(), 'VIVO': set(), 'OUTROS': set()}
        for tid, ticket in fust_tickets.items():
            fust_ids[_operadora_fust(ticket)].add(tid)
    for op, projects in PROJETOS.items():
        cards, ids, complete = [], set(), True
        for project_id, name, key in projects:
            kpi = kpis.get(key, {})
            value, tickets = kpi.get('valor'), kpi.get('tickets')
            if key == 'brad':
                if tickets is None:
                    value = None
                else:
                    tickets = {tid: title for tid, title in tickets.items()
                               if (BRAD_CLARO in title.upper() if op == 'claro'
                                   else BRAD_CLARO not in title.upper() and BRAD_VIVO in title.upper())}
                    value = len(tickets)
            elif key == 'fust':
                tickets = fust_ids[op.upper()] if fust_ids is not None else None
                value = len(tickets) if tickets is not None else None
            if key is not None:
                if tickets is None:
                    complete = False
                else:
                    ids.update(tickets)
            # Diversos Vivo não tinha fonte na API anterior: manter indisponível.
            cards.append({'id': project_id, 'nome': name, 'valor': value,
                          'kpi_id': kpi.get('kpi_id'), 'coletado_ok': value is not None})
        result[op] = {'total': len(ids) if complete else None,
                      'total_escopo': 'projetos_mapeados', 'projetos': cards}
    mapped = {key for projects in PROJETOS.values() for _, _, key in projects if key}
    mapped.update(('reincidentes_30_dias', 'noc_atacado'))
    result['atacado'] = {
        'total': kpis.get('noc_atacado', {}).get('valor'),
        'total_kpi_id': '251_2', 'total_escopo': 'NOC - ATACADO',
        'projetos': [{k: v for k, v in item.items() if k != 'tickets'}
                     for item in kpis.values()],
        'sem_correspondencia': [key for key in OTRS_ATACADO_KPIS if key not in mapped],
        'fust_por_operadora': ({op: len(ids) for op, ids in fust_ids.items()}
                              if fust_ids is not None else None),
    }
    result['total'] = result['total_em_aberto'] = result['atacado']['total']
    result['total_escopo'] = 'NOC - ATACADO'
    result['atualizado_em'] = datetime.now(timezone.utc).isoformat()
    result['parcial'] = (any(not item['coletado_ok'] for item in kpis.values())
                         or any(result[op]['total'] is None for op in PROJETOS))
    brad_tickets = kpis.get('brad', {}).get('tickets')
    result['atacado']['brad_por_operadora'] = None
    if brad_tickets is not None:
        claro = sum(BRAD_CLARO in title.upper() for title in brad_tickets.values())
        vivo = sum(BRAD_CLARO not in title.upper() and BRAD_VIVO in title.upper()
                   for title in brad_tickets.values())
        result['atacado']['brad_por_operadora'] = {
            'CLARO': claro, 'VIVO': vivo, 'OUTROS': len(brad_tickets) - claro - vivo,
        }
    return result


_lock = threading.Lock()
_snapshot = None
_expires = 0


def obter_dashboard_atacado():
    """Cache por processo, 60s. Nunca usa banco/cache persistente ou salva cookies."""
    global _snapshot, _expires
    from django.conf import settings
    from playwright.sync_api import sync_playwright

    with _lock:
        if _snapshot is not None and time.monotonic() < _expires:
            return _snapshot
        session = settings.BASE_DIR / 'otrs_cookies.json'
        if not session.is_file():
            raise ValueError('Sessão OTRS existente não encontrada')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(storage_state=str(session), locale='pt-BR')
                kpis = coletar_atacado(context.new_page())
                result = normalizar_atacado(kpis)
            finally:
                browser.close()
        _snapshot, _expires = result, time.monotonic() + 60
        return result
