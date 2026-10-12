<div align="center">
  <img src="assets/xixi-avatar.png" width="112" alt="西西">
  <h1>西西的声骸评分工具</h1>
  <p><b>托盘常驻的鸣潮声骸截图评分桌面端——QQ 申请资格 × F9 选角色 × F10 单图 × F11 多图 × 自动更新内置国内镜像</b></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white&labelColor=2b2b2b" alt="Python">
    <img src="https://img.shields.io/badge/PySide6-6.x-41CD52?logo=qt&logoColor=white&labelColor=2b2b2b" alt="PySide6">
    <img src="https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows&logoColor=white&labelColor=2b2b2b" alt="Windows">
    <img src="https://img.shields.io/badge/截屏-DXcam%20DDA-3B82F6?labelColor=2b2b2b" alt="DXcam">
    <img src="https://img.shields.io/badge/资格-QQ群%201085339175-EA580C?labelColor=2b2b2b" alt="QQ群">
    <img src="https://img.shields.io/badge/自动更新-GitHub%20%2B%20国内镜像-EA580C?labelColor=2b2b2b" alt="自动更新">
  </p>
</div>

西西是你的声骸评分小帮手：首次启动填 QQ 号申请资格（审核通过自动发 token），之后按 `F10`
框一张声骸截图，她会用你选好的角色把图送到评分服务，几秒后评分卡直接弹回桌面。
截图**不在本机落盘**（另存为是唯一例外），UI 是她亲手画的暖玻璃风——橘色围巾色只出现在主按钮上。

> 💡 **申请 / 使用问题请加 QQ 群：1085339175** · 📖 **图文教程：[docs/usage-guide.png](docs/usage-guide.png)**

## ✨ 特性一览

### 🚀 核心功能

- ✅ **评分资格申请**（**1.0.0 起必须**）：客户端不内置任何密钥，首次启动强制弹出申请窗，填 QQ 号提交 → bot/WebUI 审核 → 通过后 token 自动保存并解锁全部功能；主页底部左侧实时显示审核状态，未申请前操作按钮置灰
- ✅ **全局热键**：默认 `F9` 切换角色 / `F10` 单次截图 / `F11` 多次截图，**设置页点击按键框按什么设什么**（支持 Ctrl/Alt/Shift/Win 任意组合，查重、Esc 取消、保存即热生效）
- ✅ **角色浮窗**：头像网格 + 实时搜索（带清空按钮），目录和头像由服务端下发；没有评分模板的角色自动置灰；**顶部把手可拖动窗口、图钉可置顶**
- ✅ **冻结快照框选**：先抓整屏快照再弹遮罩，**遮罩不会拍进图里**；per-monitor DPI 换算，多显示器按光标落点接管
- ✅ **独占全屏兼容**：DXcam（Desktop Duplication API）优先，全屏游戏不黑屏；驱动不支持时自动退化 mss/GDI
- ✅ **单次确认 / 多次汇总**：`F10` 框完确认再发；`F11` 连续框选进浮窗，一次多图提交直接出合并评分卡
- ✅ **结果窗（主页）**：评分卡整卡显示；**点击大图弹出原图查看器**——Windows 照片式缩放（滚轮以鼠标为锚点、可超 100%）、拖拽平移、双击切适应/1:1
- ✅ **最近 5 条**：内存保留随时回看；复制到剪贴板、另存为（唯一落盘路径，你主动触发）
- ✅ **失败可重试**：报错 toast 具体可行动；「重新评分」原样重发

### ⌨️ 快捷键

默认 `F9` 切换角色 / `F10` 单次截图 / `F11` 多次截图。设置页点击按键框后**按下想要的组合键**即可
（Ctrl/Alt/Shift/Win 皆可叠加），保存即热生效；被占用或重复会 toast 提示并自动还原。

### 🛠 自动更新

