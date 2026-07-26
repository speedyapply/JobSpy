import os
import yaml
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_302_FOUND, HTTP_200_OK, HTTP_204_NO_CONTENT, HTTP_202_ACCEPTED
from sqlalchemy.orm import Session

from config import settings
from jobspy import scrape_jobs
from scraper import executar_buscas_paralelas, get_config_from_db
from celery_app import celery_app
from tasks import candidatar_inhire
from database import get_db, engine, Base
import models

# Função para criar as tabelas no banco de dados na inicialização
def create_tables():
    models.Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

@app.on_event("startup")
def on_startup():
    create_tables()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.app_name} API"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "environment": settings.environment}


@app.get("/statuses", response_class=HTMLResponse)
async def manage_statuses(request: Request, db: Session = Depends(get_db)):
    statuses = db.query(models.StatusVagaModel).order_by(models.StatusVagaModel.id).all()
    return templates.TemplateResponse(
        request=request,
        name="statuses.html",
        context={"statuses": statuses, "username": settings.default_username}
    )

@app.post("/statuses/add")
async def add_status(name: str = Form(...), db: Session = Depends(get_db)):
    new_status = models.StatusVagaModel(name=name.strip())
    db.add(new_status)
    db.commit()
    return RedirectResponse(url="/statuses", status_code=HTTP_302_FOUND)

@app.post("/statuses/{status_id}/delete")
async def delete_status(request: Request, status_id: int, db: Session = Depends(get_db)):
    status_to_delete = db.query(models.StatusVagaModel).filter(models.StatusVagaModel.id == status_id).first()
    if status_to_delete:
        # Before deleting, check if any Vaga is using this status
        linked_vagas = db.query(models.VagaModel).filter(models.VagaModel.status_id == status_id).count()
        if linked_vagas > 0:
            # Optionally, handle this case more gracefully, e.g., by showing an error message
            # For now, we prevent deletion.
            statuses = db.query(models.StatusVagaModel).order_by(models.StatusVagaModel.id).all()
            return templates.TemplateResponse(
                request=request,
                name="statuses.html",
                context={
                    "statuses": statuses, 
                    "username": settings.default_username, 
                    "error": f"Não é possível excluir o status '{status_to_delete.name}' pois ele está sendo utilizado por {linked_vagas} vaga(s)."
                }
            )
        db.delete(status_to_delete)
        db.commit()
    return RedirectResponse(url="/statuses", status_code=HTTP_302_FOUND)


def get_status_by_name(db: Session, name: str) -> models.StatusVagaModel | None:
    return db.query(models.StatusVagaModel).filter(models.StatusVagaModel.name == name).first()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), page: int = 1, limit: int = 20):
    status_excluido = get_status_by_name(db, "Excluida")
    status_selecionada = get_status_by_name(db, "Selecionado")

    query = db.query(models.VagaModel)
    if status_excluido:
        query = query.filter(
            (models.VagaModel.status_id.not_in([status_selecionada.id, status_excluido.id])) | 
            (models.VagaModel.status_id.is_(None))
        )

    # Count total items for pagination
    total_vagas = query.count()
    
    # Calculate offset
    offset = (page - 1) * limit

    vagas_do_banco = query.order_by(models.VagaModel.date_posted.desc()).offset(offset).limit(limit).all()

    # Get all statuses to pass to the template
    all_statuses = db.query(models.StatusVagaModel).all()
    
    # Create a dictionary for quick lookup in the template
    status_map = {status.name: status.id for status in all_statuses}

    # Calculate total pages
    total_pages = (total_vagas + limit - 1) // limit

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "username": settings.default_username,
            "job_listings": vagas_do_banco,
            "statuses": status_map,
            "status_selecionada_id": status_selecionada.id if status_selecionada else None,
            "current_page": page,
            "total_pages": total_pages,
            "limit": limit,
        }
    )

@app.delete("/vagas/{vaga_id}")
async def delete_vaga(request: Request, vaga_id: int, db: Session = Depends(get_db)):
    vaga_to_delete = db.query(models.VagaModel).filter(models.VagaModel.id == vaga_id).first()
    if vaga_to_delete:
        vaga_to_delete.status_id = get_status_by_name(db, "Excluida").id
        db.commit()
    return Response(content="", status_code=HTTP_200_OK)

