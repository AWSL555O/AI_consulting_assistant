"""模块一：热点数据获取 - Playwright + API 双模式，支持并发抓取"""
import json
import re
import time
import os
import random
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import requests
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError

from config import config


# ========== 结果缓存（TTL 缓存） ==========
class _ResultCache:
    """简单内存缓存，N 秒内命中同一请求"""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[float, list]] = {}  # key → (过期时间戳, 数据)
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[list]:
        """命中缓存返回数据，否则返回 None"""
        if key in self._cache:
            expire_at, data = self._cache[key]
            if time.time() < expire_at:
                return data
            del self._cache[key]
        return None

    def set(self, key: str, data: list):
        self._cache[key] = (time.time() + self._ttl, data)

    def clear_expired(self):
        """清理过期条目"""
        now = time.time()
        self._cache = {k: v for k, v in self._cache.items() if now < v[0]}


# 全局缓存实例
_fetch_cache = _ResultCache(ttl_seconds=300)


# ========== 调试截图辅助 ==========
def _save_debug_screenshot(page: Page, platform: str):
    """保存调试截图，按平台+时间戳命名，不覆盖旧图"""
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{platform}_{ts}.png"
    path = os.path.join(debug_dir, filename)
    try:
        page.screenshot(path=path, full_page=False)
        print(f"[调试] 截图已保存: {filename}")
    except Exception as e:
        print(f"[调试] 截图失败: {e}")


@dataclass
class HotspotItem:
    """单条热点数据的结构"""
    title: str          # 标题
    hot_value: str      # 热度值/播放量
    author: str          # 作者/UP主
    source: str          # 来源平台
    link: str            # 内容链接


# ========== 全局浏览器单例 ==========
_browser_instance: Optional[Browser] = None
_playwright_instance = None


def get_browser(headless: bool = True) -> Browser:
    """获取浏览器单例，避免每次启动 Chromium 的高昂成本"""
    global _browser_instance, _playwright_instance
    if _browser_instance is None or not _browser_instance.is_connected():
        _playwright_instance = sync_playwright().start()
        _browser_instance = _playwright_instance.chromium.launch(headless=headless)
    return _browser_instance


def close_browser():
    """关闭全局浏览器单例"""
    global _browser_instance, _playwright_instance
    if _browser_instance:
        _browser_instance.close()
        _browser_instance = None
    if _playwright_instance:
        _playwright_instance.stop()
        _playwright_instance = None


def load_cookies_from_file(filepath: str) -> list:
    """从 JSON 文件加载 Cookies"""
    if not os.path.exists(filepath):
        print(f"[警告] Cookie 文件不存在: {filepath}")
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        print(f"[OK] 已加载 {len(cookies)} 个 Cookies: {filepath}")
        return cookies
    except Exception as e:
        print(f"[错误] 加载 Cookies 失败: {e}")
        return []


