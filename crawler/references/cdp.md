# 登录墙抓取方案（references/cdp.md）

来源：复用本机已装的 `zhipin-jd-scraper` skill 的 CDP 套路（其 SKILL.md 含完整实现与排错）。

## 核心思路
- 不破解、不存凭据：复用**用户本机已登录的 Chrome** 远程调试端口（默认 9222）。
- 必须复用已登录 tab（不要 `CDP.New()` 新建），否则渲染不出登录态内容。
- 沙箱 DNS 不通时，用 `--host-resolver-rules` 把目标域名直连映射到实测可通 IP；不行再用本地正向代理兜底。

## 步骤（Windows PowerShell 示例）
```powershell
taskkill /F /IM chrome.exe /T; Start-Sleep 5
$chromeExe = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
$userDir   = "$env:LOCALAPPDATA\Google\Chrome\User Data"
# rules 按目标站点实测 IP 填；此处以 nowcoder 为例占位
$rules = 'MAP www.nowcoder.com 1.2.3.4,MAP *.nowcoder.com 1.2.3.4'
Start-Process $chromeExe -ArgumentList "--remote-debugging-port=9222","--no-sandbox","--disable-async-dns","--disable-dev-shm-usage","--host-resolver-rules=$rules","--user-data-dir=$userDir","--no-first-run"
# 验证： curl http://127.0.0.1:9222/json/version
```
依赖（脚本目录）：`npm i chrome-remote-interface`，运行时 `NODE_PATH=./node_modules node scripts/collect_login.py`。

## 关键陷阱（照搬 zhipin 经验）
- 调试端口连不上 → 杀净旧 chrome 单实例重启。
- 新标签渲染不出卡片 → 复用已登录 tab。
- 反爬：串行 + 随机 sleep，遇登录墙/验证即跳过。
- 抽取选择器需按目标站点实测结构补全（collect_login.py 的 `extract_posts` 是 TODO）。
