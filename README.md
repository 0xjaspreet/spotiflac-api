# SpotiFLAC API

FastAPI-based REST API wrapper for [SpotiFLAC](https://github.com/spotbye/SpotiFLAC) — download Spotify content in true FLAC via Qobuz, Amazon Music, and Tidal. No account required.

A thin API layer around [SpotiFLAC (Python Module)](https://github.com/ShuShuzinhuu/SpotiFLAC-Module-Version) that adds:
- **REST endpoints** for remote download triggering
- **Job queue** with status tracking
- **Auto-fallback** across multiple services (qobuz → amazon → tidal)
- **Docker packaging** for headless server deployment

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check, shows config status |
| GET | `/api/search?q=<query>` | Search for tracks/albums (if supported by SpotiFLAC version) |
| POST | `/api/download` | Queue a download. Body: `{"url": "spotify:album:xyz", "output_subdir": "Artist/Album"}` |
| GET | `/api/status` | List recent jobs (last 20) |
| GET | `/api/status/{job_id}` | Get specific job status |

## Quickstart

```bash
# 1. Clone or copy files to Goliath
mkdir -p /home/jaspreet/docker/spotiflac-api/

# 2. Create .env file with Qobuz credentials (SpotiFLAC uses these)
cat > .env << EOF
QOBUZ_EMAIL=your@email.com
QOBUZ_PASSWORD=yourpassword
EOF

# 3. Build and run
docker compose up -d --build

# 4. Check health
curl http://localhost:9118/health

# 5. Download a track
curl -X POST http://localhost:9118/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://open.spotify.com/track/abc123", "output_subdir": "INNA/Hot"}'

# 6. Check progress
curl http://localhost:9118/api/status/{job_id}
```

## Notes

- **Volume**: `/home/jaspreet/storage/music` on Goliath mounts to `/music` in container
- **Port**: `9118` (local only via Tailscale, not exposed publicly)
- **Credentials**: Qobuz email/password injected via `.env` file
- **Permissions**: Runs as UID/GID 1000 (jaspreet user) for proper file ownership
- **Concurrency**: Supports up to 3 simultaneous downloads

## Built With

- [SpotiFLAC](https://github.com/spotbye/SpotiFLAC) — Core FLAC downloader (by [afkarxyz](https://github.com/afkarxyz) / spotbye)
- [SpotiFLAC Python Module](https://github.com/ShuShuzinhuu/SpotiFLAC-Module-Version) — Python library wrapper
- [FastAPI](https://fastapi.tiangolo.com/) — REST framework
- [Uvicorn](https://www.uvicorn.org/) — ASGI server

## License

This project is MIT licensed. SpotiFLAC itself is also MIT licensed.