@app.post("/vagas/{vaga_id}/update-status")
async def update_vaga_status(
    request: Request,
    vaga_id: int,
    status_id: str = Form(...),
    db: Session = Depends(get_db)
):
    vaga = db.query(models.VagaModel).filter(models.VagaModel.id == vaga_id).first()
    if vaga:
        # If status_id is an empty string or 'None', set it to None, otherwise convert to int
        vaga.status_id = int(status_id) if status_id and status_id.isdigit() else None
        db.commit()

    referer = request.headers.get("referer")
    if referer and "minhas-vagas" in referer:
        return RedirectResponse(url="/minhas-vagas", status_code=HTTP_302_FOUND)
        
    return RedirectResponse(url="/dashboard", status_code=HTTP_302_FOUND)


@app.get("/minhas-vagas", response_class=HTMLResponse)
async def minhas_vagas(request: Request, db: Session = Depends(get_db)):
    status_selecionada = get_status_by_name(db, "Selecionado")
    
    job_listings = []
    if status_selecionada:
        job_listings = db.query(models.VagaModel).filter(models.VagaModel.status_id == status_selecionada.id).order_by(models.VagaModel.date_posted.desc()).all()

    # For the "un-select" button, we will set the status back to NULL (no status)
    return templates.TemplateResponse(
        request=request,
        name="minhas_vagas.html",
        context={
            "job_listings": job_listings,
            "username": settings.default_username,
        }
    )

@app.post("/vagas/atualizar")
async def atualizar_vagas(background_tasks: BackgroundTasks):
    """
    Aciona a tarefa em segundo plano para executar todas as buscas ativas.
    """
    background_tasks.add_task(executar_buscas_paralelas)
    return RedirectResponse(url="/dashboard", status_code=HTTP_302_FOUND)


# ==========================================
# CRUD CONFIGURAÇÕES
# ==========================================

@app.get("/configs", response_class=HTMLResponse)
async def manage_configs(request: Request, db: Session = Depends(get_db)):
    configs = db.query(models.ConfigModel).order_by(models.ConfigModel.nome).all()
    site_names = get_config_from_db(db, "SITE_NAMES")
    if isinstance(site_names, str):
        site_names = [site_names]

    return templates.TemplateResponse(
        request=request,
        name="configs.html",
        context={
            "configs": configs, 
            "username": settings.default_username,
            "site_names": site_names,
            "raw_data": None,
            "active_tab": "configs"
        }
    )

@app.post("/configs/debug")
async def debug_api(
    request: Request,
    site_name: str = Form(...),
    search_term: str = Form(None),
    db: Session = Depends(get_db)
):
    raw_data = None
    try:
        jobs_df = scrape_jobs(
            site_name=site_name,
            search_term=search_term,
            results_wanted=5,
        )
        if jobs_df is not None and not jobs_df.empty:
            raw_data = jobs_df.to_json(orient='records', indent=4)
        else:
            raw_data = "Nenhum dado retornado."
    except Exception as e:
        raw_data = f"Ocorreu um erro: {e}"

    configs = db.query(models.ConfigModel).order_by(models.ConfigModel.nome).all()
    site_names = get_config_from_db(db, "SITE_NAMES")
    if isinstance(site_names, str):
        site_names = [site_names]

    return templates.TemplateResponse(
        request=request,
        name="configs.html",
        context={
            "configs": configs,
            "username": settings.default_username,
            "site_names": site_names,
            "raw_data": raw_data,
            "selected_site": site_name,
            "search_term": search_term,
            "active_tab": "debug"
        }
    )

@app.get("/configs/add", response_class=HTMLResponse)
async def add_config_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="config_form.html",
        context={"config": None, "username": settings.default_username}
    )

