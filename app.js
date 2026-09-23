(() => {
  "use strict";

  let pick = 7;
  const GROUPS = window.AKB_GROUPS || [];
  const BY_ID = new Map();
  GROUPS.forEach((g) => g.members.forEach((m) => { m.group = g.label; BY_ID.set(m.id, m); }));

  function kamiName() { return pick === 16 ? "神16" : "神7"; }
  function defaultTitle() { return `我的 AKB48 ${kamiName()}`; }

  const $ = (s) => document.querySelector(s);
  const thumbSrc = (m) => `img/thumb/${m.id}.webp`;
  const fullSrc = (m) => `img/full/${m.id}.webp`;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // members who came from a sister group: leaving AKB48 is not a graduation, so no year
  const isTransfer = (m) => m.group === "兼任・移籍加入";

  function metaText(m) {
    if (m.status === "current") return "现役";
    if (isTransfer(m)) return m.note;
    const year = m.end ? m.end.slice(0, 4) : "";
    return year ? `${year} 毕业` : "已毕业";
  }
  function fullMeta(m) {
    if (isTransfer(m)) return `${m.note} · 兼任/移籍`;
    const parts = [m.note || m.group];
    parts.push(m.status === "current" ? "现役" : m.end ? `${m.end.slice(0, 4)} 年离开` : "已离开");
    return parts.join(" · ");
  }

  const state = {
    selected: [],
    filter: "all",
    query: "",
    open: new Set(),
  };

  /* ---------------- phase switching ---------------- */
  function show(phase) {
    for (const id of ["pick", "duel", "result"]) {
      $(`#phase-${id}`).hidden = id !== phase;
    }
    window.scrollTo({ top: 0 });
  }

  /* ---------------- pick ---------------- */
  const roster = $("#roster");

  function visible(m) {
    return state.filter === "all" || m.status === state.filter;
  }

  function cardHTML(m) {
    const i = state.selected.indexOf(m.id);
    const meta = metaText(m);
    return `<button class="card" data-id="${m.id}" aria-pressed="${i >= 0}" data-order="${i + 1}" title="${esc(m.name)}${m.kana ? "（" + esc(m.kana) + "）" : ""}">
      <span class="ph"><img src="${thumbSrc(m)}" alt="" loading="lazy" decoding="async" width="240" height="320"></span>
      <span class="nm">${esc(m.name)}</span>
      <span class="meta${m.status === "current" ? " now" : ""}">${esc(meta)}</span>
    </button>`;
  }

  function pickedIn(g) {
    return g.members.filter((m) => state.selected.includes(m.id)).length;
  }

  function renderRoster() {
    const q = normalize(state.query);
    if (q) return renderSearch(q);

    const html = [];
    GROUPS.forEach((g, gi) => {
      const ms = g.members.filter(visible);
      if (!ms.length) return;
      const open = state.open.has(gi);
      const now = ms.filter((m) => m.status === "current").length;
      const count = state.filter === "all" && now ? `${ms.length} 人 · 现役 ${now}` : `${ms.length} 人`;
      const picked = pickedIn(g);
      html.push(`<section class="gen" data-gi="${gi}">
        <button class="gen-head" aria-expanded="${open}" aria-controls="gen-${gi}">
          <i class="chev" aria-hidden="true"></i>
          <span class="gen-name">${esc(g.label)}</span>
          <span class="gen-count">${count}</span>
          <span class="gen-picked">${picked ? "已选 " + picked : ""}</span>
        </button>
        <div class="gen-body" id="gen-${gi}" ${open ? "" : "hidden"}>${open ? ms.map(cardHTML).join("") : ""}</div>
      </section>`);
    });
    roster.innerHTML = html.join("") || `<p class="empty">这个范围里没有成员。</p>`;
  }

  // variant kanji people often type with the common form (山崎 → 山﨑, 高橋 → 髙橋)
  const VARIANTS = { "﨑": "崎", "髙": "高", "邉": "辺", "邊": "辺", "濵": "浜", "德": "徳", "瀨": "瀬" };

  function normalize(s) {
    return s.trim().toLowerCase().replace(/\s+/g, "").replace(/[﨑髙邉邊濵德瀨]/g, (c) => VARIANTS[c]);
  }

  BY_ID.forEach((m) => { m.hay = normalize(m.name); });

  function renderSearch(q) {
    const hits = [];
    for (const g of GROUPS) {
      for (const m of g.members) {
        if (visible(m) && m.hay.includes(q)) hits.push(m);
      }
    }
    roster.innerHTML = hits.length
      ? `<p class="search-hint">找到 ${hits.length} 位</p><div class="gen-body">${hits.map(cardHTML).join("")}</div>`
      : `<p class="empty">没有找到“${esc(state.query)}”。请用日文汉字输入，例如 渡辺麻友；或者切换到“全部”。</p>`;
  }

  function toggleGroup(gi) {
    const sec = roster.querySelector(`.gen[data-gi="${gi}"]`);
    const head = sec.querySelector(".gen-head");
    const body = sec.querySelector(".gen-body");
    const open = !state.open.has(gi);
    if (open) {
      state.open.add(gi);
      body.innerHTML = GROUPS[gi].members.filter(visible).map(cardHTML).join("");
      body.hidden = false;
    } else {
      state.open.delete(gi);
      body.hidden = true;
      body.innerHTML = "";
    }
    head.setAttribute("aria-expanded", open);
    if (!open && head.getBoundingClientRect().top < roster.getBoundingClientRect().top) {
      roster.scrollTop = sec.offsetTop;
    }
  }

  function toggleMember(id) {
    const i = state.selected.indexOf(id);
    if (i >= 0) {
      state.selected.splice(i, 1);
    } else if (state.selected.length >= pick) {
      const tray = $("#tray");
      tray.classList.remove("shake");
      void tray.offsetWidth;
      tray.classList.add("shake");
      return;
    } else {
      state.selected.push(id);
    }
    syncSelection();
  }

  function syncSelection() {
    roster.querySelectorAll(".card").forEach((el) => {
      const i = state.selected.indexOf(el.dataset.id);
      el.setAttribute("aria-pressed", i >= 0);
      el.dataset.order = i + 1;
    });
    roster.querySelectorAll(".gen").forEach((sec) => {
      const n = pickedIn(GROUPS[sec.dataset.gi]);
      sec.querySelector(".gen-picked").textContent = n ? `已选 ${n}` : "";
    });
    roster.classList.toggle("full", state.selected.length >= pick);
    renderTray();
  }

  function renderTray() {
    const slots = [];
    for (let i = 0; i < pick; i++) {
      const m = BY_ID.get(state.selected[i]);
      slots.push(m
        ? `<li class="slot"><button type="button" data-remove="${m.id}" aria-label="移除 ${esc(m.name)}" title="点这里去掉 ${esc(m.name)}"><img src="${thumbSrc(m)}" alt="${esc(m.name)}"></button></li>`
        : `<li class="slot empty-slot" aria-label="空位"></li>`);
    }
    $("#slots").innerHTML = slots.join("");
    $("#tray").classList.toggle("wide", pick === 16);
    $("#slots").style.setProperty("--slots", String(pick === 16 ? 8 : 7));
    const left = pick - state.selected.length;
    const btn = $("#start-btn");
    btn.disabled = left > 0;
    btn.textContent = left > 0 ? `还差 ${left} 位` : "开始排序";
  }

  roster.addEventListener("click", (e) => {
    const head = e.target.closest(".gen-head");
    if (head) return toggleGroup(+head.parentElement.dataset.gi);
    const card = e.target.closest(".card");
    if (card) toggleMember(card.dataset.id);
  });

  $("#slots").addEventListener("click", (e) => {
    const b = e.target.closest("[data-remove]");
    if (b) toggleMember(b.dataset.remove);
  });

  document.querySelectorAll(".seg-filter button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".seg-filter button").forEach((x) => x.setAttribute("aria-checked", x === b));
      state.filter = b.dataset.filter;
      renderRoster();
      syncSelection();
    });
  });

  document.querySelectorAll(".seg-size button").forEach((b) => {
    b.addEventListener("click", () => {
      const next = +b.dataset.pick;
      if (next === pick) return;
      document.querySelectorAll(".seg-size button").forEach((x) => x.setAttribute("aria-checked", x === b));
      pick = next;
      if (state.selected.length > pick) state.selected.length = pick;
      $("#brand").textContent = kamiName();
      const title = $("#title-input");
      if (!title.dataset.dirty) title.value = defaultTitle();
      renderRoster();
      syncSelection();
    });
  });

  $("#title-input").addEventListener("change", () => { $("#title-input").dataset.dirty = "1"; });

  let searchTimer;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = e.target.value;
      renderRoster();
      syncSelection();
      roster.scrollTop = 0;
    }, 120);
  });

  $("#start-btn").addEventListener("click", () => startDuel(shuffle(state.selected.slice())));

  /* ---------------- duel (replayable merge sort) ---------------- */
  const duel = { order: [], answers: [], pair: null };

  function* mergeSort(a) {
    if (a.length <= 1) return a;
    const mid = a.length >> 1;
    const L = yield* mergeSort(a.slice(0, mid));
    const R = yield* mergeSort(a.slice(mid));
    const out = [];
    let i = 0, j = 0;
    while (i < L.length && j < R.length) {
      const leftWins = yield [L[i], R[j]];
      out.push(leftWins ? L[i++] : R[j++]);
    }
    return out.concat(L.slice(i), R.slice(j));
  }

  function worstCase(n) {
    return n <= 1 ? 0 : worstCase(n >> 1) + worstCase(n - (n >> 1)) + n - 1;
  }

  function shuffle(a) {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function startDuel(order) {
    duel.order = order;
    duel.answers = [];
    order.forEach((id) => { new Image().src = fullSrc(BY_ID.get(id)); });
    $("#duel-max").textContent = worstCase(order.length);
    show("duel");
    advance();
  }

  function advance() {
    const g = mergeSort(duel.order);
    let r = g.next();
    for (const a of duel.answers) r = g.next(a);
    if (r.done) return finish(r.value);
    duel.pair = r.value;
    const max = worstCase(duel.order.length);
    $("#duel-step").textContent = duel.answers.length + 1;
    $("#duel-bar").style.width = `${(duel.answers.length / max) * 100}%`;
    $("#undo-btn").disabled = duel.answers.length === 0;
    fillFighter($("#fighter-a"), BY_ID.get(r.value[0]));
    fillFighter($("#fighter-b"), BY_ID.get(r.value[1]));
  }

  function fillFighter(el, m) {
    el.classList.remove("picked");
    el.innerHTML = `<span class="ph"><img src="${fullSrc(m)}" alt=""></span>
      <span class="nm">${esc(m.name)}</span>
      <span class="kn">${esc(m.kana)}</span>
      <span class="meta">${esc(fullMeta(m))}</span>`;
    el.setAttribute("aria-label", `选 ${m.name}`);
  }

  let answering = false;
  function answer(leftWins) {
    if (answering || $("#phase-duel").hidden) return;
    answering = true;
    (leftWins ? $("#fighter-a") : $("#fighter-b")).classList.add("picked");
    setTimeout(() => {
      duel.answers.push(leftWins);
      answering = false;
      advance();
    }, 160);
  }

  function undo() {
    if (!duel.answers.length || $("#phase-duel").hidden) return;
    duel.answers.pop();
    advance();
  }

  $("#fighter-a").addEventListener("click", () => answer(true));
  $("#fighter-b").addEventListener("click", () => answer(false));
  $("#undo-btn").addEventListener("click", undo);
  $("#back-pick-btn").addEventListener("click", backToPick);

  document.addEventListener("keydown", (e) => {
    if ($("#phase-duel").hidden || e.target.closest?.("input, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "ArrowLeft") answer(true);
    else if (e.key === "ArrowRight") answer(false);
    else if (e.key === "z" || e.key === "Z" || e.key === "Backspace") undo();
  });

  function backToPick() {
    show("pick");
    renderRoster();
    syncSelection();
  }

  /* ---------------- result ---------------- */
  let ranking = [];

  function finish(ids) {
    ranking = ids.map((id) => BY_ID.get(id));
    $("#rank-list").innerHTML = ranking.map((m, i) => `<li>
      <span class="no">${i + 1}</span>
      <img src="${thumbSrc(m)}" alt="">
      <span class="nm">${esc(m.name)}<span class="meta">${esc(fullMeta(m))}</span></span>
    </li>`).join("");
    show("result");
    drawPoster();
  }

  let drawTimer;
  $("#title-input").addEventListener("input", () => {
    clearTimeout(drawTimer);
    drawTimer = setTimeout(drawPoster, 200);
  });
  $("#resort-btn").addEventListener("click", () => startDuel(shuffle(ranking.map((m) => m.id))));
  $("#restart-btn").addEventListener("click", backToPick);
  $("#save-btn").addEventListener("click", savePoster);
  $("#share-btn").addEventListener("click", () => {
    const text = `${$("#title-input").value.trim() || defaultTitle()}\n\n` +
      ranking.map((m, i) => `${i + 1}. ${m.name}`).join("\n") + "\n\n#AKB48 #好き顔ソート";
    const url = location.protocol.startsWith("http") && !/^(localhost|127\.)/.test(location.hostname) ? location.href.split("#")[0] : "";
    window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}${url ? "&url=" + encodeURIComponent(url) : ""}`, "_blank", "noopener");
  });

  /* ---------------- poster canvas ---------------- */
  const C = {
    floor: "#edeff3", card: "#ffffff", ink: "#1c1e2b", muted: "#6b6f80",
    line: "#d5d9e2", pink: "#e4007f", tape: "#f4c20d",
  };
  const UI_FONT = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif';
  const JP_FONT = '"Zen Kaku Gothic New","Hiragino Sans","Yu Gothic","Meiryo",' + UI_FONT;
  const DISPLAY = '"Dela Gothic One",' + JP_FONT;

  const imgCache = new Map();
  function loadImg(src) {
    if (!imgCache.has(src)) {
      imgCache.set(src, new Promise((res) => {
        const im = new Image();
        im.onload = () => res(im);
        im.onerror = () => res(null);
        im.src = src;
      }));
    }
    return imgCache.get(src);
  }

  async function fontsReady() {
    if (!document.fonts) return;
    const wait = Promise.all([
      document.fonts.load(`64px "Dela Gothic One"`),
      document.fonts.load(`700 40px "Zen Kaku Gothic New"`, "渡辺麻友"),
    ]);
    await Promise.race([wait, new Promise((r) => setTimeout(r, 2500))]);
  }

  function cover(ctx, im, x, y, w, h) {
    const s = Math.max(w / im.width, h / im.height);
    const sw = w / s, sh = h / s;
    const sx = (im.width - sw) / 2;
    const sy = Math.max(0, Math.min(im.height - sh, (im.height - sh) * 0.28));
    ctx.drawImage(im, sx, sy, sw, sh, x, y, w, h);
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function fitText(ctx, text, maxW, size, weight, family) {
    let s = size;
    do {
      ctx.font = `${weight} ${s}px ${family}`;
      if (ctx.measureText(text).width <= maxW) break;
      s -= 2;
    } while (s > 12);
    return s;
  }

  function tape(ctx, x, y, w, h, color, angle) {
    ctx.save();
    ctx.translate(x + w / 2, y + h / 2);
    ctx.rotate(angle);
    ctx.fillStyle = color;
    ctx.fillRect(-w / 2, -h / 2, w, h);
    ctx.restore();
  }

  function slot(ctx, im, m, rank, x, y, w, h, big) {
    ctx.save();
    ctx.shadowColor = "rgba(28,30,43,.18)";
    ctx.shadowBlur = 24;
    ctx.shadowOffsetY = 10;
    roundRect(ctx, x, y, w, h, 10);
    ctx.fillStyle = C.card;
    ctx.fill();
    ctx.restore();

    ctx.save();
    roundRect(ctx, x, y, w, h, 10);
    ctx.clip();
    if (im) cover(ctx, im, x, y, w, h);
    ctx.restore();

    const tw = big ? 118 : rank <= 3 ? 76 : 64;
    const th = big ? 70 : rank <= 3 ? 56 : 48;
    const tx = x - (big ? 14 : 10), ty = y - (big ? 18 : 14);
    tape(ctx, tx, ty, tw, th, big ? C.pink : C.tape, -0.06);
    ctx.save();
    ctx.translate(tx + tw / 2, ty + th / 2);
    ctx.rotate(-0.06);
    ctx.fillStyle = big ? "#fff" : C.ink;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    if (big) {
      ctx.font = `400 44px ${DISPLAY}`;
      ctx.fillText("1", -26, 3);
      ctx.font = `700 15px ${UI_FONT}`;
      ctx.fillText("CENTER", 22, 2);
    } else {
      ctx.font = `400 ${rank <= 3 ? 34 : 28}px ${DISPLAY}`;
      ctx.fillText(String(rank), 0, 3);
    }
    ctx.restore();

    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = C.ink;
    const nameSize = fitText(ctx, m.name, w + 10, big ? 44 : rank <= 3 ? 32 : 26, 700, JP_FONT);
    ctx.fillText(m.name, x + w / 2, y + h + nameSize + 14);
    const sub = m.status === "current" ? m.group
      : isTransfer(m) ? m.note
      : `${m.group} · ${m.end ? m.end.slice(0, 4) + "卒业" : "OG"}`;
    const subSize = fitText(ctx, sub, w + 10, big ? 20 : 17, 500, UI_FONT);
    ctx.fillStyle = C.muted;
    ctx.fillText(sub, x + w / 2, y + h + nameSize + subSize + 22);
  }

  function placeRow(ctx, imgs, start, count, y, w, h, gap) {
    const total = count * w + (count - 1) * gap;
    let x = (ctx.canvas.width - total) / 2;
    for (let i = 0; i < count; i++) {
      const idx = start + i;
      if (!ranking[idx]) continue;
      slot(ctx, imgs[idx], ranking[idx], idx + 1, x, y, w, h, false);
      x += w + gap;
    }
  }

  async function drawPoster() {
    if (!ranking.length) return;
    const canvas = $("#poster-canvas");
    const tall = ranking.length > 7;
    canvas.width = 1080;
    canvas.height = tall ? 1920 : 1440;
    $("#poster").classList.toggle("tall", tall);
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    const [imgs] = await Promise.all([Promise.all(ranking.map((m) => loadImg(fullSrc(m)))), fontsReady()]);

    ctx.fillStyle = C.floor;
    ctx.fillRect(0, 0, W, H);

    const title = $("#title-input").value.trim() || defaultTitle();
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = C.ink;
    fitText(ctx, title, W - 144, tall ? 56 : 64, 900, UI_FONT);
    ctx.fillText(title, 72, tall ? 100 : 118);
    tape(ctx, 72, tall ? 116 : 136, Math.min(ctx.measureText(title).width * 0.72, 520), 12, C.pink, -0.012);
    ctx.font = `500 24px ${UI_FONT}`;
    ctx.fillStyle = C.muted;
    const d = new Date();
    ctx.fillText(`AKB48 好き顔ソート · ${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`, 72, tall ? 168 : 190);

    if (!tall) {
      const fy = 262;
      const bigW = 392, bigH = 523, sideW = 272, sideH = 363, gap = 22;
      const fx = (W - (bigW + sideW * 2 + gap * 2)) / 2;
      const sideY = fy + bigH - sideH;
      if (ranking[1]) slot(ctx, imgs[1], ranking[1], 2, fx, sideY, sideW, sideH, false);
      if (ranking[2]) slot(ctx, imgs[2], ranking[2], 3, fx + sideW + gap + bigW + gap, sideY, sideW, sideH, false);
      slot(ctx, imgs[0], ranking[0], 1, fx + sideW + gap, fy, bigW, bigH, true);
      const by = fy + bigH + 150;
      const backW = 216, backH = 288, bgap = 26;
      placeRow(ctx, imgs, 3, 4, by, backW, backH, bgap);
    } else {
      // 3 / 6 / 7
      const fy = 210;
      const bigW = 300, bigH = 400, sideW = 220, sideH = 294, gap = 18;
      const fx = (W - (bigW + sideW * 2 + gap * 2)) / 2;
      const sideY = fy + bigH - sideH;
      if (ranking[1]) slot(ctx, imgs[1], ranking[1], 2, fx, sideY, sideW, sideH, false);
      if (ranking[2]) slot(ctx, imgs[2], ranking[2], 3, fx + sideW + gap + bigW + gap, sideY, sideW, sideH, false);
      slot(ctx, imgs[0], ranking[0], 1, fx + sideW + gap, fy, bigW, bigH, true);

      const midY = fy + bigH + 92;
      placeRow(ctx, imgs, 3, 6, midY, 148, 198, 14);
      const backY = midY + 198 + 78;
      placeRow(ctx, imgs, 9, 7, backY, 128, 170, 12);
    }

    ctx.strokeStyle = C.line;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(72, H - 84);
    ctx.lineTo(W - 72, H - 84);
    ctx.stroke();
    ctx.font = `700 22px ${UI_FONT}`;
    ctx.fillStyle = C.ink;
    ctx.textAlign = "left";
    ctx.fillText("#AKB48  #好き顔ソート", 72, H - 44);
    ctx.textAlign = "right";
    ctx.font = `500 18px ${UI_FONT}`;
    ctx.fillStyle = C.muted;
    ctx.fillText("照片：48pedia.org", W - 72, H - 44);

    try {
      $("#poster-img").src = canvas.toDataURL("image/png");
    } catch (err) {
      $("#poster-img").alt = "图片生成失败：请通过网址（http://）打开本页，而不是直接双击 html 文件。";
      console.error(err);
    }
  }

  function savePoster() {
    const canvas = $("#poster-canvas");
    canvas.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = pick === 16 ? "akb48_kami16.png" : "akb48_kami7.png";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    }, "image/png");
  }

  /* ---------------- boot ---------------- */
  renderRoster();
  syncSelection();
})();