- ✅ **三通道版本检查**：`api.github.com` → `github.com` 302 → `jsDelivr` 源码解析，任一可用即可
- ✅ **多通道下载**：直连 + 4 个 ghproxy 系代理（gh-proxy.com / gh-proxy.org / ghfast.top / ghproxy.net），
  失败自动遍历；设置里可手动选择，**「测延迟」按钮逐通道实测并自动选最快**
- ✅ **静默安装 + 自动重启**：下载完成后自动静默安装并重启应用，无需手动点安装向导
- 启动与每 4 小时静默检查，有新版本才弹窗；托盘菜单「检测更新」手动触发，无更新也会弹窗确认

## 🔧 配置

服务端地址已在打包时内置（**不含任何密钥**），首次启动只需：

1. 填 QQ 号提交申请 → 等审核（主页底部左侧可见状态）；
2. 通过后 token 自动保存并解锁，无需任何手动配置。

> 🔒 从 1.0.0 起安装包不含凭据；旧版本请升级，否则静态凭据将被服务端拒绝。

设置页可调：**快捷键**（组合键捕获，保存即热生效）、**下载通道**（默认自动选最快，也可手动固定），
托盘 → 设置里可改。

## 📁 结构

```
xixi_echo/
  __main__.py   入口（python -m xixi_echo）
  run.py        PyInstaller 打包入口（绝对导入）
  app.py        主控制器：托盘/热键/流程串联 + 设置/申请弹窗 + 更新
  hotkey.py     user32.RegisterHotKey 全局热键（组合键解析，独立消息线程）
  overlay.py    冻结快照选区浮层（logical→physical 换算在这里）
  capture.py    DXcam → mss 截图
  charpicker.py F9 角色浮窗（头像缩放 + 内存缓存，顶部拖拽把手 + 置顶）
  pending.py    待发浮窗（单次确认 / 多次汇总，可拖动置顶）
  result.py     结果窗（主页）：整卡显示 + 原图缩放查看器 + 最近 5 条
  token_apply.py 评分资格申请弹窗（QQ → 审核 → 自动发 token）
  api.py        评分服务客户端（httpx multipart + 签名 + 分发 token）
  updater.py    自动更新（三通道检查 + 多通道下载 + 测延迟）
  signing.py    签名实现（与服务端实现互为镜像，改动必须同步）
  draggable.py  浮窗拖拽把手 + 置顶切换
  config.py     %APPDATA%/xixi-echo/config.json
  theme.py      西西设计令牌 → QSS
  widgets.py    XButton / KeyCaptureButton / Toast
```

## 🧳 安装与打包

```bash
pip install -r requirements.txt
python -m xixi_echo            # 开发运行

pip install pyinstaller
pyinstaller --noconsole --name xixi-echo \
  --add-data "assets;assets" \
  --icon assets/xixi-echo.ico \
  run.py                       # 入口必须是根目录 run.py（绝对导入），不能指到包内 __main__.py
```

发新版：**先改 `xixi_echo/__init__.py` 的 `__version__`**（与 tag 一致，CI 会校验）→ 打包 →
`gh release create vX.Y.Z xixi-echo-setup.exe`。

## ⚠️ 已知边界

- **需要管理员权限运行**：鸣潮是管理员权限启动的，Windows（UIPI）会拦截普通权限进程的全局热键——
  表现为游戏在前台时热键没反应。安装的 exe 自带提权清单，每次启动会有一次 UAC 确认。
- 截图取自遮罩弹出**前**的冻结快照，分数不受影响；热键在独占全屏下同样生效。
- 选区不能跨显示器（v1 按光标所在屏幕处理）
- 本仓库必须保持 **public**：release 资产匿名下载是自动更新的前提

## 💬 交流

- 申请 / 使用 / 审核问题，加 QQ 群：**1085339175**

## 🙏 鸣谢

- [Loping151/ScoreEcho](https://github.com/Loping151/ScoreEcho) —— 本工具的声骸识别与评分能力全部来自该项目（小维）提供的鸣潮声骸评分服务，去评分就上 [scoreecho.loping151.site](https://scoreecho.loping151.site/)
