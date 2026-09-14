from fastapi import FastAPI

from tophost_api.api.errors import tophost_error_handler
from tophost_api.api.routes import auth, dns, domains
from tophost_api.errors import TophostAPIError


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tophost DNS API",
        version="0.1.0",
        description=(
            "Unofficial REST API for managing "
            "Tophost DNS resources."
        ),
    )

    app.add_exception_handler(
        TophostAPIError,
        tophost_error_handler,
    )

    @app.get(
        "/health",
        tags=["system"],
    )
    def health() -> dict[str, str]:
        return {
            "status": "ok"
        }

    app.include_router(
        auth.router,
        prefix="/v1",
    )

    app.include_router(
        domains.router,
        prefix="/v1",
    )

    app.include_router(
        dns.router,
        prefix="/v1",
    )

    return app


app = create_app()
