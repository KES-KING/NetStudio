from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .drivers import GenericReadOnlyDriver
from .fixtures import build_fixture
from .jobs import job_store
from .models import ApiError, Device, Job, PollSnapshot
from .security import Permission, Role, SessionUser, has_permission

DEMO_DEVICE = build_fixture()
DEVICES: dict[str, Device] = {DEMO_DEVICE.id: DEMO_DEVICE}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # PostgreSQL jobs reference a device row. Keep the built-in read-only
    # fixture synchronized before accepting traffic; memory mode is a no-op.
    job_store.ensure_device(DEMO_DEVICE)
    yield


app = FastAPI(title="Stocc NetStudio API", version="0.1.0", lifespan=lifespan)
allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3002,http://127.0.0.1:3002",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

def demo_session(x_stocc_user: str | None) -> SessionUser:
    """Development session boundary; production must inject an IdP provider."""
    if not x_stocc_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(code="authentication_required", message="Oturum gerekli").model_dump(mode="json"),
        )
    return SessionUser(user_id=x_stocc_user, display_name=x_stocc_user, roles={Role.OPERATOR}, site_ids={DEMO_DEVICE.site})


def require_permission(user: SessionUser, permission: Permission, device: Device) -> None:
    if not has_permission(user, permission, device.site):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ApiError(code="forbidden", message="Bu işlem için kapsamlı yetki yok").model_dump(mode="json"),
        )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "stocc-netstudio-api"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    try:
        ready = job_store.is_ready()
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="persistence_unavailable") from error
    if not ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="persistence_unavailable")
    return {"status": "ready", "service": "stocc-netstudio-api"}


@app.get("/api/v1/session/me", response_model=SessionUser)
def session_me(x_stocc_user: Annotated[str | None, Header(alias="X-Stocc-User")] = None) -> SessionUser:
    return demo_session(x_stocc_user)


@app.get("/api/v1/devices", response_model=list[Device])
def list_devices() -> list[Device]:
    return list(DEVICES.values())


@app.get("/api/v1/devices/{device_id}", response_model=Device)
def get_device(device_id: str) -> Device:
    device = DEVICES.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=ApiError(code="device_not_found", message="Cihaz bulunamadı").model_dump(mode="json"))
    return device


@app.get("/api/v1/devices/{device_id}/capabilities")
def capabilities(device_id: str) -> dict:
    device = get_device(device_id)
    return {
        "device_id": device_id,
        "driver_id": "fixture",
        "driver_version": "0.1.0",
        "support_status": device.support_status,
        "features": GenericReadOnlyDriver(device).discover_capabilities(None),
    }


@app.post("/api/v1/devices/{device_id}/connection-tests", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
def enqueue_connection_test(device_id: str, user: Annotated[str | None, Header(alias="X-Stocc-User")] = None) -> Job:
    device = get_device(device_id)
    session = demo_session(user)
    require_permission(session, Permission.JOB_CREATE, device)
    job = job_store.enqueue_connection_test(device, session.user_id)
    # The fixture is deterministic. Production drivers will be run by a worker;
    # this call only completes a local fixture job without network access.
    return job_store.run_fixture_job(job.id, device) or job


@app.post("/api/v1/devices/{device_id}/polls", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
def enqueue_poll(device_id: str, user: Annotated[str | None, Header(alias="X-Stocc-User")] = None) -> Job:
    device = get_device(device_id)
    session = demo_session(user)
    require_permission(session, Permission.JOB_CREATE, device)
    job = job_store.enqueue_inventory_read(device, session.user_id)
    return job_store.run_fixture_job(job.id, device) or job


@app.get("/api/v1/devices/{device_id}/observations/latest", response_model=PollSnapshot)
def latest_observations(device_id: str, user: Annotated[str | None, Header(alias="X-Stocc-User")] = None) -> PollSnapshot:
    device = get_device(device_id)
    session = demo_session(user)
    require_permission(session, Permission.INVENTORY_READ, device)
    # The fixture collector is deterministic and read-only. A persistent
    # observation repository will replace this fallback in the polling slice.
    from .observations import FixtureCollector

    return FixtureCollector().collect(device)


@app.get("/api/v1/jobs/{job_id}", response_model=Job)
def get_job(job_id: UUID) -> Job:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=ApiError(code="job_not_found", message="İş bulunamadı").model_dump(mode="json"))
    return job
