            compressed_file = os.path.join(tmp_path, f"{int(time.time())}.tar.gz")

            print(f"Compressing {backup['path'][0]} for {backup['name']}")

            last_log = self.get_last_log(backup['name'])
            if last_log:
                last_backup_size = last_log.file
                current_file_size = compressed_file
            
                compressed_file = Tar().compress(backup.get('path'), compressed_file)

                compressed_filename = os.path.basename(compressed_file)
                print(f"Compressed file name: {compressed_filename}")
                

                if os.path.exists(compressed_file):
                    current_file_size = os.stat(compressed_file).st_size
                    print(f"\nLast backup file compressed size: {last_backup_size}")
                    print(f"Current file compressed size: {current_file_size}")

                    if current_file_size == last_backup_size:
                        from lib.notifications.discord import send_notification
                        webhook_url = Config().read('notification', 'discord_webhook_url')
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

                    # Write initial log for file compression
                    log_compressed_files = Log().write({
                        "name": backup['name'],
                        "file_path": compressed_file,
                        "description": f"File backup is in progress: {os.path.basename(compressed_file)}",
                        "type": Log.__FILES__,
                        "storage": backup['options']['storage']
                    })

                    Log().update(file_size=current_file_size).where(Log.id == log_compressed_files.id).execute()
                    Log().update_status(log_compressed_files.id, Log.__SUCCESS__, "File Backup Success")