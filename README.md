# AeroView Special Livery Live Feed

本仓库用于生成 **AeroView Special Livery Live Radar** 的公开 JSON feed，并提供可粘贴到 GoDaddy Custom HTML 的前端组件。

后端通过 GitHub Actions 调用 AirLabs Real-Time Flights API，查询目标机场的实时航班，再用飞机注册号与 `special_liveries.json` 特殊涂装库匹配。GoDaddy 页面只读取 GitHub Pages 上的静态 JSON，不直接访问 AirLabs，也不会暴露 AirLabs API Key。

## 当前版本

现在会生成两个 feed：

| Feed | 用途 | JSON |
|---|---|---|
| Global major airports | 覆盖亚洲、美洲、欧洲主要大型机场的特殊涂装追踪 | `special-livery-live.json` |
| China all-airport special livery | 保留中国机场范围内的特殊涂装追踪版本 | `china-special-livery-live.json` |

对应元信息：

| Feed | Meta |
|---|---|
| Global major airports | `feed-meta.json` |
| China all-airport special livery | `china-feed-meta.json` |

当前前端支持：

- Global / China feed 切换
- 状态筛选：全部、在飞、今日已落地
- 涂装类别筛选：星空联盟、天合联盟、寰宇一家、其他类型
- 起飞地筛选：国家 → 机场
- 将落地筛选：国家 → 机场
- 世界地图航线绘制：只绘制当前筛选结果中仍在飞的航班
- 今日累计保留：当天出现过的特殊涂装如果后续从 live tracking 消失，会保留为 `landed`，北京时间次日自动清除

## API 说明

世界范围版本不需要更换 API。它仍然使用同一个 AirLabs endpoint：

```text
https://airlabs.co/api/v9/flights
```

变化的是查询机场集合：

- 以前 workflow 只传入少量中国重点机场。
- 现在 `generate_feed.py` 内置两个机场 profile：
  - `global_major`
  - `china_all`
- GitHub Actions 每次运行会分别用这两个 profile 调用同一个 AirLabs API，并输出两个 JSON。

这意味着 AirLabs API Key、认证方式、字段解析逻辑都没有换。需要注意的是，机场数量增加后 API 请求量也会增加，因为脚本会对每个机场分别查询 `dep_iata` 和 `arr_iata`。

## 文件结构

| 文件 | 用途 |
|---|---|
| `generate_feed.py` | 后端生成脚本；读取 AirLabs 实时航班，匹配特殊涂装注册号，输出 JSON。 |
| `special_liveries.json` | 特殊涂装飞机注册号库。 |
| `.github/workflows/update-feed.yml` | GitHub Actions workflow；生成并发布两个 feed。 |
| `aeroview_godaddy_json_reader.html` | 粘贴到 GoDaddy Custom HTML 的前端组件。 |
| `scripts/trigger_update_feed.sh` | 本机外部定时器调用的 workflow_dispatch 脚本。 |
| `launchd/com.aeroview.live-feed-dispatcher.plist` | macOS LaunchAgent 模板，每 10 分钟触发一次 workflow。 |
| `logs/.gitignore` | 本地日志目录占位，实际日志不提交。 |

## GitHub Pages 地址

本仓库当前 Pages 地址格式：

```text
https://kuanyangdai-droid.github.io/aeroview-live-feed/
```

Feed 地址：

```text
https://kuanyangdai-droid.github.io/aeroview-live-feed/special-livery-live.json
https://kuanyangdai-droid.github.io/aeroview-live-feed/feed-meta.json

https://kuanyangdai-droid.github.io/aeroview-live-feed/china-special-livery-live.json
https://kuanyangdai-droid.github.io/aeroview-live-feed/china-feed-meta.json
```

## 机场范围

### Global major airports

覆盖亚、美、欧主要大型机场，包括但不限于：

