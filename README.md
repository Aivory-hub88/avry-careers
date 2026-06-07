# avry-careers

Careers service for the Aivory platform — job listings, applications, and WebSocket real-time updates.

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- PostgreSQL
- WebSocket (real-time updates)
- Docker

## Directory Structure

```
avry-careers/
├── app/            # Application source code
├── migrations/     # Database migrations
├── tests/          # Test suite
├── main.py         # Entry point
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8089 --reload
```

## Docker

```bash
docker compose up --build
```

## VPS Deployment

```bash
docker compose -f docker-compose.yml up -d --build
```

Ensure `.env` is configured on the server with production credentials.

## Part of Aivory

This service is part of the [Aivory platform](https://github.com/ClementHansel/aivory).
