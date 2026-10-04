#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TIC TAC TOE PREMIUM BOT  --  tic.py   (single file)

Needs   : Python 3.9+    ->   pip install httpx
Run     : BOT_TOKEN=123456:ABC python tic.py     (or paste the token below)
Features: colored inline buttons (Bot API 9.4 "style"), premium custom emoji
          everywhere (text + button icons), forced channel join, groups games
          (NxN boards 3..8), challenges, stats, leaderboard, owner admin panel.
"""
import asyncio
import csv
import html
import io
import logging
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone

import httpx

# ============================== CONFIG ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8692191305:AAHH49I93AIMnvkNrpswVZufRAjyb1mf1ks")
OWNER_ID = 8200980090
OWNER_LINK = "https://t.me/X_NAGI7"
CHANNEL_ID = -1002740009398
CHANNEL_LINK = "https://t.me/+2Fxg6o4jEKAxOGQ1"
DB_FILE = "tic.db"
MIN_N, MAX_N = 3, 8          # board size limits (/game N)
GAME_IDLE = 600              # seconds of inactivity before a game expires
HEALTH_PORT = int(os.getenv("PORT", "8080"))   # /health server port (UptimeRobot ping)
# ====================================================================

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("tic")

# ======================= PREMIUM EMOJI MAP ==========================
# plain emoji -> custom (premium) emoji id.  Every emoji typed in any
# text or button below is auto-converted, so nothing is ever left plain.
EMOJI = {
    "⭐": "6309569217117035347", "👑": "6310083389126876253", "🔥": "6309811869884358547",
    "✅": "6309618368722770953", "❌": "5210952531676504517", "🎁": "6312282231993801242",
    "🔔": "6311933167116753547", "🏆": "6311834808070708173", "👾": "5361741454685256344",
    "🤖": "6309920764485180319", "✨": "6312315895947467982", "⚡": "6309883501348919953",
    "⚠": "6309743751703042732", "🔒": "6310091871687286225", "🔗": "6309893061946121745",
    "📊": "6309843875980648126", "📣": "6309618596356039410", "✉": "6312231491250165922",
    "👤": "5902335789798265487", "⚙": "5893161718179173515", "🎉": "6309961712703379735",
    "💀": "6309959943176855354", "💎": "6310032545304026289", "📌": "6309960153630251694",
    "🧩": "4958903389523018769", "👋": "4958832114540741368", "👀": "6309744151135001261",
    "➕": "5397916757333654639", "🛡": "5251203410396458957", "🆕": "5382357040008021292",
    "🔄": "5375338737028841420", "🗑": "6309887495668505491", "🚫": "6312156428106737991",
    "📞": "5893297890117292323", "🌐": "5447410659077661506", "💡": "5422439311196834318",
    "🥈": "5447203607294265305", "🥉": "5453902265922376865", "❤": "6309591606781549616",
    "💯": "6309565261452157609", "⏳": "5386367538735104399", "🔴": "5411225014148014586",
    "🟢": "5416081784641168838", "🔵": "6310043042204097096", "⬜": "6309619116047080957",
    "➡": "6311966281314606219", "⬆": "5415655814079723871", "⬇": "5406745015365943482",
    "💼": "5893255507380014983", "💬": "6310075555106528104", "📅": "5413879192267805083",
    "🔍": "5231012545799666522", "ℹ": "5334544901428229844", "❓": "5452069934089641166",
    "😎": "6309750421787254668", "🤩": "6309631429718318812", "🥳": "6309717891704954276",
    "📈": "5244837092042750681", "✔": "6310103949135322908", "🎖": "5440539497383087970",
    "📱": "5895652322469482989", "🏘": "5416041192905265756", "🔧": "5341715473882955310",
    "💰": "5893473283696759404", "🔊": "5388632425314140043", "🧠": "4958937938239947673",
    "⏰": "5902050947567194830", "🚩": "6309813746785066712", "🆗": "4956649845952611245",
    "📍": "4958728373900674046", "🔼": "6309994659397507681", "⏩": "6309994015152413596",
    "📬": "5253742260054409879", "🌟": "6309718793648084936", "🚀": "6309870788245724520",
    "💫": "6309969117226998989", "🗺": "5391032818111363540", "😭": "6312088000687773817",
}
_KEYS = "|".join(re.escape(k) for k in sorted(EMOJI, key=len, reverse=True))
_EMO_RE = re.compile(f"({_KEYS})\ufe0f?")
_LEAD_RE = re.compile(f"^({_KEYS})\ufe0f?")


def prem(text: str) -> str:
    """Convert every known emoji in an HTML text into a premium custom emoji."""
    return _EMO_RE.sub(lambda m: f'<tg-emoji emoji-id="{EMOJI[m.group(1)]}">{m.group(1)}</tg-emoji>', text)


# ============================ BUTTONS ===============================
def B(text, cb=None, url=None, style="primary"):
    """style: success (green) | danger (red) | primary (blue) | None (default)."""
    return {"t": text, "cb": cb, "url": url, "style": style}


def render_kb(rows, premium=True):
    out = []
    for row in rows:
        r = []
        for b in row:
            text, d = b["t"], {}
            m = _LEAD_RE.match(text)
            if premium and m:  # leading emoji -> premium icon on the button
                d["icon_custom_emoji_id"] = EMOJI[m.group(1)]
                text = text[m.end():].strip() or "\u2800"
            d["text"] = text
            if b.get("cb") is not None:
                d["callback_data"] = b["cb"]
            if b.get("url"):
                d["url"] = b["url"]
            if b.get("style"):
                d["style"] = b["style"]
            r.append(d)
        out.append(r)
    return {"inline_keyboard": out}


# ============================ DATABASE ==============================
db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, name TEXT, username TEXT,
    started INTEGER DEFAULT 0, banned INTEGER DEFAULT 0, blocked INTEGER DEFAULT 0,
    joined_at INTEGER, last_seen INTEGER);
CREATE TABLE IF NOT EXISTS chats(
    id INTEGER PRIMARY KEY, title TEXT, type TEXT,
    is_admin INTEGER DEFAULT 0, active INTEGER DEFAULT 1, added_at INTEGER);
CREATE TABLE IF NOT EXISTS stats(
    user_id INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0, draws INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
""")
db.commit()


def q(sql, args=()):
    return db.execute(sql, args).fetchall()


def q1(sql, args=()):
    return db.execute(sql, args).fetchone()


def ex(sql, args=()):
    db.execute(sql, args)
    db.commit()


def get_set(k, default="0"):
    r = q1("SELECT v FROM settings WHERE k=?", (k,))
    return r["v"] if r else default


def put_set(k, v):
    ex("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def clean_name(u):
    n = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x)
    n = _EMO_RE.sub("", n).strip()[:32]
    return n or "Player"


def puser(u):
    return {"id": u["id"], "name": clean_name(u), "username": u.get("username")}


def upsert_user(u, started=False):
    now = int(time.time())
    ex("""INSERT INTO users(id,name,username,started,joined_at,last_seen) VALUES(?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET name=excluded.name, username=excluded.username,
          last_seen=excluded.last_seen, started=MAX(started, excluded.started),
          blocked=CASE WHEN excluded.started=1 THEN 0 ELSE blocked END""",
       (u["id"], clean_name(u), u.get("username"), 1 if started else 0, now, now))


