from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from app.api.forecast import router as forecast_router
from app.api.external_drivers import router as external_drivers_router
from app.api.analysis import router as analysis_router

app = FastAPI(title="Demand Forecast API", version="1.0.0")


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON for unhandled exceptions so the client gets a parseable body (not HTML)."""
    if isinstance(exc, FastAPIHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": str(exc)})
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(forecast_router)
app.include_router(external_drivers_router)
app.include_router(analysis_router)


@app.get("/")
def root():
    return {"message": "Demand Forecast API", "docs": "/docs"}