- 北美：ATL、LAX、JFK、EWR、ORD、DFW、DEN、SFO、SEA、MIA、IAH、YYZ
- 欧洲：LHR、CDG、AMS、FRA、IST、MAD、BCN、MUC、ZRH、FCO、VIE、CPH、DUB
- 亚洲 / 中东：DXB、DOH、AUH、DEL、BOM、SIN、HKG、ICN、NRT、HND、BKK、KUL、TPE
- 中国核心枢纽：PVG、SHA、PEK、PKX、CAN、SZX、HGH、CTU、TFU

### China all-airport special livery

覆盖中国大陆主要民航机场，并包含港澳台相关机场：HKG、MFM、TPE、TSA。

完整列表以 `generate_feed.py` 中的 `CHINA_ALL_AIRPORTS` 为准。

## Workflow

`.github/workflows/update-feed.yml` 中会连续生成两个 feed：

```yaml
TARGET_AIRPORT_PROFILE: "global_major"
OUTPUT_PATH: "public/special-livery-live.json"
META_PATH: "public/feed-meta.json"
```

```yaml
TARGET_AIRPORT_PROFILE: "china_all"
OUTPUT_PATH: "public/china-special-livery-live.json"
META_PATH: "public/china-feed-meta.json"
```

GitHub 自带 `schedule` 仍保留，但由于 GitHub scheduled workflow 可能延迟或丢弃，本仓库还配置了本机 macOS LaunchAgent 外部定时器，通过 `workflow_dispatch` 每 10 分钟触发一次。

## GoDaddy 使用

把 `aeroview_godaddy_json_reader.html` 的完整内容粘贴到 GoDaddy 的 **Custom HTML / 自定义 HTML** 模块中。

当前 HTML 已经配置好本仓库的两个 feed 地址：

```javascript
FEEDS: {
  global: {
    feedUrl: "https://kuanyangdai-droid.github.io/aeroview-live-feed/special-livery-live.json",
    metaUrl: "https://kuanyangdai-droid.github.io/aeroview-live-feed/feed-meta.json"
  },
  china: {
    feedUrl: "https://kuanyangdai-droid.github.io/aeroview-live-feed/china-special-livery-live.json",
    metaUrl: "https://kuanyangdai-droid.github.io/aeroview-live-feed/china-feed-meta.json"
  }
}
```

## 维护特殊涂装库

`special_liveries.json` 是一个数组，每条记录至少应包含 `registration` 与 `livery`。示例：

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

新增特殊涂装飞机时，把注册号加入这个文件即可。脚本会自动用注册号匹配 AirLabs 返回的实时航班。

## 重要限制

- 只会显示 AirLabs 实时接口返回且带有注册号的航班。
- 机场范围扩大后，AirLabs API 请求量会明显高于早期中国重点机场版本。
- 今日累计保留依赖上一版 GitHub Pages JSON；如果读取上一版失败，脚本会拒绝发布可能缩水的新 feed。
- `landed` 记录按北京时间日期清理，次日自动移除。
- 世界地图为轻量 SVG 示意图，不是精确 GIS 地图。

## 本地测试

演示模式：

```bash
DEMO_MODE=true python generate_feed.py
```

真实调用全球主要机场 profile：

```bash
AIRLABS_API_KEY="你的Key" TARGET_AIRPORT_PROFILE=global_major python generate_feed.py
```

真实调用中国机场 profile：

```bash
AIRLABS_API_KEY="你的Key" TARGET_AIRPORT_PROFILE=china_all OUTPUT_PATH=public/china-special-livery-live.json META_PATH=public/china-feed-meta.json python generate_feed.py
```

## 上线检查

| 检查项 | 正常表现 |
|---|---|
| GitHub Actions | `Update AeroView Special Livery Live Feed` 运行成功。 |
| Global feed | `special-livery-live.json` 和 `feed-meta.json` 可打开。 |
| China feed | `china-special-livery-live.json` 和 `china-feed-meta.json` 可打开。 |
| GoDaddy 模块 | 可切换 Coverage，并可按状态、涂装类别、起飞地、将落地筛选。 |
| 外部定时器 | `~/Library/Logs/AeroView/dispatch.out.log` 能看到定期 workflow_dispatch 记录。 |