def upsert_chat(chat, is_admin=None, active=1):
    now = int(time.time())
    if q1("SELECT id FROM chats WHERE id=?", (chat["id"],)) is None:
        ex("INSERT INTO chats(id,title,type,is_admin,active,added_at) VALUES(?,?,?,?,?,?)",
           (chat["id"], chat.get("title") or "Group", chat["type"], 1 if is_admin else 0, active, now))
    else:
        ex("UPDATE chats SET title=?, type=?, active=? WHERE id=?",
           (chat.get("title") or "Group", chat["type"], active, chat["id"]))
        if is_admin is not None:
            ex("UPDATE chats SET is_admin=? WHERE id=?", (1 if is_admin else 0, chat["id"]))


def bump(uid, col):
    ex("INSERT OR IGNORE INTO stats(user_id) VALUES(?)", (uid,))
    ex(f"UPDATE stats SET {col}={col}+1 WHERE user_id=?", (uid,))


# ============================ TELEGRAM API ==========================
class TgError(Exception):
    def __init__(self, method, code, desc):
        super().__init__(f"{method}: {code} {desc}")
        self.code, self.desc = code, desc


http = None
ME = {}


async def call(method, **params):
    timeout = params.pop("_t", 60)
    params = {k: v for k, v in params.items() if v is not None}
    for attempt in range(3):
        try:
            r = await http.post(f"{API}/{method}", json=params, timeout=timeout)
        except httpx.HTTPError:
            if attempt == 2:
                raise
            await asyncio.sleep(1 + attempt)
            continue
        try:
            data = r.json()
        except Exception:
            raise TgError(method, r.status_code, r.text[:200])
        if data.get("ok"):
            return data["result"]
        code, desc = data.get("error_code", 0), data.get("description", "")
        if code == 429:
            await asyncio.sleep(data.get("parameters", {}).get("retry_after", 1) + 0.5)
            continue
        raise TgError(method, code, desc)
    raise TgError(method, 0, "retries exhausted")


