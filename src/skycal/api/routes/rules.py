"""Interpretation rules and per-user overrides. Phase 2."""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("")
def list_rules():
    raise HTTPException(501, "rules arrive in Phase 2")
