FROM python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
COPY requirements/ ./requirements/
RUN python -m pip install --upgrade pip==26.2 && python -m pip install -r requirements/base.txt -r requirements/dashboard.txt && python -m pip check
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY . .
RUN mkdir -p /app/data/raw /app/data/cache /app/data/processed /app/logs && chown -R app:app /app/data /app/logs
USER app
EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"
CMD ["python", "-m", "streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.headless=true", "--server.runOnSave=false", "--browser.gatherUsageStats=false"]
