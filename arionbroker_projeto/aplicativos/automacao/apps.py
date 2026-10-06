import os
import sys
import atexit
import traceback

from django.apps import AppConfig
from decouple import config


class AutomacaoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aplicativos.automacao"
    verbose_name = "Automação"

    # Mantém a trava viva enquanto o processo estiver rodando
    scheduler_lock_file = None

    # Evita tentar iniciar duas vezes dentro do MESMO processo
    scheduler_iniciado = False

    def ready(self):

        # =========================================================
        # 1. NAO INICIA EM COMANDOS DE MANUTENCAO
        # =========================================================

        executavel = os.path.basename(sys.argv[0]).lower()

        comando = ""
        if len(sys.argv) > 1:
            comando = sys.argv[1].lower()

        comandos_bloqueados = {
            "collectstatic",
            "migrate",
            "makemigrations",
            "shell",
            "check",
            "createsuperuser",
            "test",
        }

        if "gerenciar.py" in executavel and comando in comandos_bloqueados:

            print(
                f"[DEV] Scheduler nao iniciado durante comando: {comando}",
                flush=True,
            )

            return


        # =========================================================
        # 2. VERIFICA RODA_AUTOMACAO
        # =========================================================

        roda_automacao = config(
            "RODA_AUTOMACAO",
            default=False,
            cast=bool,
        )

        print(
            f"[AUTOMACAO] PID {os.getpid()} | "
            f"RODA_AUTOMACAO={roda_automacao}",
            flush=True,
        )

        if not roda_automacao:

            print(
                "[AUTOMACAO] Automacao DESABILITADA neste processo.",
                flush=True,
            )

            return


        # =========================================================
        # 3. EVITA DUPLICAR DENTRO DO MESMO PROCESSO
        # =========================================================

        if AutomacaoConfig.scheduler_iniciado:

            print(
                f"[AUTOMACAO] Scheduler ja iniciado neste PID "
                f"({os.getpid()}). Ignorando segunda inicializacao.",
                flush=True,
            )

            return


        # =========================================================
        # 4. ARQUIVO DE LOCK
        # =========================================================

        lock_file_path = os.path.join(
            os.environ.get("TEMP", "/tmp"),
            "arion_scheduler.lock",
        )

        lock_file = None


        try:

            # -----------------------------------------------------
            # Abre sem truncar o arquivo
            # -----------------------------------------------------

            lock_file = open(lock_file_path, "a+b")


            # -----------------------------------------------------
            # Garante que exista pelo menos 1 byte
            # -----------------------------------------------------

            lock_file.seek(0, os.SEEK_END)

            if lock_file.tell() == 0:

                lock_file.write(b"0")
                lock_file.flush()

            lock_file.seek(0)


            # =====================================================
            # WINDOWS
            # =====================================================

            if os.name == "nt":

                import msvcrt

                msvcrt.locking(
                    lock_file.fileno(),
                    msvcrt.LK_NBLCK,
                    1,
                )


            # =====================================================
            # LINUX
            # =====================================================

            else:

                import fcntl

                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )


            # =====================================================
            # PROCESSO ELEITO
            # =====================================================

            AutomacaoConfig.scheduler_lock_file = lock_file

            print(
                "",
                flush=True,
            )

            print(
                "============================================================",
                flush=True,
            )

            print(
                f"[SCHEDULER] PID {os.getpid()} ELEITO COMO PRINCIPAL",
                flush=True,
            )

            print(
                "============================================================",
                flush=True,
            )

            print(
                "",
                flush=True,
            )


        except (IOError, OSError):

            if lock_file:

                try:
                    lock_file.close()
                except Exception:
                    pass

            print(
                f"[SCHEDULER] Outro processo ja possui a trava. "
                f"PID atual: {os.getpid()}",
                flush=True,
            )

            return


        # =========================================================
        # 5. FUNCAO PARA LIBERAR A TRAVA
        # =========================================================

        def liberar_scheduler_lock():

            arquivo = AutomacaoConfig.scheduler_lock_file

            if arquivo is None:
                return

            try:

                arquivo.seek(0)

                if os.name == "nt":

                    import msvcrt

                    try:
                        msvcrt.locking(
                            arquivo.fileno(),
                            msvcrt.LK_UNLCK,
                            1,
                        )
                    except Exception:
                        pass

                else:

                    import fcntl

                    try:
                        fcntl.flock(
                            arquivo.fileno(),
                            fcntl.LOCK_UN,
                        )
                    except Exception:
                        pass


            finally:

                try:
                    arquivo.close()
                except Exception:
                    pass

                AutomacaoConfig.scheduler_lock_file = None

                try:
                    if os.path.exists(lock_file_path):
                        os.remove(lock_file_path)
                except Exception:
                    pass


        # =========================================================
        # 6. INICIA O SCHEDULER DE VERDADE
        # =========================================================

        try:

            print(
                "[SCHEDULER] Carregando scheduler...",
                flush=True,
            )

            from aplicativos.automacao.scheduler import iniciar_scheduler


            print(
                "[SCHEDULER] Iniciando tarefas...",
                flush=True,
            )


            # =====================================================
            # ESSA LINHA ESTAVA FALTANDO NO SEU CODIGO
            # =====================================================

            iniciar_scheduler()


            # Marca somente DEPOIS de iniciar com sucesso
            AutomacaoConfig.scheduler_iniciado = True


            print(
                "[SCHEDULER] Scheduler iniciado com sucesso.",
                flush=True,
            )


        except Exception as erro:

            print(
                "",
                flush=True,
            )

            print(
                "============================================================",
                flush=True,
            )

            print(
                "[ERRO] FALHA AO INICIAR O SCHEDULER",
                flush=True,
            )

            print(
                "============================================================",
                flush=True,
            )

            print(
                f"Erro: {erro}",
                flush=True,
            )

            print(
                "",
                flush=True,
            )

            traceback.print_exc()

            liberar_scheduler_lock()

            return


        # =========================================================
        # 7. ENCERRAMENTO OTRS
        # =========================================================

        try:

            from aplicativos.automacao.otrs_scraper import (
                fechar_sessao_otrs,
            )

            atexit.register(fechar_sessao_otrs)

        except Exception as erro:

            print(
                f"[OTRS] Aviso ao registrar encerramento: {erro}",
                flush=True,
            )


        # =========================================================
        # 8. LIBERA LOCK QUANDO O PYTHON ENCERRAR
        # =========================================================

        atexit.register(liberar_scheduler_lock)