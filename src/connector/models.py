"""Validated tool inputs and normalized ticket models."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import ValidationError


class TicketInclude(StrEnum):
    REQUESTER = "requester"
    COMPANY = "company"
    STATS = "stats"
    CONVERSATIONS = "conversations"


class ListTicketsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=300)
    per_page: int = Field(default=20, ge=1, le=100)
    email: str | None = Field(default=None, max_length=320)
    requester_id: int | None = Field(default=None, ge=1)
    company_id: int | None = Field(default=None, ge=1)
    updated_since: str | None = Field(default=None, max_length=64)
    filter: Literal["new_and_my_open", "watching", "spam", "deleted"] | None = None
    order_by: Literal["created_at", "due_by", "updated_at", "status"] = "created_at"
    order_type: Literal["asc", "desc"] = "desc"
    include_description: bool = False

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("email must be a valid email address")
        return value

    @field_validator("updated_since")
    @classmethod
    def validate_updated_since(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("updated_since must not be empty")
        return value.strip() if value else value


class GetTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: int = Field(ge=1)
    include: list[TicketInclude] = Field(default_factory=list, max_length=4)

    @field_validator("include")
    @classmethod
    def deduplicate_includes(cls, value: list[TicketInclude]) -> list[TicketInclude]:
        return list(dict.fromkeys(value))


class SearchTicketsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=512)
    page: int = Field(default=1, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value


class Requester(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None
    email: str | None = None


class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class Ticket(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    subject: str | None = None
    status: int | None = None
    status_label: str | None = None
    priority: int | None = None
    priority_label: str | None = None
    type: str | None = None
    requester_id: int | None = None
    responder_id: int | None = None
    company_id: int | None = None
    requester: Requester | None = None
    company: Company | None = None
    tags: list[str] = Field(default_factory=list)
    description_text: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    due_by: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class PageInfo(BaseModel):
    page: int
    per_page: int
    has_more: bool
    next_page: int | None = None


class TicketPage(BaseModel):
    items: list[Ticket]
    pagination: PageInfo


class SearchPage(BaseModel):
    items: list[Ticket]
    pagination: PageInfo
    total: int | None = None


STATUS_LABELS = {
    2: "open",
    3: "pending",
    4: "resolved",
    5: "closed",
    6: "waiting_on_customer",
    7: "waiting_on_third_party",
}

PRIORITY_LABELS = {1: "low", 2: "medium", 3: "high", 4: "urgent"}


def normalize_ticket(payload: Any) -> Ticket:
    """Convert one Freshdesk-like object into the connector's stable model."""

    if not isinstance(payload, dict):
        raise ValidationError("Freshdesk returned a ticket with an invalid shape.")
    ticket_id = payload.get("id")
    if not isinstance(ticket_id, int) or isinstance(ticket_id, bool) or ticket_id < 1:
        raise ValidationError("Freshdesk returned a ticket without a valid numeric ID.")

    status = payload.get("status")
    priority = payload.get("priority")
    requester_payload = payload.get("requester")
    company_payload = payload.get("company")
    requester = Requester.model_validate(requester_payload) if isinstance(requester_payload, dict) else None
    company = Company.model_validate(company_payload) if isinstance(company_payload, dict) else None
    tags = payload.get("tags")
    custom_fields = payload.get("custom_fields")

    return Ticket(
        id=ticket_id,
        subject=payload.get("subject") if isinstance(payload.get("subject"), str) else None,
        status=status if isinstance(status, int) and not isinstance(status, bool) else None,
        status_label=STATUS_LABELS.get(status, f"status_{status}") if isinstance(status, int) else None,
        priority=priority if isinstance(priority, int) and not isinstance(priority, bool) else None,
        priority_label=PRIORITY_LABELS.get(priority, f"priority_{priority}") if isinstance(priority, int) else None,
        type=payload.get("type") if isinstance(payload.get("type"), str) else None,
        requester_id=payload.get("requester_id") if isinstance(payload.get("requester_id"), int) else None,
        responder_id=payload.get("responder_id") if isinstance(payload.get("responder_id"), int) else None,
        company_id=payload.get("company_id") if isinstance(payload.get("company_id"), int) else None,
        requester=requester,
        company=company,
        tags=[tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else [],
        description_text=(
            payload.get("description_text")
            if isinstance(payload.get("description_text"), str)
            else None
        ),
        created_at=payload.get("created_at") if isinstance(payload.get("created_at"), str) else None,
        updated_at=payload.get("updated_at") if isinstance(payload.get("updated_at"), str) else None,
        due_by=payload.get("due_by") if isinstance(payload.get("due_by"), str) else None,
        custom_fields=custom_fields if isinstance(custom_fields, dict) else {},
    )
