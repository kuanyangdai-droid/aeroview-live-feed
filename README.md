# AeroView Hangzhou Special Livery Schedule

本仓库生成一个公开 JSON feed，用来展示 **杭州萧山机场 HGH 当日进出港计划航班里的特殊涂装飞机**。

后端通过 GitHub Actions 调用 AirLabs Schedules API，读取杭州到港和离港计划窗口。脚本只保留 API 已经给出具体飞机注册号的计划航班，再用注册号与 `special_liveries.json` 特殊涂装库匹配。GoDaddy 页面只读取 GitHub Pages 上的静态 JSON，不直接访问 AirLabs，也不会暴露 AirLabs API Key。

## 当前逻辑

- 只追踪一个机场：`HGH`，杭州萧山。
- 只看当天计划航班：到达杭州或从杭州离场。
- 只匹配有注册号的计划记录：例如 `B-5497`。
- 用 `special_liveries.json` 判断是否属于特殊涂装。
- 前端以列表显示，并支持方向、国家、航司、涂装类型、起飞地、到达地筛选。

## 重要限制

AirLabs 计划表接口并不保证每一条计划航班都会返回注册号。没有注册号的计划无法和特殊涂装库对比，所以会被跳过。

AirLabs schedules endpoint 是计划窗口，不是一次返回全天完整计划。脚本会合并同一天上一版 feed 的结果，把当天已经发现过的好货累计保留。第二天会按新的 `schedule_date` 重新开始，不会保留前一天记录。

## 文件结构

| 文件 | 用途 |
|---|---|
| `generate_feed.py` | 后端生成脚本；读取 HGH 当日计划，匹配特殊涂装注册号，输出 JSON。 |
| `special_liveries.json` | 特殊涂装飞机注册号库。 |
| `.github/workflows/update-feed.yml` | GitHub Actions workflow；每天生成 feed 并提交到仓库根目录。 |
| `aeroview_godaddy_json_reader.html` | 粘贴到 GoDaddy Custom HTML 的前端组件。 |
| `scripts/trigger_update_feed.sh` | 本机外部定时器调用的 workflow_dispatch 脚本。 |
| `launchd/com.aeroview.live-feed-dispatcher.plist` | macOS LaunchAgent 模板，北京时间每天 08:00 触发一次 workflow。 |

## GitHub Pages 地址

```text
https://kuanyangdai-droid.github.io/aeroview-live-feed/
```

Feed 地址：

```text
https://kuanyangdai-droid.github.io/aeroview-live-feed/special-livery-live.json
https://kuanyangdai-droid.github.io/aeroview-live-feed/feed-meta.json
```

## Workflow

`.github/workflows/update-feed.yml` 每次运行只生成杭州计划 feed：

```yaml
TRACK_AIRPORT: "HGH"
OUTPUT_PATH: "public/special-livery-live.json"
META_PATH: "public/feed-meta.json"
```

GitHub 自带 `schedule` 仍保留为每天 00:00 UTC，也就是北京时间 08:00。外部定时器同样设置为北京时间每天 08:00 通过 `workflow_dispatch` 触发一次，避免高频刷新消耗 AirLabs API 额度。

为了减少 GitHub Pages 官方部署 action 下载失败的影响，当前发布方式是让 workflow 直接更新并提交仓库根目录的 `special-livery-live.json` 和 `feed-meta.json`，GitHub Pages 从 `main` 分支根目录提供静态文件。

## GoDaddy 使用

把 `aeroview_godaddy_json_reader.html` 的完整内容粘贴到 GoDaddy 的 **Custom HTML / 自定义 HTML** 模块中。

HTML 已经配置好本仓库的 feed 地址：

```javascript
FEED_URL: "https://kuanyangdai-droid.github.io/aeroview-live-feed/special-livery-live.json",
META_URL: "https://kuanyangdai-droid.github.io/aeroview-live-feed/feed-meta.json"
```

## 维护特殊涂装库

`special_liveries.json` 是一个数组，每条记录至少应包含 `registration` 与 `livery`。当前库已整理为中国大陆、港澳台相关航司特殊涂装为主，主要来源为 Spotterlog Special Liveries，并保留原库中未覆盖的条目。示例：

```json
{
  "registration": "B-5497",
  "airline": "Air China",
  "aircraft": "Boeing B737-800",
  "livery": "Expo 2019 Beijing",
  "country": "China",
  "source": "Spotterlog Special Liveries"
}
```

新增特殊涂装飞机时，把注册号加入这个文件即可。脚本会自动用注册号匹配杭州当日计划航班。

## 本地测试

演示模式：

```bash
DEMO_MODE=true python generate_feed.py
```

真实调用：

```bash
AIRLABS_API_KEY="你的Key" TRACK_AIRPORT=HGH python generate_feed.py
```

指定日期：

```bash
AIRLABS_API_KEY="你的Key" TRACK_AIRPORT=HGH SCHEDULE_DATE=2026-05-26 python generate_feed.py
```

## 上线检查

| 检查项 | 正常表现 |
|---|---|
| GitHub Actions | `Update AeroView Hangzhou Schedule Feed` 运行成功。 |
| Feed | `special-livery-live.json` 和 `feed-meta.json` 可打开。 |
| GoDaddy 模块 | 显示杭州当日匹配列表，并可按方向、航司、涂装、起飞地、到达地筛选。 |
| 外部定时器 | `~/Library/Logs/AeroView/dispatch.out.log` 能看到每天 08:00 的 workflow_dispatch 记录。 |
