"""
Tasks Celery para automação de candidaturas.
Executam o Playwright em background para preencher formulários inHire.
"""

import os
import time
import logging
from datetime import datetime

from celery import current_task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# No Docker os módulos estão na raiz /app/, sem subpacote
from celery_app import celery_app
from models import CandidaturaModel, Base

logger = logging.getLogger(__name__)

# Database engine próprio para o worker (processo separado do FastAPI)
# Tenta a env var (Docker) primeiro, fallback para o config local
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    from config import settings as app_settings
    DATABASE_URL = app_settings.database_url
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionWorker = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _atualizar_status(candidatura_id: int, status: str, error_msg: str = None):
    """Atualiza o status de uma candidatura no banco de dados."""
    db = SessionWorker()
    try:
        cand = db.query(CandidaturaModel).filter(CandidaturaModel.id == candidatura_id).first()
        if cand:
            cand.status = status
            cand.updated_at = datetime.utcnow()
            if error_msg:
                cand.error_message = error_msg
            db.commit()
    except Exception as e:
        logger.error(f"Erro ao atualizar status da candidatura {candidatura_id}: {e}")
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def candidatar_inhire(self, candidatura_id: int, dados: dict, resume_path: str):
    """
    Task Celery: abre o navegador, preenche o formulário inHire e submete.

    Args:
        candidatura_id: ID do registro CandidaturaModel no banco
        dados: dict com os dados do candidato (nome, email, cpf, etc.)
        resume_path: caminho absoluto para o arquivo de currículo PDF
    """
    from playwright.sync_api import sync_playwright

    logger.info(f"[Candidatura {candidatura_id}] Iniciando task...")
    _atualizar_status(candidatura_id, "PROCESSING")

    # Obtém a URL do banco
    db = SessionWorker()
    try:
        cand = db.query(CandidaturaModel).filter(CandidaturaModel.id == candidatura_id).first()
        if not cand:
            logger.error(f"Candidatura {candidatura_id} não encontrada no banco.")
            _atualizar_status(candidatura_id, "ERROR", "Registro não encontrado")
            return {"status": "ERROR", "error": "Candidatura não encontrada"}
        url_vaga = cand.job_url
    finally:
        db.close()

    # Garante que o currículo existe
    if not os.path.isfile(resume_path):
        error = f"Arquivo de currículo não encontrado: {resume_path}"
        logger.error(f"[Candidatura {candidatura_id}] {error}")
        _atualizar_status(candidatura_id, "ERROR", error)
        return {"status": "ERROR", "error": error}

    # Atualiza o celery_task_id para rastreabilidade
    db = SessionWorker()
    try:
        cand = db.query(CandidaturaModel).filter(CandidaturaModel.id == candidatura_id).first()
        if cand and current_task:
            cand.celery_task_id = current_task.request.id
            db.commit()
    except Exception:
        pass
    finally:
        db.close()

    # --- Playwright: preenchimento do formulário ---
    logger.info(f"[Candidatura {candidatura_id}] Abrindo navegador para: {url_vaga}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # headless=True em produção
        page = browser.new_page()

        try:
            logger.info(f"[Candidatura {candidatura_id}] Navegando para URL...")
            page.goto(url_vaga, wait_until="domcontentloaded", timeout=80000)

            # --- DADOS PESSOAIS ---
            logger.info(f"[Candidatura {candidatura_id}] Preenchendo dados pessoais...")
            page.fill("input[name='name']", str(dados.get('nome', '')))
            page.fill("input[name='document.value']", str(dados.get('cpf', '')))
            page.fill("input[name='email']", str(dados.get('email', '')))
            page.fill("input[name='phone']", str(dados.get('telefone', '')))

            # LinkedIn (se existir)
            if dados.get('linkedin') and page.is_visible("input[name='linkedinUsername']"):
                page.fill("input[name='linkedinUsername']", str(dados.get('linkedin', '')))

            # --- PAÍS ---
            logger.info(f"[Candidatura {candidatura_id}] Selecionando país...")
            page.wait_for_selector("#country", state="visible")
            page.click("#country")
            page.wait_for_selector("[data-option-value='BR']", state="visible")
            page.click("[data-option-value='BR']")

            # --- CIDADE ---
            cidade_alvo = str(dados.get('cidade', 'São José - SC'))
            logger.info(f"[Candidatura {candidatura_id}] Pesquisando cidade: {cidade_alvo}")
            page.wait_for_selector("#districtBr", state="visible")
            page.click("#districtBr")
            time.sleep(0.5)

            input_pesquisa = "div[data-component-name='DropdownOptionsSearch'] input"
            page.wait_for_selector(input_pesquisa, state="visible")
            page.click(input_pesquisa)
            page.fill(input_pesquisa, cidade_alvo)
            time.sleep(0.2)

            seletor_opcao = f"button[data-component-name='DropdownOption'][data-option-value='{cidade_alvo}']"
            try:
                page.wait_for_selector(seletor_opcao, state="visible", timeout=1500)
                page.click(seletor_opcao)
                logger.info(f"[Candidatura {candidatura_id}] Cidade selecionada!")
            except Exception:
                logger.warning(f"[Candidatura {candidatura_id}] Opção exata não encontrada. Usando fallback...")
                primeira_opcao = "div[data-component-name='DropdownOptionsList'] button[data-component-name='DropdownOption']"
                page.wait_for_selector(primeira_opcao, state="visible")
                page.click(primeira_opcao)

            # --- MODELO DE TRABALHO (REMOTO) ---
            seletor_radio_remoto = "input[name='workModel'][value='true']"
            if page.is_visible(seletor_radio_remoto):
                page.locator(seletor_radio_remoto).click(force=True)

            # --- INDICAÇÃO (NÃO) ---
            seletor_radio_nao = "input[name='isIndication'][value='false']"
            if page.is_visible(seletor_radio_nao):
                page.check(seletor_radio_nao)

            # --- PRETENSÃO SALARIAL ---
            if page.is_visible("input[name='salaryExpectation']"):
                pretensao = str(dados.get('pretensao_salarial', ''))
                if pretensao:
                    page.click("input[name='salaryExpectation']")
                    page.type("input[name='salaryExpectation']", pretensao, delay=50)

            # --- UPLOAD CURRÍCULO ---
            seletor_curriculo = "input[type='file'][name='resume']"
            if page.locator(seletor_curriculo).count() > 0:
                logger.info(f"[Candidatura {candidatura_id}] Anexando currículo...")
                page.set_input_files(seletor_curriculo, resume_path)

            time.sleep(1)

            # --- ABA DIVERSIDADE ---
            seletor_aba_diversidade = "button[data-id='diversityForm'][data-disabled='false']"
            if page.locator(seletor_aba_diversidade).count() > 0:
                logger.info(f"[Candidatura {candidatura_id}] Avançando para Diversidade...")
                page.locator(seletor_aba_diversidade).click()
                time.sleep(1)

            # --- POLÍTICA DE PRIVACIDADE ---
            seletor_checkbox = "#privacyPolicy"
            if page.locator(seletor_checkbox).count() > 0:
                logger.info(f"[Candidatura {candidatura_id}] Aceitando política de privacidade...")
                page.eval_on_selector(
                    seletor_checkbox,
                    "el => { if (!el.checked) { el.click(); } }"
                )

            # --- SUBMETER (tenta múltiplos seletores) ---
            botoes_submeter = [
                "button[type='submit']:has-text('Continuar inscrição')",
                "button[type='submit']:has-text('Aplicar')",
                "button[type='submit']:has-text('Enviar')",
                "button[type='submit']:has-text('Candidatar')",
                "button[type='submit']:not([disabled])",
            ]
            botao_encontrado = None
            for seletor_botao_submeter in botoes_submeter:
                if page.locator(seletor_botao_submeter).count() > 0:
                    botao_encontrado = seletor_botao_submeter
                    break

            if botao_encontrado:
                logger.info(f"[Candidatura {candidatura_id}] Aguardando botão habilitar (seletor: {botao_encontrado})...")
                try:
                    page.wait_for_selector(
                        "button[type='submit']:not([disabled])",
                        state="visible",
                        timeout=15000
                    )
                    logger.info(f"[Candidatura {candidatura_id}] Enviando formulário...")
                    page.locator(botao_encontrado).click()
                    logger.info(f"[Candidatura {candidatura_id}] Formulário submetido!")
                except Exception:
                    # Se o botão submit padrão não funcionar, tenta clicar em qualquer botão tipo submit visível
                    logger.warning(f"[Candidatura {candidatura_id}] Tentando fallback: clicar no primeiro botão submit visível...")
                    botoes_submit_visiveis = page.locator("button[type='submit']:visible")
                    if botoes_submit_visiveis.count() > 0:
                        botoes_submit_visiveis.first.click()
                        logger.info(f"[Candidatura {candidatura_id}] Formulário submetido via fallback!")
            else:
                logger.warning(f"[Candidatura {candidatura_id}] Nenhum botão de submit encontrado.")

            logger.info(f"[Candidatura {candidatura_id}] Formulário enviado com sucesso!")
            _atualizar_status(candidatura_id, "SUCCESS")
            return {"status": "SUCCESS", "message": "Candidatura enviada com sucesso!"}

        except Exception as e:
            error_msg = f"Erro no preenchimento: {str(e)}"
            logger.error(f"[Candidatura {candidatura_id}] {error_msg}", exc_info=True)
            _atualizar_status(candidatura_id, "ERROR", error_msg)

            # Retenta se ainda houver tentativas (max_retries=2)
            # self.retry() levanta Retry exception que é capturada pelo Celery
            self.retry(exc=e)
            return {"status": "ERROR", "error": error_msg}

        finally:
            browser.close()

    return {"status": "SUCCESS", "message": "Candidatura enviada com sucesso!"}
