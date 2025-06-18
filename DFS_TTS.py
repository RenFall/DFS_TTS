import paramiko
import os
import posixpath
import shutil
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from gradio_client import Client, handle_file
import re
import subprocess
import pymysql

def load_config():
    config = {
        # База данных
        'db_host': os.getenv('DB_HOST', 'localhost'),
        'db_port': os.getenv('DB_PORT', '3306'),
        'db_user': os.getenv('DB_USER', ''),
        'db_password': os.getenv('DB_PASSWORD', ''),
        'db_name': os.getenv('DB_NAME', 'Voice_DB'),
        
        # SSH сервер
        'ssh_host': os.getenv('SSH_HOST', ''),
        'ssh_user': os.getenv('SSH_USER', ''),
        'ssh_password': os.getenv('SSH_PASSWORD', ''),
        'ssh_remote_path': os.getenv('SSH_REMOTE_PATH', '/var/spool/asterisk/monitor'),
        
        # Whisper API
        'whisper_api_url': os.getenv('WHISPER_API_URL', 'http://localhost:7860/'),
        
        # HuggingFace токен
        'hf_token': os.getenv('HF_TOKEN', ''),
        
        # Локальная временная директория
        'local_temp_dir': os.getenv('LOCAL_TEMP_DIR', 'TEMP'),
    }
    
    # Проверка обязательных параметров
    required_params = ['db_password', 'ssh_host', 'ssh_password', 'hf_token']
    missing_params = [param for param in required_params if not config[param.replace('_', '_')]]
    
    if missing_params:
        raise ValueError(f"Отсутствуют обязательные переменные окружения: {missing_params}")
    
    return config

config = load_config()

DATABASE_URL = f"mysql+pymysql://{config['db_user']}:{config['db_password']}@{config['db_host']}:{config['db_port']}/{config['db_name']}"
engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Transcription(Base):
    __tablename__ = 'transcriptions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    date_transcription = Column(DateTime, nullable=False)
    file_name = Column(String(255), nullable=False)
    transcription_text = Column(Text)
    flag = Column(Boolean, default=False)

# Create tables
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

#Проверка существования файла в базе данных
def check_file_exists(session, file_name):
    return session.query(Transcription).filter_by(file_name=file_name).first() is not None

def process_audio_file(file_path):
    """код из Gradio Whisper"""
    client = Client(config['whisper_api_url'])
    file = handle_file(file_path)
    try:
        result = client.predict(
            
            files=[file],
            input_folder_path="",
            file_format="txt",
            add_timestamp=False,
            progress="large-v3",
            param_5="russian",
            param_6=False,
            #beam size
            param_7=6,
            param_8=-1,
            param_9=0.4,
            param_10="float16",
            param_11=5,
            param_12=1,
            param_13=True,
            param_14=0.5,
            param_15="",
            param_16=0,
            param_17=1.8,
            param_18=True,
            param_19=0.2,
            param_20=250,
            param_21=9999,
            param_22=1500,
            param_23=2000,
            param_24=24,
            # Включить диаризацию
            param_25=True,
            # Токен HuggingFace
            param_26=config['hf_token'],
            # Устройство (cpu или cuda)
            param_27="cuda",
            param_28=1,
            # Штраф за повторение
            param_29=1.4,
            param_30=0,
            param_31="",
            param_32=True,
            param_33="[-1]",
            param_34=1,
            param_35=False,
            param_36='"¿([{-',
            # Добавляемые знаки препинания
            param_37='。,，!！?？:：")]}、',
            param_38=None,
            param_39=30,
            param_40=None,
            #Словарь
            param_41="",
            param_42=None,
            param_43=1,
            param_44=False,
            param_45="UVR-MDX-NET-Inst_HQ_4",
            param_46="cuda",
            param_47=256,
            param_48=False,
            param_49=True,
            api_name="/transcribe_file"
        )
        
        # Clean up the result text
        pattern = r'^Done in \d+ seconds! Subtitle is in the outputs folder\.\n\n------------------------------------\n[^\n]+\n'
        cleaned_text = re.sub(pattern, '', result[0])
        return cleaned_text
    except Exception as e:
        print(f"Error processing audio file: {e}")
        return None

