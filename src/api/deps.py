"""FastAPI dependencies: DB session, optional auth."""
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.services.database import get_db_session_factory


def get_db_session() -> Generator[Session, None, None]:
    factory = get_db_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db_session)]
