FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    S1_IMPL=stub \
    S2_IMPL=stub \
    MEMORY_IMPL=mock

EXPOSE 8000

# Same process as `make serve`.
CMD ["make", "serve"]
