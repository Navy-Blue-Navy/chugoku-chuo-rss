import requests
import hashlib
import re
import time
import xml.etree.ElementTree as ET

from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime


SOURCE_URL = "https://www.kouritu-cch.jp/category/topics"
OUTPUT = Path(__file__).parent / "chugoku_chuo.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

DATE_RE = re.compile(
    r"^(20\d{2})\.(\d{1,2})\.(\d{1,2})$"
)

ARTICLE_RE = re.compile(
    r"^/topics/[^/]+/\d+/?$"
)


# --------------------------------------------------
# 既存RSS読み込み
# --------------------------------------------------

old_items = {}

if OUTPUT.exists():

    try:
        tree = ET.parse(OUTPUT)

        for item in tree.getroot().findall("./channel/item"):

            guid = item.findtext("guid", "")

            if guid:
                old_items[guid] = {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "description": item.findtext(
                        "description", ""
                    ),
                    "pubDate": item.findtext(
                        "pubDate", ""
                    ),
                    "guid": guid,
                }

    except Exception as e:

        print("既存RSS読み込みエラー:", e)
        print("安全のため今回は更新しません。")

        raise SystemExit(0)


print("既存RSS件数:", len(old_items))


# --------------------------------------------------
# ページ取得
# --------------------------------------------------

response = None
MAX_RETRIES = 3

for attempt in range(1, MAX_RETRIES + 1):

    try:

        print(
            f"中国中央病院 更新情報取得 "
            f"{attempt}/{MAX_RETRIES}"
        )

        response = requests.get(
            SOURCE_URL,
            headers=HEADERS,
            timeout=30
        )

        print("HTTP:", response.status_code)

        response.raise_for_status()
        break

    except requests.RequestException as e:

        print("取得失敗:", e)
        response = None

        if attempt < MAX_RETRIES:
            print("10秒待って再試行します。")
            time.sleep(10)


if response is None:

    print()
    print("ページを取得できませんでした。")
    print("今回はRSSを更新しません。")
    print("既存XMLをそのまま維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# HTML解析
# --------------------------------------------------

soup = BeautifulSoup(
    response.content,
    "html.parser"
)

archive = soup.select_one(
    "ul.archivelist"
)

if archive is None:

    print("更新情報一覧を取得できませんでした。")
    print("ページ構造変更の可能性があります。")
    print("既存XMLを維持します。")

    raise SystemExit(0)


current_items = []


# --------------------------------------------------
# 記事取得
# --------------------------------------------------

for li in archive.find_all(
    "li",
    recursive=False
):

    date_element = li.select_one(
        "span.archivedate"
    )

    if date_element is None:
        continue

    date_text = date_element.get_text(
        " ",
        strip=True
    )

    match = DATE_RE.match(
        date_text
    )

    if not match:
        continue

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    article_link = None
    title = None

    for a in li.find_all(
        "a",
        href=True
    ):

        href = a["href"]

        absolute = urljoin(
            SOURCE_URL,
            href
        )

        path = absolute.replace(
            "https://www.kouritu-cch.jp",
            ""
        )

        if not ARTICLE_RE.match(path):
            continue

        candidate_title = a.get_text(
            " ",
            strip=True
        )

        if not candidate_title:
            continue

        article_link = absolute
        title = candidate_title
        break


    if not article_link or not title:
        continue


    # カテゴリ名もdescriptionへ入れる
    categories = []

    for a in li.find_all(
        "a",
        href=True
    ):

        href = a["href"]

        if "/category/" not in href:
            continue

        category = a.get_text(
            " ",
            strip=True
        )

        if (
            category
            and category not in categories
        ):
            categories.append(category)


    description = ""

    if categories:
        description = (
            "カテゴリー: "
            + " / ".join(categories)
        )


    dt = datetime(
        year,
        month,
        day,
        12,
        0,
        0,
        tzinfo=JST
    )


    guid = hashlib.sha256(
        article_link.encode("utf-8")
    ).hexdigest()


    current_items.append({
        "title": title,
        "link": article_link,
        "description": description,
        "pubDate": format_datetime(dt),
        "guid": guid,
    })


print()
print(
    "今回取得:",
    len(current_items),
    "件"
)


# --------------------------------------------------
# 安全確認
# --------------------------------------------------

if len(current_items) == 0:

    print("記事を1件も取得できませんでした。")
    print("ページ構造変更の可能性があります。")
    print("既存XMLを維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# 既存RSSと統合
# --------------------------------------------------

all_items = []
seen_guids = set()


for item in current_items:

    if item["guid"] not in seen_guids:

        all_items.append(item)
        seen_guids.add(
            item["guid"]
        )


for guid, item in old_items.items():

    if guid not in seen_guids:

        all_items.append(item)
        seen_guids.add(guid)


# --------------------------------------------------
# 日付順
# --------------------------------------------------

def get_date(item):

    try:
        return parsedate_to_datetime(
            item["pubDate"]
        )

    except Exception:

        return datetime.min.replace(
            tzinfo=timezone.utc
        )


all_items.sort(
    key=get_date,
    reverse=True
)


# --------------------------------------------------
# RSS生成
# --------------------------------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)

ET.SubElement(
    channel,
    "title"
).text = "中国中央病院 更新情報"

ET.SubElement(
    channel,
    "link"
).text = SOURCE_URL

ET.SubElement(
    channel,
    "description"
).text = (
    "公立学校共済組合 中国中央病院の更新情報"
)

ET.SubElement(
    channel,
    "language"
).text = "ja"


for item in all_items:

    element = ET.SubElement(
        channel,
        "item"
    )

    ET.SubElement(
        element,
        "title"
    ).text = item["title"]

    ET.SubElement(
        element,
        "link"
    ).text = item["link"]

    ET.SubElement(
        element,
        "description"
    ).text = item["description"]

    ET.SubElement(
        element,
        "pubDate"
    ).text = item["pubDate"]

    guid_element = ET.SubElement(
        element,
        "guid"
    )

    guid_element.set(
        "isPermaLink",
        "false"
    )

    guid_element.text = item["guid"]


# --------------------------------------------------
# XML保存
# --------------------------------------------------

tree = ET.ElementTree(rss)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)


print()
print("RSS作成成功")

print(
    "RSS保存件数:",
    len(all_items),
    "件"
)

print(
    "保存先:",
    OUTPUT
)

print()
print("今回取得した記事:")

for i, item in enumerate(
    current_items,
    start=1
):

    print()
    print(
        f"[{i}] "
        f"{item['pubDate']} "
        f"{item['title']}"
    )

    if item["description"]:
        print(
            "    ",
            item["description"]
        )

    print(
        "    ",
        item["link"]
    )