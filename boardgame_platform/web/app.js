/* Boardgame FRP Platform — browser client (vanilla JS) */
(() => {
  "use strict";

  const PLACEHOLDERS = [
    { title: "卡坦岛风格大厅", desc: "资源与贸易玩法筹备中", badge: "即将推出" },
    { title: "军棋 / 四国", desc: "暗棋与翻面规则开发中", badge: "即将推出" },
    { title: "更多桌游", desc: "插件化扩展位", badge: "即将推出" },
  ];

  const state = {
    ws: null,
    connected: false,
    playerId: null,
    games: [],
    selectedGameId: "tictactoe",
    room: null,
    gameState: null,
    gameOver: null,
    reconnectTimer: null,
  };

  const $ = (id) => document.getElementById(id);

  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws`;
  }

  function showView(name) {
    document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
    const view = $(`view-${name}`);
    if (view) view.classList.add("active");
  }

  function setConn(online) {
    state.connected = online;
    document.querySelectorAll(".conn-pill").forEach((el) => {
      el.classList.toggle("online", online);
      el.classList.toggle("offline", !online);
      el.textContent = online ? "已连接" : "未连接";
    });
  }

  function showError(elId, text) {
    const el = $(elId);
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = text;
  }

  function nickname() {
    const n = ($("nickname").value || "").trim();
    return n || "玩家";
  }

  function send(type, payload = {}) {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
      showError("lobby-error", "尚未连接到主机");
      return false;
    }
    state.ws.send(JSON.stringify({ type, ...payload }));
    return true;
  }

  function connect() {
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const ws = new WebSocket(wsUrl());
    state.ws = ws;

    ws.onopen = () => setConn(true);

    ws.onclose = () => {
      setConn(false);
      state.ws = null;
      if (state.reconnectTimer) clearTimeout(state.reconnectTimer);
      state.reconnectTimer = setTimeout(connect, 1500);
    };

    ws.onerror = () => setConn(false);

    ws.onmessage = (ev) => {
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }
      handleMessage(data);
    };
  }

  function handleMessage(data) {
    const t = data.type;
    switch (t) {
      case "welcome":
        state.playerId = data.player_id;
        state.games = data.games || [];
        renderHome();
        break;
      case "games":
        state.games = data.games || [];
        renderHome();
        break;
      case "room_created":
      case "room_joined":
        state.room = data.room;
        if (data.player_id) state.playerId = data.player_id;
        showError("lobby-error", "");
        enterRoomView();
        break;
      case "room_update":
        if (data.left) {
          state.room = null;
          state.gameState = null;
          showView("lobby");
          return;
        }
        if (data.room) {
          state.room = data.room;
          if (state.room.phase === "lobby") renderRoom();
          else if (state.room.phase === "playing" || state.room.phase === "finished") {
            $("play-room-code").textContent = state.room.code || "------";
          }
        }
        break;
      case "game_started":
        if (data.room) state.room = data.room;
        state.gameOver = null;
        $("game-over-overlay").hidden = true;
        showView("play");
        buildBoard();
        break;
      case "state":
        state.gameState = data.state;
        if (!document.getElementById("view-play").classList.contains("active")) {
          showView("play");
          buildBoard();
        }
        renderPlay();
        break;
      case "game_over":
        state.gameOver = data;
        if (data.room) state.room = data.room;
        showGameOver(data.reason || "游戏结束");
        break;
      case "error":
        showTransientError(data.error || "未知错误");
        break;
      default:
        break;
    }
  }

  function showTransientError(text) {
    const active = document.querySelector(".view.active");
    if (active && active.id === "view-lobby") showError("lobby-error", text);
    else if (active && active.id === "view-room") showError("room-error", text);
    else if (active && active.id === "view-play") {
      showError("play-error", text);
      setTimeout(() => showError("play-error", ""), 2500);
    } else {
      showError("lobby-error", text);
    }
  }

  function renderHome() {
    const grid = $("game-grid");
    grid.innerHTML = "";

    const live = state.games.length
      ? state.games
      : [{
          game_id: "tictactoe",
          display_name: "井字棋 (Tic-Tac-Toe)",
          description: "经典 3×3 井字棋。X 先手，轮流落子，三连获胜。",
          min_players: 2,
          max_players: 2,
        }];

    for (const g of live) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "game-card";
      btn.innerHTML = `
        <span class="card-badge">可玩</span>
        <h3>${escapeHtml(g.display_name || g.game_id)}</h3>
        <p>${escapeHtml(g.description || "")}</p>
        <p>${g.min_players}-${g.max_players} 人</p>
      `;
      btn.addEventListener("click", () => openGameLobby(g.game_id, g.display_name));
      grid.appendChild(btn);
    }

    for (const p of PLACEHOLDERS.slice(0, 3)) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "game-card coming";
      btn.disabled = true;
      btn.innerHTML = `
        <span class="card-badge">${escapeHtml(p.badge)}</span>
        <h3>${escapeHtml(p.title)}</h3>
        <p>${escapeHtml(p.desc)}</p>
      `;
      grid.appendChild(btn);
    }
  }

  function openGameLobby(gameId, title) {
    state.selectedGameId = gameId;
    $("lobby-game-title").textContent = title || gameId;
    showError("lobby-error", "");
    showView("lobby");
    if (!$("nickname").value) {
      const saved = localStorage.getItem("bg_nickname") || "";
      $("nickname").value = saved;
    }
  }

  function enterRoomView() {
    showView("room");
    renderRoom();
  }

  function isHost() {
    return state.room && state.playerId && state.room.host_player_id === state.playerId;
  }

  function mePlayer() {
    if (!state.room || !state.playerId) return null;
    return (state.room.players || []).find((p) => p.player_id === state.playerId) || null;
  }

  function renderRoom() {
    const room = state.room;
    if (!room) return;
    $("room-code").textContent = room.code || "------";
    $("play-room-code").textContent = room.code || "------";

    const list = $("seat-list");
    list.innerHTML = "";
    const max = room.max_players || 2;
    const players = room.players || [];
    for (let i = 0; i < max; i++) {
      const p = players[i];
      const card = document.createElement("div");
      if (!p) {
        card.className = "seat-card empty";
        card.innerHTML = `<div class="seat-avatar">?</div><div class="seat-name">等待加入…</div>`;
      } else {
        const tags = [];
        if (p.is_host) tags.push('<span class="tag host">房主</span>');
        if (p.player_id === state.playerId) tags.push('<span class="tag me">我</span>');
        if (p.ready) tags.push('<span class="tag ready">已准备</span>');
        const initial = (p.nickname || "?").slice(0, 1);
        card.className = "seat-card" + (p.ready ? " ready" : "");
        card.innerHTML = `
          <div class="seat-avatar">${escapeHtml(initial)}</div>
          <div class="seat-name">${escapeHtml(p.nickname || "玩家")}</div>
          <div class="seat-tags">${tags.join("")}</div>
        `;
      }
      list.appendChild(card);
    }

    const me = mePlayer();
    const readyBtn = $("btn-ready");
    const amReady = !!(me && me.ready);
    readyBtn.textContent = amReady ? "取消准备" : "准备";
    readyBtn.classList.toggle("ready-on", amReady);
    readyBtn.classList.toggle("secondary", !amReady);
    readyBtn.classList.toggle("primary", false);

    const startBtn = $("btn-start");
    startBtn.hidden = !isHost();
    startBtn.disabled = !isHost();
    showError("room-error", "");
  }

  function buildBoard() {
    const board = $("board");
    board.innerHTML = "";
    for (let i = 0; i < 9; i++) {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "cell";
      cell.dataset.cell = String(i);
      cell.addEventListener("click", () => onCellClick(i));
      board.appendChild(cell);
    }
  }

  function renderPlay() {
    const gs = state.gameState;
    if (!gs) return;

    const cells = $("board").querySelectorAll(".cell");
    const board = gs.board || [];
    const yourTurn = !!gs.your_turn;
    const over = !!(gs.winner || gs.draw || state.gameOver);

    cells.forEach((cell, i) => {
      const v = board[i];
      cell.textContent = v || "";
      cell.classList.toggle("x", v === "X");
      cell.classList.toggle("o", v === "O");
      cell.disabled = over || !yourTurn || !!v;
    });

    const sym = gs.your_symbol || "—";
    $("symbol-badge").textContent = `你是 ${sym}`;

    const turn = $("turn-indicator");
    if (over) {
      turn.textContent = "对局结束";
      turn.className = "turn-indicator";
    } else if (yourTurn) {
      turn.textContent = "轮到你落子";
      turn.className = "turn-indicator yours";
    } else {
      turn.textContent = "等待对手…";
      turn.className = "turn-indicator theirs";
    }

    const bar = $("players-bar");
    bar.innerHTML = "";
    for (const s of gs.seats || []) {
      const pill = document.createElement("div");
      const isActive = s.player_id === gs.current && !over;
      pill.className = "player-pill" + (isActive ? " active" : "");
      const symClass = (s.symbol || "").toLowerCase();
      pill.innerHTML = `<span class="sym ${symClass}">${escapeHtml(s.symbol || "?")}</span>${escapeHtml(s.nickname || "")}`;
      bar.appendChild(pill);
    }

    // Only end UI after real progress or explicit server game_over (avoid empty-board false end)
    if ((gs.winner || gs.draw) && (gs.move_count || 0) > 0) {
      const reason = gs.draw
        ? "平局！"
        : ((gs.seats || []).find((s) => s.player_id === gs.winner)?.nickname || "玩家") + " 获胜！";
      if (!state.gameOver) showGameOver(reason);
    }
  }

  function showGameOver(reason) {
    $("game-over-reason").textContent = reason;
    $("game-over-overlay").hidden = false;
    const cells = $("board").querySelectorAll(".cell");
    cells.forEach((c) => { c.disabled = true; });
  }

  function onCellClick(cell) {
    if (!state.gameState || !state.gameState.your_turn) return;
    if (state.gameState.board && state.gameState.board[cell]) return;
    send("move", { move: { cell } });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Events
  $("btn-back-home").addEventListener("click", () => {
    showView("home");
  });

  $("btn-create").addEventListener("click", () => {
    const nick = nickname();
    localStorage.setItem("bg_nickname", nick);
    showError("lobby-error", "");
    send("create_room", { game_id: state.selectedGameId, nickname: nick });
  });

  $("btn-join").addEventListener("click", () => {
    const code = ($("join-code").value || "").trim().toUpperCase();
    if (!code) {
      showError("lobby-error", "请输入房间号");
      return;
    }
    const nick = nickname();
    localStorage.setItem("bg_nickname", nick);
    showError("lobby-error", "");
    send("join_room", { code, nickname: nick });
  });

  $("join-code").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("btn-join").click();
  });

  $("btn-ready").addEventListener("click", () => {
    const me = mePlayer();
    const next = !(me && me.ready);
    send("ready", { ready: next });
  });

  $("btn-start").addEventListener("click", () => {
    showError("room-error", "");
    send("start");
  });

  $("btn-leave-room").addEventListener("click", () => {
    send("leave");
    state.room = null;
    state.gameState = null;
    state.gameOver = null;
    showView("lobby");
  });

  $("btn-back-lobby").addEventListener("click", () => {
    send("leave");
    state.room = null;
    state.gameState = null;
    state.gameOver = null;
    $("game-over-overlay").hidden = true;
    showView("lobby");
  });

  $("room-code").addEventListener("click", async () => {
    const code = state.room?.code;
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    const toast = $("copy-toast");
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, 1200);
  });

  // Optional: fetch /api/games as fallback before WS welcome
  fetch("/api/games")
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data && Array.isArray(data.games)) {
        state.games = data.games;
        renderHome();
      }
    })
    .catch(() => {});

  renderHome();
  buildBoard();
  connect();
})();