async def send(chat_id, text, rows=None, reply_to=None, **extra):
    """Send HTML text; premium emoji everywhere, with a plain fallback."""
    for on in (True, False):
        p = {"chat_id": chat_id, "text": prem(text) if on else text, "parse_mode": "HTML",
             "link_preview_options": {"is_disabled": True}}
        if reply_to:
            p["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        p.update(extra)
        if rows:
            p["reply_markup"] = render_kb(rows, on)
        try:
            return await call("sendMessage", **p)
        except TgError as e:
            if e.code != 400 or not on:
                raise
            log.warning("premium send failed (%s) -> plain fallback", e.desc)


async def edit(chat_id, msg_id, text, rows=None):
    for on in (True, False):
        p = {"chat_id": chat_id, "message_id": msg_id, "text": prem(text) if on else text,
             "parse_mode": "HTML", "link_preview_options": {"is_disabled": True},
             "reply_markup": render_kb(rows or [], on)}
        try:
            return await call("editMessageText", **p)
        except TgError as e:
            if "not modified" in e.desc:
                return None
            if e.code != 400 or not on:
                raise
            log.warning("premium edit failed (%s) -> plain fallback", e.desc)


async def answer(cb, text=None, alert=False):
    try:
        await call("answerCallbackQuery", callback_query_id=cb["id"], text=text, show_alert=alert or None)
    except TgError:
        pass


async def safe_delete(chat_id, msg_id):
    try:
        await call("deleteMessage", chat_id=chat_id, message_id=msg_id)
    except TgError:
        pass


def H(s):
    return html.escape(str(s))


def mention(p):
    return f'<a href="tg://user?id={p["id"]}">{H(p["name"])}</a>'


def ent_text(text, e):
    b = text.encode("utf-16-le")
    return b[e["offset"] * 2:(e["offset"] + e["length"]) * 2].decode("utf-16-le")


def add_group_url():
    return f"https://t.me/{ME.get('username', '')}?startgroup=true"


# ============================ GAME ENGINE ===========================
GAMES, LOBBIES, CHALLENGES, PENDING, ACTIVE = {}, {}, {}, {}, {}
AWAIT, BC = {}, {}


class Game:
    def __init__(self, chat_id, n, p1, p2):
        self.id = secrets.token_hex(3)
        self.chat_id, self.n, self.win = chat_id, n, min(n, 5)
        self.players = [p1, p2]
        self.board = [0] * (n * n)       # 0 empty | 1 = X | 2 = O
        self.turn, self.moves = 0, 0
        self.over, self.winner, self.line = False, None, []
        self.msg_id, self.updated = None, time.time()
        self.expired, self.rematched = False, False
        self.lock = asyncio.Lock()

    def check(self, idx):
        n, r, c, m = self.n, idx // self.n, idx % self.n, self.board[idx]
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            cells = [idx]
            for s in (1, -1):
                rr, cc = r + dr * s, c + dc * s
                while 0 <= rr < n and 0 <= cc < n and self.board[rr * n + cc] == m:
                    cells.append(rr * n + cc)
                    rr, cc = rr + dr * s, cc + dc * s
            if len(cells) >= self.win:
                return sorted(cells)
        return None


MARK = {1: ("❌", "danger"), 2: ("🔵", "primary")}


def game_rows(g):
    rows = []
    for r in range(g.n):
        row = []
        for c in range(g.n):
            i, v = r * g.n + c, g.board[r * g.n + c]
            if v:
                icon, style = MARK[v]
                row.append(B(icon, f"m:{g.id}:{i}", style="success" if i in g.line else style))
            else:
                row.append(B("⬜", f"m:{g.id}:{i}", style=None))
        rows.append(row)
    if g.expired or g.rematched:
        return rows
    if g.over:
        rows.append([B("🔄 Rematch", f"rm:{g.id}", style="success"), B("🗑 Close", f"cl:{g.id}", style="danger")])
    else:
        rows.append([B("🚩 Surrender", f"sur:{g.id}", style="danger")])
    return rows


def game_text(g):
    p1, p2 = g.players
    t = (f"👾 <b>Tic Tac Toe</b>  •  {g.n}×{g.n}  •  {g.win} in a row\n\n"
         f"❌ {mention(p1)} <b>(X)</b>\n🔵 {mention(p2)} <b>(O)</b>\n\n")
    if g.expired:
        return t + "⏳ <b>Game expired</b> — no moves for a while."
    if g.over:
        if g.winner is None:
            t += "🆗 <b>It's a draw!</b> Well played, both of you."
        else:
            t += f"🏆 <b>{H(g.players[g.winner]['name'])} wins!</b> 🎉"
        return t + f"\n📊 Moves: <b>{g.moves}</b>"
    cur = g.players[g.turn]
    return t + f"⏳ Turn: {mention(cur)} <b>({'X' if g.turn == 0 else 'O'})</b>\n📊 Moves: <b>{g.moves}</b>"


def finish(g, widx):
    g.over, g.winner, g.updated = True, widx, time.time()
    for p in g.players:
        ACTIVE.pop((g.chat_id, p["id"]), None)
    put_set("games_total", int(get_set("games_total", "0")) + 1)
    if widx is None:
        for p in g.players:
            bump(p["id"], "draws")
    else:
        bump(g.players[widx]["id"], "wins")
        bump(g.players[1 - widx]["id"], "losses")


async def start_game(chat_id, p1, p2, n, msg_id=None):
    g = Game(chat_id, n, p1, p2)
    GAMES[g.id] = g
    ACTIVE[(chat_id, p1["id"])] = g.id
    ACTIVE[(chat_id, p2["id"])] = g.id
    if msg_id:
        await edit(chat_id, msg_id, game_text(g), game_rows(g))
        g.msg_id = msg_id
    else:
        res = await send(chat_id, game_text(g), game_rows(g))
        g.msg_id = res["message_id"]
    return g


async def on_move(cb, gid, idx):
    g = GAMES.get(gid)
    if not g:
        return await answer(cb, "This game has expired.", True)
    async with g.lock:
        uid = cb["from"]["id"]
        if g.over:
            return await answer(cb, "The game is over.")
        if uid not in (g.players[0]["id"], g.players[1]["id"]):
            return await answer(cb, "You are not playing in this game!", True)
        if uid != g.players[g.turn]["id"]:
            return await answer(cb, "Wait for your turn ⏳")
        if not 0 <= idx < len(g.board) or g.board[idx]:
            return await answer(cb, "That box is already taken!")
        g.board[idx] = g.turn + 1
        g.moves += 1
        g.updated = time.time()
        line = g.check(idx)
        if line:
            g.line = line
            finish(g, g.turn)
        elif g.moves == len(g.board):
            finish(g, None)
        else:
            g.turn ^= 1
        asyncio.create_task(answer(cb))
        await edit(g.chat_id, g.msg_id, game_text(g), game_rows(g))


async def on_surrender(cb, gid):
    g = GAMES.get(gid)
    if not g or g.over:
        return await answer(cb, "No active game.")
    uid = cb["from"]["id"]
    ids = [p["id"] for p in g.players]
    if uid not in ids:
        return await answer(cb, "You are not playing in this game!", True)
    async with g.lock:
        finish(g, 1 - ids.index(uid))
        await answer(cb, "You surrendered 🚩")
        await edit(g.chat_id, g.msg_id, game_text(g), game_rows(g))


async def on_rematch(cb, gid):
    g = GAMES.get(gid)
    uid = cb["from"]["id"]
    if not g or not g.over or g.expired or g.rematched:
        return await answer(cb, "Rematch is not available.", True)
    if uid not in [p["id"] for p in g.players]:
        return await answer(cb, "Only the players can start a rematch!", True)
    if any((g.chat_id, p["id"]) in ACTIVE for p in g.players):
        return await answer(cb, "A player is already in another game.", True)
    g.rematched = True
    await answer(cb, "Rematch! 🔥")
    await edit(g.chat_id, g.msg_id, game_text(g), game_rows(g))
    await start_game(g.chat_id, g.players[1], g.players[0], g.n)


async def on_close(cb, gid):
    g = GAMES.get(gid)
    uid = cb["from"]["id"]
    if not g:
        await answer(cb)
        return await safe_delete(cb["message"]["chat"]["id"], cb["message"]["message_id"])
    if uid not in [p["id"] for p in g.players] and uid != OWNER_ID:
        return await answer(cb, "Only the players can close this.", True)
    GAMES.pop(gid, None)
    await answer(cb)
    await safe_delete(g.chat_id, g.msg_id)


# ======================== LOBBY / CHALLENGE =========================
def size_rows(prefix_uid):
    nums = list(range(MIN_N, MAX_N + 1))
    styles = {3: "success", 4: "primary", 5: "primary", 6: "danger", 7: "danger", 8: "danger"}
    btns = [B(f"🧩 {n}×{n}", f"sz:{prefix_uid}:{n}", style=styles[n]) for n in nums]
    return [btns[i:i + 3] for i in range(0, len(btns), 3)]


async def begin(chat_id, host, n):
    if (chat_id, host["id"]) in ACTIVE:
        return await send(chat_id, f"⚠ {mention(host)}, you already have a game or lobby here. Use /cancel to end it.")
    pend = PENDING.pop((chat_id, host["id"]), None)
    if pend and time.time() - pend["ts"] < 900 and (chat_id, pend["opp"]["id"]) not in ACTIVE:
        return await start_game(chat_id, host, pend["opp"], n)
    lid = secrets.token_hex(3)
    LOBBIES[lid] = {"chat": chat_id, "host": host, "n": n, "ts": time.time(), "msg": None}
    ACTIVE[(chat_id, host["id"])] = lid
    text = (f"👾 <b>Tic Tac Toe Lobby</b>  •  {n}×{n}\n\n"
            f"👑 Host: {mention(host)}\n⏳ Waiting for an opponent…\n\n"
            f"🔥 Tap <b>Join</b> to play!")
    rows = [[B("👾 Join Game", f"jn:{lid}", style="success"), B("❌ Cancel", f"lc:{lid}", style="danger")]]
    res = await send(chat_id, text, rows)
    LOBBIES[lid]["msg"] = res["message_id"]


async def on_join(cb, lid):
    lob = LOBBIES.get(lid)
    if not lob:
        return await answer(cb, "This lobby is no longer available.", True)
    chat_id, user = lob["chat"], puser(cb["from"])
    if user["id"] == lob["host"]["id"]:
        return await answer(cb, "You can't play against yourself 😎", True)
    if (chat_id, user["id"]) in ACTIVE:
        return await answer(cb, "You are already in a game here.", True)
    LOBBIES.pop(lid, None)
    ACTIVE.pop((chat_id, lob["host"]["id"]), None)
    upsert_user(cb["from"])
    await answer(cb, "Game on! 🔥")
    await start_game(chat_id, lob["host"], user, lob["n"], msg_id=lob["msg"])


async def on_lobby_cancel(cb, lid):
    lob = LOBBIES.get(lid)
    if not lob:
        return await answer(cb, "Already closed.")
    if cb["from"]["id"] not in (lob["host"]["id"], OWNER_ID):
        return await answer(cb, "Only the host can cancel.", True)
    LOBBIES.pop(lid, None)
    ACTIVE.pop((lob["chat"], lob["host"]["id"]), None)
    await answer(cb)
    await edit(lob["chat"], lob["msg"], "❌ <b>Lobby cancelled.</b>", [[B("👾 Add me to your group", url=add_group_url())]])


async def on_size(cb, uid, n):
    if cb["from"]["id"] != uid:
        return await answer(cb, "This menu is not for you!", True)
    if not MIN_N <= n <= MAX_N:
        return await answer(cb)
    chat_id = cb["message"]["chat"]["id"]
    await answer(cb, f"{n}×{n} selected ✅")
    await safe_delete(chat_id, cb["message"]["message_id"])
    await begin(chat_id, puser(cb["from"]), n)


async def on_challenge(cb, action, cid, tid, n=0):
    ch = CHALLENGES.get(f"{cid}:{tid}")
    if not ch:
        return await answer(cb, "This challenge has expired.", True)
    if cb["from"]["id"] != tid:
        return await answer(cb, "This challenge is not for you!", True)
    chat_id, msg_id = ch["chat"], ch["msg"]
    C, T = ch["c"], ch["t"]
    CHALLENGES.pop(f"{cid}:{tid}", None)
    if action == "pd":
        await answer(cb, "Declined.")
        return await edit(chat_id, msg_id, f"❌ {mention(T)} declined the challenge from {mention(C)}.",
                          [[B("👾 Add me to your group", url=add_group_url())]])
    if (chat_id, cid) in ACTIVE or (chat_id, tid) in ACTIVE:
        await answer(cb, "A player is already in another game.", True)
        return await edit(chat_id, msg_id, "⚠ <b>Challenge cancelled</b> — a player is busy in another game.")
    await answer(cb, "Challenge accepted! 🔥")
    if n:
        await edit(chat_id, msg_id, f"🎉 {mention(T)} accepted the challenge from {mention(C)}!")
        return await start_game(chat_id, C, T, n)
    PENDING[(chat_id, cid)] = {"opp": T, "ts": time.time()}
    text = (f"🎉 <b>Challenge accepted!</b>\n\n👑 {mention(C)}  vs  {mention(T)}\n\n"
            f"⚡ {mention(C)}, choose the board size — tap below or send /game <code>N</code> ({MIN_N}-{MAX_N}).")
    await edit(chat_id, msg_id, text, size_rows(cid))


# ============================ UI TEXTS ==============================
def welcome_text(name):
    return (f"👑 <b>Welcome, {H(name)}!</b>\n\n"
            f"👾 <b>Tic Tac Toe — Premium Edition</b>\n"
            f"Challenge your friends inside any group and battle on boards from "
            f"<b>3×3 up to 8×8</b> with live, colorful buttons!\n\n"
            f"⚡ /game <code>4</code> — start a match\n"
            f"🔥 /ply — challenge a player\n"
            f"🏆 /top — leaderboard\n"
            f"📌 /guide — full guide\n\n"
            f"🚀 Add me to your group and let the games begin!")


def welcome_rows():
    return [[B("📞 Contact Owner", url=OWNER_LINK, style="primary")],
            [B("📣 Update", url=CHANNEL_LINK, style="success")],
            [B("➕ Add me to your group", url=add_group_url(), style="danger")]]


GUIDE = (
    "📌 <b>Tic Tac Toe — Complete Guide</b>\n\n"
    "👾 <b>Playing</b>\n"
    f"⚡ /game <code>N</code> — open a lobby with an N×N board ({MIN_N}-{MAX_N}). Example: /game <code>4</code>\n"
    "⚡ /game — pick the board size with buttons\n"
    "🔥 /ply — reply to someone (or mention them) to challenge them. If they accept, "
    "send /game <code>N</code> to begin. Shortcut: /ply @user <code>4</code>\n"
    "❌ /cancel — end your own lobby / game\n\n"
    "🏆 <b>Stats</b>\n"
    "📊 /stats — your record (reply to see someone else's)\n"
    "🏆 /top — global top 10 players\n\n"
    "💡 <b>Rules</b>\n"
    "❌ goes first, 🔵 second. Get 3 in a row on 3×3, 4 on 4×4, and 5 in a row on 5×5 or bigger "
    "(rows, columns or diagonals).\n"
    "🟢 Green buttons = the winning line.\n"
    "⏳ A game with no moves for 10 minutes expires.\n\n"
    "🔔 Others: /id — your Telegram ID  •  /start — main menu")


def top_text(limit=10):
    rows = q("""SELECT s.user_id, s.wins, s.losses, s.draws, u.name FROM stats s
                LEFT JOIN users u ON u.id=s.user_id ORDER BY s.wins DESC, s.losses ASC LIMIT ?""", (limit,))
    if not rows:
        return "🏆 <b>Leaderboard</b>\n\n👀 No games played yet. Be the first — /game 3"
    medals = ["🏆", "🥈", "🥉"]
    t = "🏆 <b>Global Leaderboard</b>\n\n"
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"<b>{i + 1}.</b>"
        t += f"{m} {H(r['name'] or 'Player')} — <b>{r['wins']}</b>W • {r['losses']}L • {r['draws']}D\n"
    return t


async def force_join_gate(chat_id, uid):
    """Return True if the user may continue; otherwise show the join screen."""
    if get_set("force_join", "1") != "1" or uid == OWNER_ID:
        return True
    if await is_joined(uid):
        return True
    text = ("🔒 <b>Access Locked</b>\n\nTo use this bot you must join our official channel first.\n\n"
            "📣 Join the channel, then press <b>Check</b> to unlock everything!")
    await send(chat_id, text, [[B("📣 Join Channel", url=CHANNEL_LINK, style="primary")],
                               [B("✅ I've Joined — Check", "fj", style="success")]])
    return False


_warned = {"fj": False}


async def is_joined(uid):
    try:
        m = await call("getChatMember", chat_id=CHANNEL_ID, user_id=uid)
    except TgError as e:
        log.error("force-join check failed: %s (is the bot an admin of the channel?)", e)
        if not _warned["fj"]:
            _warned["fj"] = True
            try:
                await send(OWNER_ID, "⚠ <b>Force-join check failed.</b>\nMake sure the bot is an <b>admin</b> "
                                     f"in the channel.\n<code>{H(e.desc)}</code>")
            except Exception:
                pass
        return True
    st = m.get("status")
    return st in ("member", "administrator", "creator") or (st == "restricted" and m.get("is_member"))


async def on_fj(cb):
    uid = cb["from"]["id"]
    if await is_joined(uid):
        await answer(cb, "Verified ✅")
        upsert_user(cb["from"], started=True)
        await edit(cb["message"]["chat"]["id"], cb["message"]["message_id"],
                   welcome_text(clean_name(cb["from"])), welcome_rows())
    else:
        await answer(cb, "❌ You haven't joined the channel yet!", True)


# ============================= COMMANDS =============================
async def cmd_start(m, args):
    chat, u = m["chat"], m["from"]
    if chat["type"] != "private":
        return await send(chat["id"], "👾 <b>Tic Tac Toe is ready!</b>\n\n⚡ Start a match with /game <code>3</code>\n"
                                      "🔥 Challenge someone with /ply\n📌 Full guide: /guide",
                          [[B("📌 Open in private", url=f"https://t.me/{ME['username']}?start=guide", style="primary")]])
    first = q1("SELECT started FROM users WHERE id=?", (u["id"],))
    is_new = not first or not first["started"]
    upsert_user(u, started=True)
    if not await force_join_gate(chat["id"], u["id"]):
        return
    await send(chat["id"], welcome_text(clean_name(u)), welcome_rows())
    if u["id"] == OWNER_ID:
        await set_owner_commands()
    if is_new and u["id"] != OWNER_ID:
        total = q1("SELECT COUNT(*) c FROM users WHERE started=1")["c"]
        uname = f"@{u['username']}" if u.get("username") else "no username"
        await send(OWNER_ID, f"🆕 <b>New user started the bot</b>\n\n👤 {mention(puser(u))}\n"
                             f"📍 ID: <code>{u['id']}</code> • {H(uname)}\n📊 Total users: <b>{total}</b>")


async def cmd_guide(m, args):
    await send(m["chat"]["id"], GUIDE, [[B("➕ Add me to your group", url=add_group_url(), style="primary")],
                                        [B("📞 Contact Owner", url=OWNER_LINK, style="success")]])


async def cmd_game(m, args):
    chat, u = m["chat"], m["from"]
    if chat["type"] == "private":
        return await send(chat["id"], "👾 <b>Games are played in groups!</b>\n\nAdd me to a group, then send "
                                      "/game <code>3</code> there.",
                          [[B("➕ Add me to your group", url=add_group_url(), style="primary")]])
    me = puser(u)
    if args:
        if not args[0].isdigit() or not MIN_N <= int(args[0]) <= MAX_N:
            return await send(chat["id"], f"⚠ Board size must be a number from <b>{MIN_N}</b> to <b>{MAX_N}</b>.\n"
                                          "Example: /game <code>4</code>")
        return await begin(chat["id"], me, int(args[0]))
    await send(chat["id"], f"🧩 {mention(me)}, choose the <b>board size</b>\nor send /game <code>N</code> (example: /game 4)",
               size_rows(me["id"]))


def find_target(m):
    r = m.get("reply_to_message")
    if r and r.get("from") and not r["from"].get("is_bot"):
        return puser(r["from"])
    text = m.get("text", "")
    for e in m.get("entities", []):
        if e["type"] == "text_mention":
            return puser(e["user"])
        if e["type"] == "mention":
            un = ent_text(text, e).lstrip("@").lower()
            row = q1("SELECT id,name FROM users WHERE lower(username)=?", (un,))
            return {"id": row["id"], "name": row["name"]} if row else "unknown"
    return None


async def cmd_ply(m, args):
    chat, u = m["chat"], m["from"]
    if chat["type"] == "private":
        return await send(chat["id"], "🔥 Challenges work inside groups — add me to one!",
                          [[B("➕ Add me to your group", url=add_group_url(), style="primary")]])
    me, tgt = puser(u), find_target(m)
    n = next((int(a) for a in args if a.isdigit() and MIN_N <= int(a) <= MAX_N), 0)
    if tgt is None:
        return await send(chat["id"], "🔥 <b>Challenge someone!</b>\n\nReply to a player's message with /ply, or mention "
                                      "them: /ply @username", reply_to=m["message_id"])
    if tgt == "unknown":
        return await send(chat["id"], "👀 I don't know that user yet. Reply to their message with /ply instead.",
                          reply_to=m["message_id"])
    if tgt["id"] == me["id"]:
        return await send(chat["id"], "😎 You can't challenge yourself!", reply_to=m["message_id"])
    if (chat["id"], me["id"]) in ACTIVE or (chat["id"], tgt["id"]) in ACTIVE:
        return await send(chat["id"], "⚠ You or your opponent already have a game running here.", reply_to=m["message_id"])
    text = (f"🔥 <b>Tic Tac Toe Challenge!</b>\n\n👑 {mention(me)} challenges {mention(tgt)}"
            f"{f' on a {n}×{n} board' if n else ''}!\n\n⏳ {mention(tgt)}, do you accept?")
    rows = [[B("✅ Accept", f"pa:{me['id']}:{tgt['id']}:{n}", style="success"),
             B("❌ Decline", f"pd:{me['id']}:{tgt['id']}", style="danger")]]
    res = await send(chat["id"], text, rows)
    CHALLENGES[f"{me['id']}:{tgt['id']}"] = {"chat": chat["id"], "msg": res["message_id"], "c": me, "t": tgt, "ts": time.time()}


async def cmd_cancel(m, args):
    chat, uid = m["chat"], m["from"]["id"]
    ref = ACTIVE.get((chat["id"], uid))
    if not ref:
        return await send(chat["id"], "👀 You have no active game or lobby here.")
    if ref in LOBBIES:
        lob = LOBBIES.pop(ref)
        ACTIVE.pop((chat["id"], uid), None)
        await edit(lob["chat"], lob["msg"], "❌ <b>Lobby cancelled.</b>")
    elif ref in GAMES:
        g = GAMES[ref]
        g.over, g.expired = True, True
        for p in g.players:
            ACTIVE.pop((g.chat_id, p["id"]), None)
        await edit(g.chat_id, g.msg_id, "❌ <b>Game cancelled</b> by a player (no score counted).")
    await send(chat["id"], "✅ Cancelled.")


async def cmd_stats(m, args):
    r = m.get("reply_to_message")
    u = r["from"] if r and r.get("from") and not r["from"].get("is_bot") else m["from"]
    s = q1("SELECT * FROM stats WHERE user_id=?", (u["id"],))
    w, l, d = (s["wins"], s["losses"], s["draws"]) if s else (0, 0, 0)
    tot = w + l + d
    rate = f"{w * 100 // tot}%" if tot else "—"
    await send(m["chat"]["id"], f"📊 <b>Stats — {H(clean_name(u))}</b>\n\n🏆 Wins: <b>{w}</b>\n💀 Losses: <b>{l}</b>\n"
                                f"🆗 Draws: <b>{d}</b>\n👾 Games: <b>{tot}</b>\n📈 Win rate: <b>{rate}</b>",
               [[B("🏆 Leaderboard", "top", style="success")]])


async def cmd_top(m, args):
    await send(m["chat"]["id"], top_text(), [[B("👾 Play now: /game 3", "noop", style="primary")]])


async def cmd_id(m, args):
    await send(m["chat"]["id"], f"👤 Your ID: <code>{m['from']['id']}</code>\n💬 Chat ID: <code>{m['chat']['id']}</code>")


async def cmd_admin(m, args):
    if m["from"]["id"] != OWNER_ID:
        return
    await send(m["chat"]["id"], admin_home_text(), admin_home_rows())


async def cmd_ban(m, args, flag=1):
    if m["from"]["id"] != OWNER_ID:
        return
    if not args or not args[0].lstrip("-").isdigit():
        return await send(m["chat"]["id"], "⚠ Usage: /ban <code>user_id</code>  or  /unban <code>user_id</code>")
    ex("UPDATE users SET banned=? WHERE id=?", (flag, int(args[0])))
    await send(m["chat"]["id"], f"{'🚫 Banned' if flag else '✅ Unbanned'}: <code>{int(args[0])}</code>")


async def cmd_unban(m, args):
    await cmd_ban(m, args, 0)


COMMANDS = {"start": cmd_start, "guide": cmd_guide, "help": cmd_guide, "game": cmd_game, "ply": cmd_ply,
            "cancel": cmd_cancel, "stats": cmd_stats, "top": cmd_top, "id": cmd_id,
            "admin": cmd_admin, "ban": cmd_ban, "unban": cmd_unban}


# ========================== ADMIN PANEL =============================
def ts(t):
    return datetime.fromtimestamp(t or 0, timezone.utc).strftime("%Y-%m-%d")


def admin_home_text():
    return ("👑 <b>Admin Panel</b>\n\nWelcome back, boss! Control users, groups, broadcasts and settings "
            "from here.\n\n📊 Pick an option below:")


def admin_home_rows():
    return [[B("📊 Stats", "ad:st", style="primary"), B("🏆 Top Players", "ad:top", style="success")],
            [B("👤 Users", "ad:u:0", style="primary"), B("🏘 Groups", "ad:g:0", style="primary")],
            [B("📣 Broadcast", "ad:b", style="success"), B("🚫 Ban / Unban", "ad:ban", style="danger")],
            [B("⚙ Settings", "ad:s", style="primary"), B("💼 Export Users", "ad:ex", style="success")],
            [B("🔄 Refresh", "ad:h", style="primary")]]


BACK = [[B("⬆ Back to panel", "ad:h", style="primary")]]


def bc_targets(t):
    ids = []
    if t in ("u", "a"):
        ids += [("u", r["id"]) for r in q("SELECT id FROM users WHERE started=1 AND banned=0 AND blocked=0")]
    if t in ("g", "a"):
        ids += [("g", r["id"]) for r in q("SELECT id FROM chats WHERE active=1 AND type IN ('group','supergroup')")]
    return ids


async def run_broadcast(chat_id, msg_id, src_chat, src_msg, target):
    ids = bc_targets(target)
    ok = fail = 0
    for i, (kind, cid) in enumerate(ids, 1):
        try:
            await call("copyMessage", chat_id=cid, from_chat_id=src_chat, message_id=src_msg)
            ok += 1
        except TgError as e:
            fail += 1
            if e.code == 403 or "chat not found" in e.desc.lower():
                ex("UPDATE users SET blocked=1 WHERE id=?" if kind == "u" else "UPDATE chats SET active=0 WHERE id=?", (cid,))
        except Exception:
            fail += 1
        if i % 20 == 0:
            try:
                await edit(chat_id, msg_id, f"📣 <b>Broadcasting…</b>\n\n⏳ {i}/{len(ids)}\n✅ Sent: {ok}  •  ❌ Failed: {fail}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    await edit(chat_id, msg_id, f"🎉 <b>Broadcast finished!</b>\n\n✅ Delivered: <b>{ok}</b>\n❌ Failed: <b>{fail}</b>\n"
                                f"📊 Total targets: <b>{len(ids)}</b>", BACK)


async def handle_await(m):
    st = AWAIT.pop(OWNER_ID, None)
    if not st:
        return
    cid = m["chat"]["id"]
    if st["kind"] == "ban":
        txt = (m.get("text") or "").strip()
        if not txt.lstrip("-").isdigit():
            AWAIT[OWNER_ID] = st
            return await send(cid, "⚠ Send a numeric user ID (or /cancel).")
        uid = int(txt)
        row = q1("SELECT banned FROM users WHERE id=?", (uid,))
        new = 0 if row and row["banned"] else 1
        ex("UPDATE users SET banned=? WHERE id=?", (new, uid))
        return await send(cid, f"{'🚫 Banned' if new else '✅ Unbanned'}: <code>{uid}</code>", BACK)
    if st["kind"] == "bc":
        n = len(bc_targets(st["t"]))
        try:
            await call("copyMessage", chat_id=cid, from_chat_id=cid, message_id=m["message_id"])
        except TgError:
            pass
        BC[OWNER_ID] = {"t": st["t"], "chat": cid, "msg": m["message_id"]}
        await send(cid, f"📣 <b>Preview sent above.</b>\n\n📊 Targets: <b>{n}</b>\n⚠ Send it to everyone now?",
                   [[B("🚀 Send now", "ad:bgo", style="success"), B("❌ Cancel", "ad:bx", style="danger")]])


async def group_detail(chat_id, msg_id, gid):
    row = q1("SELECT * FROM chats WHERE id=?", (gid,))
    if not row:
        return await edit(chat_id, msg_id, "⚠ Group not found.", [[B("⬆ Back", "ad:g:0", style="primary")]])
    info, cnt, status = {}, "?", "unknown"
    try:
        info = await call("getChat", chat_id=gid)
        cnt = await call("getChatMemberCount", chat_id=gid)
        mm = await call("getChatMember", chat_id=gid, user_id=ME["id"])
        status = mm.get("status", "unknown")
        ex("UPDATE chats SET is_admin=? WHERE id=?", (1 if status == "administrator" else 0, gid))
    except TgError as e:
        status = f"error: {e.desc}"
    link = f"https://t.me/{info['username']}" if info.get("username") else get_set(f"gl:{gid}", "")
    if not link and status == "administrator":
        try:
            link = (await call("createChatInviteLink", chat_id=gid, name="Owner access"))["invite_link"]
            put_set(f"gl:{gid}", link)
        except TgError:
            link = ""
    text = (f"🏘 <b>{H(row['title'])}</b>\n\n📍 ID: <code>{gid}</code>\n👤 Members: <b>{cnt}</b>\n"
            f"🛡 Bot status: <b>{H(status)}</b>\n📅 Added: {ts(row['added_at'])}")
    rows = []
    if link:
        rows.append([B("🔗 Open Group", url=link, style="success")])
    rows.append([B("🚩 Leave Group", f"ad:gl:{gid}", style="danger"), B("⬆ Back", "ad:g:0", style="primary")])
    await edit(chat_id, msg_id, text, rows)


async def on_admin(cb, parts):
    if cb["from"]["id"] != OWNER_ID:
        return await answer(cb, "Owner only!", True)
    chat_id, msg_id = cb["message"]["chat"]["id"], cb["message"]["message_id"]
    act = parts[1] if len(parts) > 1 else "h"
    await answer(cb)

    if act == "h":
        AWAIT.pop(OWNER_ID, None)
        await edit(chat_id, msg_id, admin_home_text(), admin_home_rows())
    elif act == "st":
        u = q1("""SELECT COUNT(*) a, SUM(started) s, SUM(banned) b, SUM(blocked) k FROM users""")
        c = q1("SELECT COUNT(*) a, SUM(is_admin) m FROM chats WHERE active=1")
        live = len([g for g in GAMES.values() if not g.over])
        text = (f"📊 <b>Bot Statistics</b>\n\n👤 Known users: <b>{u['a'] or 0}</b>\n✅ Started bot: <b>{u['s'] or 0}</b>\n"
                f"🚫 Banned: <b>{u['b'] or 0}</b>\n💀 Blocked bot: <b>{u['k'] or 0}</b>\n\n"
                f"🏘 Active groups: <b>{c['a'] or 0}</b>\n🛡 Admin in: <b>{c['m'] or 0}</b>\n\n"
                f"👾 Games played: <b>{get_set('games_total', '0')}</b>\n🔥 Live games now: <b>{live}</b>")
        await edit(chat_id, msg_id, text, [[B("🔄 Refresh", "ad:st", style="success"), B("⬆ Back", "ad:h", style="primary")]])
    elif act == "top":
        await edit(chat_id, msg_id, top_text(), BACK)
    elif act == "u":
        page = int(parts[2]) if len(parts) > 2 else 0
        total = q1("SELECT COUNT(*) c FROM users WHERE started=1")["c"]
        rows_ = q("SELECT * FROM users WHERE started=1 ORDER BY joined_at DESC LIMIT 10 OFFSET ?", (page * 10,))
        text = f"👤 <b>Users who started the bot</b>  ({total})\n\n"
        for i, r in enumerate(rows_, page * 10 + 1):
            un = f"@{r['username']}" if r["username"] else "—"
            flag = " 🚫" if r["banned"] else ""
            text += f"<b>{i}.</b> {mention({'id': r['id'], 'name': r['name'] or 'User'})}{flag}\n    📍 <code>{r['id']}</code> • {H(un)} • {ts(r['joined_at'])}\n"
        if not rows_:
            text += "👀 Nothing here yet."
        nav = []
        if page > 0:
            nav.append(B("⬆ Prev", f"ad:u:{page - 1}", style="primary"))
        if (page + 1) * 10 < total:
            nav.append(B("➡ Next", f"ad:u:{page + 1}", style="success"))
        await edit(chat_id, msg_id, text, ([nav] if nav else []) + BACK)
    elif act == "g":
        page = int(parts[2]) if len(parts) > 2 else 0
        total = q1("SELECT COUNT(*) c FROM chats WHERE active=1")["c"]
        adm = q1("SELECT COUNT(*) c FROM chats WHERE active=1 AND is_admin=1")["c"]
        grp = q("SELECT * FROM chats WHERE active=1 ORDER BY is_admin DESC, added_at DESC LIMIT 8 OFFSET ?", (page * 8,))
        text = (f"🏘 <b>Groups</b>  ({total})\n\n🛡 Bot is admin in <b>{adm}</b> group(s)\n"
                f"⚠ Not admin in <b>{total - adm}</b>\n\n👀 Tap a group to open details & jump in:")
        rows = [[B(f"{'🛡' if r['is_admin'] else '⚠'} {r['title'][:40]}", f"ad:gi:{r['id']}",
                   style="success" if r["is_admin"] else "danger")] for r in grp]
        nav = []
        if page > 0:
            nav.append(B("⬆ Prev", f"ad:g:{page - 1}", style="primary"))
        if (page + 1) * 8 < total:
            nav.append(B("➡ Next", f"ad:g:{page + 1}", style="success"))
        await edit(chat_id, msg_id, text, rows + ([nav] if nav else []) + BACK)
    elif act == "gi":
        await group_detail(chat_id, msg_id, int(parts[2]))
    elif act == "gl":
        gid = int(parts[2])
        try:
            await call("leaveChat", chat_id=gid)
        except TgError:
            pass
        ex("UPDATE chats SET active=0 WHERE id=?", (gid,))
        await edit(chat_id, msg_id, f"✅ Left group <code>{gid}</code>.", [[B("🏘 Groups", "ad:g:0", style="primary")]])
    elif act == "b":
        await edit(chat_id, msg_id, "📣 <b>Broadcast</b>\n\n📍 Who should receive it?",
                   [[B("👤 Users", "ad:bt:u", style="primary"), B("🏘 Groups", "ad:bt:g", style="primary")],
                    [B("🌐 Everyone", "ad:bt:a", style="success")], [B("⬆ Back", "ad:h", style="danger")]])
    elif act == "bt":
        AWAIT[OWNER_ID] = {"kind": "bc", "t": parts[2]}
        await edit(chat_id, msg_id, "📣 <b>Send me the message to broadcast</b>\n\n💡 Text, photo, video, premium emoji, "
                                    "buttons — anything works. Send /cancel to abort.", [[B("❌ Cancel", "ad:h", style="danger")]])
    elif act == "bx":
        BC.pop(OWNER_ID, None)
        await edit(chat_id, msg_id, "❌ Broadcast cancelled.", BACK)
    elif act == "bgo":
        b = BC.pop(OWNER_ID, None)
        if not b:
            return await edit(chat_id, msg_id, "⚠ Nothing to send.", BACK)
        await edit(chat_id, msg_id, "📣 <b>Broadcasting…</b>\n\n⏳ Starting")
        asyncio.create_task(run_broadcast(chat_id, msg_id, b["chat"], b["msg"], b["t"]))
    elif act == "ban":
        AWAIT[OWNER_ID] = {"kind": "ban"}
        await edit(chat_id, msg_id, "🚫 <b>Ban / Unban</b>\n\n📍 Send the user's numeric ID — it toggles the ban.",
                   [[B("❌ Cancel", "ad:h", style="danger")]])
    elif act == "s":
        fj, mt = get_set("force_join", "1") == "1", get_set("maintenance", "0") == "1"
        await edit(chat_id, msg_id, "⚙ <b>Settings</b>\n\n🔒 Force-join protects private chat access.\n🔧 Maintenance blocks everyone but you.",
                   [[B(f"🔒 Force Join: {'ON' if fj else 'OFF'}", "ad:t:fj", style="success" if fj else "danger")],
                    [B(f"🔧 Maintenance: {'ON' if mt else 'OFF'}", "ad:t:mt", style="danger" if mt else "success")],
                    [B("⬆ Back", "ad:h", style="primary")]])
    elif act == "t":
        key = {"fj": "force_join", "mt": "maintenance"}[parts[2]]
        put_set(key, "0" if get_set(key, "1" if key == "force_join" else "0") == "1" else "1")
        await on_admin(cb, ["ad", "s"])
    elif act == "ex":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "name", "username", "started", "banned", "blocked", "joined"])
        for r in q("SELECT * FROM users ORDER BY joined_at"):
            w.writerow([r["id"], r["name"], r["username"], r["started"], r["banned"], r["blocked"], ts(r["joined_at"])])
        await http.post(f"{API}/sendDocument", data={"chat_id": chat_id, "caption": "Users export"},
                        files={"document": ("users.csv", buf.getvalue().encode("utf-8"), "text/csv")})


