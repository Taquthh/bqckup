from peewee import *
import os, time, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import BaseModel

class Log(BaseModel):
    # constants
    __SUCCESS__ = 1
    __FAILED__ = 2
    __ON_PROGRESS__ = 3
    __DATABASE__ = 'database'
    __FILES__ = 'files'
    
    id = AutoField()
    name = CharField()
    file_path = CharField()
    file_size = IntegerField(default=0)
    description = TextField()
    created_at = IntegerField()
    type = TextField()
    storage = CharField()
    object_name = TextField(null=True)
    status = IntegerField()
    
    # TODO: Fix this duplicate query
    def update_status(self, id: int, status: int, description=False):
        self.update(status=status).where(self.id == id).execute()
        if description:
            self.update(description=description).where(self.id == id).execute()    
            
    def write(self, data: dict):
        return self.create( name=data['name'], file_path=data['file_path'], description=data['description'], created_at=int(time.time()), type=data['type'], storage=data['storage'], status=self.__ON_PROGRESS__ )    
