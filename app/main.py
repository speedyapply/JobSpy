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

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    # O SQLAlchemy busca todas as vagas e converte em objetos Python nativos automaticamente
    vagas_do_banco = db.query(models.VagaModel).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "username": settings.default_username,
            "job_listings": vagas_do_banco # O Jinja consegue ler os atributos do objeto (.title, .company) direto
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