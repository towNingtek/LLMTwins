# source env/bin/activate
# uvicorn server:app --host 0.0.0.0 --port 7999 --reload

docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml up
