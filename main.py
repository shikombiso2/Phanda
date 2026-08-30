from fastapi import FastAPI

from app.app_factory import create_app

app: FastAPI = create_app()

