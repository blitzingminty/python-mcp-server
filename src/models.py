# src/models.py
# Defines SQLAlchemy ORM models based on schema.ts.txt

import datetime
from sqlalchemy import (
    Table, Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Index, PrimaryKeyConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from typing import List, Optional, Set

# Import the Base class from database.py
from .database import Base

# --- Association Tables for Many-to-Many Relationships ---

document_tags_table = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", Integer, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("tag", Text, primary_key=True),
)

memory_entry_tags_table = Table(
    "memory_entry_tags",
    Base.metadata,
    Column("memory_entry_id", Integer, ForeignKey("memory_entries.id", ondelete="CASCADE"), primary_key=True),
    Column("tag", Text, primary_key=True),
)

memory_entry_document_relations_table = Table(
    "memory_entry_document_relations",
    Base.metadata,
    Column("memory_entry_id", Integer, ForeignKey("memory_entries.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", Integer, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
)

# --- Model Classes ---

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True) # Assuming INTEGER 0/1 maps to Boolean
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    memory_entries: Mapped[List["MemoryEntry"]] = relationship("MemoryEntry", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}')>"

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False) # Consider LargeBinary if content is not text
    version: Mapped[str] = mapped_column(Text, nullable=False, default="1.0.0")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.created_at")
    tags: Mapped[Set[str]] = relationship(
        "Tag", # Assuming you might want a Tag class later, for now maps to string tags
        secondary=document_tags_table,
        collection_class=set # Store tags as a set of strings
        # If you create a Tag class: back_populates="documents"
    )
    memory_entries: Mapped[List["MemoryEntry"]] = relationship(
        "MemoryEntry",
        secondary=memory_entry_document_relations_table,
        back_populates="documents"
    )

    # Add __table_args__ for multi-column indexes if needed, e.g. for unique constraints
    # __table_args__ = (Index('idx_doc_proj_path', 'project_id', 'path', unique=True),)

    def __repr__(self):
        return f"<Document(id={self.id}, name='{self.name}', project_id={self.project_id})>"


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    # Relationship
    document: Mapped["Document"] = relationship("Document", back_populates="versions")

    def __repr__(self):
        return f"<DocumentVersion(id={self.id}, version='{self.version}', document_id={self.document_id})>"


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="memory_entries")
    tags: Mapped[Set[str]] = relationship(
        "Tag", # Assuming you might want a Tag class later, for now maps to string tags
        secondary=memory_entry_tags_table,
        collection_class=set
         # If you create a Tag class: back_populates="memory_entries"
   )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        secondary=memory_entry_document_relations_table,
        back_populates="memory_entries"
    )
    # Relationships for self-referencing MemoryEntryRelation table
    source_relations: Mapped[List["MemoryEntryRelation"]] = relationship(
        "MemoryEntryRelation",
        foreign_keys="MemoryEntryRelation.source_memory_entry_id",
        back_populates="source_entry",
        cascade="all, delete-orphan"
    )
    target_relations: Mapped[List["MemoryEntryRelation"]] = relationship(
        "MemoryEntryRelation",
        foreign_keys="MemoryEntryRelation.target_memory_entry_id",
        back_populates="target_entry",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
         return f"<MemoryEntry(id={self.id}, title='{self.title}', project_id={self.project_id})>"


class MemoryEntryRelation(Base):
    __tablename__ = "memory_entry_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_memory_entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("memory_entries.id", ondelete="CASCADE"), nullable=False)
    target_memory_entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("memory_entries.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships back to MemoryEntry
    source_entry: Mapped["MemoryEntry"] = relationship("MemoryEntry", foreign_keys=[source_memory_entry_id], back_populates="source_relations")
    target_entry: Mapped["MemoryEntry"] = relationship("MemoryEntry", foreign_keys=[target_memory_entry_id], back_populates="target_relations")

    # Add indexes if needed from original schema (not explicitly shown, but likely useful)
    # __table_args__ = (Index('idx_mem_relation_source', 'source_memory_entry_id'),
    #                   Index('idx_mem_relation_target', 'target_memory_entry_id'),)

    def __repr__(self):
         return f"<MemoryEntryRelation(id={self.id}, source={self.source_memory_entry_id}, target={self.target_memory_entry_id})>"

# --- Optional: Tag Model ---
# If you want to manage tags as their own table instead of just strings in association tables:
# class Tag(Base):
#     __tablename__ = "tags" # Or reuse document_tags/memory_entry_tags if combined
#     name: Mapped[str] = mapped_column(Text, primary_key=True)
#     documents: Mapped[List["Document"]] = relationship(secondary=document_tags_table, back_populates="tags")
#     memory_entries: Mapped[List["MemoryEntry"]] = relationship(secondary=memory_entry_tags_table, back_populates="tags")
#
#     def __repr__(self):
#         return f"<Tag(name='{self.name}')>"
