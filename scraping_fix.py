"""
THREADS SCRAPER GABUNGAN v2 (Playwright)
Tahap 1: scraping postingan hasil pencarian keyword
Tahap 2: filter bahasa Indonesia (lingua)
Tahap 3: scraping KOMENTAR postingan utama + REPLY dari tiap komentar (pohon bertingkat)
Tahap 4: export CSV akhir + edge list (reply & mention)

Cara menentukan induk yang akurat:
  Setiap komentar dibuka di halamannya sendiri. Di halaman itu Threads menampilkan
  rantai induk di atas komentar tersebut. Postingan tepat di atasnya = induk langsung.
  Anak-anaknya (reply) diambil dari bagian di bawahnya.

depth: 0 = postingan utama, 1 = komentar, 2 = reply ke komentar, dst.
"""

import csv
import re
import random
from collections import deque
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote

from playwright.sync_api import sync_playwright
from lingua import Language, LanguageDetectorBuilder

# =========================================================
# 1. KONFIGURASI
# =========================================================

TEST_MODE = False    # False = scraping penuh

BASE_DIR = Path(r"E:\UNS\SEMESTER 7\Analisis Media Sosial\Project Ansosmed")

OUTPUT_DIR = BASE_DIR / ("output_test" if TEST_MODE else "output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# PERIODE ANALISIS
# =========================================================

QUARTER = "Q4_2025"

START_DATE = datetime(2025, 9, 30, tzinfo=timezone.utc)
END_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)  # eksklusif

# =========================================================
# FILE OUTPUT
# =========================================================

RAW_CSV = OUTPUT_DIR / f"posts_raw_{QUARTER}.csv"
ID_CSV = OUTPUT_DIR / f"posts_indonesia_{QUARTER}.csv"

COMMENTS_CSV = OUTPUT_DIR / f"comments_{QUARTER}.csv"
REPLIES_CSV = OUTPUT_DIR / f"replies_{QUARTER}.csv"

COMMENTS_DONE = OUTPUT_DIR / f"comments_done_{QUARTER}.txt"

EDGE_REPLY_CSV = OUTPUT_DIR / f"edges_reply_{QUARTER}.csv"
EDGE_MENTION_CSV = OUTPUT_DIR / f"edges_mention_{QUARTER}.csv"

PROFILE_DIR = BASE_DIR / "output" / "browser_profile"

