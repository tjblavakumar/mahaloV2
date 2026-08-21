from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from backend.database import Base


class SplunkLog(Base):
    __tablename__ = "splunk_logs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(120), default="payment-service")
    level = Column(String(20), default="INFO")
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    service = Column(String(80), default="payment-service")
