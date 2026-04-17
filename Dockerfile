FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN mkdir -p /app/config /app/data/input /app/output /run/secrets

COPY config/*.example.json ./config/

RUN pip install --no-cache-dir .

EXPOSE 8000
ENTRYPOINT ["fantranslate"]
CMD ["ui", "--project", "config/project.example.json", "--host", "0.0.0.0", "--port", "8000"]
