"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import ai_analysis, auth, inventory
from app.crud import close_database


app = FastAPI(
    title="AI-Enabled Dynamic Inventory Management System",
    version="1.0.0",
    description="Configuration-driven multi-industry inventory API with advisory AI.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(inventory.router)
app.include_router(ai_analysis.router)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part not in {"body", "query", "path"})
        message = error.get("msg", "Invalid request.")
        messages.append(f"{location}: {message}" if location else message)
    detail = "; ".join(messages) or "Invalid request."
    return JSONResponse(status_code=400, content={"detail": detail})


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc) or "Invalid request."})


@app.exception_handler(KeyError)
async def key_error_exception_handler(request: Request, exc: KeyError) -> JSONResponse:
    detail = str(exc).strip("'\"") or "Requested resource was not found."
    return JSONResponse(status_code=404, content={"detail": detail})


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})


@app.on_event("shutdown")
async def shutdown() -> None:
    close_database()
