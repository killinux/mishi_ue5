# 蜜室 Mishi — Unreal Engine 5 版

Unity 版（`E:\code\othercode\mishi`，GitHub killinux/mishi）的 UE5 移植。Unity 端把一个场景（体位 × 房间）导出成
FBX + JSON 的"切片"，UE 端的 Python 脚本把切片导入成资产和关卡，C++ 模块负责游戏逻辑。

**只提交代码。** `Import/`（游戏导出物）、`Content/`（导入后的资产）、`out/`（录像）都不进 git，仅供个人使用。

## 目录

| 路径 | 内容 |
|---|---|
| `Source/MishiUE/` | C++ 游戏模块（见下表） |
| `Tools/import_slice.py` | 编辑器内运行：贴图 / 音频 / 两具身体 + 动画 / 房间网格 / 材质 / 关卡，全部自动 |
| `Tools/ue.ps1` | 一键：找引擎、编译、导入、运行、录巡游视频 |
| `Config/` | Lumen + 虚拟阴影、无烘焙光照、固定曝光；默认地图 + GameMode；关掉 Interchange 用传统 FBX 导入 |
| `Import/<场景>_<房间>/` | Unity 导出的切片（不提交） |

| C++ 类 | 作用 |
|---|---|
| `AMishiCouple` | 一对角色：部位（part）状态机 = 游戏 Animator 的规则（触发器、阶段条件、`next` / `exit_time`），自动模式计时，语音、BGM、旁白字幕，形态键轨道 |
| `UMishiAnimInstance` | 不用动画蓝图的双槽播放器：当前片段 + 渐出片段，在 proxy 的 `Evaluate` 里混合 |
| `AMishiCameraPawn` | 游戏 Cinemachine 自由视角的复刻：三条轨道（下 / 中 / 上）、偏航、缩放、目标在盒内平移 |
| `AMishiPlayerController` | 鼠标键盘 + Slate 面板；`-MishiTour` 巡游录帧 |
| `SMishiHud` | 面板：阶段 1-4、自动、语音（日 / 英 / 关）、男性显示、镜头预设（全景 / 正面 / 侧面 / 俯视 / 特写 / 复位）、旁白 |
| `FMishiSlice` | 读 slice.json |

## 前提

- **Unreal Engine 5.x**：Epic 启动器 → 虚幻引擎 → 库 → 引擎版本旁的 **+** → 选版本 → 安装，位置
  `D:\Program Files\Epic Games`。安装选项里可以去掉"入门内容 / 模板和功能包 / 引擎源代码 / 调试用编辑器符号 /
  Android、iOS、Linux 等目标平台"，下载量小很多。
- **VS 2022 Build Tools**（编 C++ 用）：已装在 `D:\VS\BuildTools`（MSVC 14.44 + Windows 11 SDK 22621）。
- ffmpeg：`D:\Program Files\ffmpeg\bin\ffmpeg.exe`（OGG 转 WAV、帧序列转 mp4）。

## 流程

```powershell
# 1) Unity 端导出切片（在 mishi 仓库里；角色和房间分两次跑，FBX SDK 在一次运行里建第三个管理器时崩过）
cd E:\code\othercode\mishi
.\tools\unity_batch.ps1 -Method Mishi.EditorTools.MishiUeExport.ExportSlice -Name ue_actors -Graphics `
    -Extra '-mishiPosture','suit_Ines_posture_15','-mishiRoom','07','-mishiOut','E:\code\othercode\mishi_ue5\Import','-mishiWhat','actors'
.\tools\unity_batch.ps1 -Method Mishi.EditorTools.MishiUeExport.ExportSlice -Name ue_room -Graphics `
    -Extra '-mishiPosture','suit_Ines_posture_15','-mishiRoom','07','-mishiOut','E:\code\othercode\mishi_ue5\Import','-mishiWhat','room'

# 2) UE 端
cd E:\code\othercode\mishi_ue5
powershell -File Tools\ue.ps1 find      # 找到的引擎版本写进 MishiUE.uproject
powershell -File Tools\ue.ps1 build     # 编 MishiUEEditor
powershell -File Tools\ue.ps1 import    # 导入 eros15_07（-Force 全部重导）；报告在 Import\eros15_07\ue_import_report.json
powershell -File Tools\ue.ps1 play      # 窗口运行
powershell -File Tools\ue.ps1 tour      # 巡游录像 -> out\eros15_07_tour.mp4（带房间 BGM）
```

