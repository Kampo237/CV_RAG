from pydantic import BaseModel
from sqlalchemy import Boolean, ForeignKey, Integer, String, Column, JSON
from database import Base
from pgvector.sqlalchemy import Vector


# une classe pour les données réelles :
class Datas(Base):
    __tablename__ = 'datas' #Table de données réelles

    id = Column(Integer, primary_key=True, index=True)
    corpus = Column(String, index=True)
    category = Column(String)  # "expérience", "compétences", "formation"
    extradatas = Column(JSON)  # Infos supplémentaires


class Embeddings(Base):
    __tablename__ = 'embeddings'

    id = Column(Integer, primary_key=True, index=True)
    corpus = Column(String, index=True)
    embedding = Column(Vector(1024))
    category = Column(String)  # "expérience", "compétences", "formation"
    extradatas = Column(JSON)  # Infos supplémentaires