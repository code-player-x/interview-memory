FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends fontconfig fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
# 容器内也保留已审核题库和导入命令，避免部署后必须手工拷贝宿主机文件。
COPY scripts/import_questions_v2.py ./scripts/import_questions_v2.py
COPY crawler/questions_v2/authored/ ./crawler/questions_v2/authored/
RUN mkdir -p /app/data/images

EXPOSE 8000

# 进程监听容器网卡；docker-compose 将宿主机发布地址限制为 127.0.0.1。
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
