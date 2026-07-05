FROM python:3.11-slim

# Run as ROOT (no USER switch). Hugging Face mounts Storage Buckets writable for
# UID 0 only (the FUSE mount is id-mapped to user_id=0); a non-root UID-1000
# container gets "unable to open database file" / Permission denied on the
# /data bucket, so our live-data snapshots would silently fail. Root is the same
# mode Gradio Spaces run in by default. We still create the user dir for a stable
# HOME/WORKDIR. See the persistence notes / DEPLOY.md.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Install dependencies first (lets Docker cache this layer)
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app
COPY --chown=user . .

# Hugging Face serves apps on port 7860
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
