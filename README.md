# DiceBot · 桌游夜航

QQ Bot 在群里登记玩家、缓存 QQ 头像并发送链接；玩家在网页选择自己的 QQ 身份，随后在浏览器里玩牌。第一个桌游是 [TTS 创意工坊《炸弹猫（个人精翻版）》](https://steamcommunity.com/sharedfiles/filedetails/?id=2375784308) 的基础版牌组。

网站首页是通用桌游大厅，展示房间入口与已开放游戏。目前支持炸弹猫、方·鸟、政变、璀璨宝石、阿瓦隆五款游戏。服务端按游戏类型创建房间，私密手牌和身份只返回给已认领座位的本人。

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

本机使用 [NapCat Shell](https://doc.napneko.icu/guide/boot/Shell) 作为 OneBot 实现端，另行保存在被 Git 忽略的 `.local-tools/napcat/shell/`。启动 `launcher-user.bat <机器人QQ号>`，登录后在 `config/onebot11_<机器人QQ号>.json` 中启用 WebSocket 客户端，连接到 `ws://127.0.0.1:8080/onebot/v11/ws`。`token` 应与 `.env` 的 `ONEBOT_ACCESS_TOKEN` 相同。NapCat WebUI 只监听 `127.0.0.1:6099`，不通过 Cloudflare Tunnel 对外开放。

## QQ 群操作

```text
/桌游 创建 炸弹猫
/桌游 创建 炸弹猫 进阶
/桌游 创建 方·鸟
/桌游 创建 政变
/桌游 创建 政变 扩展
/桌游 创建 璀璨宝石
/桌游 创建 阿瓦隆
/桌游 创建 阿瓦隆 进阶
/桌游 加入
/桌游 状态
/桌游 开始
/桌游 结束
```

建房或加入时，Bot 使用玩家 QQ ID 读取头像并上传到实时服务，获取失败则网页显示姓名首字。人数达到对应游戏要求后，房主发送“开始”，玩家打开链接并各自点击自己的 QQ 头像认领座位。玩家可以在新浏览器再次认领同一座位，旧浏览器令牌会失效。游戏操作在各自的网页牌桌完成。

炸弹猫基础规则：每人 1 张拆弹牌和 7 张普通牌起手；加入比玩家少 1 张的炸弹；支持攻击、跳过、洗牌、预知、帮帮忙、不行以及两张相同猫牌的组合。选择“进阶”组局后，还支持两张同名牌随机抽牌、三张同名牌声明并索取、五张不同牌从弃牌堆取回一张。出牌后由出牌玩家点击“确认结算”，其他玩家可在此之前用“不行”反制。

方·鸟按鸟种摆牌、夹取、补牌、收鸟群和新一轮发牌。璀璨宝石自动维护三层发展卡、宝石供应、折扣、贵族与计分。阿瓦隆自动分配身份、提供各角色的私密情报，并收集组队票与任务牌。政变保留社交诈称：玩家在 QQ 群讨论质疑和阻挡，再在网页确认亮牌、失去影响与结算；扩展模式加入判官和阵营。政变模组还含 KS 替换角色图包，当前自动牌局暂不启用这些替换角色。

四个新模组的图片和存档来自 [方·鸟](https://steamcommunity.com/sharedfiles/filedetails/?id=2299292104)、[政变](https://steamcommunity.com/sharedfiles/filedetails/?id=2385450244)、[璀璨宝石](https://steamcommunity.com/sharedfiles/filedetails/?id=2093855539)、[阿瓦隆](https://steamcommunity.com/sharedfiles/filedetails/?id=929329226)。`scripts/import_workshop_games.py` 将工坊 BSON 存档解码，把图集下载到本机缓存，并在 `web/public/assets/` 生成压缩图片和清单。网页运行时只读取本站图片，不调用 TTS 或 Steam 图床。

## 导入的 TTS 图包

本机原始存档位于 `D:\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2375784308.json`。`scripts/import_tts.py` 从该存档读取两张图集来源，下载到 `web/public/assets/exploding-kittens/`，并切出 41 种牌面、生成包含 56 张牌的 `manifest.json`。运行时网页只读取仓库里的本地图片，**不会访问 TTS 素材接口**。原存档 `tts-source.json` 一并保留，便于核对牌的数量与来源。

```powershell
uv run python scripts/import_tts.py "D:\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2375784308.json"
```

图包包含原游戏美术，工坊可下载不等于授权在公开网站再分发。特别是政变模组作者在页面明确写有“此 mod 仅供个人交流，切勿它用”；正式对外运营前需要确认原游戏权利人和模组作者对网页发布的许可。

## 上线到 GitHub Pages

1. 创建 `iPlayForSG/DiceBot` 仓库并推送 `main`。Pages 的 Source 选 **GitHub Actions**；工作流在 `.github/workflows/pages.yml`。
2. 另行部署实时服务，使用**单个进程**运行 `uvicorn tabletop_server.app:app`，为 `TABLETOP_DATA_DIR` 配置持久磁盘，并提供 HTTPS/WSS。多进程部署前需要把房间与连接状态迁移到共享存储。
3. 将 `deployment/api-url.txt` 设为实时服务的公网 HTTPS 根地址，例如 `https://tabletop-api.example.com`；工作流发布时将其写入 `web/config.js`。没有该文件时才读取仓库变量 `TABLETOP_API_URL`。
4. 实时服务环境变量设 `TABLETOP_ALLOWED_ORIGINS=https://iplayforsg.github.io`、`TABLETOP_ADMIN_TOKEN=<同 Bot>`；Bot 的 `TABLETOP_API_URL` 指向同一服务，`TABLETOP_PUBLIC_URL=https://iplayforsg.github.io/DiceBot`。

如果只发布 GitHub Pages，静态页面会出现，但不能建房和实时游玩。发布依赖 GitHub 仓库权限和一个公网后端部署位置。

### 用 Cloudflare Tunnel 暴露本机实时服务

当前本机已安装 Cloudflare 官方 `cloudflared`。另开终端启动一个临时隧道：

```powershell
cloudflared tunnel --url http://127.0.0.1:8765 --no-autoupdate
```

它会输出一个随机的 `https://...trycloudflare.com` 地址。把这个地址写入 `deployment/api-url.txt` 并推送，Pages 会自动发布；`.env` 的 `TABLETOP_ALLOWED_ORIGINS` 要包含 `https://iplayforsg.github.io`。本机实时服务和隧道进程需要一直运行。Cloudflare [将 Quick Tunnel 定位为测试用途](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)；进程重启后地址可能变化，届时需要重新发布。

在这台已保存 GitHub 凭据的电脑上，可用 `uv run python scripts/run_quick_demo.py` 一次启动 Bot、实时服务和临时隧道，并自动更新 Pages 地址文件。NapCat 仍需单独启动并登录。关闭该终端会停止这三个进程；电脑休眠或断网时，网页也无法继续联机。

固定地址应使用 Cloudflare 账号中托管的域名创建**命名隧道**，把其 Public Hostname 的 HTTP 源指向 `127.0.0.1:8765`。云端仍以 HTTPS/WSS 对外。具体创建流程见 [Cloudflare 文档](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/)。

### Windows 常驻主机

目标机使用 `C:\Users\<用户>\DiceBot` 放项目和私有 `.env`，`C:\Users\<用户>\NapCatRuntime` 放独立 QQ/NapCat。部署工具 `scripts/bootstrap_remote.py` 和 `scripts/bootstrap_napcat.py` 会生成本机密钥与反向 WebSocket 配置；密码和令牌不会进入仓库。NapCat 的便携启动器为 `scripts/launch_napcat_portable.py`。

目前无 Cloudflare 托管域名时，`scripts/run_quick_demo.py` 会在隧道重启后更新 `deployment/api-url.txt` 并推送到 GitHub，让 Pages 自动重发。远端使用**仅能写入本仓库的 GitHub 部署密钥**，不复制个人 GitHub 登录。首次配置完成后，可由管理员运行：

```powershell
./scripts/install_windows_tasks.ps1 -QQ <机器人QQ号>
```

这会登记两个仅在该 Windows 用户登录时启动的任务：游戏 API/Bot/临时隧道，以及 NapCat。电脑须保持登录、联网且不休眠；登录任务不能替代真正的常在线服务器。拥有 Cloudflare 域名后，再改成固定主机名的命名隧道。

## 验证

```powershell
uv run pytest -q
node --check web/app.js
```
