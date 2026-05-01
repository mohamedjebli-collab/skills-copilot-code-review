"""
Announcements endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementIn(BaseModel):
    message: str
    start_date: Optional[str] = None   # ISO date string (YYYY-MM-DD), optional
    expiration_date: str               # ISO date string (YYYY-MM-DD), required


def _serialize(doc: dict) -> dict:
    """Convert a MongoDB announcement document to a JSON-serializable dict."""
    doc["id"] = str(doc.pop("_id"))
    doc["start_date"] = doc["start_date"].date().isoformat() if doc.get("start_date") else None
    doc["expiration_date"] = doc["expiration_date"].date().isoformat() if doc.get("expiration_date") else None
    return doc


def _require_teacher(teacher_username: Optional[str]) -> None:
    """Raise 401 if the given username does not match a known teacher."""
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not teachers_collection.find_one({"_id": teacher_username}):
        raise HTTPException(status_code=401, detail="Invalid credentials")


def _parse_date(date_str: str, field: str) -> datetime:
    """Parse an ISO date string (YYYY-MM-DD) into a datetime, raising 400 on failure."""
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field} format. Use YYYY-MM-DD.")


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """
    Get all currently active announcements (public).

    An announcement is active when:
    - Its expiration_date is in the future, AND
    - Its start_date is either absent or is today / in the past.
    """
    now = datetime.utcnow()
    query: Dict[str, Any] = {
        "expiration_date": {"$gt": now},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": now}},
        ],
    }
    return [_serialize(doc) for doc in announcements_collection.find(query).sort("expiration_date", 1)]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(
    teacher_username: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """
    Get all announcements including expired ones.

    Requires teacher authentication (teacher_username query parameter).
    """
    _require_teacher(teacher_username)
    return [
        _serialize(doc)
        for doc in announcements_collection.find().sort("expiration_date", -1)
    ]


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_announcement(
    announcement: AnnouncementIn,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Create a new announcement.

    Requires teacher authentication (teacher_username query parameter).
    """
    _require_teacher(teacher_username)

    expiration_date = _parse_date(announcement.expiration_date, "expiration_date")
    start_date = _parse_date(announcement.start_date, "start_date") if announcement.start_date else None

    doc = {
        "message": announcement.message,
        "start_date": start_date,
        "expiration_date": expiration_date,
        "created_by": teacher_username,
    }
    result = announcements_collection.insert_one(doc)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementIn,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Update an existing announcement.

    Requires teacher authentication (teacher_username query parameter).
    """
    _require_teacher(teacher_username)

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")

    expiration_date = _parse_date(announcement.expiration_date, "expiration_date")
    start_date = _parse_date(announcement.start_date, "start_date") if announcement.start_date else None

    result = announcements_collection.update_one(
        {"_id": oid},
        {"$set": {
            "message": announcement.message,
            "start_date": start_date,
            "expiration_date": expiration_date,
        }},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Delete an announcement.

    Requires teacher authentication (teacher_username query parameter).
    """
    _require_teacher(teacher_username)

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")

    result = announcements_collection.delete_one({"_id": oid})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted successfully"}