def save_cookies_to_file(cookies: list, filepath: str) -> None:
    """保存 Cookies 到文件（JSON格式）"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"[OK] Cookies 已保存: {filepath}")
    except Exception as e:
        print(f"[错误] 保存 Cookies 失败: {e}")


# ========== API 抓取（B站官方 API，无需浏览器） ==========
def fetch_bilibili_api(top_n: int = 10, cookies: list = None) -> list[HotspotItem]:
    """B站官方 API 抓取（需要登录 Cookie）"""
    url = "https://api.bilibili.com/x/web-interface/ranking/v2"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    try:
        # 用登录态 Cookie 避免 -352
        cookie_dict = {c["name"]: c["value"] for c in (cookies or [])}
        resp = requests.get(url, headers=headers, cookies=cookie_dict, timeout=10)
        data = resp.json()
        if data["code"] != 0:
            raise Exception(f"B站API返回错误: {data.get('message', 'unknown')}")

        items = []
        for item in data["data"]["list"][:top_n]:
            stat = item.get("stat", {})
            items.append(HotspotItem(
                title=item.get("title", ""),
                hot_value=_format_view_count(stat.get("view", 0)),
                author=item.get("owner", {}).get("name", "未知"),
                source="bilibili",
                link=f"https://www.bilibili.com/video/{item.get('bvid', '')}"
            ))
        print(f"[B站API] 成功获取 {len(items)} 条数据")
        return items
    except Exception as e:
        print(f"[B站API] 失败: {e}，将降级到 Playwright 模式")
        return []


def _format_view_count(view: int) -> str:
    """格式化播放量，如 123456 → 12.3万"""
    if view >= 10000:
        return f"{view / 10000:.1f}万"
    return str(view)


# ========== 微博热搜 API（备用） ==========
def fetch_weibo_api(top_n: int = 10) -> list[HotspotItem]:
    """微博热搜 API（非官方，但比爬 DOM 更稳定）"""
    url = "https://s.weibo.com/top/summary"
    params = {"cate": "realtimehot"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://s.weibo.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        # 微博热搜直接返回 JS，解析比较麻烦，这里只做简单尝试
        # 如果失败，让调用方降级到 Playwright
        if resp.status_code != 200:
            raise Exception(f"微博API返回状态码: {resp.status_code}")
        print(f"[微博API] 状态码: {resp.status_code}，内容长度: {len(resp.text)}")
        return []
    except Exception as e:
        print(f"[微博API] 失败: {e}，将降级到 Playwright 模式")
        return []


class HotspotFetcher:
    """热点数据抓取器 - 支持 B站、抖音、微博，支持浏览器复用"""

    BILIBILI_URL = "https://www.bilibili.com/v/popular/rank/all"
    DOUYIN_URL = "https://www.douyin.com/hot"
    WEIBO_URL = "https://s.weibo.com/top/summary"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self._context = None

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bilibili_cookies_file = os.path.join(base_dir, "bilibili_cookies.json")
        self.douyin_cookies_file = os.path.join(base_dir, "douyin_cookies.json")

    def __enter__(self):
        # 复用全局浏览器单例，而非每次启动新浏览器
        self.browser = get_browser(headless=self.headless)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 不关闭浏览器，保持复用
        if self._context:
            self._context.close()
            self._context = None

    def _create_context(self, cookies: list = None) -> Page:
        """创建浏览器上下文页面"""
        context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        if cookies:
            try:
                context.add_cookies(cookies)
                print(f"[OK] 已为浏览器上下文添加 {len(cookies)} 个 Cookies")
            except Exception as e:
                print(f"[警告] 添加 Cookies 失败: {e}")

        # 去除 webdriver 检测
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self._context = context
        return context.new_page()

    def _human_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """模拟人类操作间隔（真正的随机）"""
        import random
        time.sleep(random.uniform(min_sec, max_sec))

    def login_bilibili(self) -> bool:
        """手动登录 B站 并保存 Cookies"""
        print("\n" + "=" * 50)
        print("[B站登录] 即将打开浏览器，请手动登录...")
        print("=" * 50)

        context = self.browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        try:
            page.goto("https://passport.bilibili.com/login", timeout=30000)
            print("[B站登录] 请在浏览器中完成登录（扫码或账号密码）")
            print("[B站登录] 登录成功后，按回车键继续...")
            input()
            cookies = context.cookies()
            print(f"[B站登录] 获取到 {len(cookies)} 个 Cookies")
            save_cookies_to_file(cookies, self.bilibili_cookies_file)
            print("[B站登录] 完成！")
            return True
        except Exception as e:
            print(f"[B站登录] 失败: {e}")
            return False
        finally:
            page.close()
            context.close()

    def login_douyin(self) -> bool:
        """手动登录 抖音 并保存 Cookies"""
        print("\n" + "=" * 50)
        print("[抖音登录] 即将打开浏览器，请手动登录...")
        print("=" * 50)

        context = self.browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        try:
            page.goto("https://www.douyin.com", timeout=30000)
            print("[抖音登录] 请在浏览器中完成登录（扫码或账号密码）")
            print("[抖音登录] 登录成功后，按回车键继续...")
            input()
            cookies = context.cookies()
            print(f"[抖音登录] 获取到 {len(cookies)} 个 Cookies")
            save_cookies_to_file(cookies, self.douyin_cookies_file)
            print("[抖音登录] 完成！")
            return True
        except Exception as e:
            print(f"[抖音登录] 失败: {e}")
            return False
        finally:
            page.close()
            context.close()

    # ========== B站 Playwright 抓取（API 失败时的降级方案） ==========
    def _fetch_bilibili_page(self, context, top_n: int = 10) -> list[HotspotItem]:
        """内部方法：共用 context 抓取 B站"""
        items = []
        page = context.new_page()

        try:
            print(f"[B站] 正在访问: {self.BILIBILI_URL}")
            page.goto(self.BILIBILI_URL, timeout=config.REQUEST_TIMEOUT)
            try:
                page.wait_for_selector(".rank-item", timeout=15000)
            except PlaywrightTimeoutError:
                _save_debug_screenshot(page, "bilibili")
                return items
            self._human_delay(1, 2)

            rank_items = page.query_selector_all(".rank-item")
            print(f"[B站] 找到 {len(rank_items)} 个视频条目")

            for i, item in enumerate(rank_items[:top_n]):
                try:
                    title_elem = item.query_selector(".title")
                    title = title_elem.get_attribute("title") if title_elem else ""
                    if not title:
                        title_elem2 = item.query_selector("a.title")
                        title = title_elem2.inner_text().strip() if title_elem2 else ""

                    data_boxes = item.query_selector_all(".data-box")
                    hot_value = data_boxes[1].inner_text().strip() if len(data_boxes) >= 2 else ""

                    author = ""
                    up_name_elem = item.query_selector(".up-name")
                    if up_name_elem:
                        author = up_name_elem.inner_text().strip()

                    link_elem = item.query_selector("a[href*='/video/']")
                    href = link_elem.get_attribute("href") if link_elem else ""
                    if href.startswith("/video"):
                        link = f"https://www.bilibili.com{href}"
                    elif href.startswith("//www.bilibili.com/video"):
                        link = f"https:{href}"
                    else:
                        link = href

                    rank_num = item.query_selector(".num span")
                    rank_text = rank_num.inner_text().strip() if rank_num else str(i + 1)

                    if title:
                        items.append(HotspotItem(
                            title=title,
                            hot_value=hot_value or f"排名{rank_text}",
                            author=author or "未知",
                            source="bilibili",
                            link=link
                        ))
                        print(f"[B站] [{i+1}] {title[:30]}... | {hot_value} | {author}")
                except Exception as e:
                    print(f"[B站] 解析第 {i+1} 条失败: {e}")
                    continue

        except Exception as e:
            print(f"[B站] 抓取失败: {e}")
            _save_debug_screenshot(page, "bilibili")
        finally:
            page.close()

        print(f"[B站] 成功抓取 {len(items)} 条数据")
        return items

    # 兼容旧接口（独立创建 Context）
    def fetch_bilibili(self, top_n: int = 10) -> list[HotspotItem]:
        """抓取 B站 热门排行榜前 N 条数据（独立 Context）"""
        cookies = load_cookies_from_file(self.bilibili_cookies_file)
        context = self.browser.new_context(viewport={"width": 1920, "height": 1080})
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        context.add_cookies(cookies)
        page = context.new_page()
        try:
            return self._fetch_bilibili_page(context, top_n)
        finally:
            context.close()

    # ========== 抖音 Playwright 抓取 ==========
    def _fetch_douyin_page(self, context, top_n: int = 10) -> list[HotspotItem]:
        """内部方法：共用 context 抓取抖音"""
        items = []
        page = context.new_page()

        try:
            print(f"[抖音] 正在访问: {self.DOUYIN_URL}")
            page.goto(self.DOUYIN_URL, timeout=config.REQUEST_TIMEOUT)
            try:
                page.wait_for_selector("a[href*='/hot/']", timeout=15000)
            except PlaywrightTimeoutError:
                _save_debug_screenshot(page, "douyin")
                return items
            self._human_delay(1, 2)

            hot_links = page.query_selector_all("a[href*='/hot/']")
            print(f"[抖音] 找到 {len(hot_links)} 个热搜话题")

            for i, link in enumerate(hot_links[1:top_n + 1], start=1):
                try:
                    href = link.get_attribute("href") or ""
                    title = link.inner_text().strip()
                    full_url = f"https://www.douyin.com{href}" if href.startswith("/") else href

                    if title and len(title) > 1:
                        items.append(HotspotItem(
                            title=title[:200],
                            hot_value=f"第{i}",
                            author="抖音热榜",
                            source="douyin",
                            link=full_url
                        ))
                        print(f"[抖音] [{i}] {title[:30]}...")
                except Exception as e:
                    print(f"[抖音] 解析第 {i} 条失败: {e}")
                    continue

        except Exception as e:
            print(f"[抖音] 抓取失败: {e}")
            _save_debug_screenshot(page, "douyin")
        finally:
            page.close()

        print(f"[抖音] 成功抓取 {len(items)} 条数据")
        return items

    # 兼容旧接口
    def fetch_douyin(self, top_n: int = 10) -> list[HotspotItem]:
        cookies = load_cookies_from_file(self.douyin_cookies_file)
        context = self.browser.new_context(viewport={"width": 1920, "height": 1080})
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        context.add_cookies(cookies)
        page = context.new_page()
        try:
            return self._fetch_douyin_page(context, top_n)
        finally:
            context.close()

    # ========== 微博 Playwright 抓取 ==========
    def _fetch_weibo_page(self, context, top_n: int = 10) -> list[HotspotItem]:
        """内部方法：共用 context 抓取微博"""
        items = []
        page = context.new_page()

        try:
            print(f"[微博] 正在访问: {self.WEIBO_URL}")
            page.goto(self.WEIBO_URL, timeout=config.REQUEST_TIMEOUT)
            try:
                page.wait_for_selector("tbody tr", timeout=15000)
            except PlaywrightTimeoutError:
                _save_debug_screenshot(page, "weibo")
                return items
            self._human_delay(1, 2)

            hot_items = page.query_selector_all("tbody tr")

            if not hot_items:
                for sel in ["[class*='list-item']", "[class*='topic']", ".tr"]:
                    hot_items = page.query_selector_all(sel)
                    if hot_items:
                        print(f"[微博] 使用备选选择器 '{sel}' 找到 {len(hot_items)} 个")
                        break

            # 跳过置顶项
            start_idx = 0
            for idx, elem in enumerate(hot_items):
                if 'icon-top' in elem.inner_html():
                    start_idx = idx + 1
                else:
                    break

            print(f"[微博] 跳过 {start_idx} 条置顶项，从第 {start_idx + 1} 条开始计数")

            for i, elem in enumerate(hot_items[start_idx:start_idx + top_n], start=1):
                try:
                    raw_text = elem.inner_text()

                    title_elem = elem.query_selector("a[href*='/status/']")
                    title = ""
                    if title_elem:
                        title_elem_text = title_elem.inner_text().strip()
                        cleaned_title = re.sub(r'^[\d]+\s*', '', title_elem_text)
                        title = cleaned_title if cleaned_title else title_elem_text

                    if not title or len(title) < 2:
                        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                        title = lines[1] if len(lines) > 1 else (lines[0] if lines else "")

                    numbers = re.findall(r'\d+', raw_text)
                    hot_value = ""
                    for num in numbers:
                        if len(num) >= 4:
                            hot_value = num
                            break
                    if not hot_value:
                        hot_value = numbers[0] if numbers else f"第{i+1}"

                    link = "https://s.weibo.com/top/summary"

                    title = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title).strip()
                    title = re.sub(r'^[\d]+\s*', '', title).strip()
                    title = re.sub(r'\s+\d+热?$', '', title).strip()

                    if title and 1 < len(title) < 200:
                        items.append(HotspotItem(
                            title=title[:200],
                            hot_value=hot_value,
                            author="微博热搜",
                            source="weibo",
                            link=link
                        ))
                        print(f"[微博] [{i+1}] {title[:30]}... | {hot_value}")
                except Exception as e:
                    print(f"[微博] 解析第 {i+1} 条失败: {e}")
                    continue

        except Exception as e:
            print(f"[微博] 抓取失败: {e}")
            _save_debug_screenshot(page, "weibo")
        finally:
            page.close()

        print(f"[微博] 成功抓取 {len(items)} 条数据")
        return items

    # 兼容旧接口
    def fetch_weibo(self, top_n: int = 10) -> list[HotspotItem]:
        context = self.browser.new_context(viewport={"width": 1920, "height": 1080})
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()
        try:
            return self._fetch_weibo_page(context, top_n)
        finally:
            context.close()

    # ========== 批量抓取并合并 ==========
    def fetch_all(self, top_n: int = 10) -> pd.DataFrame:
        """抓取三平台，API 优先，共用单一 Context，5分钟缓存"""
        cache_key = f"hotspot_top{top_n}"

        # 尝试命中缓存（5分钟内不重复抓）
        cached = _fetch_cache.get(cache_key)
        if cached is not None:
            print(f"[缓存] 命中，5分钟内数据直接返回（{len(cached)} 条）")
            return pd.DataFrame([{
                "title": item.title,
                "hot_value": item.hot_value,
                "author": item.author,
                "source": item.source,
                "link": item.link,
            } for item in cached])

        all_items: list[HotspotItem] = []

        # 加载 Cookie
        bilibili_cookies = load_cookies_from_file(self.bilibili_cookies_file)
        douyin_cookies = load_cookies_from_file(self.douyin_cookies_file)

        # ========== 共用一个 Context（避免重复创建） ==========
        context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        try:
            context.add_cookies(bilibili_cookies)
            context.add_cookies(douyin_cookies)
        except Exception as e:
            print(f"[警告] 添加 Cookies 失败: {e}")

        # 1. B站 API（最快）
        print("\n" + "=" * 50)
        print("开始抓取 B站（优先 API）...")
        bilibili_items = fetch_bilibili_api(top_n, cookies=bilibili_cookies)

        if not bilibili_items:
            print("B站API失败，降级到 Playwright...")
            bilibili_items = self._fetch_bilibili_page(context, top_n)
        all_items.extend(bilibili_items)
        print(f"B站: {len(bilibili_items)} 条")

        # 2. 微博
        print("\n" + "=" * 50)
        print("开始抓取 微博...")
        weibo_items = self._fetch_weibo_page(context, top_n)
        all_items.extend(weibo_items)
        print(f"微博: {len(weibo_items)} 条")

        # 3. 抖音
        print("\n" + "=" * 50)
        print("开始抓取 抖音...")
        douyin_items = self._fetch_douyin_page(context, top_n)
        all_items.extend(douyin_items)
        print(f"抖音: {len(douyin_items)} 条")

        context.close()

        # 存入缓存
        _fetch_cache.set(cache_key, all_items)

        # 转为 DataFrame
        df = pd.DataFrame([{
            "title": item.title,
            "hot_value": item.hot_value,
            "author": item.author,
            "source": item.source,
            "link": item.link,
        } for item in all_items])

        df = self._clean_dataframe(df)

        print(f"\n总计获取 {len(df)} 条数据（B站: {len(bilibili_items)}, 微博: {len(weibo_items)}, 抖音: {len(douyin_items)}）")
        return df

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """数据清洗"""
        if df.empty:
            return df

        original_len = len(df)
        df = df.dropna(subset=["title"])
        df = df[df["title"].str.strip() != ""]
        df = df.drop_duplicates(subset=["title"], keep="first")
        df.columns = df.columns.str.lower().str.strip().str.replace(" ", "_")
        df = df.reset_index(drop=True)

        cleaned_len = len(df)
        if original_len > cleaned_len:
            print(f"[清洗] 去除 {original_len - cleaned_len} 条重复/空数据")

        return df


def init_playwright():
    """初始化 Playwright 浏览器驱动（首次运行需要执行）"""
    from playwright.install import install
    print("正在安装 Playwright 浏览器驱动...")
    install()
    print("安装完成！")


if __name__ == "__main__":
    print("=" * 60)
    print("热点数据抓取测试（优化版）")
    print("=" * 60)

    with HotspotFetcher(headless=True) as fetcher:
        bilibili_data = fetcher.fetch_bilibili(top_n=5)
        print(f"\nB站数据预览: {bilibili_data[:2]}")
