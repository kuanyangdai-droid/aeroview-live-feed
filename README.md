# AeroView Special Livery Live Feed

本仓库用于生成 **AeroView Special Livery Live Radar** 的后端公开 JSON。它通过 GitHub Actions 定时调用 AirLabs Real-Time Flights API，查询上海、北京、深圳、广州、杭州、成都、大连相关机场的当前在飞航班，再用飞机注册号与 `special_liveries.json` 中的特殊涂装库匹配，最后把结果发布为 GitHub Pages 上的静态 JSON。

GoDaddy 网站不再直接访问 AirLabs，也不需要保存 AirLabs API Key。GoDaddy 自定义 HTML 模块只读取 GitHub Pages 上的 `special-livery-live.json`，因此更适合长期公开运行。

## 文件结构

| 文件 | 用途 |
|---|---|
| `generate_feed.py` | 后端生成脚本；读取 AirLabs 实时航班，匹配特殊涂装注册号，输出 JSON。 |
| `special_liveries.json` | 特殊涂装飞机注册号库，可手动增删维护。 |
| `.github/workflows/update-feed.yml` | GitHub Actions 定时任务，每 10 分钟生成并发布一次 GitHub Pages。 |
| `public/special-livery-live.json` | 前端读取的实时匹配结果，GitHub Actions 会自动更新。 |
| `public/feed-meta.json` | 生成时间、机场范围、匹配数量、错误提示等元信息。 |
| `godaddy/aeroview_godaddy_json_reader.html` | 粘贴到 GoDaddy Custom HTML 的前端滚动播报模块。 |

## 第一步：创建 GitHub 仓库

新建一个 GitHub 仓库，例如：

```text
aeroview-live-feed
```

把本目录内所有文件上传到仓库根目录。请注意，`.github/workflows/update-feed.yml` 必须保留在这个路径下，不能改成其他目录。

## 第二步：添加 AirLabs API Key

进入 GitHub 仓库的以下位置：

```text
Settings → Secrets and variables → Actions → New repository secret
```

添加一个 Secret：

| Name | Value |
|---|---|
| `AIRLABS_API_KEY` | 你的 AirLabs API Key |

脚本会从 GitHub Secrets 中读取这个值，GoDaddy 页面不会看到这个 Key。

## 第三步：启用 GitHub Pages

进入仓库：

```text
Settings → Pages
```

在 **Build and deployment** 里选择：

| 选项 | 设置 |
|---|---|
| Source | GitHub Actions |

保存后，进入 **Actions** 页面，手动运行一次 `Update AeroView Special Livery Live Feed`。运行成功后，GitHub Pages 会生成公开地址。

假设你的用户名是 `yourname`，仓库名是 `aeroview-live-feed`，则 JSON 地址通常是：

```text
https://yourname.github.io/aeroview-live-feed/special-livery-live.json
```

元信息地址通常是：

```text
https://yourname.github.io/aeroview-live-feed/feed-meta.json
```

## 第四步：配置 GoDaddy HTML

打开：

```text
godaddy/aeroview_godaddy_json_reader.html
```

找到配置区：

```javascript
const CONFIG = {
  FEED_URL: "https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/special-livery-live.json",
  META_URL: "https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/feed-meta.json",
  REFRESH_MINUTES: 5,
  TIME_ZONE: "Asia/Shanghai"
};
```

把 `FEED_URL` 和 `META_URL` 改成你的真实 GitHub Pages 地址，然后把整个 HTML 文件内容复制到 GoDaddy 的 **Custom HTML / 自定义 HTML** 模块中。

## 默认机场范围

默认目标机场覆盖你提出的城市范围。

| 城市 | 机场 | IATA |
|---|---|---|
| 上海 | 浦东、虹桥 | PVG、SHA |
| 北京 | 首都、大兴 | PEK、PKX |
| 深圳 | 宝安 | SZX |
| 广州 | 白云 | CAN |
| 杭州 | 萧山 | HGH |
| 成都 | 双流、天府 | CTU、TFU |
| 大连 | 周水子 | DLC |

如需修改机场范围，可编辑 `.github/workflows/update-feed.yml` 中的：

```yaml
TARGET_AIRPORTS: "PVG,SHA,PEK,PKX,SZX,CAN,HGH,CTU,TFU,DLC"
```

## 维护特殊涂装库

`special_liveries.json` 是一个数组，每条记录至少应包含 `registration` 与 `livery`。推荐格式如下：

```json
{
  "registration": "B-2006",
  "airline": "Air China",
  "aircraft": "Boeing 777-300ER",
  "livery": "Love China",
  "country": "China",
  "source": "AirportWebcams Special Liveries"
}
```

如果你发现某架特殊涂装飞机未被收录，只需要把注册号加到这个文件中即可。脚本会自动用注册号匹配 AirLabs 返回的实时航班。

## 重要限制

这个方案只播报 **当前在飞且 AirLabs 返回注册号** 的航班。它不是完整的“当日计划”。如果某架特殊涂装飞机还未起飞、已经落地、没有被实时追踪，或 API 没有返回 `reg_number`，它不会出现在 JSON 中。

GitHub Actions 的定时任务并不保证精确到秒，实际运行可能因 GitHub 队列而略有延迟。对网页展示而言，5 至 10 分钟刷新一次通常已经足够。

## 本地测试

如果你想在上传前验证脚本是否能运行，可以执行：

```bash
DEMO_MODE=true python generate_feed.py
```

这会在 `public/` 目录生成演示 JSON，不会调用 AirLabs。若要真实调用 AirLabs，请执行：

```bash
AIRLABS_API_KEY="你的Key" python generate_feed.py
```

## 推荐上线检查

上线后，请依次检查：

| 检查项 | 正常表现 |
|---|---|
| GitHub Actions | `Update AeroView Special Livery Live Feed` 运行成功。 |
| GitHub Pages | `special-livery-live.json` 可以直接在浏览器打开。 |
| GoDaddy 模块 | 显示加载成功、无匹配、或实时匹配结果，而不是 URL 配置错误。 |
| API 用量 | AirLabs 后台请求量与 GitHub Actions 频率一致，不会因访客量增加而倍增。 |
