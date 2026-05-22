FROM python:3.11-slim

WORKDIR /app

COPY db-server/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common common
COPY db-server/app.py app.py

EXPOSE 8004

CMD ["python", "app.py"]
