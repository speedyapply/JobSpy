from jobspy import scrape_jobs
from database import SessionLocal
from config import settings
from models import VagaModel

def executar_busca_e_salvar(search_term: str, location: str = "Brasil"):
    print(f"==================================================")
    print(f"Iniciando raspagem via JobSpy...")
    print(f"Cargo: '{search_term}' | Localização: '{location}'")
    print(f"==================================================")
    
    try:
        jobs = scrape_jobs(
            site_name=["indeed", "linkedin"],
            search_term=search_term,
            location=location,
            results_wanted=settings.scraper_results_wanted,
            hours_old=settings.scraper_hours_old,
            country_indeed='Brazil',
        )
        
        total_vagas = len(jobs)
        print(f"-> JobSpy finalizou! {total_vagas} vagas encontradas.")
        
        if total_vagas > 0:
            print("-> Gravando dados via SQLAlchemy ORM...")
            
            # Abre uma sessão limpa com o banco de dados
            db = SessionLocal()
            
            # Antes de salvar as novas, opcionalmente limpamos as antigas para manter o comportamento anterior
            db.query(VagaModel).delete()
            
            # Converte o DataFrame em dicionários
            vagas_dict = jobs.to_dict(orient='records')
            
            for vaga in vagas_dict:
                # Criamos o objeto filtrando apenas as colunas que nosso modelo aceita
                nova_vaga = VagaModel(
                    title=vaga.get('title'),
                    company=vaga.get('company'),
                    company_url=vaga.get('company_url'),
                    job_url=vaga.get('job_url'),
                    location=vaga.get('location'),
                    city=vaga.get('city'),
                    state=vaga.get('state'),
                    country=vaga.get('country'),
                    is_remote=bool(vaga.get('is_remote', False)),
                    description=vaga.get('description'),
                    job_type=vaga.get('job_type'),
                    interval=vaga.get('interval'),
                    min_amount=vaga.get('min_amount'),
                    max_amount=vaga.get('max_amount'),
                    currency=vaga.get('currency'),
                    date_posted=str(vaga.get('date_posted', '')),
                    emails=vaga.get('emails')
                )
                db.add(nova_vaga)
            
            # Comita todas as inserções de uma vez só
            db.commit()
            db.close()
            print("-> Sucesso! Banco de dados atualizado com segurança pelo ORM.")
        else:
            print("-> Nenhuma vaga retornada para salvar.")
            
    except Exception as e:
        print(f"❌ Erro crítico durante a execução do scraper: {e}")

if __name__ == "__main__":
    executar_busca_e_salvar(search_term="Desenvolvedor Python", location="Santa Catarina")