@app.post("/configs/add")
async def add_config(
    request: Request,
    nome: str = Form(...),
    descricao: str = Form(None),
    conteudo: str = Form(None),
    db: Session = Depends(get_db)
):
    nome_clean = nome.strip()
    existing = db.query(models.ConfigModel).filter(models.ConfigModel.nome == nome_clean).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="config_form.html",
            context={
                "config": None,
                "username": settings.default_username,
                "error": f"Já existe uma configuração com o nome '{nome_clean}'."
            }
        )
    
    new_config = models.ConfigModel(
        nome=nome_clean,
        descricao=descricao.strip() if descricao else None,
        conteudo=conteudo.strip() if conteudo else None
    )
    db.add(new_config)
    db.commit()
    return RedirectResponse(url="/configs", status_code=HTTP_302_FOUND)

@app.get("/configs/{config_id}/edit", response_class=HTMLResponse)
async def edit_config_form(request: Request, config_id: int, db: Session = Depends(get_db)):
    config = db.query(models.ConfigModel).filter(models.ConfigModel.id == config_id).first()
    if not config:
        return RedirectResponse(url="/configs", status_code=HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="config_form.html",
        context={"config": config, "username": settings.default_username}
    )

@app.post("/configs/{config_id}/edit")
async def edit_config(
    request: Request,
    config_id: int,
    descricao: str = Form(None),
    conteudo: str = Form(None),
    db: Session = Depends(get_db)
):
    config = db.query(models.ConfigModel).filter(models.ConfigModel.id == config_id).first()
    if not config:
        return RedirectResponse(url="/configs", status_code=HTTP_302_FOUND)
    
    config.descricao = descricao.strip() if descricao else None
    config.conteudo = conteudo.strip() if conteudo else None
    db.commit()
    return RedirectResponse(url="/configs", status_code=HTTP_302_FOUND)

@app.post("/configs/{config_id}/delete")
async def delete_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(models.ConfigModel).filter(models.ConfigModel.id == config_id).first()
    if config:
        db.delete(config)
        db.commit()
    return RedirectResponse(url="/configs", status_code=HTTP_302_FOUND)


# ==========================================
# CRUD BUSCAS
# ==========================================

import json

@app.get("/buscas", response_class=HTMLResponse)
async def manage_buscas(request: Request, db: Session = Depends(get_db)):
    buscas = db.query(models.BuscaModel).order_by(models.BuscaModel.nome).all()
    for busca in buscas:
        if busca.detalhes:
            try:
                busca.detalhes_str = json.dumps(busca.detalhes, ensure_ascii=False)
            except Exception:
                busca.detalhes_str = str(busca.detalhes)
        else:
            busca.detalhes_str = ""
            
    return templates.TemplateResponse(
        request=request,
        name="buscas.html",
        context={"buscas": buscas, "username": settings.default_username}
    )

@app.get("/buscas/add", response_class=HTMLResponse)
async def add_busca_form(request: Request):
    default_detalhes = {
        "location": "Brasil",
        "job_type": "fulltime",
        "is_remote": False
    }
    detalhes_str = json.dumps(default_detalhes, indent=2, ensure_ascii=False)
    return templates.TemplateResponse(
        request=request,
        name="busca_form.html",
        context={
            "busca": None,
            "detalhes_str": detalhes_str,
            "username": settings.default_username
        }
    )

@app.post("/buscas/add")
async def add_busca(
    request: Request,
    nome: str = Form(...),
    status: int = Form(1),
    termos: str = Form(...),
    detalhes: str = Form(None),
    db: Session = Depends(get_db)
):
    nome_clean = nome.strip()
    termos_clean = termos.strip()
    
    detalhes_json = None
    if detalhes and detalhes.strip():
        try:
            detalhes_json = json.loads(detalhes.strip())
        except json.JSONDecodeError:
            return templates.TemplateResponse(
                request=request,
                name="busca_form.html",
                context={
                    "busca": None,
                    "detalhes_str": detalhes,
                    "username": settings.default_username,
                    "error": "O campo Detalhes (Filtros JSON) não possui um formato JSON válido."
                }
            )
            
    existing = db.query(models.BuscaModel).filter(models.BuscaModel.nome == nome_clean).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="busca_form.html",
            context={
                "busca": None,
                "detalhes_str": detalhes,
                "username": settings.default_username,
                "error": f"Já existe uma busca com o nome '{nome_clean}'."
            }
        )
        
    new_busca = models.BuscaModel(
        nome=nome_clean,
        status=status,
        termos=termos_clean,
        detalhes=detalhes_json
    )
    db.add(new_busca)
    db.commit()
    return RedirectResponse(url="/buscas", status_code=HTTP_302_FOUND)

