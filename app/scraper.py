import logging
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from jobspy import scrape_jobs
from sqlalchemy.orm import Session
from database import SessionLocal
from config import settings
from models import VagaModel, BuscaModel, ConfigModel

# Inicializa o logger para este módulo
logger = logging.getLogger(__name__)

def get_config_from_db(db: Session, name: str, is_json: bool = False):
    """Busca uma configuração do banco de dados pelo nome."""
    config = db.query(ConfigModel).filter(ConfigModel.nome == name).first()
    if not config or not config.conteudo:
        logger.warning(f"Configuração '{name}' não encontrada no banco de dados.")
        return None
    if is_json:
        try:
            return json.loads(config.conteudo)
        except json.JSONDecodeError:
            logger.error(f"Erro ao decodificar o JSON da configuração '{name}'.")
            return None
    return config.conteudo.split(',') if ',' in config.conteudo else config.conteudo

def process_vaga_data(vaga_dict: dict) -> VagaModel:
    """Converte um dicionário de vaga em um objeto VagaModel, tratando os dados."""
    # Tratamento de localização
    location_data = vaga_dict.get('location')
    city, state, location_str = None, None, None
    if isinstance(location_data, dict):
        city, state = location_data.get('city'), location_data.get('state')
        location_str = ", ".join(filter(None, [city, state]))
    elif isinstance(location_data, str):
        location_str = location_data

    # Tratamento de compensação
    compensation_data = vaga_dict.get('compensation')
    min_amount, max_amount, interval, currency = None, None, None, None
    if isinstance(compensation_data, dict):
        min_amount, max_amount = compensation_data.get('min_amount'), compensation_data.get('max_amount')
        interval_enum = compensation_data.get('interval')
        interval = interval_enum.value if hasattr(interval_enum, 'value') else str(interval_enum) if interval_enum else None
        currency = compensation_data.get('currency')

    # --- TRATAMENTO SEGURO DE JOB_TYPE ---
    job_type_val = vaga_dict.get('job_type')
    job_type_str = None
    if job_type_val:
        if isinstance(job_type_val, (list, tuple, set)):
            # Se for lista, converte cada item (lidando com Enums se necessário) e une por vírgula
            job_type_str = ', '.join([item.value if hasattr(item, 'value') else str(item) for item in job_type_val])
        elif hasattr(job_type_val, 'value'):
            # Se for um Enum isolado
            job_type_str = str(job_type_val.value)
        else:
            # Se for string ou outro tipo escalar
            job_type_str = str(job_type_val)

    # --- TRATAMENTO SEGURO DE EMAILS ---
    emails_val = vaga_dict.get('emails')
    emails_str = None
    if emails_val:
        if isinstance(emails_val, (list, tuple, set)):
            emails_str = ', '.join([str(e) for e in emails_val])
        else:
            emails_str = str(emails_val)

    return VagaModel(
        title=vaga_dict.get('title'),
        company=vaga_dict.get('company'),
        company_url=vaga_dict.get('company_url'),
        job_url = vaga_dict.get('job_url_direct') or vaga_dict.get('job_url'),
        location=location_str,
        city=city,
        state=state,
        country=vaga_dict.get('country'),
        is_remote=bool(vaga_dict.get('is_remote', False)),
        description=vaga_dict.get('description'),
        job_type=job_type_str,
        interval=interval,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=currency,
        date_posted=str(vaga_dict.get('date_posted', '')),
        emails=emails_str
    )

def run_single_search(busca: BuscaModel, db_session: Session) -> list[VagaModel]:
    """Executa uma única busca e retorna uma lista de novas vagas."""
    start_time = time.time()
    logger.info(f"Iniciando busca: '{busca.nome}'", extra={"busca_nome": busca.nome, "termos": busca.termos})
    
    site_names = get_config_from_db(db_session, "SITE_NAMES")
    if not site_names:
        logger.error("Nenhum site configurado para a busca. Abortando.", extra={"busca_nome": busca.nome})
        return []

    try:
        search_details = busca.detalhes or {}
        
        jobs_df = scrape_jobs(
            site_name=site_names,
            search_term=busca.termos,
            location=search_details.get('location', 'Brasil'),
            results_wanted=int(get_config_from_db(db_session, "SCRAPER_RESULTS_WANTED") or settings.scraper_results_wanted),
            hours_old=int(get_config_from_db(db_session, "SCRAPER_HOURS_OLD") or settings.scraper_hours_old),
            country_indeed='Brazil',
            job_type=search_details.get('job_type'),
            is_remote=search_details.get('is_remote', False),
        )

        if jobs_df is None or jobs_df.empty:
            logger.info(f"Busca '{busca.nome}' não encontrou nenhuma vaga.", extra={"busca_nome": busca.nome})
            return []

        vagas_dict = jobs_df.to_dict(orient='records')
        found_jobs_count = len(vagas_dict)
        logger.info(f"Busca '{busca.nome}' encontrou {found_jobs_count} vagas.", extra={"busca_nome": busca.nome, "total_encontrado": found_jobs_count})
        
        exclude_keywords = get_config_from_db(db_session, "EXCLUDE_KEYWORDS", is_json=True) or []
        
        vagas_para_salvar = []
        vagas_puladas_count = 0
        for vaga_data in vagas_dict:
            job_url = vaga_data.get('job_url')
            if not job_url:
                vagas_puladas_count += 1
                continue

            if db_session.query(VagaModel).filter(VagaModel.job_url == job_url).first():
                logger.debug(f"Vaga já existente, pulando: {job_url}", extra={"job_url": job_url})
                vagas_puladas_count += 1
                continue
            
            title = vaga_data.get('title', '').lower()
            if any(keyword.lower() in title for keyword in exclude_keywords):
                logger.info(f"Vaga pulada por conter palavra-chave de exclusão: '{vaga_data.get('title')}'", extra={"job_title": vaga_data.get('title')})
                vagas_puladas_count += 1
                continue
            
            nova_vaga = process_vaga_data(vaga_data)
            vagas_para_salvar.append(nova_vaga)
        
        duration = time.time() - start_time
        logger.info(
            f"Busca '{busca.nome}' finalizada em {duration:.2f}s. "
            f"Novas vagas: {len(vagas_para_salvar)}. Puladas: {vagas_puladas_count}.",
            extra={
                "busca_nome": busca.nome,
                "duration_seconds": round(duration, 2),
                "novas_vagas": len(vagas_para_salvar),
                "vagas_puladas": vagas_puladas_count,
            }
        )
        return vagas_para_salvar

    except Exception as e:
        duration = time.time() - start_time
        logger.critical(
            f"Erro crítico ao executar a busca '{busca.nome}' após {duration:.2f}s: {e}",
            exc_info=True,
            extra={"busca_nome": busca.nome, "duration_seconds": round(duration, 2)}
        )
        return []

