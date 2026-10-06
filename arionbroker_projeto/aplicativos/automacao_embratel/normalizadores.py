"""
normalizadores.py

Responsável por transformar a resposta bruta da API do Modos Web (Embratel)
em dados padronizados e seguros para persistência no model TarefaEmbratel.

Não acessa banco de dados.
Não faz chamadas de API.
Não envia e-mails.
"""

import re
from decimal import Decimal
from typing import Any, Optional, Dict, List
from datetime import datetime, date

from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.conf import settings

from . import logs


def obter_valor_aninhado(dados: Any, caminho: str, padrao: Any = None) -> Any:
    """
    Navega em dicionários (e listas) através de um caminho separado por ponto.
    Retorna o valor ou o `padrao` se não encontrado / não for acessível.
    """
    if not isinstance(caminho, str) or not caminho:
        return padrao

    chaves = caminho.split('.')
    atual = dados

    try:
        for chave in chaves:
            if isinstance(atual, dict):
                atual = atual.get(chave)
            elif isinstance(atual, list) and chave.isdigit():
                atual = atual[int(chave)]
            else:
                return padrao

            if atual is None:
                return padrao
        return atual
    except (KeyError, TypeError, AttributeError, IndexError):
        return padrao


def limpar_texto(valor: Any) -> Optional[str]:
    """
    Converte para string e remove espaços extras.
    Bloqueia estritamente vazamento de dicionários e listas para a interface.
    """
    if valor is None or isinstance(valor, (dict, list)):
        return None

    texto = str(valor).strip()
    if not texto or texto.lower() == "none":
        return None

    # Substitui múltiplos espaços (na mesma linha) por um único espaço
    texto = re.sub(r'[ \t]+', ' ', texto)
    return texto


def normalizar_booleano(valor: Any) -> Optional[bool]:
    """
    Garante conversão segura de diferentes representações de booleanos.
    """
    if isinstance(valor, bool):
        return valor
    
    texto = limpar_texto(valor)
    if not texto:
        return None

    texto_lower = texto.lower()
    if texto_lower in ('1', 'true', 'sim', 'yes', 't', 'y', 's', 'ok'):
        return True
    if texto_lower in ('0', 'false', 'não', 'nao', 'no', 'f', 'n'):
        return False

    return None


def normalizar_inteiro(valor: Any) -> Optional[int]:
    """
    Converte valores numéricos e textos numéricos para inteiro com segurança.
    """
    if valor is None or isinstance(valor, (dict, list)):
        return None
    if isinstance(valor, int):
        return valor
    
    try:
        if isinstance(valor, str):
            # Lida com casos como "100,0" ou "100.0"
            valor = valor.replace(',', '.')
        return int(float(valor))
    except (ValueError, TypeError):
        return None


def normalizar_decimal_texto(valor: Any) -> Optional[str]:
    """
    Normaliza valores monetários para texto puro de forma previsível.
    """
    texto = limpar_texto(valor)
    if not texto:
        return None
    return texto


def normalizar_data_hora(valor: Any) -> Optional[datetime]:
    """
    Converte strings ISO, com ou sem timezone, para um objeto datetime compatível.
    """
    if not valor or isinstance(valor, (dict, list)):
        return None
    if isinstance(valor, datetime):
        data = valor
    elif isinstance(valor, date):
        data = datetime(valor.year, valor.month, valor.day)
    else:
        texto = limpar_texto(valor)
        if not texto:
            return None
        
        try:
            data = parse_datetime(texto)
            if not data:
                return None
        except (ValueError, TypeError):
            return None

    # Torna a data "aware" (com fuso horário) caso o Django espere
    if data and settings.USE_TZ and timezone.is_naive(data):
        data = timezone.make_aware(data, timezone.get_current_timezone())
        
    return data


