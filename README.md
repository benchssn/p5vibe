# p5vibe

`p5vibe` is a small Flask app for writing, saving, and previewing `p5.js` sketches in the browser.

It provides:

- a CodeMirror-based editor UI
- live sketch preview through an isolated HTML endpoint
- local sketch persistence in SQLite
- bundled `p5.js` assets served from `static/`
- an example `systemd` service for running it continuously on Linux

## Requirements

- Python 3.10+
- network access on first run if `static/p5.min.js` or `static/p5.sound.min.js` are missing

## Install

Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run locally

Start the Flask app with:

```bash
python app.py
```

The app listens on:

- `http://0.0.0.0:5052`
- `http://localhost:5052`

Open the root page in a browser to use the editor.

## How it works

- The main UI is served from `templates/index.html`.
- Sketches are stored in `sketches.db` in the project root.
- Preview rendering is handled by `POST /api/preview`, which returns a standalone HTML page with your sketch injected into it.
- `p5.sound.min.js` is only loaded for previews when the sketch appears to use supported audio APIs.
- If the local `p5` assets are missing, the app downloads them into `static/` on startup.

## API overview

The app exposes a small JSON API for sketch management:

- `GET /api/sketches` lists sketches
- `POST /api/sketches` creates a sketch
- `GET /api/sketches/<id>` fetches one sketch
- `PATCH /api/sketches/<id>` updates name or code
- `DELETE /api/sketches/<id>` deletes a sketch

There is also a simple rendering check at `GET /preview-test`.

## AI support

The codebase includes an AI generation endpoint, but AI features are currently disabled in the app (`AI_ENABLED = False`).

As written, `POST /api/ai` returns a `503` response unless that flag is enabled and a compatible local Ollama server is available at `http://localhost:11434`.

## Run as a service

An example `systemd` unit is included in `p5vibe.service`.

It expects:

- the project to live at `/home/bencpi/Documents/code/p5vibe`
- a virtual environment at `/home/bencpi/Documents/code/p5vibe/venv`
- the service to run as user `bencpi`

If those paths differ on your machine, update the unit file before enabling it.

Typical install steps:

```bash
sudo cp p5vibe.service /etc/systemd/system/p5vibe.service
sudo systemctl daemon-reload
sudo systemctl enable --now p5vibe
sudo systemctl status p5vibe
```

## Notes

- The app runs with `debug=False` by default.
- Sketch data is local only unless you add your own backup or export flow.
- This repository currently has minimal dependency requirements: Flask and Requests.