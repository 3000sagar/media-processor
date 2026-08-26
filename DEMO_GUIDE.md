# Judge Demo Guide

## Problem statement

Media files are large, slow, and unsafe to process inside an HTTP request. A client
needs a way to upload media directly to object storage, receive a quick response, and
have the processing happen reliably in the background.

This project solves that problem with a distributed media-processing service. It accepts
an image or video job, creates a scoped S3 upload, queues processing through Celery, and
publishes a result only after validation and moderation.

## Architecture

```text
Client -> FastAPI -> Redis job state
             |
             +-> presigned S3 upload
             |
             +-> RabbitMQ -> Celery worker -> FFmpeg/Pillow -> S3 output
                                      |
                                      +-> moderation gate -> published URL
```

- FastAPI exposes the job API and health endpoints.
- Redis stores job status and distributed idempotency locks.
- RabbitMQ carries background task messages.
- Celery workers process images and videos outside the request path.
- S3 stores raw uploads and processed output.
- Pillow handles images and FFmpeg handles videos.
- API keys, ownership checks, file-type validation, path-safe keys, rate limits, and
  moderation protect the workflow.

## Run the complete demo with Docker

1. Start Docker Desktop and wait until it reports that the engine is running.
2. From the repository root, run:

```powershell
cd "C:\Users\Asus\OneDrive\Desktop\MEDIA PROCESSOR\media-processor"
Copy-Item .env.example .env -ErrorAction SilentlyContinue
cd infra
docker compose up --build
```

3. In another terminal, check the containers:

```powershell
cd "C:\Users\Asus\OneDrive\Desktop\MEDIA PROCESSOR\media-processor\infra"
docker compose ps
```

4. Open the interactive API documentation:

```text
http://localhost:8000/docs
```

Use `testkey123` as the `X-API-Key` value when trying endpoints in the docs. The
default local configuration maps that key to `owner_1`.

## What to demonstrate

1. Call `GET /api/v1/health`.
2. Call `POST /api/v1/jobs` with an image or video request.
3. Explain that the response contains a `job_id` and a presigned S3 POST.
4. Upload the file using the returned S3 form fields.
5. Call `POST /api/v1/jobs/{job_id}/confirm-upload`.
6. Poll `GET /api/v1/jobs/{job_id}`.
7. Show the status moving from `pending` to `uploaded` and then `completed`.

The completed response contains the processed media URL. A rejected or manual-review
job does not receive a publishable result URL.

## Judge explanation

"This is an asynchronous media-processing backend. The API responds quickly with a
presigned upload instead of receiving a large file directly. Redis tracks the job,
RabbitMQ delivers work, and Celery workers process the media with Pillow or FFmpeg.
Security controls prevent unauthorized job access, unsafe filenames, spoofed file types,
duplicate processing, and publishing content that fails moderation."

## Expected limitations

- The default moderation provider is `none`, so local/demo jobs are auto-approved.
- Real production use still requires choosing a moderation vendor, cloud account, key
  storage, retention policy, log destination, and deployment target. See
  `DECISIONS_NEEDED.md`.
- Docker must be running for the complete local flow. Direct Windows execution also
  needs native `libmagic` and the FFmpeg executable.