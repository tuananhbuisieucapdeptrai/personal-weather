"""Hardware acceptance app for the production vision module; no image endpoint."""
import json
from http.server import ThreadingHTTPServer
import api
import contracts
import vision

PAGE = b'''<!doctype html><meta charset="utf-8"><title>Personal Weather vision check</title>
<style>body{font:17px system-ui;max-width:900px;margin:30px auto;padding:20px}button{padding:12px;margin:5px}pre{background:#edf2f6;padding:20px;white-space:pre-wrap}.note{background:#fff0cf;padding:16px}</style>
<h1>Personal Weather clothing check v3</h1>
<p>LIVE camera measurements. Experimental presence and clothing classification. Clothing confidence is uncalibrated; live acceptance is required.</p>
<p class="note">No images are saved or served. Visible-face detection plus a full-body fallback provides experimental presence cues, not identity recognition. Looking away or occlusion can still cause misses. Check face_count and presence_cue below. Accuracy is not yet validated.</p>
<button onclick='control({camera:"on"})'>Camera on</button>
<button onclick='control({camera:"off"})'>Camera off</button>
<p>Camera starts only when requested. Closing the shutter for about 3 seconds should release capture. Reopening alone must not restart. Dark-room robustness needs testing.</p>
<p>For presence: stay in view, then leave the frame, then return; hold each for 10 seconds. Compare actual presence with vision.present. Record inference timing below.</p>
<p>Manual clothing controls exercise the existing production API rules:</p>
<button onclick='control({clothing:"outer"})'>Outer layer</button>
<button onclick='control({clothing:"none"})'>No outer layer</button>
<button onclick='control({clothing:"auto"})'>Auto</button>
<p id="error"></p><pre id="state">Loading...</pre>
<script>
async function control(body){let r=await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});document.getElementById('error').textContent=r.ok?'':await r.text();}
setInterval(async()=>{try{let r=await fetch('/state');document.getElementById('state').textContent=JSON.stringify(await r.json(),null,2)}catch(e){document.getElementById('error').textContent=String(e)}},500);
</script>'''


def main():
    control = api.ControlState(on_camera=lambda on: vision.start() if on else vision.stop(),
                               state_dir=None)
    control.apply({'camera': 'off'})

    def snapshot():
        state = vision.latest()
        contracts.check_vision(state)
        clothing, source = control.effective_clothing(state['clothing'])
        return dict(build='clothing-v3', vision=state, diagnostics=vision.diagnostics(),
                    control=control.snapshot(), effective_clothing=clothing,
                    clothing_source=source, presence_validated=False,
                    clothing_classifier=vision.diagnostics().get('clothing_classifier', 'unavailable or camera off'), inputs='live')

    class Handler(api._make_handler(control, snapshot)):
        def do_GET(self):
            if self.path == '/':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(PAGE)))
                self.end_headers()
                self.wfile.write(PAGE)
            else:
                super().do_GET()

    server = ThreadingHTTPServer(('0.0.0.0', 8000), Handler)
    print('Vision check on port 8000. Camera OFF until explicit Camera on.', flush=True)
    try:
        server.serve_forever()
    finally:
        vision.stop()
        server.server_close()


if __name__ == '__main__':
    main()
