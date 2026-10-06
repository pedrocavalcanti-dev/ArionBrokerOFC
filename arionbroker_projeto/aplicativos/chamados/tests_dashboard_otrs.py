"""Regressões do dashboard; SimpleTestCase proíbe consultas reais ao banco."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, RequestFactory

from .dashboard_otrs import (
    OTRS_ATACADO_KPIS, OTRS_BASE, _buscar_tickets,
    coletar_atacado, normalizar_atacado, parse_ajax,
)


def snapshot():
    return {key: {'id': key, 'nome': title, 'kpi_id': profile,
                  'chart_id': 'NumericChart_' + profile, 'valor': 0,
                  'coletado_ok': True, 'fonte': 'busca', 'tickets': {}}
            for key, (title, profile) in OTRS_ATACADO_KPIS.items()}


class DashboardOtrsTests(SimpleTestCase):
    def test_reconhece_os_13_perfis_sem_wish(self):
        self.assertEqual({profile for _, profile in OTRS_ATACADO_KPIS.values()}, {
            '686_2', '613_2', '640_2', '731_2', '654_2', '643_2', '723_2',
            '251_2', '701_2', '655_2', '702_2', '682_2', '724_2',
        })
        self.assertEqual(len(OTRS_ATACADO_KPIS), 13)

    def ajax_page(self, omitted=None):
        page = MagicMock()
        page.goto.return_value = SimpleNamespace(status=200)
        page.locator.return_value.count.return_value = 0
        page.locator.return_value.first.get_attribute.return_value = '?ChallengeToken=test-token'
        items = [{'TypeKPI': 'Numeric', 'ID': 'NumericChart_' + profile, 'Total': 0}
                 for _, profile in OTRS_ATACADO_KPIS.values() if profile != omitted]
        # Mesmo que o OTRS continue retornando WISH, não entra no dashboard.
        items.append({'TypeKPI': 'Numeric', 'ID': 'NumericChart_652_2', 'Total': 99})
        page.context.request.post.return_value = SimpleNamespace(
            status=200, json=lambda: {'JSON': items})
        return page

    @patch('aplicativos.chamados.dashboard_otrs._buscar_tickets', return_value={})
    def test_coleta_sem_escrita_em_banco_e_sem_wish_no_json(self, search):
        # Sem mocks de models: SimpleTestCase rejeita qualquer acesso real ao banco.
        page = self.ajax_page()
        with self.assertLogs('aplicativos.chamados.dashboard_otrs', level='INFO') as logs:
            result = normalizar_atacado(coletar_atacado(page))
        self.assertTrue(any('13/13 KPIs ATACADO processados' in line for line in logs.output))
        self.assertFalse(result['parcial'])
        self.assertEqual(len(result['atacado']['projetos']), 13)
        self.assertEqual(result['atacado']['sem_correspondencia'], ['fust', 'monitoramento_rreip'])
        public_json = json.dumps(result).upper()
        for unwanted in ('GRUPO WISH', 'GRUPO_WISH', '652_2'):
            self.assertNotIn(unwanted, public_json)
        self.assertTrue(all(call.args[1] != '652_2' for call in search.call_args_list))
        self.assertEqual(page.context.request.post.call_args.kwargs['form']['Action'],
                         'KPIWidgetAJAXHandler')

    @patch('aplicativos.chamados.dashboard_otrs._buscar_tickets')
    def test_kpi_ausente_e_fallback_falho_sao_null_e_parcial(self, search):
        def tickets(page, profile, token):
            if profile == '731_2':
                raise ValueError('Busca indisponível')
            return {}
        search.side_effect = tickets
        result = normalizar_atacado(coletar_atacado(self.ajax_page(omitted='731_2')))
        fust = next(k for k in result['atacado']['projetos'] if k['id'] == 'fust')
        self.assertIsNone(fust['valor'])
        self.assertFalse(fust['coletado_ok'])
        self.assertTrue(result['parcial'])

    def test_ajax_distingue_zero_de_valor_ausente_ou_invalido(self):
        values = parse_ajax({'JSON': [
            {'TypeKPI': 'Numeric', 'ID': 'NumericChart_613_2', 'Total': '8'},
            {'TypeKPI': 'Numeric', 'ID': 'NumericChart_686_2', 'Total': 0},
            {'TypeKPI': 'Numeric', 'ID': 'missing'},
            {'TypeKPI': 'Numeric', 'ID': 'invalid', 'Total': -1},
            {'TypeKPI': 'Graphic', 'ID': 'gauge', 'Total': 19},
            {'TypeKPI': 'Numeric', 'ID': 'boolean', 'Total': True},
        ]})
        self.assertEqual(values, {'NumericChart_613_2': 8, 'NumericChart_686_2': 0})
        self.assertEqual(parse_ajax({'JSON': None}), {})

    def test_total_deduplicado_brad_dividido_e_metricas_separadas(self):
        kpis = snapshot()
        kpis['brad'].update(valor=3, tickets={
            '1': 'TELMEX link', '2': 'TELEFONICA link', '3': 'OUTRA OPERADORA',
        })
        kpis['correios'].update(valor=2, tickets={'1': 'mesmo chamado', '4': 'outro'})
        kpis['noc_atacado']['valor'] = 11
        kpis['monitoramento_rreip']['valor'] = 19
        kpis['reincidentes_30_dias']['valor'] = 8
        result = normalizar_atacado(kpis)
        self.assertEqual(result['claro']['total'], 2)  # não 1 + 2
        self.assertEqual(result['vivo']['total'], 1)
        self.assertEqual(result['total'], 11)  # não somar métricas sobrepostas
        self.assertEqual(result['total_em_aberto'], 11)
        self.assertEqual(result['atacado']['brad_por_operadora'],
                         {'CLARO': 1, 'VIVO': 1, 'OUTROS': 1})
        self.assertIsNone(result['vivo']['projetos'][-1]['valor'])
        self.assertEqual(len(result['atacado']['projetos']), 13)
        self.assertEqual(result['total_escopo'], 'NOC - ATACADO')
        self.assertNotIn('tickets', json.dumps(result))

    def test_falha_de_classificacao_nao_vira_zero(self):
        kpis = snapshot()
        kpis['brad'].update(valor=8, tickets=None)
        result = normalizar_atacado(kpis)
        self.assertIsNone(result['claro']['projetos'][0]['valor'])
        self.assertIsNone(result['vivo']['total'])
        self.assertTrue(result['parcial'])
        self.assertEqual(result['atacado']['projetos'][1]['valor'], 8)

    def search_page(self, pages):
        page = MagicMock()
        page.url = OTRS_BASE + '?Action=AgentKPISearch'
        state = {'index': -1}
        def goto(*args, **kwargs):
            state['index'] += 1
            return SimpleNamespace(status=200)
        def locator(selector):
            current = pages[state['index']]
            loc = MagicMock()
            loc.count.return_value = 0
            if selector == '.Pagination':
                loc.all_inner_texts.return_value = [current['pagination']]
            elif selector == 'table.TableSmall':
                loc.count.return_value = int(bool(current.get('tickets')))
            elif selector == '#EmptyMessageSmall':
                loc.count.return_value = int(current.get('empty', False))
            elif selector == 'table.TableSmall tbody a.MasterActionLink':
                links = []
                for tid in current.get('tickets', []):
                    link = MagicMock()
                    link.get_attribute.side_effect = lambda attr, tid=tid: (
                        f'?Action=AgentTicketZoom;TicketID={tid}' if attr == 'href' else 'TELMEX')
                    links.append(link)
                loc.all.return_value = links
            elif selector.startswith('a[title='):
                loc.count.return_value = int(bool(current.get('next')))
                loc.first.is_visible.return_value = True
                loc.first.get_attribute.return_value = current.get('next')
            return loc
        page.goto.side_effect = goto
        page.locator.side_effect = locator
        return page

    def test_busca_zero_confirmado_sem_tabela(self):
        page = self.search_page([{'pagination': '0-0 de 0', 'empty': True}])
        self.assertEqual(_buscar_tickets(page, '686_2', 'secret'), {})

    def test_busca_com_um_ticket_redireciona_para_zoom(self):
        page = MagicMock()
        page.url = OTRS_BASE + '?Action=AgentTicketZoom;TicketID=42'
        page.goto.return_value = SimpleNamespace(status=200)
        heading = MagicMock()
        heading.count.return_value = 1
        heading.inner_text.return_value = 'TELMEX link'
        login = MagicMock()
        login.count.return_value = 0
        page.locator.side_effect = lambda selector: login if selector == '#User' else heading
        self.assertEqual(_buscar_tickets(page, '613_2', 'secret'), {'42': 'TELMEX link'})

    def test_busca_paginada_e_deduplicada(self):
        page = self.search_page([
            {'pagination': '1-2 de 3', 'tickets': ['1', '2'],
             'next': OTRS_BASE + '?Action=AgentKPISearch;StartHit=3'},
            {'pagination': '3-3 de 3', 'tickets': ['3']},
        ])
        self.assertEqual(set(_buscar_tickets(page, '613_2', 'secret')), {'1', '2', '3'})

    def test_busca_parcial_ou_pagina_invalida_rejeitada(self):
        for search in ({'pagination': '1-2 de 3', 'tickets': ['1', '2']},
                       {'pagination': '', 'empty': True}):
            with self.subTest(search=search), self.assertRaises(ValueError):
                _buscar_tickets(self.search_page([search]), '613_2', 'secret')

    @patch('aplicativos.chamados.views.KpiOtrs')
    @patch('aplicativos.chamados.views.obter_dashboard_atacado')
    def test_api_preserva_sla_e_corrige_reincidencias(self, collect, model):
        from .views import api_dashboard_resumo
        kpis = snapshot()
        kpis['reincidentes_30_dias']['valor'] = 8
        kpis['monitoramento_rreip']['valor'] = 19
        collect.return_value = normalizar_atacado(kpis)
        def query(**kwargs):
            if 'grupo' in kwargs:
                return [SimpleNamespace(valor=2), SimpleNamespace(valor=3)]
            return SimpleNamespace(first=lambda: SimpleNamespace(valor=7))
        model.objects.filter.side_effect = query
        response = api_dashboard_resumo.__wrapped__(RequestFactory().get('/projetos/api/dashboard-resumo/'))
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['atrasados'], 5)
        self.assertEqual(data['outros']['projetos'][1]['valor'], 8)
        self.assertEqual(data['outros']['projetos'][1]['kpi_id'], '724_2')
        atacado = {k['id']: k for k in data['atacado']['projetos']}
        self.assertEqual(atacado['monitoramento_rreip']['kpi_id'], '723_2')
        self.assertEqual(atacado['monitoramento_rreip']['valor'], 19)
        self.assertEqual(atacado['reincidentes_30_dias']['kpi_id'], '724_2')
        self.assertEqual(atacado['reincidentes_30_dias']['valor'], 8)
        self.assertNotIn('GRUPO WISH', json.dumps(data))
        self.assertNotIn('resolvidos', data)  # fonte não existe na API original
        model.objects.update_or_create.assert_not_called()

    @patch('aplicativos.chamados.views.obter_dashboard_atacado')
    def test_erro_nao_expoe_token(self, collect):
        from .views import api_dashboard_resumo
        collect.side_effect = RuntimeError('URL;ChallengeToken=secret')
        response = api_dashboard_resumo.__wrapped__(RequestFactory().get('/projetos/api/dashboard-resumo/'))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'secret', response.content)
