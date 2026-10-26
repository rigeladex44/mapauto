FROM python:3.11-slim
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY portal/backend/requirements.lock.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && playwright install --with-deps chromium
COPY portal /app/portal
RUN useradd -m app && mkdir -p /app/portal/runtime && chown -R app:app /app/portal/runtime
USER app
ENV MAP_HEADLESS=true
EXPOSE 8000
CMD ["uvicorn", "portal.backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