# ============================ UPDATE ROUTER =========================
def parse_cmd(text):
    mm = re.match(r"^/(\w+)(?:@(\w+))?(?:\s+(.*))?$", text, re.S)
    if not mm:
        return None, None, []
    return mm.group(1).lower(), mm.group(2), (mm.group(3) or "").split()


async def on_message(m):
    chat, u = m["chat"], m.get("from")
    if not u or u.get("is_bot"):
        return
    text = m.get("text") or m.get("caption") or ""
    upsert_user(u)
    if chat["type"] in ("group", "supergroup"):
        upsert_chat(chat)
    uid, private = u["id"], chat["type"] == "private"
    row = q1("SELECT banned FROM users WHERE id=?", (uid,))
    if row and row["banned"] and uid != OWNER_ID:
        if private:
            await send(chat["id"], "🚫 <b>You are banned from using this bot.</b>", [[B("📞 Contact Owner", url=OWNER_LINK)]])
        return
    if uid == OWNER_ID and private and uid in AWAIT and not text.startswith("/"):
        return await handle_await(m)
    if uid == OWNER_ID and text.startswith("/"):
        AWAIT.pop(OWNER_ID, None)
    if not text.startswith("/"):
        return
    cmd, tgt_bot, args = parse_cmd(text)
    if not cmd or (tgt_bot and tgt_bot.lower() != ME["username"].lower()):
        return
    fn = COMMANDS.get(cmd)
    if not fn:
        return
    if uid != OWNER_ID and get_set("maintenance", "0") == "1":
        return await send(chat["id"], "🔧 <b>Under maintenance</b>\n\nWe'll be back very soon!",
                          [[B("📣 Update", url=CHANNEL_LINK, style="success")]])
    if private and cmd != "start" and cmd not in ("admin", "ban", "unban"):
        if not await force_join_gate(chat["id"], uid):
            return
    await fn(m, args)


