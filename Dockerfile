# One image, three roles (api / worker / beat) selected by the command each
# docker-compose service runs -- see docker-compose.yml. Keeping one image
# rather than three avoids drift between what each process imports; they
# already share the entire codebase in-process (see app/celery_app.py).
FROM python:3.12-slim

WORKDIR /app

# psycopg[binary] and reportlab ship prebuilt wheels for this base image, so
# no compiler toolchain is installed here on purpose -- keep the image small.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 phanda
USER phanda

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
