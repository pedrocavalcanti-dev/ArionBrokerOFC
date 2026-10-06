"""
rodar_robo_embratel.py

Management command do Django para executar o scheduler da automação Embratel.
Pode ser executado em modo contínuo (padrão) ou uma única vez (--once).
Desenvolvido para ser acionado externamente via Cron, Agendador de Tarefas do Windows,
ou rodar como serviço em background.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import close_old_connections

from ... import logs
from ...scheduler import (
    executar_scheduler_uma_vez,
    obter_status_scheduler,
)
from ...models import ConfiguracaoRoboEmbratel


class Command(BaseCommand):
    help = "Executa o scheduler da automação Embratel (modo contínuo ou único)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Executa apenas um ciclo e encerra.'
        )
        parser.add_argument(
            '--intervalo',
            type=int,
            help='Intervalo de espera entre os ciclos em segundos (sobrescreve o banco).'
        )
        parser.add_argument(
            '--forcar',
            action='store_true',
            help='Ignora o intervalo de tempo e tenta executar imediatamente (respeitando pausa e concorrência).'
        )
        parser.add_argument(
            '--processar-emails',
            action='store_true',
            help='Executa a coleta e força o processamento de e-mails no mesmo ciclo.'
        )
        parser.add_argument(
            '--somente-coleta',
            action='store_true',
            help='Executa apenas a coleta, sem disparar o envio de e-mails neste ciclo.'
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Retorna o status atual do scheduler sem executar a coleta ou envio.'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Retorna o resultado em formato JSON limpo (útil para integrações e scripts).'
        )
        parser.add_argument(
            '--silencioso',
            action='store_true',
            help='Não imprime saída em caso de sucesso ou estado controlado. Apenas exibe falhas.'
        )
        parser.add_argument(
            '--falhar-se-nao-executar',
            action='store_true',
            help='Lança erro (Exit Code 1) se o robô não executar (ex: fora do intervalo, pausado, etc).'
        )

    def handle(self, *args, **options):
        # 1. Extração de Opções
        is_once = options['once']
        intervalo_arg = options['intervalo']
        forcar = options['forcar']
        opt_processar = options['processar_emails']
        opt_somente = options['somente_coleta']
        is_status = options['status']
        is_json = options['json']
        is_silencioso = options['silencioso']
        falhar_se_nao_executar = options['falhar_se_nao_executar']

        try:
            # 2. Validação de Argumentos Conflitantes
            if opt_processar and opt_somente:
                self._gerar_erro_validacao(
                    "Use apenas uma opção entre --processar-emails e --somente-coleta.",
                    "ARGUMENTOS_INVALIDOS",
                    is_json
                )
            
            if is_status and (forcar or opt_processar or opt_somente):
                self._gerar_erro_validacao(
                    "A opção --status não pode ser combinada com opções de execução.",
                    "ARGUMENTOS_INVALIDOS",
                    is_json
                )

            # 3. Modo Status (Sai Imediatamente)
            if is_status:
                status_info = obter_status_scheduler()
                if is_json:
                    self._escrever_json(status_info)
                elif not is_silencioso:
                    self._imprimir_status_humano(status_info)
                return

            # 4. Modo Execução (Contínuo ou Único)
            processar_emails = None
            if opt_processar:
                processar_emails = True
            elif opt_somente:
                processar_emails = False

            if not is_json and not is_silencioso:
                modo_str = "ÚNICA (--once)" if is_once else "CONTÍNUO"
                self.stdout.write(self.style.SUCCESS(f"\n[EMBRATEL-COMMAND] Iniciado em modo: {modo_str}"))

            logs.info("EMBRATEL-COMMAND", f"Management command rodar_robo_embratel iniciado (Modo: {'Unico' if is_once else 'Continuo'}).")

            ciclo = 1

            while True:
                # Renova a conexão com o banco de dados a cada iteração do loop para evitar expiração
                close_old_connections()
                
                intervalo_segundos = self._obter_intervalo_segundos(intervalo_arg)

                if not is_json and not is_silencioso and not is_once:
                    self.stdout.write(self.style.WARNING(f"\n--- INICIANDO CICLO {ciclo} ---"))

                try:
                    resultado = executar_scheduler_uma_vez(
                        forcar=forcar,
                        processar_emails=processar_emails
                    )

                    if not isinstance(resultado, dict):
                        raise CommandError("O retorno do scheduler não é um dicionário válido.")

                    sucesso = bool(resultado.get("sucesso"))
                    executado = bool(resultado.get("executado"))

                    # Formatação da Saída
                    if is_json:
                        self._escrever_json(resultado)
                    elif not is_silencioso or not sucesso:
                        self._imprimir_resultado_humano(resultado)

                    # Avaliação de Falhas e Erros
                    if not sucesso:
                        msg_erro = self._limitar_mensagem(resultado.get("erro") or resultado.get("mensagem") or "Falha desconhecida.")
                        logs.erro("EMBRATEL-COMMAND", f"Erro no ciclo {ciclo}: {msg_erro}")
                        
                        # Se for --once, a falha derruba o script. Se for contínuo, apenas loga e aguarda o próximo ciclo.
                        if is_once:
                            raise CommandError(f"Falha na execução: {msg_erro}")

                    # Regra de falha forçada (geralmente usada em Cron/scripts que esperam Exit Code 1)
                    if not executado and falhar_se_nao_executar:
                        motivo = resultado.get("mensagem", "Motivo desconhecido.")
                        raise CommandError(f"Execução pulada e --falhar-se-nao-executar está ativo. Motivo: {motivo}")

                except CommandError:
                    raise  # Repassa o erro crítico para interromper
                except Exception as e:
                    msg_erro = self._limitar_mensagem(str(e))
                    logs.erro("EMBRATEL-COMMAND", f"Exceção inesperada no ciclo {ciclo}.", e)
                    if is_once:
                        raise CommandError(f"Falha inesperada no comando: {msg_erro}")

                # Limpa conexões após a rotina pesada
                close_old_connections()

                # Quebra o loop se for execução única
                if is_once:
                    break
                
                # Aguarda o próximo ciclo
                proxima_execucao = timezone.now() + timedelta(seconds=intervalo_segundos)
                
                if not is_json and not is_silencioso:
                    self.stdout.write(self.style.NOTICE(f"[EMBRATEL-COMMAND] Ciclo {ciclo} concluído. Próxima execução em {intervalo_segundos}s (aprox. {proxima_execucao.strftime('%H:%M:%S')})."))
                
                time.sleep(intervalo_segundos)
                ciclo += 1

        except CommandError:
            raise

        except KeyboardInterrupt:
            if not is_json:
                self.stdout.write(self.style.WARNING("\n[EMBRATEL-COMMAND] Comando interrompido manualmente (Ctrl+C). Encerrando com segurança..."))
            logs.info("EMBRATEL-COMMAND", "Solicitação de encerramento recebida via Ctrl+C. Saindo do loop.")
            # Encerra de forma limpa (exit code 0), a não ser que seja lançado um erro
            return

        except Exception as e:
            msg_erro = self._limitar_mensagem(str(e))
            logs.erro("EMBRATEL-COMMAND", "Falha crítica que interrompeu o management command.", e)
            
            if is_json:
                self._escrever_json({
                    "sucesso": False,
                    "executado": False,
                    "codigo": "ERRO_CRITICO",
                    "mensagem": "Ocorreu um erro interno fatal no script.",
                    "erro": msg_erro,
                    "dados": None
                })
            raise CommandError("Falha crítica no comando. Verifique os logs internos.")

    # ══════════════════════════════════════════════════════════════
    #  MÉTODOS AUXILIARES
    # ══════════════════════════════════════════════════════════════

    def _obter_intervalo_segundos(self, intervalo_arg: Optional[int]) -> int:
        """Determina o intervalo respeitando a precedência: Argumento -> Banco -> Fallback."""
        if intervalo_arg and intervalo_arg > 0:
            return intervalo_arg
        
        try:
            config = ConfiguracaoRoboEmbratel.obter()
            if config.intervalo_minutos and config.intervalo_minutos > 0:
                return config.intervalo_minutos * 60
        except Exception as e:
            logs.aviso("EMBRATEL-COMMAND", f"Não foi possível ler intervalo do banco, usando fallback 300s. Erro: {e}")
            
        return 300

    def _escrever_json(self, dados: Dict[str, Any]) -> None:
        """Escreve um dicionário no stdout como JSON puro."""
        self.stdout.write(
            json.dumps(
                dados,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

    def _gerar_erro_validacao(self, mensagem: str, codigo: str, is_json: bool) -> None:
        """Centraliza o retorno de validação falha para texto ou JSON antes de lançar o erro crítico."""
        if is_json:
            self._escrever_json({
                "sucesso": False,
                "executado": False,
                "codigo": codigo,
                "mensagem": mensagem
            })
        raise CommandError(mensagem)

    def _limitar_mensagem(self, valor: Any, limite: int = 500) -> str:
        """Limpa e restringe o tamanho de strings de erro para o terminal."""
        if not valor:
            return ""
        texto = str(valor).replace("\r", "").replace("\n", " ").strip()
        return f"{texto[:limite]}..." if len(texto) > limite else texto

    def _formatar_data_hora(self, valor: Any) -> str:
        """Converte datas em strings legíveis e seguras."""
        if not valor:
            return "—"
        if isinstance(valor, datetime):
            try:
                local_dt = timezone.localtime(valor)
                return local_dt.strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                return str(valor)
        if isinstance(valor, str):
            try:
                dt = datetime.fromisoformat(valor)
                local_dt = timezone.localtime(dt)
                return local_dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                return valor
        return str(valor)

    def _imprimir_status_humano(self, st: Dict[str, Any]) -> None:
        """Exibe o dump de informações do scheduler."""
        self.stdout.write(self.style.SUCCESS("\nStatus do scheduler Embratel\n"))
        
        ativo_sch = "Sim" if st.get("scheduler_ativo") else "Não"
        ativo_rob = "Sim" if st.get("robo_ativo") else "Não"
        andamento = "Sim" if st.get("execucao_em_andamento") else "Não"
        pode_exec = "Sim" if st.get("pode_executar") else "Não"

        self.stdout.write(f"Scheduler ativo: {ativo_sch}")
        self.stdout.write(f"Robô ativo: {ativo_rob}")
        self.stdout.write(f"Execução em andamento: {andamento}")
        self.stdout.write(f"Intervalo: {st.get('intervalo_minutos', '—')} minutos")
        self.stdout.write(f"Última execução: {self._formatar_data_hora(st.get('ultima_execucao'))}")
        self.stdout.write(f"Próxima execução: {self._formatar_data_hora(st.get('proxima_execucao'))}")
        self.stdout.write(f"Tempo restante: {st.get('segundos_restantes', '—')} segundos")
        self.stdout.write(f"Pode executar agora: {pode_exec}")
        self.stdout.write(f"Código: {st.get('codigo', '—')}\n")

    def _imprimir_resultado_humano(self, res: Dict[str, Any]) -> None:
        """Exibe o desfecho de uma chamada de execução em texto amigável."""
        sucesso = res.get("sucesso")
        executado = res.get("executado")
        codigo = res.get("codigo", "—")
        mensagem = res.get("mensagem", "—")
        dados = res.get("dados") or {}

        estilo_aviso = self.style.WARNING

        if sucesso and executado:
            self.stdout.write(self.style.SUCCESS("  [EMBRATEL] Ciclo executado com sucesso."))
            self.stdout.write(f"  Código: {codigo}")
            self._imprimir_resumo_coleta(dados)
            self._imprimir_resumo_emails(dados)

        elif sucesso and not executado:
            if codigo == "ROBO_PAUSADO":
                self.stdout.write(estilo_aviso("  [EMBRATEL] Robô pausado."))
            else:
                self.stdout.write(estilo_aviso(f"  [EMBRATEL] Execução ignorada: {mensagem}"))
            self.stdout.write(f"  Código: {codigo}")

        else:
            self.stdout.write(self.style.ERROR("  [EMBRATEL] Falha na execução."))
            self.stdout.write(f"  Código: {codigo}")
            erro = res.get("erro") or mensagem
            self.stdout.write(f"  Mensagem: {self._limitar_mensagem(erro)}")

    def _imprimir_resumo_coleta(self, dados: Dict[str, Any]) -> None:
        """Analisa o DTO e exibe a parte de coleta de forma amigável."""
        coleta = dados.get("coleta", {}).get("dados", {}) if "coleta" in dados else dados

        enc = coleta.get("tarefas_encontradas")
        novas = coleta.get("tarefas_novas")
        atu = coleta.get("tarefas_atualizadas")
        ign = coleta.get("tarefas_ignoradas")

        if enc is not None:
            self.stdout.write(f"  Coleta: concluída (Encontradas: {enc} | Novas: {novas} | Atualizadas: {atu} | Ignoradas: {ign})")

    def _imprimir_resumo_emails(self, dados: Dict[str, Any]) -> None:
        """Analisa o DTO e exibe a parte de e-mails de forma amigável."""
        if "emails" not in dados:
            return
            
        emails_dto = dados.get("emails")
        if not emails_dto:
            self.stdout.write("  E-mails: não processados")
            return
            
        em = emails_dto.get("dados", {})
        proc = em.get("processadas")
        env = em.get("enviadas")
        rev = em.get("revisao")
        ign = em.get("ignoradas")

        if proc is not None:
            self.stdout.write(f"  E-mails: (Processados: {proc} | Enviados: {env} | Para Revisão: {rev} | Ignorados: {ign})")