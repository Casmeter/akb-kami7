import json
import os
import time
import urllib.parse
import urllib.request

PROXY = os.environ.get("AKB_PROXY", "http://127.0.0.1:7897")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
API = "https://48pedia.org/api.php"

_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}) if PROXY else urllib.request.ProxyHandler({})
)


def get(url, retries=4, data=None):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Referer": "https://48pedia.org/"})
            with _opener.open(req, timeout=40) as r:
                return r.read()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def api(**params):
    params.setdefault("format", "json")
    return json.loads(get(API, data=urllib.parse.urlencode(params).encode()))


def wikitext(page):
    return api(action="parse", page=page, prop="wikitext")["parse"]["wikitext"]["*"]
