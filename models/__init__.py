from peewee import *
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constant import BQ_PATH

database = SqliteDatabase(
    os.path.join(BQ_PATH, 'database', 'bqckup.db'),
    pragmas={ 'journal_mode': 'wal', 'cache_size': -1024 * 64}
)

class BaseModel(Model):
    class Meta:
        database = database