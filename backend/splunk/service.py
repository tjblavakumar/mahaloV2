from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.splunk_models import SplunkLog


class SplunkService:
    @staticmethod
    def create_log(
        db: Session,
        source: str,
        level: str,
        message: str,
        service: str,
    ) -> SplunkLog:
        log = SplunkLog(source=source, level=level, message=message, service=service)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def list_logs(db: Session, limit: int = 100) -> List[SplunkLog]:
        return db.query(SplunkLog).limit(limit).all()

    @staticmethod
    def search_logs(db: Session, query: str) -> List[SplunkLog]:
        return db.query(SplunkLog).filter(SplunkLog.message.ilike(f"%{query}%")).all()

    @staticmethod
    def get_logs_by_service(db: Session, service: str) -> List[SplunkLog]:
        return db.query(SplunkLog).filter(SplunkLog.service == service).all()
