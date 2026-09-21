#!/usr/bin/env python3
"""登录墙源抓取骨架（牛客深度帖 / 小红书 等需登录站点）。
复用 zhipin-jd-scraper 的 CDP 方案：用本机已登录的 Chrome（远程调试端口 9222）读取页面，
全程只读 DOM、不存储账号凭据。选择器需按目标站点实际结构补全（见 TODO）。
"""
import json
import sys
import time

try:
    from chrome_remote_interface import Chrome
except ImportError:
    print("缺少 chrome-remote-interface：在脚本目录 `npm i chrome-remote-interface`", file=sys.stderr)
    sys.exit(1)

TARGETS = {
    "nowcoder": "https://www.nowcoder.com/search?query=Agent%E5%BC%80%E5%8F%91%20%E9%9D%A2%E7%BB%8F",
    # "xiaohongshu": "https://www.xiaohongshu.com/search_result?keyword=Agent开发面经",
}


def open_tab(chrome, url):
    """复用已登录 tab（不要 New() 新建，否则渲染不出登录态内容）。"""
    # TODO: 适配 zhipin 方案里的 pickTab() —— 找到匹配目标域名的已开 tab
    tab = chrome.new_tab(url)  # 占位：正式实现应复用已登录 tab
    tab.start()
    time.sleep(3)  # 等渲染 + 登录态
    return tab


def extract_posts(tab):
    """TODO: 按目标站点的帖子卡片选择器抽取 {title, content, url}。"""
    # 例（牛客帖子结构待实测）：
    # dom = tab.Runtime.evaluate("document.body.innerText")
    # 解析出每条面经片段与手撕题，返回 list[dict]
    return []


def main():
    chrome = Chrome("http://127.0.0.1:9222")
    out = []
    for name, url in TARGETS.items():
        tab = open_tab(chrome, url)
        try:
            out.extend(extract_posts(tab))
        finally:
            tab.stop()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
