# DiceBot · 桌游夜航

QQ Bot 在群里登记玩家、缓存 QQ 头像并发送链接；玩家在网页选择自己的 QQ 身份，随后在浏览器里玩牌。第一个桌游是 [TTS 创意工坊《炸弹猫（个人精翻版）》](https://steamcommunity.com/sharedfiles/filedetails/?id=2375784308) 的基础版牌组。

## 组成

| 部分 | 作用 | 部署位置 |
| --- | --- | --- |
| `bot.py`、`dicebot/` | NoneBot2 + OneBot V11，处理 QQ 群组局命令，向实时服务上传头像和名单 | 能连接 QQ OneBot 的主机 |
| `tabletop_server/` | 牌堆、手牌、行动校验、WebSocket 实时同步，持久化房间和头像 | 可从公网通过 HTTPS/WSS 访问的 Python 主机 |
| `web/` | 静态牌桌页面和本地卡牌图片 | GitHub Pages |

GitHub Pages 本身不能运行 Python 或 WebSocket 服务。正式联机需要同时部署 `tabletop_server`，并给它一个公网 HTTPS 地址。服务端只把手牌和“预知”结果发给本人；群里的朋友自行选择 QQ 身份，因此房间没有强身份认证。

## 本地运行

需要 Python 3.10+ 和 `uv`。在项目根目录：

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

编辑 `.env`，至少填写随机的 `TABLETOP_ADMIN_TOKEN`。Bot 与实时服务共用同一份 `.env`，令牌不要提交到 Git。然后分别启动三个终端：

```powershell
uv run uvicorn tabletop_server.app:app --host 127.0.0.1 --port 8765
python -m http.server 8077 --bind 127.0.0.1 -d web
uv run python bot.py
```

浏览器可打开 `http://127.0.0.1:8077/`。QQ 的 OneBot V11 实现端需开启**反向 WebSocket**，连接到 `ws://127.0.0.1:8080/onebot/v11/`；如启用 access token，两端填写相同值。配置细节见 [OneBot 适配器文档](https://onebot.adapters.nonebot.dev/docs/guide/setup/)。本仓库不包含 QQ 登录协议实现端。

## QQ 群操作

```text
/桌游 创建 炸弹猫
/桌游 加入
/桌游 状态
/桌游 开始
/桌游 结束
```

建房或加入时，Bot 使用玩家 QQ ID 读取头像并上传到实时服务，获取失败则网页显示姓名首字。房主发送“开始”后，2–5 位玩家打开链接，各自点击自己的 QQ 头像认领座位。玩家可以在新浏览器再次认领同一座位，旧浏览器令牌会失效。游戏开始后，出牌、抽牌、反制和拆弹都在网站完成。

当前基础规则：每人 1 张拆弹牌和 7 张普通牌起手；加入比玩家少 1 张的炸弹；支持攻击、跳过、洗牌、预知、帮帮忙、不行以及两张相同猫牌的组合。出牌后由出牌玩家点击“确认结算”，其他玩家可在此之前用“不行”反制。工坊备注中的进阶三张、五张组合尚未实现。

## 导入的 TTS 图包

本机原始存档位于 `D:\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2375784308.json`。`scripts/import_tts.py` 从该存档读取两张图集来源，下载到 `web/public/assets/exploding-kittens/`，并切出 41 种牌面、生成包含 56 张牌的 `manifest.json`。运行时网页只读取仓库里的本地图片，**不会访问 TTS 素材接口**。原存档 `tts-source.json` 一并保留，便于核对牌的数量与来源。

```powershell
uv run python scripts/import_tts.py "D:\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2375784308.json"
```

图包来自创意工坊作者 ChopDaSushi 的个人翻译版，包含原游戏美术。创意工坊可下载不等于授权在公开网站再分发；公开发布前应确认原游戏权利人和模组作者对网页发布的许可。

## 上线到 GitHub Pages

1. 创建 `iPlayForSG/DiceBot` 仓库并推送 `main`。Pages 的 Source 选 **GitHub Actions**；工作流在 `.github/workflows/pages.yml`。
2. 另行部署实时服务，使用**单个进程**运行 `uvicorn tabletop_server.app:app`，为 `TABLETOP_DATA_DIR` 配置持久磁盘，并提供 HTTPS/WSS。多进程部署前需要把房间与连接状态迁移到共享存储。
3. 在仓库 Actions variables 中设置 `TABLETOP_API_URL` 为实时服务的公网 HTTPS 根地址，例如 `https://tabletop-api.example.com`。工作流会在发布时写入 `web/config.js`。
4. 实时服务环境变量设 `TABLETOP_ALLOWED_ORIGINS=https://iplayforsg.github.io`、`TABLETOP_ADMIN_TOKEN=<同 Bot>`；Bot 的 `TABLETOP_API_URL` 指向同一服务，`TABLETOP_PUBLIC_URL=https://iplayforsg.github.io/DiceBot`。

如果只发布 GitHub Pages，静态页面会出现，但不能建房和实时游玩。发布依赖 GitHub 仓库权限和一个公网后端部署位置。

### 用 Cloudflare Tunnel 暴露本机实时服务

当前本机已安装 Cloudflare 官方 `cloudflared`。另开终端启动一个临时隧道：

```powershell
cloudflared tunnel --url http://127.0.0.1:8765 --no-autoupdate
```

它会输出一个随机的 `https://...trycloudflare.com` 地址。把这个地址设为仓库变量 `TABLETOP_API_URL`，重新运行 Pages 工作流；`.env` 的 `TABLETOP_ALLOWED_ORIGINS` 要包含 `https://iplayforsg.github.io`。本机实时服务和隧道进程需要一直运行。Cloudflare [将 Quick Tunnel 定位为测试用途](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)；进程重启后地址可能变化，届时需要更新仓库变量并重新发布。

固定地址应使用 Cloudflare 账号中托管的域名创建**命名隧道**，把其 Public Hostname 的 HTTP 源指向 `127.0.0.1:8765`。云端仍以 HTTPS/WSS 对外。具体创建流程见 [Cloudflare 文档](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/)。

## 验证

```powershell
uv run pytest -q
node --check web/app.js
```