async def on_callback(cb):
    data, uid = cb.get("data", ""), cb["from"]["id"]
    parts = data.split(":")
    row = q1("SELECT banned FROM users WHERE id=?", (uid,))
    if row and row["banned"] and uid != OWNER_ID:
        return await answer(cb, "You are banned.", True)
    if uid != OWNER_ID and get_set("maintenance", "0") == "1":
        return await answer(cb, "Under maintenance 🔧", True)
    k = parts[0]
    if k == "m":
        await on_move(cb, parts[1], int(parts[2]))
    elif k == "sur":
        await on_surrender(cb, parts[1])
    elif k == "rm":
        await on_rematch(cb, parts[1])
    elif k == "cl":
        await on_close(cb, parts[1])
    elif k == "jn":
        await on_join(cb, parts[1])
    elif k == "lc":
        await on_lobby_cancel(cb, parts[1])
    elif k == "sz":
        await on_size(cb, int(parts[1]), int(parts[2]))
    elif k in ("pa", "pd"):
        await on_challenge(cb, k, int(parts[1]), int(parts[2]), int(parts[3]) if len(parts) > 3 else 0)
    elif k == "fj":
        await on_fj(cb)
    elif k == "top":
        await answer(cb)
        await send(cb["message"]["chat"]["id"], top_text())
    elif k == "ad":
        await on_admin(cb, parts)
    else:
        await answer(cb)


