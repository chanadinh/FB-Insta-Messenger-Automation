FROM node:22-alpine AS dashboard-build
WORKDIR /dashboard
COPY dashboard/package*.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

# Playwright Python image — browser version must match requirements.txt (playwright==1.49.0).
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DATA_DIR=/data \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=dashboard-build /dashboard/dist ./dashboard/dist

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
