import os, time, shutil
from classes.database import Database
from classes.storage import Storage
from classes.tar import Tar
from classes.file import File
from classes.config import Config
from classes.yml_parser import Yml_Parser
from models.log import Log
from models.notification_log import NotificationLog
from constant import BQ_PATH, STORAGE_CONFIG_PATH, SITE_CONFIG_PATH
from classes.s3 import s3
from helpers import difference_in_days, get_today, time_since, get_server_ip
from datetime import datetime
from helpers.file_management import remove_folder
from hashlib import sha256
from lib.notifications.discord import send_notification
import time
from hashlib import sha256
from configparser import ConfigParser
class ConfigExceptions(Exception):
    pass

class Bqckup:
    def __init__(self):
        self.last_backup_sizes = {} 
        
        if not os.path.exists(SITE_CONFIG_PATH):
            os.makedirs(SITE_CONFIG_PATH)
            
    def validate_config(self, name: str) -> None:
        print(f"\nChecking {name} config ...")
        config = self.detail(name)
        if not config:
            raise ConfigExceptions(f"Backup {name} not found")

        # validate files
        for path in config.get('path'):
            if not os.path.exists(path):
                raise ConfigExceptions(f"Can't find {path}")
            
        # validate database
        if config.get('database'):
            if config.get('database').get('type') not in Database().SUPPORTED_DATABASE:
                raise ConfigExceptions(f"Database type {config.get('database').get('type')} not supported")
            
            Database(type=config.get('database').get('type')).test_connection({
                "user": config.get('database').get('user'),
                "password": config.get('database').get('password'),
                "host": config.get('database').get('host'),
                "name": config.get('database').get('name')
            })
            
        if config.get('options').get('provider') == 's3':
            Storage().get_storage_detail(config.get('options').get('storage'))
            
        print("All OK !")
            
    def detail(self, name: str):
        backups = self.list()
        
        for i in backups:
            if backups[i]['name'] == name:
                return backups[i]
            
        return None
    
    def _interval_in_number(self, interval: str) -> int:
        if interval == 'weekly':
            return 7
        elif interval == 'monthly':
            return 30
        return 1
    
    def list(self):
        files = File().get_file_list(SITE_CONFIG_PATH)
        files = [file for file in files if file.endswith('.yml')]
        results = {}
        
        for index, file in enumerate(files):
            file_name = os.path.basename(file)
            parsed_content = Yml_Parser.parse(file)
            bqckup = parsed_content['bqckup']
            log = self.get_last_log(bqckup['name'])
            results[index] = {}
            results[index] = bqckup
            results[index]['file_name'] = file_name
            results[index]['last_backup'] = log.created_at if log else None
            
            results[index]['next_backup'] = False
            if results[index]['last_backup']:
                next_backup_in_date = datetime.fromtimestamp(results[index]['last_backup'] + (self._interval_in_number(bqckup['options']['interval']) * 86400)).strftime('%d/%m/%Y 00:00:00')
                results[index]['next_backup'] = time_since(datetime.strptime(next_backup_in_date, '%d/%m/%Y %H:%M:%S').timestamp(), time.time(), reverse=True)
                
        return results
            
    def get_last_log(self, name:str):
        return Log().select().where((Log.name == name) & (Log.status != Log.__FAILED__) & (Log.type == Log.__FILES__)).order_by(Log.id.desc()).first()
        
        
    def get_last_db(self, name:str):
        return Log.select().where((Log.name == name) & (Log.status != Log.__FAILED__) & (Log.type == Log.__DATABASE__)).order_by(Log.id.desc()).first()
        
    def get_logs(self, name: str):
        return list(Log().select().where(Log.name == name))
    
    def backup(self, force:bool = False):
        backups = self.list()
        
        if not backups:
            print("No backups found")
            return
        
        for i in backups:
            backup = backups[i]
            # self.validate_config(backup['name'])
            last_log = self.get_last_log(backup['name'])
            
            if last_log:
                interval = backup['options']['interval']
                last_backup = last_log.created_at
                last_backup = abs(difference_in_days(last_backup, time.time()))
                to_compare = self._interval_in_number(interval)
                
                # Not enough time has passed
                if not force and last_backup < to_compare:
                    print("\n=========================================")
                    print(f"Backup Name: {backup['name']}")
                    print(f"Current Date: {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())}")
                    print(f"Last Backup: {datetime.fromtimestamp(last_log.created_at).strftime('%d/%m/%Y %H:%M:%S')}")
                    print(f"Next bqckup: {datetime.fromtimestamp(last_log.created_at + (to_compare * 86400)).strftime('%d/%m/%Y 00:00:00')}")
                    print(f"Day passed: {last_backup}")
                    print(f"Interval: {interval}")
                    print(f"\nBackup for {backup['name']} is not needed yet...")
                    print("=========================================\n")
                    print(f"Visit: https://bqckup.com\n")
                    continue
                

                
            self.do_backup(backup['file_name'])
    
    # Upload
    def do_backup(self, backup_config):
        try:
            bqckup_config_location = os.path.join(SITE_CONFIG_PATH, backup_config)
            backup = Yml_Parser.parse(bqckup_config_location)['bqckup']
            backup_folder = f"{backup.get('name')}/{get_today()}"
            tmp_path = os.path.join(BQ_PATH, 'tmp', f"{backup.get('name')}")

            if Log().select().where((Log.name == backup.get('name')) & (Log.status == Log.__ON_PROGRESS__)).exists():
                print(f"Backup for {backup.get('name')} is already running...")
                return False

            if not File().is_exists(tmp_path):
                os.makedirs(tmp_path)

            # File Backup        
            print(f"Compressing {backup['path'][0]} for {backup['name']}")
            compressed_file = os.path.join(tmp_path, f"{int(time.time())}.tar.gz")
            Tar().compress(backup.get('path'), compressed_file)

            current_file_size = os.stat(compressed_file).st_size
            last_log = self.get_last_log(backup['name'])
            
            log_compressed_files = None  # Initialize the variable

            if last_log and last_log.file_size is not None and current_file_size == last_log.file_size:
                print(f"Backup file name: {os.path.basename(compressed_file)}")
                print(f"\nCurrent file size: {current_file_size}")
                print(f"Last backup size: {last_log.file_size}")
                print(f"\nSorry, unable to do backup file for {backup['name']}, current file size is exactly same as before.")
                print("Please make sure, your set the right file for this backup")
                webhook_url = Config().read('notification', 'discord_webhook_url')
                compressed_filename = os.path.basename(compressed_file)
                if webhook_url:
                    send_notification({
                                "embeds": [{
                                    "title": "Bqckup File Failed",
                                    "description": "This is an automated notification to inform you that the bqckup has failed.",
                                    "color": 15548997,
                                    "fields": [
                                        {"name": "Date",  "value": get_today(format="%d-%B-%Y"), "inline":True},     
                                        {"name": "Name", "value": backup.get('name'), "inline": True},
                                        {"name": "Server IP", "value": get_server_ip(), "inline": True},
                                        {"name": "File Backup", "value": compressed_filename, "inline": True}, 
                                        {"name": "Details", "value": "Please make sure, your set the right file for this backup", "inline": False}
                                    ],
                                    "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
                                }]
                            })
                    return False
            
            else:
                print("Writing log for file backup in progress...")
                log_compressed_files = Log().write({
                    "name": backup['name'],
                    "file_path": compressed_file,
                    "description": "File backup is in progress...",
                    "type": Log.__FILES__,
                    "file_size": current_file_size,
                    "storage": backup['options']['storage']
                })

            # Database Backup
            if backup.get('database'):
                print(f"\nExporting Database for {backup['name']}")
                sql_path = os.path.join(tmp_path, f"{int(time.time())}.sql.gz")

                Database().export(
                    sql_path,
                    db_user=backup.get('database').get('user'),
                    db_password=backup.get('database').get('password'),
                    db_name=backup.get('database').get('name'),
                )
                

                current_file_size_db = os.stat(sql_path).st_size
                last_log_db = self.get_last_db(backup['name'])
                
                log_database = None  # Initialize the variable

                if last_log_db and last_log_db.file_size is not None and current_file_size_db == last_log_db.file_size:
                    print(f"Database file name: {os.path.basename(sql_path)}")
                    print(f"\nLast database backup size: {last_log_db.file_size}")
                    print(f"Current database backup size: {current_file_size_db}")
                    print(f"\nSorry, unable to do backup database for {backup['name']}, current database size is exactly same as before.")
                    print("Please make sure, your set the right database for this backup")
                    database_filename = os.path.basename(sql_path)
                    webhook_url = Config().read('notification', 'discord_webhook_url')
                    if webhook_url:
                        send_notification({
                                        "embeds": [{
                                            "title": "Bqckup Database Failed",
                                            "description": "This is an automated notification to inform you that the bqckup has failed.",
                                            "color": 15548997,
                                            "fields": [
                                            {"name": "Date",  "value": get_today(format="%d-%B-%Y"), "inline":True},     
                                            {"name": "Name", "value": backup.get('name'), "inline": True},
                                            {"name": "Server IP", "value": get_server_ip(), "inline": True},
                                            {"name": "Database File", "value": database_filename, "inline": True}, 
                                            {"name": "Details", "value": "Please make sure, your set the right database for this backup", "inline": False}
                                            ],
                                            "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
                                                        }]
                                    })
                    return False
                else:
                    print("Writing log for database backup in progress...")
                    log_database = Log().write({
                    "name": backup['name'],
                    "file_path": sql_path,
                    "description": "Database Backup is in Progress",
                    "type": Log.__DATABASE__,
                    "file_size": current_file_size_db,
                    "storage": backup['options']['storage']
                })
                    
            # Local Save
            if backup.get('options').get('provider') == 'local':
                destination = backup.get('options').get('destination')
                backup_path = os.path.join(destination, backup_folder)

                if not os.path.exists(backup_path):
                    os.makedirs(backup_path, exist_ok=True)

                file_backup_complete = False
                database_backup_complete = False

                try:
                    if os.path.exists(compressed_file):
                        shutil.move(compressed_file, os.path.join(backup_path, os.path.basename(compressed_file)))
                        current_file_size = os.stat(os.path.join(backup_path, os.path.basename(compressed_file))).st_size
                        if 'log_compressed_files' in locals() and log_compressed_files is not None:  # Check if the log was created and is not None
                            Log().update(file_size=current_file_size).where((Log.id == log_compressed_files.id) & (Log.type == Log.__FILES__)).execute()
                            Log().update(status=Log.__SUCCESS__, description="File Backup Success").where((Log.id == log_compressed_files.id) & (Log.type == Log.__FILES__)).execute()
                            file_backup_complete = True
                    else:
                        if 'log_compressed_files' in locals() and log_compressed_files is not None:  # Check if the log was created and is not None
                            Log().update(status=Log.__FAILED__, description="File Backup Failed: Compressed file does not exist or could not be moved.").where((Log.id == log_compressed_files.id) & (Log.type == Log.__FILES__)).execute()
                        print(f"Compressed file {compressed_file} does not exist or could not be moved.")

                    if backup.get('database'):
                        if os.path.exists(sql_path):
                            shutil.move(sql_path, os.path.join(backup_path, os.path.basename(sql_path)))
                            current_file_size_db = os.stat(os.path.join(backup_path, os.path.basename(sql_path))).st_size
                            if 'log_database' in locals() and log_database is not None:  # Check if the log was created and is not None
                                Log().update(file_size=current_file_size_db).where((Log.id == log_database.id) & (Log.type == Log.__DATABASE__)).execute()
                                Log().update(status=Log.__SUCCESS__, description="Database Backup Success").where((Log.id == log_database.id) & (Log.type == Log.__DATABASE__)).execute()
                                database_backup_complete = True
                        else:
                            if 'log_database' in locals() and log_database is not None:  # Check if the log was created and is not None
                                Log().update(status=Log.__FAILED__, description="Database Backup Failed: SQL file does not exist or could not be moved.").where((Log.id == log_database.id) & (Log.type == Log.__DATABASE__)).execute()
                            print(f"SQL file {sql_path} does not exist or could not be moved.")
                except Exception as e:
                    print(f"An error occurred while moving files: {e}")

                if file_backup_complete:
                    print(f"\nBackup for {backup['name']} completed: {os.path.basename(compressed_file)}")
                if database_backup_complete:
                    print(f"Database backup for {backup['name']} completed: {os.path.basename(sql_path)}")

                should_save_locally = backup.get('options').get('save_locally')
                save_locally_path = backup.get('options').get('save_locally_path')

                if not should_save_locally:
                    if os.path.exists(os.path.join(backup_path, os.path.basename(compressed_file))):
                        os.unlink(os.path.join(backup_path, os.path.basename(compressed_file)))
                    if os.path.exists(os.path.join(backup_path, os.path.basename(sql_path))):
                        os.unlink(os.path.join(backup_path, os.path.basename(sql_path)))
                elif should_save_locally and save_locally_path:
                    print("\nSaving locally ...")
                    if not os.path.isdir(save_locally_path):
                        raise Exception(f"Save locally path {save_locally_path} is not a directory")
                    else:
                        try:
                            file_saved = False
                            db_saved = False
                            
                            if os.path.exists(os.path.join(backup_path, os.path.basename(compressed_file))):
                                if 'log_compressed_files' in locals() and log_compressed_files is not None:
                                    shutil.copy(os.path.join(backup_path, os.path.basename(compressed_file)), save_locally_path)
                                    file_saved = True
                            if os.path.exists(os.path.join(backup_path, os.path.basename(sql_path))):
                                if 'log_database' in locals() and log_database is not None:
                                    shutil.copy(os.path.join(backup_path, os.path.basename(sql_path)), save_locally_path)
                                    db_saved = True
                            
                            if file_saved:
                                print(f"\nSuccessfully saved {os.path.basename(compressed_file)} to {save_locally_path}")
                            if db_saved:
                                print(f"\nSuccessfully saved {os.path.basename(sql_path)} to {save_locally_path}")
                                
                        except Exception as e:
                            print(f"Failed to save locally: {e}")
                            
        except Exception as e:
            if log_compressed_files:
                Log().update(status=Log.__FAILED__, description=f"File Backup Failed: {str(e)}").where((Log.id == log_compressed_files.id) & (Log.type == Log.__FILES__)).execute()
            if log_database:
                Log().update(status=Log.__FAILED__, description=f"Database Backup Failed: {str(e)}").where((Log.id == log_database.id) & (Log.type == Log.__DATABASE__)).execute()
            print(e)
            return False
    
    def remove(self):
        pass