def selecionar_tarefa_atual(tarefas: List[Dict]) -> Optional[Dict]:
    """
    Seleciona a tarefa aberta mais recente.
    Caso todas estejam finalizadas, seleciona a tarefa mais recente de todas.
    Ordenado por updated_at, created_at e id.
    """
    if not isinstance(tarefas, list):
        return None

    tarefas_validas = [
        tarefa
        for tarefa in tarefas
        if isinstance(tarefa, dict)
    ]

    if not tarefas_validas:
        return None

    def chave_ordenacao(tarefa: Dict):
        atualizado = str(tarefa.get("updated_at") or "")
        criado = str(tarefa.get("created_at") or "")
        tarefa_id = normalizar_inteiro(tarefa.get("id")) or 0
        return (atualizado, criado, tarefa_id)

    abertas = [
        tarefa
        for tarefa in tarefas_validas
        if not tarefa.get("finalized_at")
    ]

    candidatas = abertas if abertas else tarefas_validas
    candidatas.sort(key=chave_ordenacao, reverse=True)

    return candidatas[0]


def extrair_nome_status(tarefa: Dict) -> str:
    """Busca o nome do status em chaves comuns. Retorna '-' se não achar."""
    if not isinstance(tarefa, dict):
        return "-"

    opcoes = [
        obter_valor_aninhado(tarefa, "status.nome"),
        obter_valor_aninhado(tarefa, "status.name"),
        obter_valor_aninhado(tarefa, "status_portal"),
        obter_valor_aninhado(tarefa, "nome_status"),
        tarefa.get("status") if isinstance(tarefa.get("status"), str) else None
    ]
    
    for op in opcoes:
        texto = limpar_texto(op)
        if texto:
            return texto
    return "-"


def extrair_tipo_tarefa(tarefa: Dict) -> str:
    """Busca o tipo/nome da etapa da tarefa em chaves comuns. Retorna '-' se não achar."""
    if not isinstance(tarefa, dict):
        return "-"

    opcoes = [
        obter_valor_aninhado(tarefa, "ctrl_tarefa.nome"),
        obter_valor_aninhado(tarefa, "ctrl_tarefa.name"),
        tarefa.get("nome"),
        tarefa.get("tipo_tarefa"),
        tarefa.get("nomeEtapa"),
    ]
    
    for op in opcoes:
        texto = limpar_texto(op)
        if texto:
            return texto
    return "-"


def extrair_mapa_tarefa(tarefa: Dict) -> Optional[str]:
    """Busca o mapa (ex: 'DS102') em chaves comuns."""
    if not isinstance(tarefa, dict):
        return None

    opcoes = [
        obter_valor_aninhado(tarefa, "ctrl_tarefa.map"),
        obter_valor_aninhado(tarefa, "ctrl_tarefa.mapa"),
        tarefa.get("map"),
        tarefa.get("mapa"),
    ]
    
    for op in opcoes:
        texto = limpar_texto(op)
        if texto:
            return texto
    return None


def extrair_lista_workflows(resposta: Dict) -> List[Dict]:
    """
    Busca o array de workflows onde quer que ele esteja na resposta (paginada ou não).
    """
    if not isinstance(resposta, dict):
        return []

    lista_dados = obter_valor_aninhado(resposta, "data.data")
    if isinstance(lista_dados, list):
        return lista_dados

    lista_direta = resposta.get("data")
    if isinstance(lista_direta, list):
        return lista_direta

    return []


def extrair_paginacao(resposta: Dict) -> Dict:
    """
    Padroniza informações de paginação caso a API envie.
    """
    base = resposta.get("data") if isinstance(resposta.get("data"), dict) else resposta
    if not isinstance(base, dict):
        base = {}

    pagina_atual = normalizar_inteiro(base.get("current_page") or base.get("page")) or 1
    ultima_pagina = normalizar_inteiro(base.get("last_page")) or 1
    por_pagina = normalizar_inteiro(base.get("per_page")) or 20
    total = normalizar_inteiro(base.get("total")) or 0

    return {
        "pagina_atual": pagina_atual,
        "ultima_pagina": ultima_pagina,
        "por_pagina": por_pagina,
        "total": total,
        "tem_proxima": pagina_atual < ultima_pagina,
    }


