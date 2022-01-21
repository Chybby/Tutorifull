from config import DATABASE, REDIS_PORT
from flask import g
from redis import StrictRedis
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

engine = create_engine(DATABASE)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    import models  # NOQA (ignore unused import error)
    Base.metadata.create_all(engine)


def get_redis():
    redis = getattr(g, '_redis', None)
    if redis is None:
        redis = g._redis = StrictRedis(host='localhost', port=REDIS_PORT, db=0)
    return redis