## 切片里有什么（`Import/<场景>_<房间>/`）

| 文件 | 内容 |
|---|---|
| `female.fbx` / `male.fbx` | 游戏自己的裸身模型（根 = 游戏 avatar 根 `pc_a01_nk` / `pc_a00_nk`），形态键，每个部位的片段是一个 take |
| `room_meshes.fbx` | 房间里每个不同的网格一次（节点 `RM_*`，在原点） |
| `room_instances.json` | 每处摆放：世界变换、网格节点、材质 |
| `room.fbx` | 整个房间（世界坐标），只用来检查坐标换算 |
| `materials.json` | 每个材质：类型（skin / eye / hair / lash / cloth / liquid / room）、shader、贴图（按属性）、颜色、数值 |
| `slice.json` | 部位、阶段规则、镜头、形态键轨道、语音、旁白、灯光、后期、两个角色根的偏移 |
| `textures/`、`audio/` | 贴图 PNG、语音和 BGM（OGG） |

## 坐标换算

Unity（米，左手系，Y 上，Z 前）经 Unity FBX Exporter（x 取反、厘米、Y 上）再经 UE 的 FBX 导入（Y 上转 Z 上并翻回 Y），
一个 Unity 点落在 UE 的 `(-x, z, y) × 100`：Unity 的前 +Z → UE 的 +Y（导入的角色朝 +Y），右 +X → -X。这是一个真旋转
（行列式 +1），所以四元数的向量部分同样换算、角度不变。`MishiUE.h` 的 `MishiSpace` 和 `import_slice.py` 的 `ue_*` 用的都是它；
每次导入都会把按 `room_instances.json` 摆好的房间和整体导入的 `room.fbx` 比包围盒（报告里的 `space_check`），换算错了这里会报。

## 材质

母材质在 `/Game/Mishi/Materials`（第一次导入时生成），每个 Unity 材质一个实例：

| 母材质 | 用于 | 要点 |
|---|---|---|
| `M_Mishi_Skin` | ROE/Skin | Subsurface Profile；MGAC：R 金属 G 光泽 B AO |
| `M_Mishi_Eye` | ROE/Eye | Clear Coat（眼睛的高光） |
| `M_Mishi_Hair` | ROE/Hair | Masked 双面，阈值 = Unity 的 `_Cutoff` |
| `M_Mishi_Masked` | 眉毛、alpha clip | 同上 |
| `M_Mishi_Translucent` | 透明（玻璃、泪） | Surface Forward Shading |
| `M_Mishi_Lit` | 房间（ROE/Environment）等 | MGA + 自发光贴图 |
| `M_Mishi_Unlit` | URP Unlit（他的剪影身体） | |
| `M_Mishi_Hidden` | 粒子、液体 | Effect 层还没移植 |

法线贴图：Unity 是 OpenGL 风格（绿色向上），导入时翻转绿色通道。遮罩贴图用 TC_Masks（线性）。

## 灯光

房间的灯全部改成实时灯（Lumen 全局光照 + 虚拟阴影贴图，项目里关掉了静态光照）。URP 的灯光强度 × π = UE 的
lux（平行光）/ candela（点光、聚光、面光）：URP 的漫反射没有 1/π，UE 有。再加一个实时捕获的天光、一个无界后期体积
（手动曝光、bloom 用房间自己的数值）。

## 操作

| 输入 | 作用 |
|---|---|
| 左键拖动 | 转镜头（左右偏航，上下改轨道高度） |
| 右键拖动 | 平移目标（限制在游戏允许的盒子里） |
| 滚轮 / Q E / PageUp PageDown | 缩放 |
| A D / ← → | 偏航；W S / ↑ ↓ 轨道高度 |
| 中键 / Home | 镜头复位 |
| 1 2 3 4 | 阶段 1-4（和游戏一样：先走过渡部位） |
| 空格 | 自动开 / 关 |
| V | 语音：日 → 英 → 关 |
| M | 男性显示 / 隐藏 |
| H | 面板显示 / 隐藏 |

## 还没做

- Effect 层（液体贴花、粒子）、潮红 / 出汗、回忆模式、换身体（Fiona / Tifa / Eve 等）、多场景选择菜单
- 镜头避墙
- 打包（Cook）：中文字体在打包版里需要带一个 CJK 字体
