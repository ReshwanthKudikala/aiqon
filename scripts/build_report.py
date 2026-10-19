"""Render docs/technical_report.md to self-contained HTML (and optionally PDF).

Standard library only. Supports the Markdown subset used by the report:
ATX headings, paragraphs, bullet lists, pipe tables, blockquotes, **bold**,
*italic*, `code`. The PDF step drives an installed Chromium browser (Edge or
Chrome) headlessly over the DevTools protocol so the footer carries
"Page x of y"; it is optional and never required by the package.

  python scripts/build_report.py                 # -> docs/technical_report.html
  python scripts/build_report.py --pdf           # also -> docs/technical_report.pdf
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "technical_report.md"
HTML_OUT = ROOT / "docs" / "technical_report.html"
PDF_OUT = ROOT / "docs" / "technical_report.pdf"

CSS = """
@page { size: A4; margin: 18mm 17mm 20mm 17mm; }
html { font-size: 10.4pt; }
body { font-family: Georgia, 'Times New Roman', serif; color: #111; line-height: 1.38; margin: 0; }
h1 { font-family: Arial, Helvetica, sans-serif; font-size: 17pt; margin: 0 0 4pt 0; line-height: 1.2; }
h2 { font-family: Arial, Helvetica, sans-serif; font-size: 11.6pt; margin: 11pt 0 4pt 0; padding-bottom: 1.5pt;
     border-bottom: 0.6pt solid #888; page-break-after: avoid; }
p { margin: 0 0 5.5pt 0; text-align: justify; }
p.lead { color: #333; font-size: 9.6pt; text-align: left; }
ul { margin: 0 0 6pt 0; padding-left: 16pt; }
li { margin: 0 0 2.5pt 0; text-align: justify; }
code { font-family: Consolas, 'Courier New', monospace; font-size: 9pt; background: #f2f2f2; padding: 0 2px; }
blockquote { margin: 3pt 0 7pt 10pt; padding: 3pt 8pt; border-left: 2.5pt solid #999; background: #f7f7f7;
             font-size: 9.4pt; color: #222; }
blockquote p { margin: 0; text-align: left; }
table { border-collapse: collapse; width: 100%; margin: 3pt 0 8pt 0; font-size: 9.2pt; page-break-inside: avoid;
        font-family: Arial, Helvetica, sans-serif; }
th, td { border: 0.6pt solid #999; padding: 2.5pt 5pt; vertical-align: top; text-align: left; }
th { background: #e8e8e8; font-weight: bold; }
td.num, th.num { text-align: right; }
strong { font-weight: bold; }
"""

NUMERIC = re.compile(r"^[\d.,\-+/%() ]+$|^(n=\d+)$")


def inline(text: str) -> str:
    """Escape HTML then apply inline markup: `code`, **bold**, *italic*."""
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(_emphasis(html.escape(text[pos:m.start()])))
        out.append(f"<code>{html.escape(m.group(1))}</code>")
        pos = m.end()
    out.append(_emphasis(html.escape(text[pos:])))
    return "".join(out)


def _emphasis(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return s


def _table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    header, body = cells[0], cells[2:]  # cells[1] is the separator row
    out = ["<table>", "<thead><tr>"]
    for j, c in enumerate(header):
        numeric = all(NUMERIC.match(b[j]) for b in body if j < len(b) and b[j])
        out.append(f"<th class=\"{'num' if numeric else ''}\">{inline(c)}</th>")
    out.append("</tr></thead><tbody>")
    for b in body:
        out.append("<tr>")
        for j, c in enumerate(b):
            out.append(f"<td class=\"{'num' if NUMERIC.match(c) else ''}\">{inline(c)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def convert(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    first_paragraph_after_h1 = False
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("# "):
            out.append(f"<h1>{inline(line[2:].strip())}</h1>")
            first_paragraph_after_h1 = True
            i += 1
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:].strip())}</h2>")
            i += 1
        elif line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i]); i += 1
            out.append(_table(rows))
        elif line.startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].startswith("- "):
                item = [lines[i][2:]]
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    item.append(lines[i].strip()); i += 1
                out.append(f"<li>{inline(' '.join(item))}</li>")
            out.append("</ul>")
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i][1:].strip()); i += 1
            out.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6} |- |>|\s*\|)", lines[i]):
                para.append(lines[i].strip()); i += 1
            cls = ' class="lead"' if first_paragraph_after_h1 else ""
            first_paragraph_after_h1 = False
            out.append(f"<p{cls}>{inline(' '.join(para))}</p>")
    title = re.search(r"^# (.+)$", md, re.M)
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title.group(1) if title else 'Technical report')}</title>"
        f"<style>{CSS}</style></head><body>" + "\n".join(out) + "</body></html>\n"
    )


def find_browser() -> str | None:
    candidates = [
        shutil.which("msedge"), shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


FOOTER = ('<div style="width:100%;font-size:8pt;font-family:Arial,Helvetica,sans-serif;color:#555;'
          'text-align:center;">Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>')


class _WebSocket:
    """Minimal RFC 6455 client (text frames only), enough to talk to DevTools."""

    def __init__(self, url: str):
        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", url)
        if not m:
            raise ValueError(url)
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError("websocket handshake failed")

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126); header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127); header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def recv(self) -> str:
        message = b""
        while True:
            b1, b2 = self._read(2)
            fin, opcode, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            if b2 & 0x80:
                mask = self._read(4)
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._read(n)))
            else:
                data = self._read(n)
            if opcode == 0x8:
                raise ConnectionError("websocket closed by peer")
            if opcode in (0x9, 0xA):
                continue  # ping/pong
            message += data
            if fin:
                return message.decode()

    def close(self) -> None:
        self.sock.close()


def to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Print via DevTools Page.printToPDF on a headless Chromium (Edge/Chrome),
    with CSS @page size/margins and a centred 'Page x of y' footer."""
    browser = find_browser()
    if browser is None:
        sys.exit("no Chromium-based browser found; open the HTML in a browser and print to PDF instead")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
             f"--remote-debugging-port={port}", "--remote-allow-origins=*", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 30
            targets = None
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as r:
                        targets = json.load(r)
                    break
                except (urllib.error.URLError, ConnectionError, OSError):
                    time.sleep(0.25)
            if not targets:
                raise RuntimeError("browser did not expose a DevTools endpoint")
            page = next(t for t in targets if t.get("type") == "page")
            ws = _WebSocket(page["webSocketDebuggerUrl"])
            msg_id = 0

            def call(method: str, **params):
                nonlocal msg_id
                msg_id += 1
                ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
                while True:
                    reply = json.loads(ws.recv())
                    if reply.get("id") == msg_id:
                        if "error" in reply:
                            raise RuntimeError(reply["error"])
                        return reply.get("result", {})

            call("Page.enable")
            call("Page.navigate", url=html_path.resolve().as_uri())
            for _ in range(100):
                state = call("Runtime.evaluate", expression="document.readyState", returnByValue=True)
                if state.get("result", {}).get("value") == "complete":
                    break
                time.sleep(0.1)
            result = call("Page.printToPDF", printBackground=True, preferCSSPageSize=True,
                          displayHeaderFooter=True, headerTemplate="<div></div>", footerTemplate=FOOTER,
                          marginTop=0.71, marginBottom=0.79, marginLeft=0.67, marginRight=0.67)
            pdf_path.write_bytes(base64.b64decode(result["data"]))
            ws.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", action="store_true", help="also render docs/technical_report.pdf with headless Chromium")
    args = ap.parse_args()
    HTML_OUT.write_text(convert(SRC.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {HTML_OUT.relative_to(ROOT)}")
    if args.pdf:
        to_pdf(HTML_OUT, PDF_OUT)
        print(f"wrote {PDF_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
