# services/webserver/src/routes/pages.py
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter()
path_template = Path(__file__).parent.parent / 'templates'
templates = Jinja2Templates(directory=path_template)

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 페이지"""
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/voice-converter", response_class=HTMLResponse)
async def voice_converter_page(request: Request):
    """음성 변환 페이지"""
    return templates.TemplateResponse("voice_converter.html", {"request": request})

@router.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {"status": "healthy", "service": "voice-converter"}

@router.get("/api/models")
async def get_available_models():
    """사용 가능한 음성 모델 목록"""
    return {
        "models": [
            {"id": "model1", "name": "남성 → 여성"},
            {"id": "model2", "name": "여성 → 남성"},
            {"id": "model3", "name": "성인 → 아동"}
        ]
    }