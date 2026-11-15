"""The web API and the single-page frontend, served together.

Reads come from api/views.py. Actions are few and all go through the code that already guards them: proposals go to the risk gate, approvals and
rejections are the owner's clicks, the kill switch and halt reset are the owner's. The trader can be started from here but only ever in shadow mode:
it writes a plan and gate what-ifs; turning an idea into a proposal is a separate click that goes through the gate again, and approving that
proposal is a third.

This is a local tool with no login. It must listen on localhost only (the compose file publishes 127.0.0.1:8000), and every state-changing request
must carry the header `X-Getrich-Action: 1` and, when the browser sends an Origin, an origin on localhost, which stops other web pages from driving it.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import config
from ..obs.events import emit, utcnow
from ..trading import book, instruments, service
from ..trading.types import OrderIntent
from . import jobs, views

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def static_dir() -> Path | None:
    for cand in (os.environ.get("GETRICH_STATIC"), str(config.root() / "frontend" / "dist"), "/app/frontend_dist"):
        if cand and (Path(cand) / "index.html").exists():
            return Path(cand)
    return None


class TraderRun(BaseModel):
    classes: list[str] = Field(default_factory=lambda: ["crypto"])
    refresh: bool = True                  # bring data and news up to date before planning


class Refresh(BaseModel):
    classes: list[str] = Field(default_factory=lambda: ["crypto", "fx", "metal"])


def create_app() -> FastAPI:
    config.load_env()
    app = FastAPI(title="getrich", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if request.headers.get("x-getrich-action") != "1" or (origin and (urlparse(origin).hostname or "") not in LOCAL_HOSTS):
                return JSONResponse({"detail": "state-changing requests need the X-Getrich-Action header and a local origin"}, status_code=403)
        return await call_next(request)

    def guarded(fn):
        try:
            return fn()
        except KeyError as exc:
            raise HTTPException(404, f"not found: {exc.args[0]}")
        except (ValueError, TimeoutError) as exc:
            raise HTTPException(400 if isinstance(exc, ValueError) else 503, str(exc))

    # ---------------------------------------------------------------- reads
    @app.get("/api/overview")
    def overview():
        return guarded(views.overview)

    @app.get("/api/universe")
    def universe(classes: str | None = None):
        wanted = tuple(c for c in (classes or "").split(",") if c) or None
        return guarded(lambda: views.universe(wanted))

    @app.get("/api/instrument/{symbol}")
    def instrument(symbol: str):
        return guarded(lambda: views.instrument_detail(symbol))

    @app.get("/api/bars/{symbol}")
    def bars(symbol: str, timeframe: str = "1h", limit: int = 500):
        return guarded(lambda: views.bars(symbol, timeframe, limit))

    @app.get("/api/trader/plans")
    def trader_plans(limit: int = 8):
        return guarded(lambda: views.trader_plans(max(1, min(limit, 40))))

    @app.get("/api/trader/packet/{ref}")
    def packet(ref: str):
        return guarded(lambda: views.packet(ref))

    @app.get("/api/orders")
    def orders(limit: int = 40):
        return guarded(lambda: views.orders(max(1, min(limit, 200))))

    @app.get("/api/news")
    def news():
        return guarded(views.news)

    @app.get("/api/health")
    def health():
        return guarded(views.health)

    @app.get("/api/research")
    def research():
        return guarded(views.research)

    @app.get("/api/docs/{directory}/{name}", response_class=PlainTextResponse)
    def doc(directory: str, name: str):
        return guarded(lambda: views.doc(directory, name))

    @app.get("/api/jobs")
    def list_jobs():
        return {"jobs": jobs.list_jobs(20)}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        meta = jobs.get(job_id)
        if meta is None:
            raise HTTPException(404, "no such job")
        return {**meta, "tail": jobs.tail(job_id)}

    # ---------------------------------------------------------------- actions (all guarded by the middleware above)
    @app.post("/api/trader/run")
    def trader_run(body: TraderRun):
        if not body.classes or any(c not in ("crypto", "fx", "metal") for c in body.classes):
            raise HTTPException(400, "classes must be a non-empty list of crypto, fx, metal")
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise HTTPException(400, "no Anthropic key in this environment (set it in the gitignored .env)")
        try:
            return jobs.start("trader", ["--classes", *body.classes, *([] if body.refresh else ["--no-refresh"])])          # shadow mode only: never --propose from here
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/data/refresh")
    def refresh(body: Refresh):
        if not body.classes or any(c not in ("crypto", "fx", "metal") for c in body.classes):
            raise HTTPException(400, "classes must be a non-empty list of crypto, fx, metal")
        try:
            return jobs.start("refresh-data", ["--classes", *body.classes])
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/ideas/{insight_id}/propose")
    def propose_idea(insight_id: str):
        """Turn one stored trader idea into a proposal at the current price. The gate decides; nothing is filled until the owner approves."""
        it = views.idea(insight_id)
        if it is None:
            raise HTTPException(404, "no such idea")
        if (utcnow() - it["as_of"]).total_seconds() > 2 * 3600:
            raise HTTPException(409, "this idea is more than two hours old: run the trader again")
        if it["action"] == "open_short" or it["action"] not in ("open_long", "exit", "reduce"):
            raise HTTPException(400, f"{it['action']} cannot become an order")
        sym = it["instrument"]
        state = book.load_state(instruments.symbols(), utcnow())
        px = state.prices.get(sym)
        if px is None:
            raise HTTPException(409, f"no price for {sym}")
        from ..agents import trader as trader_mod

        positions = [{"symbol": s, "qty": p.qty} for s, p in state.positions.items()]
        intent: OrderIntent | None = trader_mod.to_intent({**it, "instrument": sym}, px[0], {"portfolio": {"positions": positions}})
        if intent is None:
            raise HTTPException(400, "nothing to propose for this idea")
        order_id, verdict = service.propose(intent)
        emit("api.idea_proposed", service="api", insight_id=insight_id, order_id=order_id, approved_by_gate=verdict["approved"])
        views.clear_cache()
        return {"order_id": order_id, "verdict": verdict}

    @app.post("/api/orders/{order_id}/approve")
    def approve(order_id: str):
        res = service.approve(order_id)
        views.clear_cache()
        return res

    @app.post("/api/orders/{order_id}/reject")
    def reject(order_id: str):
        res = service.reject(order_id, "rejected in the web UI")
        views.clear_cache()
        return res

    @app.post("/api/risk/kill")
    def kill():
        res = service.kill()
        views.clear_cache()
        return res

    @app.post("/api/risk/unkill")
    def unkill():
        return {"was_on": service.unkill()}

    @app.post("/api/risk/unhalt")
    def unhalt():
        return {"was_latched": service.unhalt()}

    # ---------------------------------------------------------------- the frontend
    static = static_dir()
    if static is not None:
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            f = static / path
            return FileResponse(f if path and f.is_file() and static in f.resolve().parents else static / "index.html")
    return app


app = create_app()
