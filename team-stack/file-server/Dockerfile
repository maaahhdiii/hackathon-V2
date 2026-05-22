FROM python:3.11-slim

WORKDIR /app

COPY file-server/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common common
COPY file-server/app.py app.py

EXPOSE 8003

CMD ["python", "app.py"]
