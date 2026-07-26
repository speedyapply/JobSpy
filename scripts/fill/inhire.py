import time
import sys
import argparse
import yaml
import logging
from playwright.sync_api import sync_playwright

# Configuração de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def ler_dados_candidato(caminho_dados):
    with open(caminho_dados, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def preencher_formulario_inhire(url_vaga, dados, caminho_curriculo):
    logger.info("Iniciando navegador...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            logger.info(f"Navegando para: {url_vaga}")
            page.goto(url_vaga, wait_until="domcontentloaded", timeout=80000)

            logger.info("Preenchendo dados pessoais...")
            page.fill("input[name='name']", str(dados.get('nome', '')))
            page.fill("input[name='document.value']", str(dados.get('cpf', '')))
            page.fill("input[name='email']", str(dados.get('email', '')))
            page.fill("input[name='phone']", str(dados.get('telefone', '')))
            
            if page.is_visible("input[name='linkedinUsername']"):
                page.fill("input[name='linkedinUsername']", str(dados.get('linkedin', '')))

            # 1. Clicar no dropdown de País
            logger.info("Selecionando País...")
            page.wait_for_selector("#country", state="visible")
            page.click("#country")
            page.wait_for_selector("[data-option-value='BR']", state="visible")
            page.click("[data-option-value='BR']")

            # 2. Seleção Dinâmica de Cidade
            cidade_alvo = str(dados.get('cidade', 'São José - SC'))
            logger.info(f"Pesquisando cidade: {cidade_alvo}")
            page.wait_for_selector("#districtBr", state="visible")
            page.click("#districtBr")
            time.sleep(0.5)
            
            # Seletor exato do input de pesquisa pelo componente do inHire
            input_pesquisa = "div[data-component-name='DropdownOptionsSearch'] input"
            page.wait_for_selector(input_pesquisa, state="visible")
            page.click(input_pesquisa)
            page.fill(input_pesquisa, cidade_alvo)

            # Aguarda 500ms para a lista re-renderizar com o filtro
            time.sleep(0.2)

            # 3. Clicar no botão da opção filtrada usando o seletor exato do HTML
            seletor_opcao = f"button[data-component-name='DropdownOption'][data-option-value='{cidade_alvo}']"

            try:
                # Tenta clicar no botão exatamente correspondente (ex: data-option-value="São José - SC")
                page.wait_for_selector(seletor_opcao, state="visible", timeout=1500)
                page.click(seletor_opcao)
                logger.info(f"Cidade '{cidade_alvo}' selecionada com sucesso!")
            except Exception:
                logger.warning(f"Opção exata '{seletor_opcao}' não encontrada. Tentando selecionar a primeira opção filtrada...")
                # Fallback: clica na primeira opção disponível da lista filtrada
                primeira_opcao = "div[data-component-name='DropdownOptionsList'] button[data-component-name='DropdownOption']"
                page.wait_for_selector(primeira_opcao, state="visible")
                page.click(primeira_opcao)

            # Marca o radio "Sim" workModel = trabahlo remoto
            logger.info("Selecionando modelo de trabalho: Sim...")
            seletor_radio = "input[name='workModel'][value='true']"
            if page.is_visible(seletor_radio):
                logger.info("Selecionando modelo de trabalho remoto: Sim")
                page.locator(seletor_radio).click(force=True)
                

            # Marca o radio "Nao" isIndication = indicacao
            logger.info("É indicação: Não...")
            seletor_radio_nao = "input[name='isIndication'][value='false']"

            if page.is_visible(seletor_radio_nao):
                page.check(seletor_radio_nao)


            # 3. Pretensão Salarial (Digitação pausada para respeitar a máscara React)
            if page.is_visible("input[name='salaryExpectation']"):
                pretensao = str(dados.get('pretensao_salarial', ''))
                if pretensao:
                    logger.info("Preenchendo pretensão salarial...")
                    page.click("input[name='salaryExpectation']")
                    page.type("input[name='salaryExpectation']", pretensao, delay=50)

            # 4. Upload do Currículo (PDF)
            seletor_curriculo = "input[type='file'][name='resume']"
            # Verifica se o elemento existe no DOM (ou use is_visible)
            if page.locator(seletor_curriculo).count() > 0:
                logger.info("Injetando arquivo de currículo...")
                page.set_input_files(seletor_curriculo, caminho_curriculo)

            time.sleep(1) # aguardar atualizar

            # 5. Ir para a aba de Diversidade
            seletor_aba_diversidade = "button[data-id='diversityForm'][data-disabled='false']"

            if page.locator(seletor_aba_diversidade).count() > 0:
                logger.info("Avançando para a aba de Diversidade...")
                page.locator(seletor_aba_diversidade).click()
                time.sleep(1) # Aguarda a transição de aba/re-renderização


            # 6. Aceitar Termos e Política de Privacidade
            seletor_checkbox = "#privacyPolicy"

            if page.locator(seletor_checkbox).count() > 0:
                logger.info("Aceitando política de privacidade via JS...")
                page.eval_on_selector(
                    seletor_checkbox,
                    "el => { if (!el.checked) { el.click(); } }"
                )

            # 7. Clicar no botão "Continuar inscrição"
            seletor_botao_submeter = "button[type='submit']:has-text('Continuar inscrição')"

            if page.locator(seletor_botao_submeter).count() > 0:
                logger.info("Aguardando botão 'Continuar inscrição' ficar habilitado...")
                
                # Aguarda o botão não estar mais disabled (timeout de 10s para conferência)
                page.wait_for_selector("button[type='submit']:not([disabled])", state="visible", timeout=10000)
                
                logger.info("Enviando formulário...")
                page.locator(seletor_botao_submeter).click()

            logger.info("Formulário preenchido com sucesso!")
            time.sleep(10)  # Pausa para conferência visual

        except Exception as e:
            logger.error(f"Erro ao preencher formulário: {e}", exc_info=True)
        finally:
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--resume", required=True)
    args = parser.parse_args()

    dados = ler_dados_candidato(args.data)
    preencher_formulario_inhire(args.url, dados, args.resume)