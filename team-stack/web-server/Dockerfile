FROM python:3.11-slim

WORKDIR /app

COPY web-server/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common common
COPY web-server/app.py app.py

EXPOSE 8001

CMD ["python", "app.py"]