@app.get("/buscas/{busca_id}/edit", response_class=HTMLResponse)
async def edit_busca_form(request: Request, busca_id: int, db: Session = Depends(get_db)):
    busca = db.query(models.BuscaModel).filter(models.BuscaModel.id == busca_id).first()
    if not busca:
        return RedirectResponse(url="/buscas", status_code=HTTP_302_FOUND)
        
    detalhes_str = ""
    if busca.detalhes:
        detalhes_str = json.dumps(busca.detalhes, indent=2, ensure_ascii=False)
        
    return templates.TemplateResponse(
        request=request,
        name="busca_form.html",
        context={
            "busca": busca,
            "detalhes_str": detalhes_str,
            "username": settings.default_username
        }
    )

@app.post("/buscas/{busca_id}/edit")
async def edit_busca(
    request: Request,
    busca_id: int,
    nome: str = Form(...),
    status: int = Form(1),
    termos: str = Form(...),
    detalhes: str = Form(None),
    db: Session = Depends(get_db)
):
    busca = db.query(models.BuscaModel).filter(models.BuscaModel.id == busca_id).first()
    if not busca:
        return RedirectResponse(url="/buscas", status_code=HTTP_302_FOUND)
        
    nome_clean = nome.strip()
    termos_clean = termos.strip()
    
    detalhes_json = None
    if detalhes and detalhes.strip():
        try:
            detalhes_json = json.loads(detalhes.strip())
        except json.JSONDecodeError:
            return templates.TemplateResponse(
                request=request,
                name="busca_form.html",
                context={
                    "busca": busca,
                    "detalhes_str": detalhes,
                    "username": settings.default_username,
                    "error": "O campo Detalhes (Filtros JSON) não possui um formato JSON válido."
                }
            )
            
    existing = db.query(models.BuscaModel).filter(models.BuscaModel.nome == nome_clean, models.BuscaModel.id != busca_id).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="busca_form.html",
            context={
                "busca": busca,
                "detalhes_str": detalhes,
                "username": settings.default_username,
                "error": f"Já existe outra busca com o nome '{nome_clean}'."
            }
        )
        
    busca.nome = nome_clean
    busca.status = status
    busca.termos = termos_clean
    busca.detalhes = detalhes_json
    db.commit()
    return RedirectResponse(url="/buscas", status_code=HTTP_302_FOUND)

@app.post("/buscas/{busca_id}/delete")
async def delete_busca(busca_id: int, db: Session = Depends(get_db)):
    busca = db.query(models.BuscaModel).filter(models.BuscaModel.id == busca_id).first()
    if busca:
        db.delete(busca)
        db.commit()
    return RedirectResponse(url="/buscas", status_code=HTTP_302_FOUND)

@app.post("/buscas/{busca_id}/toggle-status")
async def toggle_busca_status(busca_id: int, db: Session = Depends(get_db)):
    busca = db.query(models.BuscaModel).filter(models.BuscaModel.id == busca_id).first()
    if busca:
        busca.status = 0 if busca.status == 1 else 1
        db.commit()
    return RedirectResponse(url="/buscas", status_code=HTTP_302_FOUND)


# ==========================================
# API DE CANDIDATURAS (Task Queue com Celery)
# ==========================================

# Caminhos padrão dos assets de candidatura
DADOS_CANDIDATURA_PATH = os.getenv(
    "DADOS_CANDIDATURA_PATH",
    "/home/rodrigo/web/JobSpy/assets/dados_candidatura.md"
)
CURRICULO_PATH = os.getenv(
    "CURRICULO_PATH",
    "/home/rodrigo/web/JobSpy/assets/curriculo.pdf"
)