SCREENSHOT_DIR = OUTPUT_DIR / f"debug_{QUARTER}"
SCREENSHOT_DIR.mkdir(exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# KEYWORD
# =========================================================

KEYWORDS = ["Mistral"]

# =========================================================
# TAHAP 1: POSTINGAN
# =========================================================

SCRAPE_POSTS = True

MAX_SCROLLS = 8 if TEST_MODE else 400
MAX_IDLE_SCROLLS_POSTS = 50 
SCROLL_WAIT = 2
PAGE_LOAD_WAIT = 3000

# =========================================================
# TAHAP 3: KOMENTAR + REPLY
# =========================================================

SCRAPE_COMMENTS = True

MAX_COMMENT_POSTS = 3 if TEST_MODE else None

MAX_DEPTH = 2

MAX_EXPAND_PER_ROOT = 8 if TEST_MODE else 100

MAX_SCROLLS_PER_POST = 30
MAX_IDLE_SCROLLS = 4

NESTED_MAX_SCROLLS = 15
NESTED_IDLE_SCROLLS = 2
NESTED_LOAD_WAIT = 2500

REPLY_SCROLL_WAIT = (1.5, 3.0)
VISIT_WAIT = (3, 6)
POST_WAIT = (4, 8)

FILTER_ONLY_INDONESIAN_REPLIES = False

POST_FIELDS = ["keyword", "post_id", "url", "timestamp", "text",]
# komentar langsung ke postingan utama
COMMENT_FIELDS = [
    "post_url", "post_id", "comment_url", "comment_id",
    "timestamp", "text",]
# reply ke komentar (dan reply ke reply jika MAX_DEPTH >= 3)
REPLY_FIELDS = [
    "post_url", "post_id", "comment_url", "comment_id",
    "reply_url", "reply_id", "timestamp", "text",
]


# =========================================================
# 2. DETEKTOR BAHASA
# =========================================================

detector = LanguageDetectorBuilder.from_languages(
    Language.INDONESIAN, Language.ENGLISH, Language.MALAY, Language.FRENCH,
    Language.SPANISH, Language.GERMAN, Language.PORTUGUESE, Language.ITALIAN,
    Language.DUTCH, Language.JAPANESE, Language.KOREAN, Language.CHINESE,
    Language.RUSSIAN, Language.ARABIC, Language.THAI, Language.VIETNAMESE,
).build()


# =========================================================
# 3. FUNGSI PENDUKUNG
# =========================================================

POST_URL_RE = re.compile(r"/@([^/]+)/post/([A-Za-z0-9_-]+)")
URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@([A-Za-z0-9._]+)")


def clean_text(text):
    if not text:
        return ""
    text = text.replace("\u200b", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def norm_text(text):
    text = URL_RE.sub("", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def parse_timestamp(value):
    if not value:
        return None
    try:
        value = value.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def is_in_date_range(timestamp):
    dt = parse_timestamp(timestamp)
    return dt is not None and START_DATE <= dt < END_DATE


def is_indonesian(text):
    text = clean_text(text)
    if not text:
        return False
    try:
        return detector.detect_language_of(text) == Language.INDONESIAN
    except Exception as error:
        print(f"Deteksi bahasa gagal: {error}")
        return False


def parse_post_url(url):
    m = POST_URL_RE.search(url or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def canonical_url(url):
    """Seragamkan URL (buang /media dan query) agar dedup konsisten."""
    user, code = parse_post_url(url)
    if code:
        return f"https://www.threads.com/@{user}/post/{code}"
    return (url or "").split("?")[0]


def text_key(username, text):
    return f"{(username or '').lower()}|{norm_text(text)}"


def ts_of(card):
    return parse_timestamp(card.get("timestamp"))


def save_csv(filepath, rows, fields):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(filepath):
    if not Path(filepath).exists():
        return []
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# =========================================================
# 4. JAVASCRIPT
# =========================================================

# Ekstraksi postingan di halaman hasil pencarian (logika asli dipertahankan)
JS_EXTRACT_POSTS = r"""
() => {
    const results = [];
    const seen = new Set();
    const anchors = document.querySelectorAll('a[href*="/post/"]');

    for (const postLink of anchors) {
        const href = postLink.getAttribute("href") || "";
        if (!href.includes("/post/")) continue;

        const url = new URL(href, window.location.origin).href.split("?")[0];
        if (seen.has(url)) continue;
        seen.add(url);

        let node = postLink, postNode = null, timeElement = null;
        for (let level = 0; level < 10 && node; level++) {
            const time = node.querySelector("time");
            if (time) {
                const text = (node.innerText || "").trim();
                if (text.length > 0 && text.length < 12000) {
                    postNode = node; timeElement = time; break;
                }
            }
            node = node.parentElement;
        }
        if (!postNode || !timeElement) continue;

        const timestamp = timeElement.getAttribute("datetime") || "";

        // Label komunitas persis "AI Threads" -> dilewati
        const links = Array.from(postNode.querySelectorAll("a"));
        const isAIThreadsCommunity = links.some(link => {
            const label = (link.innerText || "").replace(/\s+/g, " ").trim();
            const linkHref = link.getAttribute("href") || "";
            return label.toLowerCase() === "ai threads" && !linkHref.includes("/post/");
        });
        if (isAIThreadsCommunity) {
            results.push({url, timestamp, text: "", excluded_community: true});
            continue;
        }

        const uiLabels = ["ai threads","translate","read more","for you","search",
            "messages","activity","profile","insights","recent","top","profiles"];
        const textParts = [];
        for (const element of postNode.querySelectorAll('[dir="auto"]')) {
            if (element.querySelectorAll('[dir="auto"]').length > 0) continue;
            const text = (element.innerText || "").replace(/\s+/g, " ").trim();
            if (!text) continue;
            if (uiLabels.includes(text.toLowerCase())) continue;
            textParts.push(text);
        }
        const text = [...new Set(textParts)].join(" ").trim();
        results.push({url, timestamp, text, excluded_community: false});
    }
    return results;
}
"""

# Semua kartu postingan di sebuah halaman, SESUAI URUTAN DOM
# (rantai induk di atas, postingan fokus, lalu reply di bawah)
JS_EXTRACT_CARDS = r"""
() => {
  const POST_RE = /\/@([^\/]+)\/post\/([A-Za-z0-9_-]+)/;
  const UI = ["translate","terjemahkan","read more","baca selengkapnya","for you",
              "search","messages","activity","profile","insights","recent","top",
              "profiles","reply","balas","like","suka","repost","share","bagikan",
              "author","penulis","verified","ai threads"];
  const results = [], seen = new Set();

  const distinctCodes = (el) => {
    const s = new Set();
    el.querySelectorAll('a[href*="/post/"]').forEach(a => {
      const m = (a.getAttribute("href") || "").match(POST_RE);
      if (m) s.add(m[2]);
    });
    return s;
  };

  document.querySelectorAll('a[href*="/post/"]').forEach(a => {
    const href = a.getAttribute("href") || "";
    const m = href.match(POST_RE);
    if (!m) return;
    const username = m[1], code = m[2];
    if (seen.has(code)) return;

    // naik ke kontainer terbesar yang HANYA memuat satu postingan
    let node = a, best = null;
    while (node.parentElement) {
      const parent = node.parentElement;
      if (distinctCodes(parent).size > 1) break;
      node = parent;
      if (node.querySelector("time")) best = node;
    }
    if (!best) return;
    seen.add(code);

    const t = best.querySelector("time");
    const timestamp = t ? (t.getAttribute("datetime") || "") : "";

    const parts = [];
    best.querySelectorAll('[dir="auto"]').forEach(el => {
      if (el.querySelector('[dir="auto"]')) return;
      const txt = (el.innerText || "").replace(/\s+/g, " ").trim();
      if (!txt) return;
      if (txt.toLowerCase() === username.toLowerCase()) return;
      if (UI.includes(txt.toLowerCase())) return;
      if (/^[\d.,]+\s*[KkMmRrbB]*$/.test(txt)) return;
      if (/^\d+\s*(s|m|h|d|w|j|mnt|hr|mg|jam|menit|detik|hari|minggu)$/i.test(txt)) return;
      parts.push(txt);
    });

    results.push({
      url: new URL(href, window.location.origin).href.split("?")[0],
      username, code, timestamp,
      text: [...new Set(parts)].join(" ").trim()
    });
  });
  return results;
}
"""

# Klik tombol "lihat balasan" agar balasan tersembunyi terbuka
JS_CLICK_MORE = r"""
() => {
  const re = /(view|see|show|lihat|tampilkan).{0,40}(repl|balas)/i;
  let n = 0;
  document.querySelectorAll('[role="button"], button').forEach(el => {
    const t = (el.innerText || "").trim();
    if (t.length > 0 && t.length < 60 && re.test(t) && !el.dataset._clicked) {
      el.dataset._clicked = "1";
      el.click();
      n++;
    }
  });
  return n;
}
"""


# =========================================================
# 5. TAHAP 1: SCRAPING POSTINGAN
# =========================================================

def extract_posts(page, keyword):
    items = page.evaluate(JS_EXTRACT_POSTS)
    results = []

    for item in items:
        if item.get("excluded_community", False):
            continue

        url = canonical_url((item.get("url") or "").strip())
        timestamp = (item.get("timestamp") or "").strip()
        text = clean_text(item.get("text", ""))

        if not url or not timestamp or not text:
            continue
        
        # if not contains_keyword(text, keyword):
        #     continue

        if not is_in_date_range(timestamp):
            continue

        username, post_id = parse_post_url(url)

        results.append({
            "keyword": keyword,
            "post_id": post_id or "",
            "url": url,
            "username": username or "",  # untuk proses internal
            "timestamp": timestamp,
            "text": text,
        })

    return results


def scrape_posts(page, all_posts, seen_text):
    for keyword in KEYWORDS:
        print(f"\n=== Memulai pencarian keyword: {keyword} ===")
        page.goto("https://www.threads.com/search?q=" + quote(keyword),
                  wait_until="domcontentloaded")
        page.wait_for_timeout(PAGE_LOAD_WAIT)

        input("Atur filter tanggal dan pilih tab Recent jika tersedia. "
              "Setelah siap, tekan ENTER...")

        idle = 0
        for scroll_num in range(1, MAX_SCROLLS + 1):
            try:
                posts = extract_posts(page, keyword)
            except Exception as error:
                print(f"Kesalahan ekstraksi: {error}")
                posts = []

            new_posts, dup_text = 0, 0
            for post in posts:
                url = post["url"]
                if url in all_posts:
                    if len(post["text"]) > len(all_posts[url]["text"]):
                        all_posts[url]["text"] = post["text"]
                    continue
                tk = text_key(post["username"], post["text"])
                if tk in seen_text:           # dedup: teks identik dari user yang sama
                    dup_text += 1
                    continue
                seen_text.add(tk)
                all_posts[url] = post
                new_posts += 1

            print(f"Scroll {scroll_num}/{MAX_SCROLLS} | baru: {new_posts} | "
                  f"dup teks: {dup_text} | total: {len(all_posts)}")

            save_csv(RAW_CSV, list(all_posts.values()), POST_FIELDS)

            idle = 0 if new_posts else idle + 1
            if idle >= MAX_IDLE_SCROLLS_POSTS:
                print("Tidak ada post baru beberapa scroll berturut-turut, lanjut.")
                break

            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(SCROLL_WAIT * 1000)

        try:
            page.screenshot(path=str(SCREENSHOT_DIR / f"posts_{keyword}.png"))
        except Exception as error:
            print(f"Gagal screenshot: {error}")


# =========================================================
# 6. TAHAP 2: FILTER BAHASA INDONESIA
# =========================================================

def filter_indonesian(all_posts):
    raw_posts = list(all_posts.values())
    print(f"\nMemfilter bahasa {len(raw_posts)} postingan...")
    result = []
    for i, post in enumerate(raw_posts, start=1):
        ok = is_indonesian(post["text"])
        if ok:
            result.append(post)
        print(f"[{i}/{len(raw_posts)}] {'INDONESIA' if ok else 'DITOLAK  '}: "
              f"{post['text'][:80]}")
    save_csv(ID_CSV, result, POST_FIELDS)
    print(f"Post Indonesia: {len(result)} -> {ID_CSV}")
    return result


# =========================================================
# 7. TAHAP 3: KOMENTAR + REPLY BERTINGKAT
# =========================================================

def snapshot(page):
    """Semua kartu postingan di halaman, urutan DOM, URL sudah dikanonikalkan."""
    cards = []
    for it in page.evaluate(JS_EXTRACT_CARDS):
        user, code = parse_post_url(it["url"])
        if not code:
            continue
        cards.append({
            "url": canonical_url(it["url"]), "code": code, "username": user,
            "timestamp": it.get("timestamp", ""), "text": clean_text(it.get("text", "")),
        })
    return cards


def visit_page(page, node, is_root):
    """
    Buka halaman satu node. Kembalikan:
      ancestors   : kartu di atas node (urutan dari akar ke induk langsung)
      descendants : kartu di bawah node (reply), tanpa duplikat
    """
    page.goto(node["url"], wait_until="domcontentloaded")
    page.wait_for_timeout(3500 if is_root else NESTED_LOAD_WAIT)

    node_ts = parse_timestamp(node["timestamp"])
    first = snapshot(page)

    idx = next((i for i, c in enumerate(first) if c["code"] == node["code"]), None)
    if idx is not None:
        ancestors = first[:idx]
    else:
        # kartu fokus tidak ditemukan: pakai waktu sebagai cadangan
        ancestors = sorted(
            [c for c in first if ts_of(c) and node_ts and ts_of(c) < node_ts],
            key=ts_of,
        )

    anc_codes = {c["code"] for c in ancestors}
    found = {}

    def harvest(cards):
        for c in cards:
            if c["code"] == node["code"] or c["code"] in anc_codes:
                continue
            t = ts_of(c)
            if not t:
                continue
            if node_ts and t <= node_ts:      # lebih lama dari node = bukan reply
                continue
            found.setdefault(c["url"], c)

    harvest(first)

    max_scrolls = MAX_SCROLLS_PER_POST if is_root else NESTED_MAX_SCROLLS
    idle_limit = MAX_IDLE_SCROLLS if is_root else NESTED_IDLE_SCROLLS
    idle = 0
    for _ in range(max_scrolls):
        try:
            page.evaluate(JS_CLICK_MORE)
        except Exception:
            pass
        before = len(found)
        page.mouse.wheel(0, 2200)
        page.wait_for_timeout(int(random.uniform(*REPLY_SCROLL_WAIT) * 1000))
        try:
            harvest(snapshot(page))
        except Exception as e:
            print(f"    Kesalahan ekstraksi: {e}")
        idle = 0 if len(found) > before else idle + 1
        if idle >= idle_limit:
            break

    return ancestors, list(found.values())


def crawl_root(page, root_post, seen_reply_urls, writers, files, idx):
    """Telusuri pohon komentar satu postingan utama (BFS), lalu tulis ke CSV."""
    root_url = canonical_url(root_post["url"])
    root_user, root_code = parse_post_url(root_url)
    if not root_code:
        print(f"  URL induk tidak valid: {root_post['url']}")
        return 0

    root = {
        "url": root_url, "code": root_code, "username": root_user,
        "timestamp": root_post["timestamp"], "text": root_post.get("text", ""),
        "parent": None, "depth": 0, "verified": True,
    }
    tree = {root_url: root}          # url -> node (urutan penemuan dipertahankan)
    queue = deque([root_url])
    visited, visits = set(), 0

    while queue:
        url = queue.popleft()
        node = tree[url]
        if url in visited or node["depth"] >= MAX_DEPTH:
            continue
        is_root = node is root
        if not is_root and MAX_EXPAND_PER_ROOT and visits >= MAX_EXPAND_PER_ROOT:
            break
        visited.add(url)
        if not is_root:
            visits += 1
            page.wait_for_timeout(int(random.uniform(*VISIT_WAIT) * 1000))

        try:
            ancestors, descendants = visit_page(page, node, is_root)
        except Exception as e:
            print(f"    [error] {url}: {e}")
            continue

        # verifikasi induk langsung dari rantai di atas node
        if not is_root and ancestors:
            p = ancestors[-1]
            if p["url"] in tree and p["url"] != url:
                node["parent"] = p["url"]
                node["verified"] = True
                node["depth"] = tree[p["url"]]["depth"] + 1

        if node["depth"] >= MAX_DEPTH:
            continue

        for c in descendants:
            if c["url"] == root_url:
                continue
            ex = tree.get(c["url"])
            if ex is None:
                tree[c["url"]] = {
                    "url": c["url"], "code": c["code"], "username": c["username"],
                    "timestamp": c["timestamp"], "text": c["text"],
                    "parent": url, "depth": node["depth"] + 1, "verified": False,
                }
                queue.append(c["url"])
            else:
                if len(c["text"]) > len(ex["text"]):
                    ex["text"] = c["text"]
                # induk sementara diperbarui ke node yang lebih dalam
                if not ex["verified"] and node["depth"] + 1 > ex["depth"]:
                    ex["parent"] = url
                    ex["depth"] = node["depth"] + 1

        print(f"    dibuka: depth={node['depth']} | anak ditemukan: {len(descendants)} "
              f"| total node: {len(tree) - 1}")

    # cari komentar level-1 yang menaungi sebuah node (naik lewat rantai induk)
    def comment_ancestor(node):
        cur, guard = node, 0
        while cur and cur["depth"] > 1 and cur["parent"] in tree and guard < 20:
            cur = tree[cur["parent"]]
            guard += 1
        return cur if cur and cur is not root else None

    # tulis hasil ke file terpisah
    written, order = 0, 0
    n_comments, n_replies = 0, 0
    for url, node in tree.items():
        if node is root:
            continue
        order += 1
        if url in seen_reply_urls:                 # dedup global
            continue
        text = clean_text(node["text"])
        if not text:
            continue
        ind = is_indonesian(text)
        if FILTER_ONLY_INDONESIAN_REPLIES and not ind:
            continue

        if node["depth"] <= 1:
            # KOMENTAR langsung ke postingan utama
            writers["comments"].writerow({
                "post_url": root_url,
                "post_id": root_code,
                "comment_url": url,
                "comment_id": node["code"],
                "timestamp": node["timestamp"],
                "text": text,
            })
            n_comments += 1
        else:
            # REPLY ke komentar
            c = comment_ancestor(node)
            writers["replies"].writerow({
                "post_url": root_url,
                "post_id": root_code,
                "comment_url": c["url"] if c else "",
                "comment_id": c["code"] if c else "",
                "reply_url": url,
                "reply_id": node["code"],
                "timestamp": node["timestamp"],
                "text": text,
            })
            n_replies += 1
        seen_reply_urls.add(url)
        written += 1
    for fh in files:
        fh.flush()
    print(f"  Ditulis: {n_comments} komentar, {n_replies} reply")

    if len(tree) == 1:
        try:
            page.screenshot(path=str(SCREENSHOT_DIR / f"komentar_kosong_{idx}.png"))
        except Exception:
            pass
    return written


def load_done():
    if COMMENTS_DONE.exists():
        return set(COMMENTS_DONE.read_text(encoding="utf-8").split())
    return set()


def scrape_comments(page, roots):
    done = load_done()
    seen_reply_urls = (
        {r["comment_url"] for r in read_csv(COMMENTS_CSV)}
        | {r["reply_url"] for r in read_csv(REPLIES_CSV)}
    )

    todo = [p for p in roots if canonical_url(p["url"]) not in done]
    if MAX_COMMENT_POSTS:
        todo = todo[:MAX_COMMENT_POSTS]

    print("\n=== Scraping komentar + reply ===")
    print(f"Postingan utama: {len(roots)} | selesai: {len(done)} | "
          f"diproses sekarang: {len(todo)} | tersimpan: {len(seen_reply_urls)}")

    new_comments = not COMMENTS_CSV.exists()
    new_replies = not REPLIES_CSV.exists()
    total_new = 0
    with open(COMMENTS_CSV, "a", newline="", encoding="utf-8-sig") as fc, \
         open(REPLIES_CSV, "a", newline="", encoding="utf-8-sig") as fr:
        writers = {
            "comments": csv.DictWriter(fc, fieldnames=COMMENT_FIELDS),
            "replies": csv.DictWriter(fr, fieldnames=REPLY_FIELDS),
        }
        if new_comments:
            writers["comments"].writeheader()
        if new_replies:
            writers["replies"].writeheader()
        files = [fc, fr]

        for i, root_post in enumerate(todo, start=1):
            print(f"\n[{i}/{len(todo)}] {root_post['url']}")
            try:
                n = crawl_root(page, root_post, seen_reply_urls, writers, files, i)
            except Exception as e:
                print(f"  [error] {e} -> dilewati, bisa diulang di run berikutnya")
                continue

            total_new += n
            with open(COMMENTS_DONE, "a", encoding="utf-8") as df:
                df.write(canonical_url(root_post["url"]) + "\n")
            page.wait_for_timeout(int(random.uniform(*POST_WAIT) * 1000))

    print(f"Baru run ini: {total_new}")


# =========================================================
# 8. TAHAP 4: EDGE LIST
# =========================================================

def build_edges(posts_id):
    comments = read_csv(COMMENTS_CSV)
    replies = read_csv(REPLIES_CSV)

    # =====================================================
    # EDGE REPLY
    # Source = akun yang membalas
    # Target = akun yang menerima balasan
    # =====================================================

    with open(EDGE_REPLY_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)

        w.writerow([
            "source",
            "target",
            "type",
            "timestamp",
            "root_url",
            "target_url",
            "source_url",
        ])

        # Komentar -> penulis postingan utama
        for r in comments:
            source, _ = parse_post_url(r["comment_url"])
            target, _ = parse_post_url(r["post_url"])

            if source and target and source.lower() != target.lower():
                w.writerow([
                    source,
                    target,
                    "comment",
                    r["timestamp"],
                    r["post_url"],
                    r["post_url"],
                    r["comment_url"],
                ])

        # Reply -> penulis komentar tingkat pertama
        for r in replies:
            source, _ = parse_post_url(r["reply_url"])
            target, _ = parse_post_url(r["comment_url"])

            if source and target and source.lower() != target.lower():
                w.writerow([
                    source,
                    target,
                    "reply",
                    r["timestamp"],
                    r["post_url"],
                    r["comment_url"],
                    r["reply_url"],
                ])

    # =====================================================
    # EDGE MENTION
    # =====================================================

    with open(EDGE_MENTION_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)

        w.writerow([
            "source",
            "target",
            "timestamp",
            "url",
        ])

        # Mention di postingan
        for p in posts_id:
            username = p.get("username") or parse_post_url(p["url"])[0]

            for m in set(MENTION_RE.findall(p["text"])):
                w.writerow([
                    username,
                    m.lower(),
                    p["timestamp"],
                    p["url"],
                ])

        # Mention di komentar
        for r in comments:
            username, _ = parse_post_url(r["comment_url"])

            for m in set(MENTION_RE.findall(r["text"])):
                w.writerow([
                    username or "",
                    m.lower(),
                    r["timestamp"],
                    r["comment_url"],
                ])

        # Mention di reply
        for r in replies:
            username, _ = parse_post_url(r["reply_url"])

            for m in set(MENTION_RE.findall(r["text"])):
                w.writerow([
                    username or "",
                    m.lower(),
                    r["timestamp"],
                    r["reply_url"],
                ])

    print(f"Edge reply   -> {EDGE_REPLY_CSV}")
    print(f"Edge mention -> {EDGE_MENTION_CSV}")



# def contains_keyword(text, keyword):
#     """
#     Mengecek apakah teks mengandung keyword sebagai kata/frasa utuh.
#     Tidak sensitif terhadap huruf besar/kecil.
#     """
#     text = clean_text(text).lower()
#     keyword = clean_text(keyword).lower()

#     if not text or not keyword:
#         return False

#     pattern = r"\b" + re.escape(keyword) + r"\b"
#     return re.search(pattern, text) is not None



# =========================================================
# 9. MAIN
# =========================================================

def main():
    all_posts, seen_text = {}, set()
    for r in read_csv(RAW_CSV):
        username, post_id = parse_post_url(r.get("url", ""))

        r["post_id"] = post_id or ""
        r["username"] = r.get("username") or username or ""

        all_posts[r["url"]] = r
        seen_text.add(text_key(r["username"], r["text"]))
    print(f"Postingan lama dimuat: {len(all_posts)}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1365, "height": 900},
            locale="id-ID",
        )
        page = context.pages[0] if context.pages else context.new_page()

        page.goto("https://www.threads.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(PAGE_LOAD_WAIT)
        input("Pastikan kamu sudah login ke Threads. Tekan ENTER untuk melanjutkan...")

        if SCRAPE_POSTS:
            scrape_posts(page, all_posts, seen_text)

        posts_id = filter_indonesian(all_posts)

        if SCRAPE_COMMENTS:
            scrape_comments(page, posts_id)

        context.close()

    build_edges(posts_id)

    print("\n" + "=" * 50)
    print("SELESAI")
    print("=" * 50)
    print(f"Postingan mentah      : {len(all_posts)}")
    print(f"Postingan Indonesia   : {len(posts_id)}")
    print(f"Komentar (depth 1)    : {len(read_csv(COMMENTS_CSV))} -> {COMMENTS_CSV.name}")
    print(f"Reply ke komentar     : {len(read_csv(REPLIES_CSV))} -> {REPLIES_CSV.name}")
    print(f"Folder output         : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()