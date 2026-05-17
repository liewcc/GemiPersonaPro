# 🔔 Notifier & Monitor Guide

## 宗旨与设计理念
GemiPersonaPro 的 **Notifier (系统托盘通知器)** 和 **Monitor (性能监控面板)** 都是独立于主程序（Streamlit Web UI）运行的轻量化桌面端工具。

它们的主要**功能与宗旨**在于：
当您不需要开启笨重的浏览器页面，或正在本地电脑进行其他工作（如文档编辑、游戏、剪辑）时，这些工具可以静默运行在后台，并在无需切换窗口的情况下，随时让您掌握底层自动化引擎（Engine）和 4K Upscaler 的实时进度与健康状态。

它们具有极低的系统资源占用，即使关闭了 GemiPersonaPro 的浏览器 UI，只要引擎还在运行，它们就能继续为您提供无缝的监控体验。

---

## 1. Background Image Notifier (后台托盘通知器)
`image_notifier.py` / `start_notifier.vbs` 是一个运行在 Windows 系统托盘的静默独立程序。

### 核心功能
- **独立运行生命周期**：它独立于 Streamlit 进程，这意味着您可以放心地关闭浏览器界面，而通知器将继续坚守岗位。
- **双目录智能侦测**：它同时监控您的**自动化保存目录 (Automation Save Directory)** 与 **4K 放大输出目录 (Upscaler Output Directory)**，只要有新图片生成，就会在右下角弹出无边框通知。
- **动态状态跟踪**：
  - 通知 UI 使用大号字体并排显示 "Auto" 和 "Upscaler" 的未确认统计数量。
  - **红字高亮**：通知器会追踪您自上次手动确认以来，累计生成了多少张 "未看" 的图片。
  - 如果某个管道（如 Upscaler）未运行，对应的文字将智能置灰，让您一眼辨识当前的系统活跃状态。

### 快捷交互面板
当通知弹出时，您可以直接进行快捷操作：
- **📁 Download / Upscale Folder**：一键直达对应存放图片的 Windows 资源管理器目录。
- **📊 Monitor**：一键唤醒独立的 `Monitor` 监控面板，查看详细报表。
- **Open GemiPersona**：一键启动系统。如果检测到主引擎尚未运行，点击此按钮可直接唤醒 `run.bat`；若系统已在运行，该按钮会自动禁用以防止重复启动进程。

### 如何控制
- **开启**：在 Dashboard 页面左下角点击 **Start Notifier** 按钮即可启动。
- **关闭**：在右下角系统托盘找到蓝色的 `GemiPersona Notifier` 图标，右键选择 **"Quit"**。安全退出时，它会自动帮您关闭所有联动的通知弹窗和 Monitor 面板。

---

## 2. GemiPersona Monitor (桌面级性能监控面板)
`monitor_window.py` 是一个基于 Tkinter 打造的轻量级透明数据面板，它与 Notifier 联动，为您提供媲美 Dashboard 网页版的极客数据看板，但却不占用任何浏览器资源。

### 核心功能
- **零负担的 CPU 优化 (Smart Polling)**：
  - Monitor 不会盲目占用系统性能，它利用增量日志解析技术，在系统空闲时 CPU 占用近乎为 **0%**。
  - 数据呈现上，它直接与底层的轻量化 API (`/browser/automation/stats`) 和 `reject_stat_log.json` 对齐，确保这里显示的数字和主 Dashboard **完全一模一样**。

### 丰富的数据洞察
- **全局统计 (Top Row)**：
  - **Total Cycles**：当前底层引擎历经的自动化循环次数。
  - **Images / Refused / Reset**：汇总整个自动化历史中下载的图片总数、Gemini 拒绝服务的总次数以及引擎浏览器崩溃重启的总次数。
- **当前账号健康状态 (Second Row)**：
  - 实时显示当前正在被调度使用的账号（剥离了长邮箱后缀的短名）。
  - 显示该账号的**切入时间 (Switch At)**，以及它在本次会话中贡献的图片数量和遭遇的阻力（Refused / Reset）。
- **Cycle Performance Insights 图表**：
  - 将庞杂的日志转化为可视化的柱状图。
  - **By Account 图表**：按账号交替颜色（深浅绿色）展示每个 Session 下载的图片产能。零产出的 Session 被智能剔除以保持界面整洁。
  - 支持交互式的 **Tooltip (鼠标悬浮提示)**：当鼠标靠近某个柱形图时，图表右下角会优雅地浮现该柱形代表的账号名和准确数字，既直观又绝不会弹出越界导致程序闪烁。

有了 Notifier 与 Monitor 的配合，GemiPersonaPro 真正实现了从浏览器束缚中解脱的“全自动后台生产黑盒”。
