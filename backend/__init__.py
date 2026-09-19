"""应用包初始化：在导入任一 backend 模块前读取本地 .env（环境变量优先）。"""
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")
