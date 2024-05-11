from peewee import AutoField, CharField
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import BaseModel
        
class NotificationLog(BaseModel):
    
    class Meta:
        db_table='notification_logs'
    
    id = AutoField()
    hash = CharField()
    sent_at = CharField()


    # TODO: Fix this duplicate query
    # def update_status(self, id: int, status: int, description=False):
    #     self.update(status=status).where(self.id == id).execute()
    #     if description:
    #         self.update(description=description).where(self.id == id).execute()    
            
    # def write(self, data: dict):
    #     return self.create( name=data['name'], file_path=data['file_path'], description=data['description'], created_at=int(time.time()), type=data['type'], storage=data['storage'], status=self.__ON_PROGRESS__ )    