async def on_my_chat_member(mc):
    chat, new, old = mc["chat"], mc["new_chat_member"]["status"], mc["old_chat_member"]["status"]
    by = mc.get("from", {})
    if chat["type"] == "private":
        if new in ("kicked", "left"):
            ex("UPDATE users SET blocked=1 WHERE id=?", (chat["id"],))
        return
    if chat["type"] not in ("group", "supergroup"):
        return
    active = new in ("member", "administrator")
    upsert_chat(chat, is_admin=(new == "administrator"), active=1 if active else 0)
    if active and old in ("left", "kicked"):
        who = f"{mention(puser(by))} (<code>{by.get('id')}</code>)" if by else "someone"
        await send(OWNER_ID, f"➕ <b>Added to a new group</b>\n\n🏘 {H(chat.get('title'))}\n📍 <code>{chat['id']}</code>\n"
                             f"👤 By: {who}\n🛡 Status: <b>{new}</b>",
                   [[B("🏘 Open Groups", "ad:g:0", style="primary")]])
        try:
            await send(chat["id"], "👾 <b>Tic Tac Toe is here!</b> 🎉\n\n⚡ Start a game: /game <code>3</code>\n"
                                   "🔥 Challenge a friend: /ply\n📌 Guide: /guide\n\n🛡 Tip: make me an admin for the best experience!",
                       [[B("📌 Guide", url=f"https://t.me/{ME['username']}?start=guide", style="primary")]])
        except TgError:
            pass
    elif not active and old in ("member", "administrator"):
        await send(OWNER_ID, f"🚩 <b>Removed from group</b>\n\n🏘 {H(chat.get('title'))}\n📍 <code>{chat['id']}</code>")


