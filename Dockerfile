# One image runs the whole app: the API and the UI together on port 8000.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Install the packages first, so rebuilding after a code change reuses this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# The app creates its own database and loads the employees and templates on startup.
# Hosts like Railway tell the app which port to use through $PORT; when it is not set (docker run, compose) it is 8000.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
