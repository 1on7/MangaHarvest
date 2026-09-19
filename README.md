# MangaHarvest

Multi-source manga data aggregation API built with Python, FastAPI, asynchronous web scraping, and MongoDB.

## What it does

MangaHarvest searches multiple manga sources, compares available chapter information, collects manga metadata and chapters, enriches metadata, and stores results in MongoDB for API consumption.

## Architecture

Manga name -> source scrapers -> chapter comparison -> metadata enrichment -> MongoDB -> FastAPI

## Technology

- Python
- FastAPI
- aiohttp
- BeautifulSoup
- MongoDB / PyMongo
- Vercel

## API

- POST /manga/add
- GET /manga/?manga_id=<id>
- GET /manga/search?name=<name>
- GET /manga/latest
- GET /manga/chapters/<id>
- PUT /manga/<id>
- DELETE /manga/<id>

## Configuration

Set MONGO_URI as an environment variable. Never commit real credentials. For local development, copy .env.example to a local .env. For deployment, configure MONGO_URI in the platform environment.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.app:app --reload --host 0.0.0.0 --port 5000
```

## Security

If database credentials have ever been committed to a public repository, rotate them immediately. Removing credentials from the current file does not remove them from Git history.

## Deployment

Production deploys are triggered from the `master` branch.

## License

Apache License 2.0.
