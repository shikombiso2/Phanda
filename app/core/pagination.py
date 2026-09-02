"""Limit/offset pagination shared by every list endpoint.

Deliberately the simplest correct option, not a cursor scheme: at MVP scale
(a few thousand listings, a handful of applications or saved jobs per user)
offset pagination's one real weakness -- large offsets getting slow -- never
comes up. One `Page[T]` response shape and one query-param dependency means
Android writes one pagination handling path, not one per endpoint.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool


class PageParams(BaseModel):
    limit: int
    offset: int


def pagination_params(limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def page_of(items: list, total: int, params: PageParams) -> Page:
    return Page(items=items, total=total, limit=params.limit, offset=params.offset, has_more=params.offset + len(items) < total)
