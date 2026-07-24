from fastapi import FastAPI, Request, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session

from config import settings
from scraper import executar_busca_e_salvar
from database import get_db, engine
import models

app = FastAPI(title=settings.app_name)

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
        "statuses.html",
        {"request": request, "statuses": statuses, "username": settings.default_username}
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
                "statuses.html",
                {
                    "request": request, 
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
async def dashboard(request: Request, db: Session = Depends(get_db)):
    status_excluido = get_status_by_name(db, "excluido")
    status_selecionada = get_status_by_name(db, "selecionada")

    query = db.query(models.VagaModel)
    if status_excluido:
        query = query.filter(models.VagaModel.status_id != status_excluido.id)

    vagas_do_banco = query.order_by(models.VagaModel.date_posted.desc()).all()

    # Get all statuses to pass to the template
    all_statuses = db.query(models.StatusVagaModel).all()
    
    # Create a dictionary for quick lookup in the template
    status_map = {status.name: status.id for status in all_statuses}

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "username": settings.default_username,
            "job_listings": vagas_do_banco,
            "statuses": status_map,
            "status_selecionada_id": status_selecionada.id if status_selecionada else None,
        }
    )

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
    status_selecionada = get_status_by_name(db, "selecionada")
    
    job_listings = []
    if status_selecionada:
        job_listings = db.query(models.VagaModel).filter(models.VagaModel.status_id == status_selecionada.id).order_by(models.VagaModel.date_posted.desc()).all()

    # For the "un-select" button, we will set the status back to NULL (no status)
    return templates.TemplateResponse(
        "minhas_vagas.html",
        {
            "request": request,
            "job_listings": job_listings,
            "username": settings.default_username,
        }
    )



@app.post("/vagas/atualizar")
async def atualizar_vagas(
    background_tasks: BackgroundTasks,
    search_term: str = Form(...),
    location: str = Form("")
):
    if not location.strip():
        location = "Brasil"
        
    background_tasks.add_task(executar_busca_e_salvar, search_term=search_term, location=location)
    return RedirectResponse(url="/dashboard", status_code=HTTP_302_FOUND)