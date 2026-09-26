"""Typed, path-independent records for a story construction project."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    world_info_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorldInfo:
    id: str
    name: str
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorldInfoEntry:
    id: str
    world_info_id: str
    title: str
    content: str
    source_ref: str = ""
    version: str = ""


@dataclass(frozen=True, slots=True)
class Character:
    id: str
    project_id: str
    name: str
    content: str
    source_ref: str = ""
    version: str = ""


@dataclass(frozen=True, slots=True)
class NoteCategory:
    id: str
    project_id: str
    name: str
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class Note:
    id: str
    project_id: str
    title: str
    content: str
    category_id: str | None = None
    reference: bool = False
    source_ref: str = ""
    version: str = ""


@dataclass(frozen=True, slots=True)
class Volume:
    id: str
    project_id: str
    title: str


@dataclass(frozen=True, slots=True)
class Chapter:
    id: str
    project_id: str
    volume_id: str
    title: str
    content: str
    source_ref: str = ""
    version: str = ""