def preparar_json_serializavel(valor: Any) -> Any:
    """
    Converte recursivamente objetos Python que não são serializáveis nativamente em JSON
    para estruturas seguras (strings, inteiros, floats, listas, dicionários).
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float, bool, str)):
        return valor
    if isinstance(valor, dict):
        return {str(k): preparar_json_serializavel(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [preparar_json_serializavel(v) for v in valor]
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    
    return str(valor)


def normalizar_workflow(workflow: Dict) -> Optional[Dict]:
    """
    Lê um workflow bruto e extrai exatamente as chaves necessárias
    para salvar em TarefaEmbratel, aplicando extração profunda segura
    para impedir dicionários stringificados (ex: "{'id': 1}").
    """
    if not isinstance(workflow, dict):
        return None

    tarefa_atual = selecionar_tarefa_atual(workflow.get("tarefas", [])) or {}
    prov = workflow.get("provedor_recuperacao") or {}
    ctrl_wf = workflow.get("ctrl_workflow") or {}

    # --- INÍCIO DA ZONA DE DIAGNÓSTICO ---
    # Logs desativados temporariamente para não poluir
    # logs.info("EMBRATEL-DEBUG", f"Chaves workflow: {list(workflow.keys())}")
    # logs.info("EMBRATEL-DEBUG", f"Chaves provedor_recuperacao: {list(prov.keys())}")
    # logs.info("EMBRATEL-DEBUG", f"Chaves tarefa: {list(tarefa_atual.keys())}")

    # Mapeamento pontual da chave interna de designação para corrigirmos a extração
    designacao_bruta = prov.get("designacao")
    if isinstance(designacao_bruta, dict):
        logs.info(
            "EMBRATEL-DEBUG",
            f"Chaves designacao: {list(designacao_bruta.keys())}"
        )
    # --- FIM DA ZONA DE DIAGNÓSTICO ---

    # 1. IDs e Identificadores
    id_portal = limpar_texto(tarefa_atual.get("id")) or limpar_texto(workflow.get("id"))
    if not id_portal:
        logs.aviso("EMBRATEL-API", "Workflow ignorado por falta de id_portal (id).")
        return None

    id_processo = normalizar_inteiro(tarefa_atual.get("pco_processo_id")) or normalizar_inteiro(workflow.get("pco_processo_id"))
    id_workflow = normalizar_inteiro(workflow.get("id")) or normalizar_inteiro(workflow.get("ctrl_workflow_id"))
    
    id_tarefa_anterior = normalizar_inteiro(tarefa_atual.get("pco_tarefa_anterior_id")) or normalizar_inteiro(tarefa_atual.get("tarefa_anterior_id"))

    # 2. Status e Classificações
    status_portal = extrair_nome_status(tarefa_atual)
    tipo_tarefa = extrair_tipo_tarefa(tarefa_atual)

    # 3. Informações de Negócio - Extração Profunda e Segura
    rec = limpar_texto(prov.get("rec")) or limpar_texto(prov.get("numero_rec")) or limpar_texto(workflow.get("rec"))
    cliente = limpar_texto(prov.get("cliente_final")) or limpar_texto(workflow.get("cliente_final")) or limpar_texto(workflow.get("cliente"))
    uf = limpar_texto(prov.get("uf")) or limpar_texto(workflow.get("uf"))
    gestor = limpar_texto(prov.get("gestor")) or limpar_texto(workflow.get("gestor")) or limpar_texto(prov.get("responsavel"))
    
    projeto = limpar_texto(workflow.get("projeto")) or limpar_texto(prov.get("projeto")) or limpar_texto(prov.get("holding"))
    
    provedor = limpar_texto(obter_valor_aninhado(prov, "provedor.nome")) or \
               limpar_texto(obter_valor_aninhado(prov, "provedor")) or \
               limpar_texto(obter_valor_aninhado(prov, "designacao.provedor"))

    designacao = limpar_texto(obter_valor_aninhado(prov, "designacao.nome")) or \
                 limpar_texto(obter_valor_aninhado(prov, "designacao.designacao")) or \
                 limpar_texto(prov.get("designacao"))

    circuito = limpar_texto(obter_valor_aninhado(prov, "designacao.circuito")) or \
               limpar_texto(prov.get("acesso_lp")) or \
               limpar_texto(workflow.get("circuito")) or \
               limpar_texto(prov.get("identificacao_acesso_provedor"))

    sintoma_completo = limpar_texto(workflow.get("sintoma")) or limpar_texto(prov.get("sintoma")) or limpar_texto(prov.get("descricao_problema"))
    sintoma = sintoma_completo[:255] if sintoma_completo else None

    desc_problema = limpar_texto(prov.get("descricao_problema"))
    obs = limpar_texto(prov.get("observacoes"))
    
    if desc_problema and obs and desc_problema != obs:
        descricao = f"Descrição: {desc_problema}\n\nObservações: {obs}"
    elif desc_problema:
        descricao = desc_problema
    else:
        descricao = obs

    # 4. Dados Técnicos (JSONField)
    dados_tecnicos_brutos = {
        "numero_rec": rec,
        "uf": uf,
        "gestor": gestor,
        "workflow_nome": limpar_texto(ctrl_wf.get("nome")) or limpar_texto(workflow.get("nome")),
        "identificacao_acesso_provedor": limpar_texto(prov.get("identificacao_acesso_provedor")),
        "observacoes": obs,
        "id_recuperacao": normalizar_inteiro(prov.get("id")),
        "id_book": limpar_texto(prov.get("id_book")),
        "holding": limpar_texto(prov.get("holding")),
        "acesso_lp": limpar_texto(prov.get("acesso_lp")),
        "valor_mensal": normalizar_decimal_texto(prov.get("valor_mensal")),
        "sla": limpar_texto(prov.get("sla")),
        "mapa_tarefa": extrair_mapa_tarefa(tarefa_atual),
        "ctrl_tarefa_id": normalizar_inteiro(tarefa_atual.get("ctrl_tarefa_id")),
        "pco_status_id": normalizar_inteiro(tarefa_atual.get("pco_status_id")),
        "usuario_tratamento": tarefa_atual.get("usuario_tratamento"),
        "tratamentos": tarefa_atual.get("tratamentos", []),
    }
    dados_tecnicos = preparar_json_serializavel(dados_tecnicos_brutos)

    # 5. Datas e SLAs
    data_criacao = normalizar_data_hora(tarefa_atual.get("created_at")) or \
                   normalizar_data_hora(workflow.get("created_at")) or \
                   normalizar_data_hora(prov.get("data_abertura_ticket"))
                   
    data_atualizacao = normalizar_data_hora(tarefa_atual.get("updated_at")) or \
                       normalizar_data_hora(workflow.get("updated_at"))
                       
    data_finalizacao = normalizar_data_hora(tarefa_atual.get("finalized_at"))

    dentro_sla = normalizar_booleano(workflow.get("dentro_sla"))
    
    # 6. Aging - Extração direta preservando None se não existir
    aging_minutos = normalizar_inteiro(tarefa_atual.get("aging"))
    if aging_minutos is None:
        aging_minutos = normalizar_inteiro(workflow.get("aging"))
    if aging_minutos is None:
        aging_minutos = normalizar_inteiro(workflow.get("aging_minutos"))

    url_tarefa = limpar_texto(workflow.get("url")) or limpar_texto(tarefa_atual.get("url"))

    return {
        "id_portal": str(id_portal),
        "id_processo": id_processo,
        "id_workflow": id_workflow,
        "id_tarefa_anterior": id_tarefa_anterior,
        "status_portal": status_portal,
        "tipo_tarefa": tipo_tarefa,
        "cliente": cliente,
        "provedor": provedor,
        "designacao": designacao,
        "circuito": circuito,
        "projeto": projeto,
        "sintoma": sintoma,
        "descricao": descricao,
        "dados_tecnicos": dados_tecnicos,
        "data_criacao_portal": data_criacao,
        "data_atualizacao_portal": data_atualizacao,
        "data_finalizacao_portal": data_finalizacao,
        "dentro_sla": dentro_sla,
        "aging_minutos": aging_minutos,
        "url_tarefa": url_tarefa,
    }


def normalizar_workflows(resposta: Dict) -> List[Dict]:
    """
    Orquestrador que processa a listagem da API de forma segura.
    Registra erros pontuais para não quebrar o lote inteiro.
    """
    lista_bruta = extrair_lista_workflows(resposta)
    normalizados = []

    for item in lista_bruta:
        try:
            workflow_limpo = normalizar_workflow(item)
            if workflow_limpo:
                normalizados.append(workflow_limpo)
        except Exception as e:
            item_id = item.get("id") if isinstance(item, dict) else "Desconhecido"
            logs.erro(
                "EMBRATEL-API", 
                f"Erro na normalização do workflow ID {item_id}: {str(e)}", 
                excecao=e
            )

    return normalizados