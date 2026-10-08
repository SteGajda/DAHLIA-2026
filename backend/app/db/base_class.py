"""SQLAlchemy declarative base class.

This module defines the single :class:`Base` instance that every ORM model
in the DAHLIA backend must inherit from.

It is intentionally kept minimal — no model imports here — so that model
modules can safely import :data:`Base` without triggering circular imports.

For Alembic autogenerate, import from :mod:`app.db.base` instead, which
re-imports all models as a side-effect so that ``Base.metadata`` is fully
populated.

Usage in a model module::

    from app.db.base_class import Base

    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all DAHLIA ORM models.

    All SQLAlchemy model classes must inherit from this class.  Using
    ``DeclarativeBase`` (SQLAlchemy 2.0+ style) instead of the legacy
    ``declarative_base()`` factory ensures full compatibility with the
    modern typed-mapping API.
    """