def executar_buscas_paralelas():
    """Orquestra a execução de todas as buscas ativas em paralelo."""
    main_start_time = time.time()
    logger.info("==================================================")
    logger.info("Iniciando processo de raspagem de vagas...")
    
    db = SessionLocal()
    try:
        popular_configs_iniciais(db)
        buscas_ativas = db.query(BuscaModel).filter(BuscaModel.status == 1).all()
        if not buscas_ativas:
            logger.warning("Nenhuma busca ativa encontrada no banco de dados.")
            return

        logger.info(f"Encontradas {len(buscas_ativas)} buscas ativas para processar.")
        
        todas_as_novas_vagas = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_busca = {executor.submit(run_single_search, busca, db): busca for busca in buscas_ativas}
            
            for future in as_completed(future_to_busca):
                busca = future_to_busca[future]
                try:
                    novas_vagas = future.result()
                    if novas_vagas:
                        todas_as_novas_vagas.extend(novas_vagas)
                except Exception as exc:
                    logger.error(f"Busca '{busca.nome}' gerou uma exceção não tratada no worker: {exc}", exc_info=True)
        
        if todas_as_novas_vagas:
            logger.info(f"Total de {len(todas_as_novas_vagas)} novas vagas para salvar no banco de dados.")
            db.add_all(todas_as_novas_vagas)
            db.commit()
            logger.info("Sucesso! Novas vagas salvas no banco de dados.")
        else:
            logger.info("Nenhuma vaga nova encontrada em todas as buscas executadas.")

    except Exception as e:
        logger.critical("Erro fatal no orquestrador de buscas.", exc_info=True)
        db.rollback()
    finally:
        db.close()
        duration = time.time() - main_start_time
        logger.info(f"Processo de raspagem de vagas finalizado em {duration:.2f} segundos.")
        logger.info("==================================================")

def popular_configs_iniciais(db: Session):
    """Popula o banco com configurações e buscas padrão se não existirem."""
    if db.query(ConfigModel).count() == 0:
        logger.info("Populando configurações iniciais...")
        configs = [
            ConfigModel(nome="SITE_NAMES", descricao="Lista de sites para buscar vagas", conteudo="linkedin,indeed,glassdoor,google"),
            ConfigModel(nome="SCRAPER_RESULTS_WANTED", descricao="Resultados desejados por busca", conteudo="25"),
            ConfigModel(nome="SCRAPER_HOURS_OLD", descricao="Limite de horas desde a postagem", conteudo="120"),
            ConfigModel(nome="EXCLUDE_KEYWORDS", descricao="Palavras-chave para excluir vagas (JSON array)", conteudo='["estágio", "internship", "trainee"]'),
        ]
        db.add_all(configs)
        logger.info("Configurações iniciais salvas.")

    if db.query(BuscaModel).count() == 0:
        logger.info("Populando buscas iniciais...")
        buscas = [
            BuscaModel(nome="Dev Python Sr", status=1, termos="Desenvolvedor Python, Engenheiro de Software Python", detalhes={"location": "Santa Catarina", "job_type": "fulltime"}),
            BuscaModel(nome="Engenheiro de Dados Pl", status=1, termos="Engenheiro de Dados, Data Engineer", detalhes={"location": "São Paulo"}),
            BuscaModel(nome="Dev Fullstack Remoto", status=1, termos="Fullstack Developer, Desenvolvedor Fullstack", detalhes={"is_remote": True}),
        ]
        db.add_all(buscas)
        logger.info("Buscas iniciais salvas.")
        
    db.commit()


if __name__ == "__main__":
    db_session = SessionLocal()
    try:
        popular_configs_iniciais(db_session)
        executar_buscas_paralelas()
    finally:
        db_session.close()