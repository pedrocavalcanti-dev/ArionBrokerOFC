"""
ARION PROJETOS — BROKER
aplicativos/automacao/scraper.py
"""

import os
import json
import subprocess
import sys
import requests
import urllib3
from datetime import datetime
from zoneinfo import ZoneInfo
from decouple import config

from django.db import transaction
from aplicativos.core_broker.models import TicketREC, OrigemAcao
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── CONFIGURAÇÕES ─────────────────────────────────────────────
URL_LOGIN    = "https://nocclaro.com.br/pbroker/#/login"
URL_PORTAL   = "https://nocclaro.com.br/pbroker/#/"
API_LOGIN    = "https://nocclaro.com.br/Webservice/pbrokerApi/api/login"
API_RECS     = "https://nocclaro.com.br/Webservice/pbrokerApi/api/dashboard/total-recs?per_page=all"
API_LOGOUT   = "https://nocclaro.com.br/Webservice/pbrokerApi/api/logout"

USUARIO = config('SCRAPER_USUARIO')
SENHA   = config('SCRAPER_SENHA')

TZ_BRASIL = ZoneInfo("America/Sao_Paulo")

FORMATOS_DATA = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d",
]

TIMEOUT_ELEMENTO = 10_000

def _converter_data(valor: str | None) -> datetime | None:
    if not valor or not str(valor).strip():
        return None
    valor_limpo = str(valor).strip()
    for fmt in FORMATOS_DATA:
        try:
            dt_naive = datetime.strptime(valor_limpo, fmt)
            return dt_naive.replace(tzinfo=TZ_BRASIL)
        except ValueError:
            continue
    print(f"  [AVISO] Formato de data nao reconhecido: '{valor_limpo}'")
    return None

def _is_login_response(response) -> bool:
    try:
        return (
            response.request.method.upper() == "POST"
            and response.url.rstrip("/") == API_LOGIN.rstrip("/")
        )
    except Exception:
        return False

