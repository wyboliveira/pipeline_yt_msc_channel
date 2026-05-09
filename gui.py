"""
gui.py
Interface web do pipeline OvxrNight — FastAPI + WebSocket + Tailwind CSS.

Uso:
    python gui.py
"""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

# ── HTML Template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>OvxrNight Control Center</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='14' fill='%230E1120'/><path d='M20 8a10 10 0 1 0 0 16 8 8 0 1 1 0-16z' fill='%238B9FE8'/></svg>"/>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        app:    '#0E1120',
        panel:  '#151829',
        card:   '#1C2138',
        inp:    '#232840',
        rowsel: '#1E2A50',
        brd:    '#252D48',
      }
    }
  }
}
</script>
<style>
*  { box-sizing: border-box; }
body { margin:0; background:#0E1120; color:#E2E8F0; font-family:'Segoe UI',sans-serif; height:100vh; overflow:hidden; display:flex; flex-direction:column; }

/* scrollbar */
::-webkit-scrollbar        { width:5px; height:5px; }
::-webkit-scrollbar-track  { background:#151829; }
::-webkit-scrollbar-thumb  { background:#252D48; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#7B5CF0; }

/* buttons */
.btn { display:inline-flex; align-items:center; justify-content:center; gap:6px;
       border:none; border-radius:6px; font-weight:700; cursor:pointer;
       transition:background 0.15s, opacity 0.15s, transform 0.1s; font-family:inherit; }
.btn:hover:not(:disabled) { filter:brightness(1.12); }
.btn:active:not(:disabled) { transform:scale(0.97); }
.btn:disabled { opacity:0.4; cursor:not-allowed; pointer-events:none; }

.btn-accent  { background:#7B5CF0; color:#fff; }
.btn-green   { background:#0A6B52; color:#fff; }
.btn-blue    { background:#1E4070; color:#fff; }
.btn-red     { background:#7A1515; color:#fff; }
.btn-neutral { background:#232840; color:#8892A4; }
.btn-neutral:hover:not(:disabled) { background:#2A3255; color:#E2E8F0; }
.btn-ghost   { background:transparent; color:#8892A4; border:1px solid #252D48; }
.btn-ghost:hover:not(:disabled) { background:#232840; color:#E2E8F0; }

/* inputs */
input, textarea {
  background:#232840; border:1px solid #252D48; color:#E2E8F0;
  border-radius:6px; padding:7px 10px; width:100%; outline:none;
  font-family:inherit; font-size:13px; transition:border-color 0.15s;
}
input:focus, textarea:focus { border-color:#7B5CF0; }
textarea { resize:vertical; }
input::placeholder, textarea::placeholder { color:#4A5568; }

/* track rows */
.track-row {
  display:flex; align-items:center; gap:6px; padding:0 10px;
  height:44px; border-radius:4px; cursor:pointer;
  background:#181E35; transition:background 0.12s;
  border-left:3px solid transparent;
}
.track-row:hover { background:#1E2A50; }
.track-row.active { background:#1E2A50; border-left-color:#7B5CF0; }

/* step rows */
.step-row {
  display:flex; align-items:center; justify-content:space-between;
  padding:9px 14px; border-radius:4px; transition:background 0.2s;
}
.step-row.running { background:#1E2A50; }
.step-row.done    { background:#0D2318; }
.step-row.error   { background:#2A0D0D; }

/* badge */
.badge {
  display:inline-flex; align-items:center; padding:2px 9px;
  border-radius:4px; font-size:11px; font-weight:700; white-space:nowrap;
}

/* log */
.log-line { font-family:Consolas,monospace; font-size:11.5px; line-height:1.5; white-space:pre-wrap; word-break:break-all; color:#8892A4; }

/* section title */
.sec { color:#7B5CF0; font-size:11px; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; }

/* divider */
.hr { border:none; border-top:1px solid #252D48; margin:8px 0; }

/* panels */
.left-panel  { width:288px; min-width:288px; border-right:1px solid #252D48; background:#151829; display:flex; flex-direction:column; overflow:hidden; }
.right-panel { width:300px; min-width:300px; border-left:1px solid #252D48; background:#151829; display:flex; flex-direction:column; overflow:hidden; }
.center { flex:1; overflow:hidden; display:flex; flex-direction:column; }
</style>
</head>
<body>

<!-- ── Title bar ─────────────────────────────────────────────────────────── -->
<div style="background:#151829; border-bottom:1px solid #252D48; padding:10px 18px; display:flex; align-items:center; gap:10px; flex-shrink:0;">
  <span style="color:#7B5CF0;font-weight:900;font-size:13px;letter-spacing:.14em;">OVXRNIGHT</span>
  <span style="color:#E2E8F0;font-weight:700;font-size:15px;flex:1;">Control Center</span>
  <button class="btn btn-neutral" style="height:28px;padding:0 12px;font-size:12px;" onclick="shutdownApp()" title="Encerrar aplicação">⏻ Encerrar</button>
  <span id="ws-badge" class="badge" style="background:#0D2318;color:#22C55E;font-size:11px;">● CONNECTED</span>
</div>

<!-- ── Main layout ────────────────────────────────────────────────────────── -->
<div style="flex:1;display:flex;overflow:hidden;">

  <!-- LEFT ────────────────────────────────────────────────────────────────── -->
  <div class="left-panel">

    <!-- Queue header -->
    <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px 8px;">
      <span class="sec">Queue Management</span>
      <button class="btn btn-neutral" style="width:26px;height:26px;font-size:14px;padding:0;" title="Configurações">⚙</button>
    </div>

    <!-- Inbox card -->
    <div style="margin:0 10px 6px;background:#1C2138;border-radius:8px;padding:10px 12px;">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <span id="inbox-count" style="color:#E2E8F0;font-size:12px;font-weight:700;">INBOX</span>
        <span style="color:#8892A4;font-size:16px;letter-spacing:2px;">···</span>
      </div>
      <div style="color:#8892A4;font-size:11px;margin-top:2px;">Ordenado do mais antigo</div>
    </div>

    <!-- Add file button -->
    <div style="padding:0 10px 6px;">
      <button class="btn btn-ghost" style="width:100%;height:32px;font-size:12px;" onclick="pickFile()">
        📂 Adicionar arquivo ao inbox
      </button>
    </div>

    <!-- Queue list -->
    <div id="queue-list" style="flex:1;overflow-y:auto;padding:0 10px;display:flex;flex-direction:column;gap:3px;"></div>

    <!-- Review Queue -->
    <div style="margin:6px 10px 4px;background:#1C2138;border-radius:8px;padding:10px 12px;">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <span id="review-count" style="color:#E2E8F0;font-size:12px;font-weight:700;">REVIEW (0)</span>
        <button class="btn btn-neutral" style="width:26px;height:26px;font-size:13px;padding:0;" onclick="openReview()" title="Abrir pasta /review">📁</button>
      </div>
      <div style="color:#8892A4;font-size:11px;margin-top:2px;">Prontos para publicar</div>
    </div>
    <div id="review-list" style="max-height:120px;overflow-y:auto;padding:0 10px 2px;display:flex;flex-direction:column;gap:3px;"></div>

    <hr class="hr" style="margin:8px 10px;"/>

    <!-- Real-Time Log -->
    <div style="display:flex;align-items:center;justify-content:space-between;padding:0 16px 6px;">
      <span class="sec">Real-Time Log</span>
      <button class="btn btn-neutral" style="height:24px;padding:0 10px;font-size:11px;" onclick="clearLog()">Limpar</button>
    </div>
    <div id="log-box" style="flex:0 0 220px;overflow-y:auto;margin:0 10px 10px;padding:8px 10px;background:#1C2138;border:1px solid #252D48;border-radius:8px;display:flex;flex-direction:column;gap:1px;"></div>
  </div>

  <!-- CENTER ───────────────────────────────────────────────────────────────── -->
  <div class="center">

    <!-- Workspace header -->
    <div style="padding:16px 20px 10px;flex-shrink:0;">
      <div class="sec" style="margin-bottom:4px;">Active Workspace</div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
        <div id="song-title" style="color:#E2E8F0;font-size:20px;font-weight:700;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          Nenhum arquivo selecionado
        </div>
        <button id="btn-start" class="btn btn-accent" style="height:36px;padding:0 20px;font-size:13px;flex-shrink:0;" disabled onclick="startPipeline()">▶ Iniciar Pipeline</button>
      </div>
    </div>

    <!-- Review mode bar -->
    <div id="review-mode-bar" style="display:none;margin:0 12px 6px;background:#1A1034;border:1px solid #3D2A8A;border-radius:8px;padding:8px 14px;align-items:center;gap:10px;">
      <span style="color:#7B5CF0;font-size:11px;font-weight:700;letter-spacing:.1em;flex-shrink:0;">MODO REVIEW</span>
      <span id="review-video-label" style="color:#8892A4;font-size:11px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">—</span>
      <button class="btn btn-neutral" style="height:26px;padding:0 10px;font-size:11px;flex-shrink:0;" onclick="exitReviewMode()">✕ Sair</button>
    </div>

    <!-- Cards area -->
    <div style="flex:1;overflow-y:auto;padding:0 12px 12px;">

      <!-- Row 1: Metadata + Image -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">

        <!-- Metadata card -->
        <div style="background:#1C2138;border-radius:10px;padding:16px;">
          <div class="sec" style="margin-bottom:12px;">Metadata Edit</div>

          <div style="margin-bottom:10px;">
            <div style="color:#8892A4;font-size:11px;font-weight:700;margin-bottom:5px;">TITLE</div>
            <div style="display:flex;gap:8px;">
              <input id="inp-title" type="text" placeholder="Artista - Nome da Música" style="flex:1;"/>
              <button id="btn-confirm-inline" class="btn btn-accent" style="height:35px;padding:0 12px;font-size:12px;flex-shrink:0;" disabled onclick="confirmTitle()">Confirm Title</button>
            </div>
          </div>

          <div style="margin-bottom:10px;">
            <div style="color:#8892A4;font-size:11px;font-weight:700;margin-bottom:5px;">DESCRIPTION</div>
            <textarea id="inp-desc" rows="4" placeholder="Descrição do vídeo..."></textarea>
          </div>

          <div style="margin-bottom:14px;">
            <div style="color:#8892A4;font-size:11px;font-weight:700;margin-bottom:5px;">TAGS</div>
            <input id="inp-tags" type="text" placeholder="slowed, reverb, anime, ..."/>
          </div>

          <button id="btn-confirm-full" class="btn btn-accent" style="width:100%;height:40px;font-size:13px;" disabled onclick="confirmTitle()">Confirm Title</button>

          <!-- Review actions (visíveis só no modo review) -->
          <div id="review-actions" style="display:none;flex-direction:column;gap:6px;margin-top:6px;">
            <button id="btn-gen-meta" class="btn btn-blue" style="width:100%;height:36px;font-size:12px;" onclick="genReviewMeta()">⚡ Gerar Metadados</button>
            <button id="btn-publish-review" class="btn btn-accent" style="width:100%;height:40px;font-size:13px;" onclick="publishReview()">▶ Publicar da Review</button>
          </div>
        </div>

        <!-- Image card -->
        <div style="background:#1C2138;border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:10px;">
          <div class="sec">Image Review</div>

          <!-- Preview -->
          <div id="img-area" style="background:#232840;border-radius:8px;height:190px;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative;cursor:pointer;" onclick="openLightbox()" title="Clique para expandir">
            <span id="img-placeholder" style="color:#8892A4;font-size:13px;">Aguardando geração da imagem...</span>
            <img id="img-el" src="" alt="preview" style="display:none;width:100%;height:100%;object-fit:contain;"/>
            <div id="img-expand-hint" style="display:none;position:absolute;bottom:7px;right:8px;background:rgba(0,0,0,0.65);border-radius:4px;padding:2px 8px;font-size:11px;color:#CBD5E1;pointer-events:none;">🔍 Expandir</div>
          </div>

          <!-- Prompt info -->
          <div>
            <div style="color:#8892A4;font-size:11px;font-weight:700;margin-bottom:4px;">Prompt Elements:</div>
            <div id="img-char"  style="color:#8892A4;font-size:12px;">Character: —</div>
            <div id="img-scene" style="color:#8892A4;font-size:12px;">Scene: —</div>
            <div id="img-style" style="color:#8892A4;font-size:12px;">Style: —</div>
          </div>

          <!-- Image action buttons -->
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px;margin-top:auto;">
            <button id="btn-img-ok"     class="btn btn-green"   style="height:36px;font-size:12px;" disabled onclick="imgDecision('s')">Aprovar</button>
            <button id="btn-img-new"    class="btn btn-blue"    style="height:36px;font-size:12px;" disabled onclick="imgDecision('n')">Nova Imagem</button>
            <button id="btn-img-choose" class="btn btn-neutral" style="height:36px;font-size:12px;" disabled onclick="chooseImage()">📂 Escolher</button>
          </div>
        </div>
      </div>

      <!-- Row 2: Video card -->
      <div style="background:#1C2138;border-radius:10px;padding:16px;">
        <div class="sec" style="margin-bottom:12px;">Video Preview</div>
        <div style="display:grid;grid-template-columns:3fr 2fr;gap:14px;">

          <!-- Left: player -->
          <div style="display:flex;flex-direction:column;gap:8px;">
            <div id="vid-area" style="background:#232840;border-radius:8px;height:148px;display:flex;align-items:center;justify-content:center;">
              <span id="vid-placeholder" style="color:#8892A4;font-size:13px;">Aguardando vídeo...</span>
            </div>
            <!-- Progress bar -->
            <div style="background:#232840;border-radius:3px;height:4px;overflow:hidden;">
              <div id="vid-progress" style="background:#7B5CF0;height:100%;width:0%;transition:width 0.4s;"></div>
            </div>
            <!-- Controls -->
            <div style="display:flex;align-items:center;gap:6px;">
              <button class="btn btn-neutral" style="width:32px;height:30px;font-size:13px;padding:0;" onclick="openVideo()">▶</button>
              <button class="btn btn-neutral" style="width:30px;height:30px;font-size:13px;padding:0;">⏸</button>
              <button class="btn btn-neutral" style="width:30px;height:30px;font-size:13px;padding:0;">⏭</button>
              <div style="flex:1;"></div>
              <button class="btn btn-neutral" style="width:30px;height:30px;font-size:13px;padding:0;">🔊</button>
              <button class="btn btn-neutral" style="width:30px;height:30px;font-size:13px;padding:0;">⛶</button>
            </div>
          </div>

          <!-- Right: publish actions -->
          <div style="display:flex;flex-direction:column;gap:8px;">
            <div id="vid-name" style="color:#8892A4;font-size:12px;word-break:break-all;min-height:32px;">—</div>
            <button class="btn btn-neutral" style="height:32px;font-size:12px;" onclick="openReview()">📁 Abrir /review</button>
            <div style="flex:1;"></div>
            <button id="btn-publish" class="btn btn-accent" style="height:40px;font-size:13px;" disabled onclick="vidDecision('s')">▶ Publicar no YouTube</button>
            <button id="btn-reject"  class="btn btn-red"    style="height:34px;font-size:12px;" disabled onclick="vidDecision('n')">✗ Descartar Vídeo</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- RIGHT ───────────────────────────────────────────────────────────────── -->
  <div class="right-panel">

    <!-- Header -->
    <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px 10px;">
      <span class="sec">Pipeline Monitoring</span>
      <span style="color:#8892A4;font-size:16px;">ⓘ</span>
    </div>

    <!-- Task status card -->
    <div style="margin:0 10px 10px;background:#1C2138;border-radius:8px;overflow:hidden;">
      <div style="padding:8px 14px 4px;color:#8892A4;font-size:11px;font-weight:700;">TASK STATUS</div>
      <div id="step-0" class="step-row">
        <span style="font-size:13px;font-weight:600;">1. Metadata</span>
        <span class="badge" style="background:#1E2340;color:#8892A4;">PENDING</span>
      </div>
      <div id="step-1" class="step-row">
        <span style="font-size:13px;font-weight:600;">2. Image</span>
        <span class="badge" style="background:#1E2340;color:#8892A4;">PENDING</span>
      </div>
      <div id="step-2" class="step-row">
        <span style="font-size:13px;font-weight:600;">3. Video</span>
        <span class="badge" style="background:#1E2340;color:#8892A4;">PENDING</span>
      </div>
      <div id="step-3" class="step-row">
        <span style="font-size:13px;font-weight:600;">4. Upload</span>
        <span class="badge" style="background:#1E2340;color:#8892A4;">PENDING</span>
      </div>
      <div style="height:6px;"></div>
    </div>

    <!-- History -->
    <hr class="hr" style="margin:4px 10px 8px;"/>
    <div style="padding:0 16px 8px;">
      <span class="sec">History</span>
    </div>

    <!-- Published -->
    <div style="padding:0 14px 5px;">
      <span style="color:#22C55E;font-size:11px;font-weight:700;letter-spacing:.08em;">PUBLISHED</span>
    </div>
    <div id="hist-pub" style="flex:1;overflow-y:auto;padding:0 10px 6px;display:flex;flex-direction:column;gap:2px;"></div>

    <!-- Rejected -->
    <div style="padding:6px 14px 5px;">
      <span style="color:#EF4444;font-size:11px;font-weight:700;letter-spacing:.08em;">REJECTED</span>
    </div>
    <div id="hist-rej" style="flex:0 0 110px;overflow-y:auto;padding:0 10px 12px;display:flex;flex-direction:column;gap:2px;"></div>
  </div>
</div>

<!-- Toast -->
<div id="toast" style="display:none;position:fixed;bottom:20px;right:20px;z-index:9999;max-width:340px;background:#1C2138;border:1px solid #252D48;border-radius:12px;padding:14px 18px;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
  <div id="toast-title" style="font-weight:700;font-size:13px;margin-bottom:4px;"></div>
  <div id="toast-msg" style="color:#8892A4;font-size:12px;word-break:break-all;"></div>
</div>

<!-- Lightbox -->
<div id="lightbox" style="display:none;position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.93);" onclick="if(event.target===this)closeLightbox()">
  <!-- Controls bar -->
  <div style="position:absolute;top:0;left:0;right:0;display:flex;align-items:center;justify-content:flex-end;gap:8px;padding:12px 16px;background:linear-gradient(rgba(0,0,0,0.6),transparent);z-index:1;pointer-events:none;">
    <span style="color:#4A5568;font-size:11px;flex:1;">Scroll → zoom &nbsp;·&nbsp; Arrastar → mover &nbsp;·&nbsp; ESC → fechar</span>
    <button class="btn btn-neutral" style="height:30px;padding:0 13px;font-size:16px;pointer-events:all;" onclick="lbZoom(0.3)" title="Zoom +">＋</button>
    <button class="btn btn-neutral" style="height:30px;padding:0 13px;font-size:16px;pointer-events:all;" onclick="lbZoom(-0.3)" title="Zoom −">－</button>
    <button class="btn btn-neutral" style="height:30px;padding:0 13px;font-size:12px;pointer-events:all;" onclick="lbReset()" title="Resetar zoom">1:1</button>
    <button class="btn btn-red"     style="height:30px;padding:0 14px;font-size:13px;pointer-events:all;" onclick="closeLightbox()" title="Fechar">✕</button>
  </div>
  <!-- Image (centered via flex on lightbox) -->
  <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;" onclick="if(event.target===document.getElementById('lightbox'))closeLightbox()">
    <img id="lb-img" src="" draggable="false" style="max-width:92vw;max-height:92vh;object-fit:contain;border-radius:6px;cursor:grab;user-select:none;transform-origin:center center;" onclick="event.stopPropagation()"/>
  </div>
</div>

<script>
// ── State ────────────────────────────────────────────────────────────────────
let ws = null;
let reconnectTimer = null;
let currentVideoPath = null;
let selectedIndex = 0;
let queueItems = [];
let reviewMode = false;
let selectedReviewVideo = null;
let reviewItems = [];

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws');
  ws.onopen  = () => { setWsBadge(true);  clearTimeout(reconnectTimer); loadQueue(); loadHistory(); loadReviewQueue(); };
  ws.onclose = () => { setWsBadge(false); reconnectTimer = setTimeout(connect, 2500); };
  ws.onerror = () => ws.close();
  ws.onmessage = e => { const m = JSON.parse(e.data); (handlers[m.type] || (() => {}))(m); };
}

function wsSend(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function setWsBadge(ok) {
  const el = document.getElementById('ws-badge');
  el.textContent  = ok ? '● CONNECTED' : '● OFFLINE';
  el.style.background = ok ? '#0D2318' : '#2A0D0D';
  el.style.color      = ok ? '#22C55E' : '#EF4444';
}

// ── Message handlers ──────────────────────────────────────────────────────────
const handlers = {
  log(m)           { appendLog(m.msg); },
  step(m)          { setStep(m.index, m.status); },
  meta_ready(m)    { onMetaReady(m); },
  img_ready(m)     { onImgReady(m); },
  vid_ready(m)     { onVidReady(m); },
  done_ok(m)       { onDoneOk(m.url); },
  done_ko(m)       { onDoneKo(m.msg); },
  queue_update(m)  { renderQueue(m.items); },
  history_update(m){ renderHistory(m.published, m.rejected); },
  review_update(m) { renderReviewQueue(m.items); },
};

// ── Log ────────────────────────────────────────────────────────────────────────
function appendLog(msg) {
  const box = document.getElementById('log-box');
  const ts  = new Date().toTimeString().slice(0,8);
  const el  = document.createElement('div');
  el.className = 'log-line';
  el.textContent = '[' + ts + '] ' + msg;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}
function clearLog() { document.getElementById('log-box').innerHTML = ''; }

// ── Steps ──────────────────────────────────────────────────────────────────────
const STEP_CFG = {
  idle:    { cls:'',        badge:'PENDING', bg:'#1E2340', col:'#8892A4', lc:'#8892A4' },
  running: { cls:'running', badge:'ACTIVE',  bg:'#7B5CF0', col:'#ffffff', lc:'#E2E8F0' },
  done:    { cls:'done',    badge:'OK',      bg:'#0A3D20', col:'#22C55E', lc:'#E2E8F0' },
  error:   { cls:'error',   badge:'ERROR',   bg:'#4A1010', col:'#EF4444', lc:'#EF4444' },
};
function setStep(i, status) {
  const row = document.getElementById('step-' + i);
  if (!row) return;
  const cfg = STEP_CFG[status] || STEP_CFG.idle;
  row.className = 'step-row ' + cfg.cls;
  row.querySelector('.badge').textContent   = cfg.badge;
  row.querySelector('.badge').style.background = cfg.bg;
  row.querySelector('.badge').style.color      = cfg.col;
  row.querySelector('span:first-child').style.color = cfg.lc;
}

// ── Queue ──────────────────────────────────────────────────────────────────────
async function loadQueue() {
  const r = await fetch('/api/queue');
  const d = await r.json();
  renderQueue(d.items);
}
function renderQueue(items) {
  queueItems = items;
  if (selectedIndex >= items.length) selectedIndex = 0;

  const list = document.getElementById('queue-list');
  list.innerHTML = '';
  document.getElementById('inbox-count').textContent =
    'INBOX  (' + items.length + (items.length === 1 ? ' Track' : ' Tracks') + ')';

  if (items.length === 0) {
    document.getElementById('song-title').textContent = 'Inbox vazia';
    document.getElementById('song-title').style.color = '#8892A4';
    document.getElementById('btn-start').disabled = true;
    return;
  }

  items.forEach((item, i) => {
    const row = document.createElement('div');
    const isActive = i === selectedIndex;
    row.className = 'track-row' + (isActive ? ' active' : '');
    const stem = item.stem.length > 26 ? item.stem.slice(0,24) + '…' : item.stem;
    row.innerHTML =
      '<span style="color:' + (isActive ? '#7B5CF0' : '#8892A4') + ';font-size:14px;flex-shrink:0;">♪</span>' +
      '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:600;color:' + (isActive ? '#E2E8F0' : '#8892A4') + ';">' +
        String(i+1).padStart(2,'0') + '. ' + stem + '</span>' +
      '<span style="color:#8892A4;font-size:11px;flex-shrink:0;">' + item.date + '</span>';
    row.onclick = () => selectTrack(i);
    list.appendChild(row);
  });

  updateWorkspaceTitle();
  document.getElementById('btn-start').disabled = false;
}

function selectTrack(i) {
  selectedIndex = i;
  renderQueue(queueItems);
}

function updateWorkspaceTitle() {
  if (!queueItems.length) return;
  const stem = queueItems[selectedIndex].stem;
  const titleEl = document.getElementById('song-title');
  titleEl.textContent = stem.length > 58 ? stem.slice(0,56) + '…' : stem;
  titleEl.style.color = '#E2E8F0';
}

// ── History ────────────────────────────────────────────────────────────────────
async function loadHistory() {
  const r = await fetch('/api/history');
  const d = await r.json();
  renderHistory(d.published, d.rejected);
}
function renderHistory(pub, rej) {
  const pubEl = document.getElementById('hist-pub');
  pubEl.innerHTML = '';
  pub.forEach(n => {
    const el = document.createElement('div');
    el.style.cssText = 'font-size:12px;color:#22C55E;background:#0D2318;border-radius:4px;padding:4px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    el.title = n;
    el.textContent = n;
    pubEl.appendChild(el);
  });
  const rejEl = document.getElementById('hist-rej');
  rejEl.innerHTML = '';
  rej.forEach(n => {
    const el = document.createElement('div');
    el.style.cssText = 'font-size:12px;color:#EF4444;background:#2A0D0D;border-radius:4px;padding:4px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    el.title = n;
    el.textContent = '♪  ' + n;
    rejEl.appendChild(el);
  });
}

// ── Pipeline actions ───────────────────────────────────────────────────────────
function startPipeline() {
  if (document.getElementById('btn-start').disabled) return;
  if (!queueItems.length) return;
  resetUI();
  wsSend({ type: 'start', index: selectedIndex });
  document.getElementById('btn-start').disabled = true;
  appendLog('Pipeline iniciado: ' + queueItems[selectedIndex].stem);
}

function confirmTitle() {
  const titulo = document.getElementById('inp-title').value.trim();
  wsSend({ type: 'confirm_titulo', titulo });
  document.getElementById('btn-confirm-inline').disabled = true;
  document.getElementById('btn-confirm-full').disabled   = true;
  appendLog('Título confirmado: ' + (titulo || '(mantido)'));
}

function imgDecision(d) {
  wsSend({ type: 'img_decision', decision: d });
  ['btn-img-ok','btn-img-new','btn-img-choose'].forEach(id =>
    document.getElementById(id).disabled = true);
  appendLog({ s:'Imagem aprovada.', n:'Gerando nova imagem...' }[d] || '');
}

async function chooseImage() {
  const btn = document.getElementById('btn-img-choose');
  btn.disabled = true;
  btn.textContent = '⌛ Abrindo...';
  try {
    const r = await fetch('/api/pick-image', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      const img = document.getElementById('img-el');
      const ph  = document.getElementById('img-placeholder');
      img.src = '/img/current?t=' + Date.now();
      img.onload  = () => { ph.style.display = 'none'; img.style.display = 'block'; document.getElementById('img-expand-hint').style.display = ''; };
      img.onerror = () => { ph.textContent = 'Erro ao carregar imagem'; };
      appendLog('Imagem carregada: ' + d.name + ' — clique em Aprovar para continuar.');
    } else if (!d.cancelled) {
      appendLog('Erro ao carregar imagem: ' + (d.error || 'desconhecido'));
    }
  } catch(e) {
    appendLog('Erro: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '📂 Escolher';
  }
}

function vidDecision(d) {
  wsSend({ type: 'vid_decision', decision: d });
  document.getElementById('btn-publish').disabled = true;
  document.getElementById('btn-reject').disabled  = true;
  appendLog(d === 's' ? 'Publicando no YouTube...' : 'Vídeo rejeitado. Devolvendo áudio ao /inbox.');
}

// ── Server callbacks ──────────────────────────────────────────────────────────
function onMetaReady(m) {
  document.getElementById('inp-title').value = m.nome_musica || '';
  document.getElementById('inp-desc').value  = m.descricao || '';
  document.getElementById('inp-tags').value  = Array.isArray(m.tags) ? m.tags.join(', ') : (m.tags || '');
  document.getElementById('btn-confirm-inline').disabled = false;
  document.getElementById('btn-confirm-full').disabled   = false;
  appendLog('Metadados prontos — edite o título e confirme.');
}

function onImgReady(m) {
  const ph  = document.getElementById('img-placeholder');
  const img = document.getElementById('img-el');
  img.src = '/img/current?t=' + Date.now();
  img.onload  = () => { ph.style.display = 'none'; img.style.display = 'block'; document.getElementById('img-expand-hint').style.display = ''; };
  img.onerror = () => { ph.textContent = 'Erro ao carregar imagem'; };
  document.getElementById('img-char').textContent  = 'Character: ' + (m.personagem || '—');
  document.getElementById('img-scene').textContent = 'Scene: '     + (m.cenario    || '—');
  document.getElementById('img-style').textContent = 'Style: '     + (m.estilo     || '—');
  ['btn-img-ok','btn-img-new','btn-img-choose'].forEach(id =>
    document.getElementById(id).disabled = false);
  appendLog('Imagem pronta — avalie e decida.');
}

function onVidReady(m) {
  currentVideoPath = m.path;
  document.getElementById('vid-placeholder').textContent = '▶  Vídeo pronto — abra /review para assistir';
  document.getElementById('vid-name').textContent = m.name || '—';
  document.getElementById('vid-progress').style.width = '60%';
  document.getElementById('btn-publish').disabled = false;
  document.getElementById('btn-reject').disabled  = false;
  appendLog('Vídeo pronto em /review — assista e decida.');
}

function onDoneOk(url) {
  appendLog('✓ Publicado: ' + url);
  document.getElementById('vid-progress').style.width = '100%';
  showToast('Publicado!', url, '#0D2318', '#22C55E');
  loadQueue(); loadHistory(); loadReviewQueue();
  if (reviewMode) { exitReviewMode(); } else { document.getElementById('btn-start').disabled = false; }
}

function onDoneKo(msg) {
  if (msg !== 'descartado' && msg !== 'rejeitado') {
    appendLog('✗ Erro: ' + msg);
    showToast('Erro no pipeline', msg.slice(0,260), '#2A0D0D', '#EF4444');
  }
  if (!reviewMode) document.getElementById('btn-start').disabled = false;
  else { document.getElementById('btn-publish-review').disabled = false; document.getElementById('btn-gen-meta').disabled = false; }
  loadQueue(); loadHistory(); loadReviewQueue();
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function resetUI() {
  [0,1,2,3].forEach(i => setStep(i, 'idle'));
  ['btn-confirm-inline','btn-confirm-full','btn-img-ok','btn-img-new',
   'btn-img-choose','btn-publish','btn-reject'].forEach(id =>
    document.getElementById(id).disabled = true);
  document.getElementById('inp-title').value = '';
  document.getElementById('inp-desc').value  = '';
  document.getElementById('inp-tags').value  = '';
  const ph  = document.getElementById('img-placeholder');
  const img = document.getElementById('img-el');
  ph.textContent = 'Aguardando geração da imagem...';
  ph.style.display = '';
  img.style.display = 'none';
  img.src = '';
  document.getElementById('img-expand-hint').style.display = 'none';
  document.getElementById('img-char').textContent  = 'Character: —';
  document.getElementById('img-scene').textContent = 'Scene: —';
  document.getElementById('img-style').textContent = 'Style: —';
  document.getElementById('vid-placeholder').textContent = 'Aguardando vídeo...';
  document.getElementById('vid-name').textContent = '—';
  document.getElementById('vid-progress').style.width = '0%';
  currentVideoPath = null;
}

async function openReview() {
  await fetch('/api/open-review', { method: 'POST' });
}

async function openVideo() {
  await fetch('/api/open-video', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path: currentVideoPath }),
  });
}

async function pickFile() {
  const btn = event.currentTarget;
  btn.disabled = true;
  btn.textContent = '⌛ Abrindo...';
  try {
    const r = await fetch('/api/pick-file', { method: 'POST' });
    const d = await r.json();
    if (d.name) {
      appendLog('Arquivo adicionado ao inbox: ' + d.name);
      loadQueue();
    }
  } catch(e) { /* ignore */ }
  btn.disabled = false;
  btn.textContent = '📂 Adicionar arquivo ao inbox';
}

async function shutdownApp() {
  if (!confirm('Encerrar a aplicação?')) return;
  await fetch('/api/shutdown', { method: 'POST' }).catch(() => {});
  document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#8892A4;font-size:16px;">Aplicação encerrada. Feche esta aba.</div>';
}

// ── Lightbox ──────────────────────────────────────────────────────────────────
let _lbScale = 1, _lbX = 0, _lbY = 0;
let _lbDrag = false, _lbDragAnchor = {x:0, y:0};

function lbApply() {
  document.getElementById('lb-img').style.transform =
    `translate(${_lbX}px,${_lbY}px) scale(${_lbScale})`;
}

function openLightbox() {
  const src = document.getElementById('img-el').src;
  if (!src || document.getElementById('img-el').style.display === 'none') return;
  const lb  = document.getElementById('lightbox');
  const img = document.getElementById('lb-img');
  img.src = src;
  _lbScale = 1; _lbX = 0; _lbY = 0;
  img.style.transform = '';
  lb.style.display = 'block';
  document.addEventListener('keydown', _lbKeyDown);
}

function closeLightbox() {
  document.getElementById('lightbox').style.display = 'none';
  document.removeEventListener('keydown', _lbKeyDown);
}

function _lbKeyDown(e) { if (e.key === 'Escape') closeLightbox(); }

function lbZoom(delta) {
  _lbScale = Math.max(0.25, Math.min(10, _lbScale + delta * _lbScale));
  lbApply();
}

function lbReset() { _lbScale = 1; _lbX = 0; _lbY = 0; lbApply(); }

// Zoom por scroll
document.addEventListener('DOMContentLoaded', () => {
  const lb  = document.getElementById('lightbox');
  const img = document.getElementById('lb-img');

  lb.addEventListener('wheel', e => {
    if (lb.style.display === 'none') return;
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    _lbScale = Math.max(0.25, Math.min(10, _lbScale * factor));
    lbApply();
  }, { passive: false });

  // Arrastar para mover
  img.addEventListener('mousedown', e => {
    e.stopPropagation();
    _lbDrag = true;
    _lbDragAnchor = { x: e.clientX - _lbX, y: e.clientY - _lbY };
    img.style.cursor = 'grabbing';
  });
  document.addEventListener('mousemove', e => {
    if (!_lbDrag) return;
    _lbX = e.clientX - _lbDragAnchor.x;
    _lbY = e.clientY - _lbDragAnchor.y;
    lbApply();
  });
  document.addEventListener('mouseup', () => {
    if (_lbDrag) { _lbDrag = false; img.style.cursor = 'grab'; }
  });
});

// ── Review Queue ───────────────────────────────────────────────────────────────
async function loadReviewQueue() {
  const r = await fetch('/api/review-queue');
  const d = await r.json();
  renderReviewQueue(d.items);
}

function renderReviewQueue(items) {
  reviewItems = items;
  document.getElementById('review-count').textContent = 'REVIEW (' + items.length + ')';
  const list = document.getElementById('review-list');
  list.innerHTML = '';
  items.forEach(item => {
    const row = document.createElement('div');
    const isActive = selectedReviewVideo === item.name;
    row.className = 'track-row' + (isActive ? ' active' : '');
    const label = item.stem.length > 28 ? item.stem.slice(0,26) + '…' : item.stem;
    row.innerHTML =
      '<span style="color:' + (isActive ? '#22C55E' : '#8892A4') + ';font-size:13px;flex-shrink:0;">▶</span>' +
      '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:600;color:' + (isActive ? '#E2E8F0' : '#8892A4') + ';">' + label + '</span>' +
      '<span style="color:#8892A4;font-size:11px;flex-shrink:0;">' + item.date + '</span>';
    row.onclick = () => selectReviewVideo(item);
    list.appendChild(row);
  });
}

function selectReviewVideo(item) {
  selectedReviewVideo = item.name;
  reviewMode = true;
  renderReviewQueue(reviewItems);

  const titleEl = document.getElementById('song-title');
  titleEl.textContent = item.stem.length > 58 ? item.stem.slice(0,56) + '…' : item.stem;
  titleEl.style.color = '#E2E8F0';

  document.getElementById('review-mode-bar').style.display = 'flex';
  document.getElementById('review-video-label').textContent = item.name;
  document.getElementById('btn-start').disabled = true;

  const niceName = item.stem
    .replace(/_final$/, '')
    .replace(/-slowedandreverbstudio(?:studio)?/gi, '')
    .replace(/[_]+/g, ' ')
    .trim();
  document.getElementById('inp-title').value    = niceName;
  document.getElementById('inp-desc').value     = '';
  document.getElementById('inp-tags').value     = '';

  document.getElementById('review-actions').style.display       = 'flex';
  document.getElementById('review-actions').style.flexDirection = 'column';
  document.getElementById('btn-confirm-inline').style.display   = 'none';
  document.getElementById('btn-confirm-full').style.display     = 'none';
  document.getElementById('btn-publish-review').disabled = false;
  document.getElementById('btn-gen-meta').disabled = false;

  appendLog('Review: ' + item.name + ' selecionado.');
}

function exitReviewMode() {
  reviewMode = false;
  selectedReviewVideo = null;
  renderReviewQueue(reviewItems);

  document.getElementById('review-mode-bar').style.display     = 'none';
  document.getElementById('review-actions').style.display      = 'none';
  document.getElementById('btn-confirm-inline').style.display  = '';
  document.getElementById('btn-confirm-full').style.display    = '';

  document.getElementById('inp-title').value = '';
  document.getElementById('inp-desc').value  = '';
  document.getElementById('inp-tags').value  = '';

  if (queueItems.length) {
    updateWorkspaceTitle();
    document.getElementById('btn-start').disabled = false;
  } else {
    document.getElementById('song-title').textContent = 'Nenhum arquivo selecionado';
    document.getElementById('song-title').style.color = '#8892A4';
    document.getElementById('btn-start').disabled = true;
  }
}

async function genReviewMeta() {
  if (!selectedReviewVideo) return;
  const btn = document.getElementById('btn-gen-meta');
  btn.disabled = true;
  btn.textContent = '⌛ Gerando metadados...';
  try {
    const r = await fetch('/api/gen-meta', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_name: selectedReviewVideo }),
    });
    const d = await r.json();
    if (d.error) { appendLog('Erro: ' + d.error); return; }
    document.getElementById('inp-title').value = d.nome_musica || '';
    document.getElementById('inp-desc').value  = d.descricao   || '';
    document.getElementById('inp-tags').value  = Array.isArray(d.tags) ? d.tags.join(', ') : (d.tags || '');
    appendLog('Metadados gerados. Revise e publique.');
  } catch(e) {
    appendLog('Erro ao gerar metadados: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Gerar Metadados';
  }
}

function publishReview() {
  if (!selectedReviewVideo) return;
  const titulo    = document.getElementById('inp-title').value.trim();
  const descricao = document.getElementById('inp-desc').value.trim();
  const tagsRaw   = document.getElementById('inp-tags').value.trim();
  const tags      = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
  if (!titulo) { appendLog('Preencha o título antes de publicar.'); return; }
  [0,1,2,3].forEach(i => setStep(i, 'idle'));
  setStep(3, 'running');
  document.getElementById('btn-publish-review').disabled = true;
  document.getElementById('btn-gen-meta').disabled = true;
  wsSend({ type: 'publish_review', video_name: selectedReviewVideo, titulo, descricao, tags });
  appendLog('Publicando da review: ' + selectedReviewVideo);
}

let toastTimer = null;
function showToast(title, msg, bg, titleColor) {
  const t = document.getElementById('toast');
  t.style.display = 'block';
  t.style.background = bg || '#1C2138';
  const tt = document.getElementById('toast-title');
  tt.textContent = title;
  tt.style.color = titleColor || '#E2E8F0';
  document.getElementById('toast-msg').textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = 'none'; }, 7000);
}

connect();
setInterval(loadQueue, 10000);
setInterval(loadReviewQueue, 15000);
</script>
</body>
</html>
"""

# ── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._ws:   Optional[WebSocket]                    = None
        self._loop: Optional[asyncio.AbstractEventLoop]    = None
        self._lock  = threading.Lock()

    def connect(self, ws: WebSocket, loop: asyncio.AbstractEventLoop):
        with self._lock:
            self._ws, self._loop = ws, loop

    def disconnect(self):
        with self._lock:
            self._ws = self._loop = None

    def send(self, data: dict):
        with self._lock:
            ws, loop = self._ws, self._loop
        if ws and loop and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(ws.send_json(data), loop)
            except Exception:
                pass


manager = ConnectionManager()

# ── Pipeline Worker ───────────────────────────────────────────────────────────

class PipelineWorker(threading.Thread):

    def __init__(self, audio_path: Path):
        super().__init__(daemon=True)
        self.audio_path      = audio_path
        self._titulo_editado = ""
        self._decisao_img    = ""
        self._decisao_vid    = ""
        self._cancelled      = False
        self._evt_titulo     = threading.Event()
        self._evt_imagem     = threading.Event()
        self._evt_video      = threading.Event()

    def set_titulo(self, titulo: str):
        self._titulo_editado = titulo
        self._evt_titulo.set()

    def set_decisao_imagem(self, d: str):
        self._decisao_img = d
        self._evt_imagem.set()

    def set_decisao_video(self, d: str):
        self._decisao_vid = d
        self._evt_video.set()

    def cancel(self):
        self._cancelled = True
        for e in (self._evt_titulo, self._evt_imagem, self._evt_video):
            e.set()

    def _log(self, msg: str):  manager.send({"type": "log",  "msg": msg})
    def _step(self, i, s):     manager.send({"type": "step", "index": i, "status": s})

    def run(self):
        import json as _json
        from image_generator    import gerar_imagem
        from ken_burns           import aplicar_ken_burns
        from metadata_generator  import gerar_metadados, NOME_CANAL
        from youtube_uploader    import publicar_video

        nome           = self.audio_path.name
        DIR_PROCESSING = Path("processing")
        DIR_REVIEW     = Path("review")
        DIR_REJECTED   = Path("rejected")
        DIR_LOGS       = Path("logs")
        DIR_PROCESSING.mkdir(exist_ok=True)

        audio_proc = DIR_PROCESSING / nome
        shutil.move(str(self.audio_path), str(audio_proc))

        def devolver():
            try: shutil.move(str(audio_proc), str(self.audio_path))
            except Exception: pass

        def limpar(manter=None):
            for f in DIR_PROCESSING.iterdir():
                if manter and f.resolve() == Path(manter).resolve(): continue
                try: f.unlink()
                except Exception: pass

        def push_queue():
            manager.send({"type": "queue_update", "items": _get_queue_items()})

        def push_history():
            pub, rej = _get_history()
            manager.send({"type": "history_update", "published": pub, "rejected": rej})

        try:
            # [1] Metadados
            self._step(0, "running")
            self._log(f"[1/4] Gerando metadados — {nome}")
            meta = gerar_metadados(nome)
            self._step(0, "done")
            self._log(f"  Título: {meta['titulo']}")
            manager.send({"type": "meta_ready",
                          "titulo":      meta.get("titulo", ""),
                          "nome_musica": meta.get("nome_musica", ""),
                          "descricao":   meta.get("descricao", ""),
                          "tags":        meta.get("tags", [])})
            self._evt_titulo.wait()
            if self._cancelled: devolver(); return

            if self._titulo_editado:
                old = meta["titulo"]
                meta["titulo"] = f"｜ {self._titulo_editado} ｜ slowed + reverb - vers {NOME_CANAL}"
                meta["descricao"] = meta["descricao"].replace(old, meta["titulo"])
            self._log(f"  Título final: {meta['titulo']}")

            res = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(audio_proc)],
                capture_output=True, text=True,
            )
            if res.returncode != 0: raise RuntimeError(f"ffprobe: {res.stderr}")
            duracao = 0
            for s in _json.loads(res.stdout).get("streams", []):
                d = s.get("duration")
                if d: duracao = int(float(d)); break
            if not duracao: raise RuntimeError("Duração do áudio não encontrada.")
            self._log(f"  Duração: {duracao}s")

            # [2] Imagem
            tentativa = 0
            while True:
                tentativa += 1
                self._step(1, "running")
                self._evt_imagem.clear()
                self._log(f"[2/4] Gerando imagem (tentativa {tentativa})...")
                img_path, img_meta = gerar_imagem(destino=str(DIR_PROCESSING / "imagem_gerada.png"))
                self._step(1, "done")
                self._log(f"  Personagem: {img_meta.get('personagem','')}")
                self._log(f"  Cenário   : {img_meta.get('cenario','')}")
                manager.send({"type": "img_ready",
                              "personagem": img_meta.get("personagem", "—"),
                              "cenario":    img_meta.get("cenario",    "—"),
                              "estilo":     img_meta.get("estilo",     "—")})
                self._evt_imagem.wait()
                if self._cancelled: devolver(); return
                if self._decisao_img == "s":
                    break
                elif self._decisao_img == "d":
                    self._step(1, "error")
                    devolver(); limpar()
                    self._log("  Descartado. Áudio devolvido ao /inbox.")
                    manager.send({"type": "done_ko", "msg": "descartado"})
                    push_queue(); push_history(); return

            # [3] Ken Burns + merge
            self._step(2, "running")
            self._log("[3/4] Aplicando Ken Burns...")
            video_anim = str(DIR_PROCESSING / "video_animado.mp4")
            aplicar_ken_burns(imagem=img_path, duracao=duracao, saida=video_anim,
                              fps=60, resolucao="1920x1080")
            self._log("  Vídeo animado gerado.")
            self._log("[4a] Combinando áudio + vídeo...")
            nome_final  = Path(nome).stem + "_final.mp4"
            video_final = DIR_PROCESSING / nome_final
            res = subprocess.run(
                ["ffmpeg", "-y", "-i", str(video_anim), "-i", str(audio_proc),
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(video_final)],
                capture_output=True, text=True,
            )
            if res.returncode != 0: raise RuntimeError(f"FFmpeg: {res.stderr[-600:]}")
            self._step(2, "done")

            DIR_REVIEW.mkdir(exist_ok=True)
            video_review = DIR_REVIEW / nome_final
            shutil.move(str(video_final), str(video_review))
            limpar(manter=audio_proc)
            self._log(f"  Vídeo pronto: {video_review.name}")
            manager.send({"type": "vid_ready", "path": str(video_review), "name": video_review.name})

            self._evt_video.wait()
            if self._cancelled: devolver(); return

            if self._decisao_vid != "s":
                DIR_REJECTED.mkdir(exist_ok=True)
                shutil.move(str(video_review), str(DIR_REJECTED / nome_final))
                devolver(); limpar()
                self._log("  Rejeitado. Áudio devolvido ao /inbox.")
                manager.send({"type": "done_ko", "msg": "rejeitado"})
                push_queue(); push_history(); return

            # [4] Upload
            self._step(3, "running")
            self._log("[4/4] Publicando no YouTube...")
            resultado = publicar_video(video_path=str(video_review),
                                       titulo=meta["titulo"],
                                       descricao=meta["descricao"],
                                       tags=meta["tags"])
            self._step(3, "done")

            DIR_LOGS.mkdir(exist_ok=True)
            agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            (DIR_LOGS / f"publicado_{Path(nome).stem}_{agora}.txt").write_text(
                f"Arquivo  : {nome}\nTítulo   : {resultado['titulo']}\n"
                f"Video ID : {resultado['video_id']}\nURL      : {resultado['url']}\n"
                f"Horário  : {agora}\n\nPrompt:\n{img_meta.get('prompt_completo','')}\n",
                encoding="utf-8",
            )
            limpar()
            self._log(f"  ✓ Publicado: {resultado['url']}")
            manager.send({"type": "done_ok", "url": resultado["url"]})
            push_queue(); push_history()

        except Exception:
            err = traceback.format_exc()
            devolver()
            self._log(f"[ERRO] {err.splitlines()[-1]}")
            manager.send({"type": "done_ko", "msg": err.splitlines()[-1]})
            for i in range(4): self._step(i, "error")


# ── Review Publish Worker ─────────────────────────────────────────────────────

class ReviewPublishWorker(threading.Thread):
    """Publica um vídeo já existente em /review, sem refazer o pipeline."""

    def __init__(self, video_path: Path, titulo: str, descricao: str, tags: list):
        super().__init__(daemon=True)
        self.video_path = video_path
        self.titulo     = titulo
        self.descricao  = descricao
        self.tags       = tags

    def _log(self, msg: str):
        manager.send({"type": "log", "msg": msg})

    def run(self):
        from youtube_uploader   import publicar_video
        from metadata_generator import NOME_CANAL

        try:
            self._log(f"[Review] Publicando: {self.video_path.name}")
            manager.send({"type": "step", "index": 3, "status": "running"})

            titulo = self.titulo
            if NOME_CANAL not in titulo:
                titulo = f"｜ {titulo} ｜ slowed + reverb - vers {NOME_CANAL}"

            resultado = publicar_video(
                video_path=str(self.video_path),
                titulo=titulo,
                descricao=self.descricao,
                tags=self.tags,
            )
            manager.send({"type": "step", "index": 3, "status": "done"})

            DIR_LOGS = Path("logs")
            DIR_LOGS.mkdir(exist_ok=True)
            agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            (DIR_LOGS / f"publicado_{self.video_path.stem}_{agora}.txt").write_text(
                f"Arquivo  : {self.video_path.name}\nTítulo   : {resultado['titulo']}\n"
                f"Video ID : {resultado['video_id']}\nURL      : {resultado['url']}\n"
                f"Horário  : {agora}\n[via Review Queue]\n",
                encoding="utf-8",
            )

            self._log(f"  ✓ Publicado: {resultado['url']}")
            manager.send({"type": "done_ok", "url": resultado["url"]})

            pub, rej = _get_history()
            manager.send({"type": "history_update", "published": pub, "rejected": rej})
            manager.send({"type": "review_update",  "items": _get_review_items()})

        except Exception:
            err = traceback.format_exc()
            self._log(f"[ERRO] {err.splitlines()[-1]}")
            manager.send({"type": "done_ko",  "msg": err.splitlines()[-1]})
            manager.send({"type": "step", "index": 3, "status": "error"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_queue_items() -> list:
    inbox = Path("inbox")
    inbox.mkdir(exist_ok=True)
    exts = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
    files = sorted(
        (f for f in inbox.iterdir() if f.is_file() and f.suffix.lower() in exts),
        key=lambda f: f.stat().st_mtime,
    )
    return [
        {"stem": f.stem,
         "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y")}
        for f in files
    ]


def _get_history() -> tuple:
    DIR_LOGS     = Path("logs");     DIR_LOGS.mkdir(exist_ok=True)
    DIR_REJECTED = Path("rejected"); DIR_REJECTED.mkdir(exist_ok=True)
    published = [
        f.stem[10:] for f in sorted(
            DIR_LOGS.glob("publicado_*.txt"),
            key=lambda x: x.stat().st_mtime, reverse=True,
        )[:12]
    ]
    rejected = [
        f.stem[:-6] for f in sorted(
            DIR_REJECTED.glob("*_final.mp4"),
            key=lambda x: x.stat().st_mtime, reverse=True,
        )[:8]
    ]
    return published, rejected


def _get_review_items() -> list:
    review = Path("review")
    review.mkdir(exist_ok=True)
    files = sorted(
        (f for f in review.iterdir() if f.is_file() and f.suffix.lower() == ".mp4"),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    return [
        {"name": f.name, "stem": f.stem,
         "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y")}
        for f in files
    ]


def _pick_image_sync() -> dict:
    """Abre dialog de imagem em assets/images e copia para processing/imagem_gerada.png."""
    assets_dir = Path("assets/images").resolve()
    assets_dir.mkdir(parents=True, exist_ok=True)
    assets_str = str(assets_dir).replace("\\", "\\\\")

    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.OpenFileDialog; "
        "$d.Filter = 'Image Files|*.png;*.jpg;*.jpeg;*.webp|All Files|*.*'; "
        f"$d.InitialDirectory = '{assets_str}'; "
        "$d.Title = 'Selecionar imagem para o vídeo'; "
        "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $d.FileName }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=120,
        )
        path = r.stdout.strip()
        if path and Path(path).exists():
            dest = Path("processing") / "imagem_gerada.png"
            Path("processing").mkdir(exist_ok=True)
            shutil.copy2(path, dest)
            return {"ok": True, "name": Path(path).name}
    except Exception as e:
        return {"error": str(e)}
    return {"cancelled": True}


def _pick_file_sync() -> Optional[str]:
    """Abre dialog nativo do Windows via PowerShell e copia o arquivo para /inbox."""
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.OpenFileDialog; "
        "$d.Filter = 'Audio Files|*.mp3;*.wav;*.flac;*.m4a;*.ogg|All Files|*.*'; "
        "$d.Title = 'Selecionar arquivo de audio para o inbox'; "
        "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $d.FileName }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=120,
        )
        path = r.stdout.strip()
        if path and Path(path).exists():
            dest = Path("inbox") / Path(path).name
            Path("inbox").mkdir(exist_ok=True)
            shutil.copy2(path, dest)
            return Path(path).name
    except Exception:
        pass
    return None


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI()
_worker: Optional[PipelineWorker] = None
_server: Optional[uvicorn.Server]  = None


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_TEMPLATE


@app.get("/api/queue")
async def api_queue():
    return JSONResponse({"items": _get_queue_items()})


@app.get("/api/history")
async def api_history():
    pub, rej = _get_history()
    return JSONResponse({"published": pub, "rejected": rej})


@app.get("/img/current")
async def img_current():
    path = Path("processing") / "imagem_gerada.png"
    if path.exists():
        return FileResponse(str(path), media_type="image/png")
    return JSONResponse({"error": "not found"}, status_code=404)


@app.post("/api/open-review")
async def api_open_review():
    d = Path("review")
    d.mkdir(exist_ok=True)
    subprocess.Popen(["explorer", str(d.resolve())])
    return {"ok": True}


@app.post("/api/open-video")
async def api_open_video(request: Request):
    body = await request.json()
    path = body.get("path", "")
    if path and Path(path).exists():
        os.startfile(path)
    else:
        d = Path("review")
        d.mkdir(exist_ok=True)
        subprocess.Popen(["explorer", str(d.resolve())])
    return {"ok": True}


@app.get("/api/review-queue")
async def api_review_queue():
    return JSONResponse({"items": _get_review_items()})


@app.post("/api/gen-meta")
async def api_gen_meta(request: Request):
    body = await request.json()
    video_name = body.get("video_name", "")
    if not video_name:
        return JSONResponse({"error": "video_name required"}, status_code=400)
    try:
        from metadata_generator import gerar_metadados
        loop = asyncio.get_event_loop()
        meta = await loop.run_in_executor(None, gerar_metadados, video_name)
        return JSONResponse(meta)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/pick-file")
async def api_pick_file():
    loop = asyncio.get_event_loop()
    name = await loop.run_in_executor(None, _pick_file_sync)
    items = _get_queue_items()
    manager.send({"type": "queue_update", "items": items})
    return JSONResponse({"name": name})


@app.post("/api/pick-image")
async def api_pick_image():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _pick_image_sync)
    return JSONResponse(result)


@app.post("/api/shutdown")
async def api_shutdown():
    def _stop():
        import time
        time.sleep(0.4)
        if _server:
            _server.should_exit = True
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_stop, daemon=True).start()
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    global _worker
    await websocket.accept()
    loop = asyncio.get_event_loop()
    manager.connect(websocket, loop)
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            t   = msg.get("type")

            if t == "start":
                inbox = Path("inbox")
                exts  = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
                files = sorted(
                    (f for f in inbox.iterdir() if f.is_file() and f.suffix.lower() in exts),
                    key=lambda f: f.stat().st_mtime,
                )
                if not files:
                    manager.send({"type": "log", "msg": "Inbox vazia."})
                    continue
                if _worker and _worker.is_alive():
                    manager.send({"type": "log", "msg": "Pipeline já em execução."})
                    continue
                idx = min(msg.get("index", 0), len(files) - 1)
                _worker = PipelineWorker(files[idx])
                _worker.start()

            elif t == "confirm_titulo" and _worker:
                _worker.set_titulo(msg.get("titulo", ""))

            elif t == "img_decision" and _worker:
                _worker.set_decisao_imagem(msg.get("decision", ""))

            elif t == "vid_decision" and _worker:
                _worker.set_decisao_video(msg.get("decision", ""))

            elif t == "publish_review":
                if _worker and _worker.is_alive():
                    manager.send({"type": "log", "msg": "Pipeline já em execução."})
                    continue
                video_name = msg.get("video_name", "")
                video_path = Path("review") / video_name
                if not video_path.exists():
                    manager.send({"type": "log", "msg": f"Vídeo não encontrado: {video_name}"})
                    continue
                _worker = ReviewPublishWorker(
                    video_path=video_path,
                    titulo=msg.get("titulo", ""),
                    descricao=msg.get("descricao", ""),
                    tags=msg.get("tags", []),
                )
                _worker.start()

    except WebSocketDisconnect:
        manager.disconnect()
    except Exception:
        manager.disconnect()


# ── Entry point ───────────────────────────────────────────────────────────────

def _open_browser():
    import time
    time.sleep(1.2)
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    _server = uvicorn.Server(config)
    _server.run()
