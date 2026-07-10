FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY agents.py /app/agents.py

ENTRYPOINT ["python3", "agents.py"]
# CMD is gone!