def _extrair_token_do_json(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("token"):
        return str(payload["token"]).strip()
    data = payload.get("data")
    if isinstance(data, dict):
        if data.get("token"):
            return str(data["token"]).strip()
        if data.get("access_token"):
            return str(data["access_token"]).strip()
    if payload.get("access_token"):
        return str(payload["access_token"]).strip()
    return None

def _fazer_login(page: Page) -> str:
    print("[SCRAPER] Acessando portal da Claro...")
    page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(1_500)

    print("[LOGIN] Preenchendo credenciais...")
    page.locator('input[type="email"], input[name="email"], input[type="text"]').first.fill(USUARIO)
    page.locator('input[type="password"]').first.fill(SENHA)

    with page.expect_response(_is_login_response, timeout=30_000) as login_info:
        page.locator(
            'button[type="submit"], button:has-text("Entrar"), button:has-text("Login")'
        ).first.click()

    login_response = login_info.value

    if login_response.status != 200:
        raise RuntimeError(f"Login retornou status {login_response.status}.")

    try:
        payload = login_response.json()
    except Exception:
        raise ValueError("Resposta do login nao e JSON valido.")

    token = _extrair_token_do_json(payload)
    if not token:
        raise ValueError("Login respondeu 200, mas o token nao foi encontrado no JSON.")

    print(f"[LOGIN] Token capturado: {token[:18]}...")
    page.wait_for_timeout(1_000)
    return token

def _fazer_logout(page: Page) -> None:
    print("[LOGOUT] Encerrando sessao via interface...")
    try:
        page.goto(URL_PORTAL, wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(1_000)
        logout_selector = (
            'button:has-text("Sair"), a:has-text("Sair"), '
            'button:has-text("Logout"), a:has-text("Logout"), '
            '[aria-label="Logout"], [title="Sair"]'
        )
        btn = page.locator(logout_selector).first
        if btn.is_visible(timeout=5_000):
            btn.click()
            page.wait_for_timeout(1_500)
            print("[LOGOUT] Sessao encerrada via interface com sucesso.")
        else:
             print("[LOGOUT] Botao de logout nao encontrado na interface.")
    except Exception as e:
        print(f"[LOGOUT] Nao foi possivel encerrar via interface: {e}")

def _buscar_recs_da_api(page: Page, token: str) -> list:
    """
    Usa o contexto do próprio Playwright (que já está autenticado e possui todos os
    cookies e headers corretos de navegador) para realizar a requisição GET na API.
    Isso evita o bloqueio (401 Unauthorized) que a Claro aplica a clientes HTTP puros (requests).
    """
    print(f"[SCRAPER] Chamando API via Playwright: {API_RECS}")
    
    # Injeta um script JavaScript no navegador para fazer a requisição fetch
    js_code = f"""
    async () => {{
        const response = await fetch('{API_RECS}', {{
            method: 'GET',
            headers: {{
                'Authorization': 'Bearer {token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }}
        }});
        if (!response.ok) {{
            throw new Error(`HTTP Error: ${{response.status}}`);
        }}
        return await response.json();
    }}
    """
    
    try:
        # Executa o código JS dentro da página do portal
        data = page.evaluate(js_code)
        
        if isinstance(data, dict):
            recs_list = data.get("rows", data.get("chamados", []))
        else:
            recs_list = data
            
        print(f"[API] Total de RECs recebidas via Playwright: {len(recs_list)}")
        return recs_list
        
    except Exception as e:
        error_msg = str(e)
        print(f"[API] Falha ao buscar dados via Playwright: {error_msg}")
        if "HTTP Error: 401" in error_msg:
            raise PermissionError("Token invalido ou expirado (401 Unauthorized) mesmo usando o navegador.")
        raise ConnectionError(f"Erro na API de RECs (Playwright): {error_msg}")


def _pegar_sintoma_completo(page: Page, rec_id: str) -> str:
    try:
        print(f"  [LAPIS] Abrindo detalhe da REC {rec_id}...")
        linha = page.locator(f'tr:has-text("{rec_id}")').first
        if not linha.is_visible(timeout=TIMEOUT_ELEMENTO):
            return ""

        btn_editar = linha.locator(
            'button[title*="dit"], button[aria-label*="dit"], button.btn-edit, '
            'button:has(svg), a[title*="edit"], a[title*="Editar"], '
            'button:has-text("Editar"), i.fa-pencil, i.fa-edit'
        ).first

        if not btn_editar.is_visible(timeout=5_000):
            return ""

        btn_editar.click()
        modal = page.locator('.modal, [role="dialog"], .modal-content, .v-dialog').first
        modal.wait_for(state="visible", timeout=TIMEOUT_ELEMENTO)

        sintoma_texto = ""
        candidatos = [
            'textarea[name*="sintoma"]', 'textarea[placeholder*="sintoma"]',
            '[class*="sintoma"] textarea', '[class*="sintoma"] p', '[class*="sintoma"] span',
            'label:has-text("Sintoma") + *', 'label:has-text("Sintoma") ~ *',
            'td:has-text("Sintoma") + td',
        ]

        for seletor in candidatos:
            try:
                el = modal.locator(seletor).first
                if el.is_visible(timeout=2_000):
                    sintoma_texto = (el.input_value() if el.evaluate("e => e.tagName") == "TEXTAREA" else el.inner_text()).strip()
                    if sintoma_texto:
                        break
            except Exception:
                continue

        if sintoma_texto:
            print(f"  [LAPIS] Sintoma capturado ({len(sintoma_texto)} chars).") 
        else:
            print(f"  [LAPIS] Sintoma nao encontrado na REC {rec_id}.")

        try:
            btn_fechar = modal.locator(
                'button:has-text("Fechar"), button:has-text("Cancelar"), '
                'button[aria-label="Close"], button.close, .modal-close'
            ).first
            if btn_fechar.is_visible(timeout=3_000):
                btn_fechar.click()
            else:
                page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            page.keyboard.press("Escape")

        return sintoma_texto

    except Exception as e:
        print(f"  [LAPIS] Erro na REC {rec_id}: {e}")
        return ""

def _coletar_dados_novos(
    recs_list: list,
    page: Page,
    ids_existentes: set,
    chamados_existentes: dict,
    origem: str,
    executor: str,
) -> tuple[list, list, int, list]:
    novos_dados = []
    atualizacoes = []
    ignoradas = 0
    erros = []

    for item in recs_list:
        try:
            rec_id = str(item.get("num_recup", "")).strip()
            if not rec_id:
                continue

            chamado_api = str(item.get("chamado_operadora", "") or "").strip()

            if rec_id in ids_existentes:
                chamado_salvo = str(chamados_existentes.get(rec_id, "") or "").strip()
                if chamado_api and chamado_api != chamado_salvo:
                    atualizacoes.append({
                        "rec_id": rec_id,
                        "chamado_operadora": chamado_api,
                    })
                    print(f"  [^] CHAMADO NOVO: REC {rec_id} -> {chamado_api}")
                else:
                    ignoradas += 1
                continue

            sintoma_api = item.get("sintoma", "") or ""
            sintoma_completo = _pegar_sintoma_completo(page, rec_id)
            sintoma_final = sintoma_completo or sintoma_api

            dados_rec = {
                "rec_id":                  rec_id,
                "designacao_claro":        item.get("designacao", "") or "",
                "bl_dados":                item.get("designacao_operadora", "") or "",
                "cliente":                 item.get("cliente", "") or "",
                "status_interface":        item.get("host_interface_status", "") or "",
                "status_equip":            item.get("status", "") or "",
                "sintoma":                 sintoma_final,
                "data_abertura_portal":    _converter_data(item.get("data_abertura")),
                "data_registro_operadora": _converter_data(item.get("dh_registro_operadora")),
                "data_atualizacao_portal": _converter_data(item.get("atualizacao")),
                "chamado_operadora":       chamado_api,
                "origem_coleta":           origem,
                "coletado_por":            executor,
            }

            novos_dados.append(dados_rec)
            ids_existentes.add(rec_id)

        except Exception as item_erro:
            msg = f"Erro ao processar item {item.get('num_recup', '?')}: {item_erro}"
            erros.append(msg)
            print(f"  [ERRO] {msg}")

    return novos_dados, atualizacoes, ignoradas, erros


def _salvar_recs_no_banco(novos_dados: list, atualizacoes: list) -> int:
    from aplicativos.core_broker.models import StatusEnvio

    print(f"\n[BANCO] Salvando {len(novos_dados)} novas RECs...")
    novas = 0

    for dados in novos_dados:
        try:
            with transaction.atomic():
                obj, criado = TicketREC.criar_ou_ignorar(dados)
                
            if criado:
                novas += 1
                tem_chamado = "com chamado" if obj.tem_chamado_arion else "sem chamado"
                data_abertura = dados.get('data_abertura_portal')
                print(
                    f"  [+] SALVA: REC {obj.rec_id} - "
                    f"Projeto: {obj.projeto} | {tem_chamado} | "
                    f"Abertura: {data_abertura or '-'} | "
                    f"Sintoma: {'sim' if dados.get('sintoma') else 'nao'} | "
                    f"Origem: {dados.get('origem_coleta')} | "
                    f"Por: {dados.get('coletado_por')}"
                )
        except Exception as e:
            print(f"  [ERRO] Falha ao salvar REC {dados.get('rec_id')} (pode ser duplicidade em andamento): {e}")

    if atualizacoes:
        print(f"[BANCO] Atualizando chamado de {len(atualizacoes)} REC(s)...")
        for upd in atualizacoes:
            try:
                with transaction.atomic():
                    TicketREC.objects.filter(rec_id=upd["rec_id"]).update(
                        chamado_operadora=upd["chamado_operadora"],
                        status_envio=StatusEnvio.REGISTRADO
                    )
                print(f"  [^] ATUALIZADA E FINALIZADA: REC {upd['rec_id']} -> {upd['chamado_operadora']}")
            except Exception as e:
                print(f"  [ERRO] Falha ao atualizar chamado da REC {upd['rec_id']}: {e}")

    return novas


def executar_scraper(origem: str = OrigemAcao.AUTOMATICA, executor: str = 'robo') -> dict:
    print(f"[SCRAPER] Iniciando - origem={origem} | executor={executor}")
    print("[SCRAPER] Carregando cache de IDs do banco de dados...")

    ids_existentes = set(TicketREC.objects.values_list('rec_id', flat=True))
    chamados_existentes = dict(
        TicketREC.objects.filter(rec_id__in=ids_existentes)
        .values_list('rec_id', 'chamado_operadora')
    )

    novos_dados = []
    atualizacoes = []
    ignoradas = 0
    erros = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                locale="pt-BR",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                token = _fazer_login(page)
                
                # Usar o contexto da página do Playwright para bater na API,
                # garantindo que todos os cookies e headers da sessão sejam passados.
                recs_list = _buscar_recs_da_api(page, token)

                novos_dados, atualizacoes, ignoradas, erros_coleta = _coletar_dados_novos(
                    recs_list, page, ids_existentes, chamados_existentes,
                    origem=origem,
                    executor=executor,
                )
                erros.extend(erros_coleta)

            finally:
                try:
                    if 'token' in locals() and token:
                        _fazer_logout(page)
                except Exception as logout_err:
                    print(f"[LOGOUT] Erro nao critico no logout: {logout_err}")
                finally:
                    browser.close()
                    print("[SCRAPER] Navegador fechado com seguranca.")

    except Exception as e:
        print(f"\n[ERRO CRITICO] Processo do Playwright interrompido: {e}")
        erros.append(str(e))
        raise

    novas_salvas = _salvar_recs_no_banco(novos_dados, atualizacoes)

    print(
        f"\n[SCRAPER] [OK] Concluido - "
        f"Novas Salvas: {novas_salvas} | "
        f"Atualizadas: {len(atualizacoes)} | "
        f"Ignoradas: {ignoradas} | "
        f"Erros: {len(erros)}"
    )

    return {
        "novas":     novas_salvas,
        "ignoradas": ignoradas,
        "erros":     erros,
    }