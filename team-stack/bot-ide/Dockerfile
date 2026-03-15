FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    nodejs npm \
    golang-go \
    default-jdk \
    gcc g++ make \
    curl wget git \
    bash \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install requests flask flask-cors beautifulsoup4 colorama
RUN npm install -g axios node-fetch

WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt --no-cache-dir
COPY . .

RUN mkdir -p /app/workspace
RUN cp starter-bots/* /app/workspace/ 2>/dev/null || true

EXPOSE 8080
CMD ["python3", "ide_server.py"]
