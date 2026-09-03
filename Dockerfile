# One image, three roles (api / worker / beat) selected by the command each
# docker-compose service runs -- see docker-compose.yml. Keeping one image
# rather than three avoids drift between what each process imports; they
# already share the entire codebase in-process (see app/celery_app.py).
FROM python:3.12-slim

WORKDIR /app

# `COPY --chown` below fixes ownership of everything it copies IN to /app,
# but not the /app directory entry itself -- WORKDIR creates that as root,
# and a directory's own owner (not its contents') governs whether a
# non-root user can create new entries in it. Without this line, `phanda`
# could read every file it owned but not create celerybeat-schedule or the
# local storage fallback directory (both new files, not copied ones) --
# verified: beat crashed with a real Permission denied error, and GET
# /ready correctly reported storage: false, until this was added.
RUN useradd --create-home --uid 1000 phanda && chown phanda:phanda /app

# psycopg[binary] and reportlab ship prebuilt wheels for this base image, so
# no compiler toolchain is installed here on purpose -- keep the image small.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --chown, not a separate `RUN chown -R`: celery beat writes its schedule
# file into the working directory (celerybeat-schedule) and local storage
# falls back to a directory under here too (see app/core/storage.py) --
# both need /app writable by the user that actually runs the process, not
# root (verified: beat crashed with `_gdbm.error: Permission denied` before
# this, since COPY without --chown leaves everything root-owned).
COPY --chown=phanda:phanda . .

USER phanda

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
