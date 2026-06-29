from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Nativa Gestion")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Nativa Gestion API OK"}

@app.get("/dashboard")
def dashboard():
    return {
        "sales": 0,
        "production": 0,
        "profit": 0,
        "stock_alerts": 0
    }
