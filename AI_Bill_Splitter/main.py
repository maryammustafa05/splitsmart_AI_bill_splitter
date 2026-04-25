import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routes.health import router as health_router
from routes.manual_split import router as manual_router
from routes.image_split import router as image_router
from routes.history import router as history_router

app = FastAPI(
    title="AI Bill Splitter API",
    description="Backend API for the AI Bill Splitter and Expense Explainer project",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(manual_router)
app.include_router(image_router)
app.include_router(history_router)