async def handle(u):
    try:
        if "message" in u:
            await on_message(u["message"])
        elif "callback_query" in u:
            cb = u["callback_query"]
            try:
                await on_callback(cb)
            except Exception:
                await answer(cb)
                raise
        elif "my_chat_member" in u:
            await on_my_chat_member(u["my_chat_member"])
    except Exception:
        log.exception("update handler failed")


# ============================ BACKGROUND ============================
async def janitor():
    while True:
        await asyncio.sleep(60)
        try:
            now = time.time()
            for gid, g in list(GAMES.items()):
                if g.over and now - g.updated > 1800:
                    GAMES.pop(gid, None)
                elif not g.over and now - g.updated > GAME_IDLE:
                    g.over, g.expired = True, True
                    for p in g.players:
                        ACTIVE.pop((g.chat_id, p["id"]), None)
                    await edit(g.chat_id, g.msg_id, game_text(g), game_rows(g))
            for lid, lob in list(LOBBIES.items()):
                if now - lob["ts"] > 300:
                    LOBBIES.pop(lid, None)
                    ACTIVE.pop((lob["chat"], lob["host"]["id"]), None)
                    await edit(lob["chat"], lob["msg"], "⏳ <b>Lobby expired</b> — nobody joined in time.")
            for k, ch in list(CHALLENGES.items()):
                if now - ch["ts"] > 300:
                    CHALLENGES.pop(k, None)
                    await edit(ch["chat"], ch["msg"], "⏳ <b>Challenge expired.</b>")
            for k, p in list(PENDING.items()):
                if now - p["ts"] > 900:
                    PENDING.pop(k, None)
        except Exception:
            log.exception("janitor error")