def dfs_files(sftp_client, directory, session):

    stack = [directory]
    processed_files = []

    while stack:
        current_dir = stack.pop()
        try:
            # Получаем список файлов в текущей директории
            for entry in sftp_client.listdir(current_dir):
                # Нормализуем путь к удаленной директории
                full_path = posixpath.join(current_dir, entry)
                try:
                    # Получаем информацию о файле/директории
                    file_attr = sftp_client.stat(full_path)
                    # Проверка на директорию
                    if file_attr.st_mode & 0o40000:  # Directory
                        print(f"Found directory: {full_path}")
                        stack.append(full_path)
                    # Проверка на файл    
                    elif file_attr.st_mode & 0o100000:  # File
                        if full_path.lower().endswith(('.wav', '.mp3')):
                            file_name = os.path.basename(full_path)
                            if not check_file_exists(session, file_name):
                                print(f"Found new audio file: {full_path}")
                                processed_files.append(full_path)
                            else:
                                print(f"File {file_name} already processed, skipping.")
                except IOError as e:
                    print(f"Error processing {full_path}: {e}")
                    continue
        except IOError as e:
            print(f"Error reading directory {current_dir}: {e}")
            continue

    return processed_files

def process_file(sftp_client, remote_path, local_temp_dir, session):
    """Process a single audio file"""
    try:
        file_name = os.path.basename(remote_path)
        local_path = os.path.join(local_temp_dir, file_name)
        
        print(f"Downloading {remote_path} to {local_path}")
        sftp_client.get(remote_path, local_path)
        
        print(f"Processing {file_name}")
        transcription_text = process_audio_file(local_path)
        
        if transcription_text:
            result = {
                "transcription_text": transcription_text
            }
            
            new_transcription = Transcription(
                date_transcription=datetime.now(),
                file_name=file_name,
                transcription_text=json.dumps(result, ensure_ascii=False),
                flag=True
            )
            
            session.add(new_transcription)
            session.commit()
            print(f"Successfully processed and saved {file_name}")
            
            #Очистить /tmp 
            os.remove(local_path)
            return True
        
        
        return False
    except Exception as e:
        print(f"Error processing file {remote_path}: {e}")
        if os.path.exists(local_path):
            os.remove(local_path)
        session.rollback()
        return False
    finally:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError as e:
                print(f"Error removing temporary file {local_path}: {e}")

def main(hostname, username, password, remote_path, local_temp_dir):
    """Main function to coordinate the scanning and processing"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Создать /tmp
        os.makedirs(local_temp_dir, exist_ok=True)
        
        # Подключение к SSH
        print(f"Connecting to {hostname}...")
        client.connect(
            hostname=hostname,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False
        )
        print("Successfully connected to server")
        
        sftp = client.open_sftp()
        session = Session()
        
        try:
            sftp.stat(remote_path)
            
            #Найти все аудио файлы
            print(f"Scanning directory {remote_path}")
            audio_files = dfs_files(sftp, remote_path, session)
            
            if not audio_files:
                print("No new audio files found")
                return
            
            print(f"Found {len(audio_files)} new audio files")
            
            # Обработать каждый файл
            for remote_file in audio_files:
                success = process_file(sftp, remote_file, local_temp_dir, session)
                if success:
                    print(f"Successfully processed {remote_file}")
                else:
                    print(f"Failed to process {remote_file}")
                
                    
        except IOError as e:
            print(f"Remote directory {remote_path} does not exist: {e}")
        finally:
            session.close()
            sftp.close()
            
    except paramiko.SSHException as e:
        print(f"SSH connection error: {e}")
    except Exception as e:
        print(f"General error: {e}")
    finally:
        client.close()
        print("Connection closed")

if __name__ == "__main__":
    try:
        CONFIG = {
            "hostname": config['ssh_host'],
            "username": config['ssh_user'],
            "password": config['ssh_password'],
            "remote_path": config['ssh_remote_path'],
            "local_temp_dir": config['local_temp_dir']
        }
        
        main(**CONFIG)
        print("Processing completed")
    except ValueError as e:
        print(f"Ошибка конфигурации: {e}")
        print("Убедитесь, что все необходимые переменные окружения установлены.")
    except Exception as e:
        print(f"Ошибка выполнения: {e}")