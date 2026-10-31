"""FastAPI application: routes, validation and friendly error handling.

Run locally:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from datetime import timedelta
from typing import Any

from fastapi import FastAPI, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.schemas import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    ErrorResponse,
    HealthResponse,
    JourneyMapOut,
    LiveOut,
    JourneyResponse,
    LiveUsageOut,
    MetaResponse,
    PlaceOut,
    SearchRequest,
    SearchResponse,
)
from .api.serialize import Serializer
from .config import Settings, load_settings
from .core.availability import TicketQuery
from .core.live import LiveAnswer, LiveUnavailable
from .core.models import CLASS_LABELS
from .core.route_shape import itinerary_shape
from .core.search import InvalidItinerary, SearchLimits, SearchOptions, SearchParams, SearchRequestError
from .core.stations import UnknownPlaceError
from .core.timeutil import Clock, to_iso
from .services import Services

__version__ = "0.1.0"
log = logging.getLogger("wims")

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    410: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, hint: str | None = None, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details


def _error(status: int, code: str, message: str, hint: str | None = None, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if hint:
        body["hint"] = hint
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def _field_message(err: dict[str, Any]) -> str:
    loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
    field = ".".join(loc) or "request"
    friendly = {
        "passengers": "Passengers must be between 1 and 6.",
        "max_transfers": "Max transfers must be between 0 and 3.",
        "flexible_days": "Flexible dates can be at most ±3 days.",
        "date": "Please give a valid travel date (YYYY-MM-DD).",
        "travel_class": "Class must be one of SL, 3A, 2A, 1A, CC, 2S or ANY.",
        "max_budget": "Budget must be between ₹50 and ₹1,00,000 per person.",
        "max_duration_hours": "Max journey duration must be between 1 and 48 hours.",
        "origin": "Please choose a 'From' station.",
        "destination": "Please choose a 'To' station.",
    }
    return friendly.get(loc[0] if loc else "", f"{field}: {err.get('msg', 'invalid value')}")


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    options: SearchOptions | None = None,
    limits: SearchLimits | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    services = Services(settings, clock=clock, options=options, limits=limits)
    serializer = Serializer(services.directory, services.availability, services.notice, services.fares)
    engine = services.engine

    app = FastAPI(
        title="Where Is My Seat API",
        version=__version__,
        description=(
            "Finds practical alternative train journeys when the direct train is full. "
            "Demo mode uses SIMULATED timetables and availability."
        ),
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ----- error handling: friendly JSON, never a stack trace ------------
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.hint, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        message = _field_message(errors[0]) if errors else "The request is not valid."
        details = [{"field": ".".join(str(p) for p in e.get("loc", [])), "message": e.get("msg")} for e in errors]
        return _error(422, "INVALID_REQUEST", message, details=details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return _error(500, "INTERNAL_ERROR", "Something went wrong on our side. Please try again.")

    def resolve(text: str, which: str):
        try:
            return engine.resolve_place(text)
        except UnknownPlaceError as exc:
            hint = (
                f"Did you mean {', '.join(exc.suggestions)}?"
                if exc.suggestions
                else "Try a station code like NDLS or a city like Jaipur."
            )
            raise ApiError(404, "UNKNOWN_STATION", f"We couldn't find a {which} station called '{text}'.", hint)

    # ----- routes --------------------------------------------------------
    @app.get("/health", response_model=HealthResponse)
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": services.notice.mode,
            "stations": len(services.directory.all()),
            "trains": len(services.timetable.trains()),
            "availability_provider": services.notice.availability_source,
            "availability_live": services.notice.availability_live,
            "timetable_version": services.notice.timetable_version,
        }

    @app.get("/meta", response_model=MetaResponse)
    def meta() -> dict[str, Any]:
        today = services.clock.now().date()
        return {
            "app": "Where Is My Seat",
            "version": __version__,
            "today": today.isoformat(),
            "demo_date": services.demo_date.isoformat(),
            "max_advance_days": settings.max_advance_days,
            "classes": [{"code": c, "label": CLASS_LABELS[c]} for c in ("SL", "3A", "2A", "1A", "CC", "2S")],
            "samples": services.samples(),
            "data_notice": serializer.notice_dict(),
            "rush_periods": [
                {
                    "name": f.name,
                    "date": f.date.isoformat(),
                    "from": (f.date - timedelta(days=f.before)).isoformat(),
                    "to": (f.date + timedelta(days=f.after)).isoformat(),
                    "level": f.level,
                }
                for f in services.rush.upcoming(today, settings.max_advance_days + 30)
            ],
            "limits": {
                "max_passengers": 6,
                "max_transfers": 3,
                "max_flexible_days": 3,
                "min_transfer_minutes": engine.options.min_transfer_minutes,
            },
        }

    @app.get("/stations", response_model=list[PlaceOut])
    def stations(
        query: str = Query("", max_length=40), limit: int = Query(8, ge=1, le=20)
    ) -> list[dict[str, Any]]:
        return [serializer.place(p) for p in services.directory.search(query, limit)]

    @app.post("/journeys/search", response_model=SearchResponse, responses=ERROR_RESPONSES)
    async def search(req: SearchRequest) -> dict[str, Any]:
        origin = resolve(req.origin, "'From'")
        destination = resolve(req.destination, "'To'")
        params = SearchParams(
            origin=origin,
            destination=destination,
            travel_date=req.date,
            passengers=req.passengers,
            travel_class=req.travel_class,
            max_budget=req.max_budget,
            max_duration_minutes=int(req.max_duration_hours * 60) if req.max_duration_hours else None,
            max_transfers=req.max_transfers,
            flexible_days=req.flexible_days,
            include_nearby=req.include_nearby,
            allow_unreserved=req.allow_unreserved,
            smart_tickets=req.smart_tickets,
            sort=req.sort,
        )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(engine.search, params), timeout=settings.search_timeout_seconds
            )
        except SearchRequestError as exc:
            raise ApiError(422, exc.code, exc.message, exc.hint) from exc
        except TimeoutError as exc:
            raise ApiError(
                504, "SEARCH_TIMEOUT", "The search took too long.", "Try fewer transfers or a specific station."
            ) from exc
        return serializer.search(result, generated_at=to_iso(services.clock.now()))

    @app.get("/journeys/{journey_id}", response_model=JourneyResponse, responses=ERROR_RESPONSES)
    async def journey(journey_id: str = Path(min_length=8, max_length=4000)) -> dict[str, Any]:
        try:
            it, ends = await asyncio.to_thread(engine.resolve_itinerary, journey_id)
        except InvalidItinerary as exc:
            if str(exc) == "This journey link is not valid.":
                raise ApiError(400, "INVALID_JOURNEY_LINK", str(exc), "Search again to get a fresh link.") from exc
            raise ApiError(
                409, "JOURNEY_NO_LONGER_VALID", str(exc), "The timetable changed. Search again for current options."
            ) from exc
        if it.depart_at < services.clock.now():
            raise ApiError(410, "JOURNEY_DEPARTED", "This journey has already departed.", "Search for a new date.")
        return {
            "itinerary": serializer.itinerary(it),
            "origin": serializer.place(services.directory.resolve(it.origin_key)),
            "destination": serializer.place(services.directory.resolve(it.destination_key)),
            "data_notice": serializer.notice_dict(),
            "checked_at": to_iso(services.clock.now()),
        }

    @app.get("/journeys/{journey_id}/map", response_model=JourneyMapOut, responses=ERROR_RESPONSES)
    async def journey_map(journey_id: str = Path(min_length=8, max_length=4000)) -> dict[str, Any]:
        try:
            it, _ = await asyncio.to_thread(engine.resolve_itinerary, journey_id)
        except InvalidItinerary as exc:
            raise ApiError(400, "INVALID_JOURNEY_LINK", str(exc), "Search again to get a fresh link.") from exc
        return await asyncio.to_thread(itinerary_shape, it, services.directory, services.railmap)

    # ----- live tools (RailRadar free plan, own key) ------------------------
    live_status = {"LIVE_LIMIT_REACHED": 429, "NOT_IN_FREE_PLAN": 402, "LIVE_SOURCE_ERROR": 503}

    def live_call(fn, *args) -> dict[str, Any]:
        if services.live is None:
            raise ApiError(
                409, "LIVE_NOT_CONFIGURED", "Live information is not set up.",
                "Add your own RailRadar key as WIMS_RAILRADAR_KEY in backend/.env and restart.",
            )
        try:
            result = fn(*args)
        except LiveUnavailable as exc:
            raise ApiError(live_status.get(exc.code, 503), exc.code, str(exc), "Check NTES or the IRCTC app instead.") from exc
        extra: dict[str, Any] = {}
        if isinstance(result, tuple):
            items, result = result
            extra = {"items": items, "updated_at": result.data.get("updated_at")}
        assert isinstance(result, LiveAnswer)
        return {
            "data": extra or result.data,
            "source": services.live.source,
            "fetched_at": to_iso(result.fetched_at),
            "cached": result.cached,
            "requests_left": services.railradar_quota.remaining(services.clock.now()),
        }

    def train_no():  # a fresh Path() per route: FastAPI binds each one to its parameter
        return Path(pattern=r"^\d{5}$", description="5-digit train number")

    def station_code():
        return Path(pattern=r"^[A-Za-z]{1,8}$", description="Station code")

    @app.get("/live/trains/{number}", response_model=LiveOut, responses=ERROR_RESPONSES)
    async def live_train(number: str = train_no(), date: dt.date | None = None) -> dict[str, Any]:
        return await asyncio.to_thread(live_call, services.live.train_live if services.live else None, number, date)

    @app.get("/live/trains/{number}/punctuality", response_model=LiveOut, responses=ERROR_RESPONSES)
    async def live_punctuality(number: str = train_no()) -> dict[str, Any]:
        return await asyncio.to_thread(live_call, services.live.punctuality if services.live else None, number)

    @app.get("/live/trains/{number}/alerts", response_model=LiveOut, responses=ERROR_RESPONSES)
    async def live_alerts(number: str = train_no()) -> dict[str, Any]:
        return await asyncio.to_thread(live_call, services.live.alerts if services.live else None, number)

    @app.get("/live/trains/{number}/coaches/{station}", response_model=LiveOut, responses=ERROR_RESPONSES)
    async def live_coaches(number: str = train_no(), station: str = station_code()) -> dict[str, Any]:
        return await asyncio.to_thread(live_call, services.live.coaches if services.live else None, number, station.upper())

    @app.get("/live/stations/{code}", response_model=LiveOut, responses=ERROR_RESPONSES)
    async def live_station(code: str = station_code(), hours: int = Query(2, ge=2, le=8)) -> dict[str, Any]:
        hours = min((2, 4, 6, 8), key=lambda h: abs(h - hours))
        return await asyncio.to_thread(live_call, services.live.station_board if services.live else None, code.upper(), hours)

    @app.get("/live/fare", response_model=LiveOut, responses=ERROR_RESPONSES)
    async def live_fare(
        train: str = Query(pattern=r"^\d{5}$"),
        from_code: str = Query(pattern=r"^[A-Za-z]{1,8}$"),
        to_code: str = Query(pattern=r"^[A-Za-z]{1,8}$"),
        date: dt.date = Query(),
        travel_class: str = Query(pattern=r"^(1A|2A|3A|3E|CC|EC|FC|SL|2S)$"),
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            live_call, services.live.fare if services.live else None,
            train, from_code.upper(), to_code.upper(), date, travel_class,
        )

    @app.get("/availability/usage", response_model=LiveUsageOut)
    def availability_usage() -> dict[str, Any]:
        return services.live_usage()

    @app.post("/availability/check", response_model=AvailabilityCheckResponse, responses=ERROR_RESPONSES)
    def availability_check(req: AvailabilityCheckRequest) -> dict[str, Any]:
        quota_limited = getattr(services.check_provider, "quota_limited", False)
        if quota_limited and len(req.checks) > 3:
            raise ApiError(
                422, "TOO_MANY_LIVE_CHECKS", "Live checks are limited to 3 tickets at a time.",
                "Check the tickets you care about most.",
            )
        session = services.check_availability.session(max_checks=3 if quota_limited else 40)
        results = []
        for item in req.checks:
            train = services.timetable.train(item.train_number)
            error = None
            i = train.index_of(item.from_code.upper()) if train else None
            j = train.index_of(item.to_code.upper()) if train else None
            if train is None:
                error = f"Train {item.train_number} is not in the timetable."
            elif i is None or j is None:
                missing = item.from_code if i is None else item.to_code
                error = f"{train.number} does not halt at {missing.upper()}."
            elif i >= j:
                error = f"{train.number} reaches {item.to_code.upper()} before {item.from_code.upper()}."
            elif not train.stops[i].boardable or not train.stops[j].alightable:
                error = f"{train.number} does not take passengers between these stations."
            elif item.travel_class not in train.classes:
                error = f"{train.number} has no {item.travel_class} class."
            elif services.timetable.run_for_journey_date(train, i, item.journey_date) is None:
                error = f"{train.number} does not leave {item.from_code.upper()} on {item.journey_date}."
            if error:
                results.append({"request": item, "ok": False, "error": error, "availability": None})
                continue
            obs = session.check(
                TicketQuery(
                    train_number=train.number,
                    journey_date=item.journey_date,
                    from_code=item.from_code.upper(),
                    to_code=item.to_code.upper(),
                    travel_class=item.travel_class,
                    passengers=req.passengers,
                )
            )
            results.append({"request": item, "ok": True, "error": None, "availability": serializer.observation(obs)})
        if services.refresh_notice():
            serializer.notice = services.notice
        return {
            "results": results,
            "data_notice": serializer.notice_dict(),
            "checked_at": to_iso(services.clock.now()),
            "live_usage": services.live_usage(),
        }

    return app


class _StripApiPrefix:
    """Accept paths under /api as well: on Vercel the frontend's /api/* is routed here unchanged."""

    def __init__(self, inner: FastAPI) -> None:
        self.inner = inner

    async def __call__(self, scope, receive, send):  # noqa: ANN001
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                scope = {**scope, "path": path[4:] or "/", "raw_path": None}
        await self.inner(scope, receive, send)


api = create_app()
app = _StripApiPrefix(api)
