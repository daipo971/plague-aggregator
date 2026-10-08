# 部署说明：从零上线

## 一、准备工作

1. 在 GitHub 新建一个**公开**仓库（Actions 定时任务在公开仓库免费且不限时），
   例如 `plague-aggregator`。
2. 把本项目所有文件上传到仓库根目录（保留目录结构）。

## 二、配置 API Key（GitHub Secrets）

1. 打开仓库页面 → **Settings** → **Secrets and variables** → **Actions**。
2. 点 **New repository secret**，Name 填 `AI_API_KEY`，
   Secret 填你的模型 API Key（DeepSeek / OpenAI / 通义等均可）。
3. Key 只存在 GitHub 的加密存储里，代码和日志里都不会出现明文。

> 不想花钱调 AI？把 `config.yaml` 里 `ai.enabled` 改为 `false`，
> 网站会用原文标题+摘要直接展示，照样能跑。

## 二之二、可选：配置 X（推特）信源

社交平台的未证实与争议说法栏目需要 X 的搜索 API，这是付费服务（免费套餐一般不提供搜索，价格以 X 官网为准）。
1. 在 X 开发者平台申请付费套餐，拿到 **Bearer Token**。
2. 在仓库 Settings → Secrets and variables → Actions 里新增 Secret，Name 填 `X_BEARER_TOKEN`。
3. 没有配置时，相关栏目会是空的，其他信源不受影响。

## 三、开启 GitHub Pages

1. **Settings** → **Pages**。
2. **Build and deployment** → Source 选 **Deploy from a branch**。
3. Branch 选 `main`，目录选 `/docs`，点 **Save**。
4. 等 1～2 分钟，页面会显示你的网址：`https://你的用户名.github.io/仓库名/`。
5. 把 `config.yaml` 里的 `base_url` 改成这个网址（影响 RSS 里的链接），
   提交后等下一次定时任务（或手动触发一次）即生效。

## 四、手动触发第一次更新

1. 打开仓库 **Actions** → 左侧选 **更新疫情聚合**。
2. 点 **Run workflow** → **Run workflow**，等 2～3 分钟。
3. 成功后 `docs/index.html` 和 `docs/feed.xml` 会自动提交，
   刷新你的 Pages 网址就能看到页面。

## 五、绑定 Cloudflare 域名（可选）

1. Cloudflare → 你的域名 → **DNS** → 添加记录：
   - 类型 `CNAME`，名称填你想要的前缀（如 `plague`），
     目标填 `你的用户名.github.io`，代理状态按需开启。
2. 回到 GitHub 仓库 **Settings** → **Pages** → **Custom domain**，
   填 `plague.你的域名`，点 **Save**，等待证书签发（约 10～30 分钟，
   勾选 **Enforce HTTPS**）。
3. 把 `config.yaml` 的 `base_url` 改为 `https://plague.你的域名` 并提交。

## 六、日常维护

- 增删信源：改 `sources.yaml`，提交即生效（下次定时任务自动用新配置）。
- 换模型：改 `config.yaml` 的 `ai.provider` 和对应参数。
- 看运行日志：**Actions** → 点某次运行 → 看每一步的输出。
- 某个源长期抓取失败：日志里会有 `抓取信源 [xxx] 失败`，换个 RSS 地址即可。
- 费用控制：`config.yaml` 里 `ai.max_per_run` 限制每轮 AI 调用条数，
  处理过的链接会缓存，不重复花钱。

## 七、安全提醒

- 不要把 API Key 写进任何文件、不要截图发出来。
- 定期在模型商后台轮换 Key，GitHub Secrets 里更新即可。
- 本站只聚合公开信息、不转载全文；页面底部有免责声明，
  不要删除顶部的医疗提示横幅。