OWNER_CMDS = [("admin", "Owner admin panel"), ("ban", "Ban a user id"), ("unban", "Unban a user id")]
BASE_CMDS = [("start", "Main menu"), ("game", "Start a Tic Tac Toe game"), ("ply", "Challenge a player"),
             ("guide", "How to play"), ("stats", "Your stats"), ("top", "Leaderboard"),
             ("cancel", "Cancel your game"), ("id", "Show your ID")]


def _mk(c):
    return [{"command": a, "description": b} for a, b in c]


async def set_owner_commands():
    # fails with "chat not found" until the owner has pressed /start once -> never crash on it
    try:
        await call("setMyCommands", commands=_mk(BASE_CMDS + OWNER_CMDS),
                   scope={"type": "chat", "chat_id": OWNER_ID})
    except TgError as e:
        log.warning("owner command menu skipped (%s) - send /start to the bot once", e.desc)


async def setup_commands():
    await call("setMyCommands", commands=_mk(BASE_CMDS))
    await set_owner_commands()


async def _health_handler(reader, writer):
    """Tiny HTTP responder: any request (GET/HEAD, /health or /) -> 200 OK."""
    try:
        try:
            await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        except Exception:
            pass
        body = b"OK"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                     b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def start_health_server():
    try:
        srv = await asyncio.start_server(_health_handler, "0.0.0.0", HEALTH_PORT)
        log.info("health server listening on :%s  (GET /health -> 200 OK)", HEALTH_PORT)
        return srv
    except OSError as e:
        log.warning("health server not started: %s", e)


async def main():
    global http
    if "PASTE_YOUR" in BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN (env var or at the top of tic.py)")
    http = httpx.AsyncClient(timeout=60)
    ME.update(await call("getMe"))
    await call("deleteWebhook")
    await setup_commands()
    await start_health_server()
    asyncio.create_task(janitor())
    log.info("@%s is running", ME["username"])
    offset, tasks = None, set()
    while True:
        try:
            updates = await call("getUpdates", offset=offset, timeout=50, _t=70,
                                 allowed_updates=["message", "callback_query", "my_chat_member"])
        except Exception as e:
            log.warning("polling error: %s", e)
            await asyncio.sleep(3)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            t = asyncio.create_task(handle(u))
            tasks.add(t)
            t.add_done_callback(tasks.discard)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
