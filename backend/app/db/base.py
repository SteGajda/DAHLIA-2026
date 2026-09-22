"""SQLAlchemy declarative base and metadata registry.

This module re-exports :class:`~app.db.base_class.Base` and imports all
ORM models so that Alembic's ``env.py`` can discover the full schema
through ``Base.metadata`` after importing this module.
"""

# Re-export Base so callers that previously imported from here still work.
from app.db.base_class import Base  # noqa: F401

# Model imports — keep this section in sync with app/models/
# Alembic autogenerate will only detect tables whose models are imported here.
from app.models.user import AppUser, RefreshToken, RoleRequest  # noqa: F401