@app.post("/api/vagas/{vaga_id}/candidatar", status_code=HTTP_202_ACCEPTED)
async def candidatar_vaga(vaga_id: int, db: Session = Depends(get_db)):
    """
    Dispara uma candidatura para uma vaga existente no banco de dados.
    Retorna 202 Accepted com o ID da candidatura para polling.
    """
    # 1. Verifica se a vaga existe
    vaga = db.query(models.VagaModel).filter(models.VagaModel.id == vaga_id).first()
    if not vaga:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    if not vaga.job_url:
        raise HTTPException(status_code=400, detail="Vaga não possui URL")

    # 2. Verifica se os assets existem
    if not os.path.isfile(DADOS_CANDIDATURA_PATH):
        raise HTTPException(status_code=500, detail="Arquivo de dados do candidato não encontrado")
    if not os.path.isfile(CURRICULO_PATH):
        raise HTTPException(status_code=500, detail="Arquivo de currículo não encontrado")

    # 3. Lê os dados do candidato
    try:
        with open(DADOS_CANDIDATURA_PATH, "r", encoding="utf-8") as f:
            dados = yaml.safe_load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler dados do candidato: {e}")

    # 4. Cria o registro de candidatura no banco
    candidatura = models.CandidaturaModel(
        vaga_id=vaga.id,
        job_url=vaga.job_url,
        status="PENDING",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(candidatura)
    db.commit()
    db.refresh(candidatura)

    # 5. Dispara a task Celery em background
    task = candidatar_inhire.delay(
        candidatura_id=candidatura.id,
        dados=dados,
        resume_path=CURRICULO_PATH,
    )

    # Salva o ID da task Celery para rastreamento
    candidatura.celery_task_id = task.id
    db.commit()

    return {
        "message": "Candidatura iniciada",
        "candidatura_id": candidatura.id,
        "status": "PENDING",
        "poll_url": f"/api/candidaturas/{candidatura.id}",
    }


@app.post("/api/candidaturas", status_code=HTTP_202_ACCEPTED)
async def candidatar_por_url(job_url: str, db: Session = Depends(get_db)):
    """
    Dispara uma candidatura para uma URL qualquer (sem vínculo com vaga do banco).
    """
    if not job_url:
        raise HTTPException(status_code=400, detail="job_url é obrigatório")

    if not os.path.isfile(DADOS_CANDIDATURA_PATH):
        raise HTTPException(status_code=500, detail="Arquivo de dados do candidato não encontrado")
    if not os.path.isfile(CURRICULO_PATH):
        raise HTTPException(status_code=500, detail="Arquivo de currículo não encontrado")

    try:
        with open(DADOS_CANDIDATURA_PATH, "r", encoding="utf-8") as f:
            dados = yaml.safe_load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler dados do candidato: {e}")

    candidatura = models.CandidaturaModel(
        job_url=job_url,
        status="PENDING",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(candidatura)
    db.commit()
    db.refresh(candidatura)

    task = candidatar_inhire.delay(
        candidatura_id=candidatura.id,
        dados=dados,
        resume_path=CURRICULO_PATH,
    )

    candidatura.celery_task_id = task.id
    db.commit()

    return {
        "message": "Candidatura iniciada",
        "candidatura_id": candidatura.id,
        "status": "PENDING",
        "poll_url": f"/api/candidaturas/{candidatura.id}",
    }


@app.get("/api/candidaturas/{candidatura_id}")
async def status_candidatura(candidatura_id: int, db: Session = Depends(get_db)):
    """
    Endpoint de polling: consulta o status atual de uma candidatura.
    """
    candidatura = db.query(models.CandidaturaModel).filter(
        models.CandidaturaModel.id == candidatura_id
    ).first()

    if not candidatura:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")

    return {
        "id": candidatura.id,
        "vaga_id": candidatura.vaga_id,
        "job_url": candidatura.job_url,
        "status": candidatura.status,
        "error_message": candidatura.error_message,
        "celery_task_id": candidatura.celery_task_id,
        "created_at": candidatura.created_at.isoformat() if candidatura.created_at else None,
        "updated_at": candidatura.updated_at.isoformat() if candidatura.updated_at else None,
    }


@app.get("/api/candidaturas")
async def listar_candidaturas(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Lista as candidaturas recentes.
    """
    candidaturas = (
        db.query(models.CandidaturaModel)
        .order_by(models.CandidaturaModel.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": c.id,
            "vaga_id": c.vaga_id,
            "job_url": c.job_url,
            "status": c.status,
            "error_message": c.error_message,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in candidaturas
    ]
