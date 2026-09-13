FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.production.txt /app/backend/requirements.production.txt
RUN python -m pip install --requirement backend/requirements.production.txt
COPY backend /app/backend
RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /data/resumes && chown appuser:appuser /data/resumes
USER appuser
EXPOSE 8000
ENTRYPOINT ["python", "-m", "backend.docker_entrypoint"]
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
