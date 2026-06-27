import os, re, sqlite3, json, uuid, requests
from flask import Flask, render_template, jsonify, request, Response, stream_with_context, make_response
from datetime import datetime

app  = Flask(__name__)
DB   = 'sketches.db'
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
AI_ENABLED = False
os.makedirs(STATIC, exist_ok=True)

P5_SYSTEM_PROMPT = (
    "You are an expert p5.js creative coding assistant. "
    "When given a p5.js sketch and an instruction, respond with ONLY the complete "
    "modified JavaScript code. Do not include markdown code fences, backticks, "
    "explanations, or any text other than pure JavaScript. The code must be valid "
    "p5.js that runs in a browser with the p5.js library loaded. Always include "
    "setup() and draw() functions. Do not use import statements or ES modules."
)

PREVIEW_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    * { margin:0; padding:0; box-sizing:border-box }
    body { overflow:hidden; background:#000 }
    canvas { display:block }
</style>
<script src="/static/p5.min.js"></script>
__P5_SOUND__
</head>
<body>
<div id="preview-error" style="display:none;position:fixed;left:12px;right:12px;top:12px;z-index:9999;padding:10px 12px;border:1px solid #ff6b6b;background:rgba(28,0,0,0.9);color:#ffd7d7;font:12px/1.4 monospace;white-space:pre-wrap;border-radius:6px"></div>
<script>
(() => {
    const box = document.getElementById('preview-error');
    const show = (msg) => {
        if (!box) return;
        box.style.display = 'block';
        box.textContent = `Preview error: ${msg}`;
    };
    window.addEventListener('error', (e) => show(e.message || String(e.error || e)));
    window.addEventListener('unhandledrejection', (e) => {
        const reason = e.reason && (e.reason.message || e.reason);
        show(reason || 'Unhandled promise rejection');
    });
})();
</script>
<script>
__P5_CODE__
</script>
</body>
</html>"""

PREVIEW_TEST_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: #05070c; color: #dbe8ff; font: 14px/1.4 monospace; }
    #hint { position: fixed; left: 12px; top: 12px; z-index: 20; opacity: 0.8; }
</style>
<script src="/static/p5.min.js"></script>
</head>
<body>
<div id="hint">p5 preview test page: if you see moving circles, rendering is working.</div>
<script>
function setup() {
    createCanvas(windowWidth, windowHeight);
    textFont('monospace');
}

function draw() {
    background(8, 12, 20);
    const t = frameCount * 0.02;
    const x = width * 0.5 + sin(t) * min(width, 320) * 0.35;
    const y = height * 0.5 + cos(t * 1.4) * min(height, 240) * 0.3;

    noStroke();
    fill(90, 190, 255, 90);
    circle(x, y, 150);
    fill(255, 120, 170, 90);
    circle(width - x, height - y, 120);

    fill(235);
    textAlign(CENTER, CENTER);
    text('Rendering OK', width / 2, height / 2);
}

function windowResized() {
    resizeCanvas(windowWidth, windowHeight);
}
</script>
</body>
</html>"""


def ensure_p5():
    """Download p5.js to static/ on first run so preview works with no CDN dependency."""
    files = [
        ('p5.min.js',       'https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js'),
        ('p5.sound.min.js', 'https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js'),
    ]
    for name, url in files:
        path = os.path.join(STATIC, name)
        if not os.path.exists(path):
            print(f'[p5vibe] Downloading {name}…', flush=True)
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                with open(path, 'wb') as f:
                    f.write(r.content)
                print(f'[p5vibe] {name} saved ({len(r.content)//1024} KB)', flush=True)
            except Exception as e:
                print(f'[p5vibe] Warning: could not download {name}: {e}', flush=True)


def get_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with get_db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sketches (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL DEFAULT 'Untitled Sketch',
                code       TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


init_db()
ensure_p5()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@app.route('/api/preview', methods=['POST'])
def preview():
    """Serve a self-contained sketch HTML page — target of the run/fullscreen forms."""
    code = request.form.get('code', '')
    # Avoid str.format so JavaScript braces in user sketches do not break preview rendering.
    safe_code = code.replace('</script>', '<\\/script>')
    # p5.sound can fail on insecure HTTP contexts on some devices/browsers.
    # Load it only when sketch code appears to need audio APIs.
    needs_sound = bool(re.search(r'\b(p5\.AudioIn|p5\.FFT|getAudioContext|userStartAudio|soundFormats|loadSound)\b', code))
    sound_tag = '<script src="/static/p5.sound.min.js"></script>' if needs_sound else ''
    html = PREVIEW_HTML.replace('__P5_SOUND__', sound_tag).replace('__P5_CODE__', safe_code)
    return html, 200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
    }


@app.route('/preview-test')
def preview_test():
    return PREVIEW_TEST_HTML, 200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
    }


@app.route('/api/models')
def get_models():
    if not AI_ENABLED:
        return jsonify([])
    try:
        r = requests.get('http://localhost:11434/api/tags', timeout=5)
        return jsonify([m['name'] for m in r.json().get('models', [])])
    except Exception:
        return jsonify([])


@app.route('/api/sketches', methods=['GET'])
def list_sketches():
    with get_db() as c:
        rows = c.execute(
            'SELECT id, name, created_at, updated_at FROM sketches ORDER BY updated_at DESC'
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/sketches', methods=['POST'])
def create_sketch():
    data = request.json or {}
    now  = datetime.now().isoformat()
    sid  = str(uuid.uuid4())
    name = data.get('name', 'Untitled Sketch')
    code = data.get('code', '')
    with get_db() as c:
        c.execute('INSERT INTO sketches VALUES (?,?,?,?,?)', (sid, name, code, now, now))
    return jsonify({'id': sid, 'name': name, 'code': code, 'created_at': now, 'updated_at': now})


@app.route('/api/sketches/<sid>', methods=['GET'])
def get_sketch(sid):
    with get_db() as c:
        row = c.execute('SELECT * FROM sketches WHERE id=?', (sid,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))


@app.route('/api/sketches/<sid>', methods=['PATCH'])
def update_sketch(sid):
    data = request.json or {}
    now  = datetime.now().isoformat()
    with get_db() as c:
        for field in ('name', 'code'):
            if field in data:
                c.execute(
                    f'UPDATE sketches SET {field}=?, updated_at=? WHERE id=?',
                    (data[field], now, sid)
                )
    return jsonify({'ok': True})


@app.route('/api/sketches/<sid>', methods=['DELETE'])
def delete_sketch(sid):
    with get_db() as c:
        c.execute('DELETE FROM sketches WHERE id=?', (sid,))
    return jsonify({'ok': True})


@app.route('/api/ai', methods=['POST'])
def ai_generate():
    if not AI_ENABLED:
        return jsonify({'error': 'AI features are temporarily disabled'}), 503

    data        = request.json or {}
    code        = data.get('code', '')
    instruction = data.get('instruction', '').strip()
    model       = data.get('model', 'gemma3:1b')

    if not instruction:
        return jsonify({'error': 'No instruction provided'}), 400

    messages = [
        {'role': 'system', 'content': P5_SYSTEM_PROMPT},
        {'role': 'user',   'content': f"Current sketch:\n\n{code}\n\nInstruction: {instruction}"}
    ]

    def generate():
        try:
            r = requests.post(
                'http://localhost:11434/api/chat',
                json={'model': model, 'messages': messages, 'stream': True},
                stream=True, timeout=180
            )
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get('message', {}).get('content', '')
                if token:
                    yield f"data: {json.dumps({'token': token})}\n\n"
                if chunk.get('done'):
                    break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5052, debug=False)
