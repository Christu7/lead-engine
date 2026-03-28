"""Custom field definition management endpoints.

Field definition CRUD is admin-only.
Value updates (PATCH /leads/{id}/custom-fields and /companies/{id}/custom-fields)
are handled in leads.py and companies.py respectively.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user, require_admin
from app.schemas.custom_field import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionResponse,
    CustomFieldDefinitionUpdate,
)
from app.services import custom_fields as cf_service
from app.services.custom_fields import IncompatibleFieldTypeError

router = APIRouter(
    prefix="/custom-fields",
    tags=["custom-fields"],
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/", response_model=list[CustomFieldDefinitionResponse])
async def list_definitions(
    entity_type: str = Query(..., pattern="^(lead|company)$"),
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """List active custom field definitions for the given entity type."""
    return await cf_service.get_field_definitions(db, client_id, entity_type)


@router.post(
    "/",
    response_model=CustomFieldDefinitionResponse,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_definition(
    data: CustomFieldDefinitionCreate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom field definition. Admin only."""
    try:
        return await cf_service.create_field_definition(db, data, client_id)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("RESTORE_HINT:"):
            field_id = msg.split(":", 1)[1]
            raise HTTPException(
                status_code=409,
                detail=f"A soft-deleted field with this key already exists. Restore it via POST /api/custom-fields/{field_id}/restore",
            )
        raise HTTPException(status_code=409, detail="A field with this key already exists for this entity type")


@router.patch(
    "/{field_id}",
    response_model=CustomFieldDefinitionResponse,
    dependencies=[Depends(require_admin)],
)
async def update_definition(
    field_id: uuid.UUID,
    data: CustomFieldDefinitionUpdate,
    force: bool = Query(False, description="Force type change even if existing data is incompatible"),
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom field definition. Admin only.

    If changing field_type and incompatible records exist, returns 409 unless force=true.
    With force=true, incompatible values are set to null.
    """
    try:
        field_def = await cf_service.update_field_definition(db, field_id, data, client_id, force=force)
    except IncompatibleFieldTypeError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"{exc.count} record(s) have values incompatible with the new field type. Use ?force=true to nullify them.",
        )
    if field_def is None:
        raise HTTPException(status_code=404, detail="Field definition not found")
    return field_def


@router.delete(
    "/{field_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
async def delete_definition(
    field_id: uuid.UUID,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a custom field definition. Admin only."""
    deleted = await cf_service.delete_field_definition(db, field_id, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Field definition not found")


@router.post(
    "/{field_id}/restore",
    response_model=CustomFieldDefinitionResponse,
    dependencies=[Depends(require_admin)],
)
async def restore_definition(
    field_id: uuid.UUID,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    """Restore a soft-deleted custom field definition. Admin only."""
    field_def = await cf_service.restore_field_definition(db, field_id, client_id)
    if field_def is None:
        raise HTTPException(status_code=404, detail="Soft-deleted field definition not found")
    return field_def
