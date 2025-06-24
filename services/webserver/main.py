from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 라우터 임포트
from routes import pages, websocket

app = FastAPI(title="Kidding")

# Static 파일 및 Templates 설정
app.mount("/static", StaticFiles(directory="static"), name="static")

# 라우터 등록
app.include_router(pages.router, tags=["pages"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])

@app.get("/")
async def root():
    return {"message": "음성 변환 서버가 실행 중입니다"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)