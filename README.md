# 蜜室 Mishi — Unreal Engine 5 版

把《Rise of Eros》蜜室（eros mode）的一个场景在 UE5 里重做：游戏自己的模型、动作、声音和房间，
但灯光、材质、镜头按 UE5 的能力重新设计（Lumen 全局光照、虚拟阴影、次表面皮肤、真实镜头景深）。
Unity 版在 `E:\code\othercode\mishi`（GitHub killinux/mishi），它负责把一个场景（体位 × 房间）导出成"切片"。

**只提交代码。** `Import/`（游戏导出物）、`Content/`（导入后的资产）、`out/`、`Saved/` 都不进 git，仅供个人使用。

当前做完的切片：

- **Ines（伊娜丝）eros15 × 房间 07**（`eros15_07`）—— 蜜室的一个场景。
- **伊娜丝 a08 × 战斗舞台 s01**（`a08_s01`）—— 不是蜜室：金甲巨剑的 a08 站在城堡屋顶的战斗舞台上，
  按钮是她的战斗动作（按游戏的技能时间线复现），为的是把高清盔甲看清楚。见下面"展示切片"一节。

## 目录

| 路径 | 内容 |
|---|---|
| `Source/MishiUE/` | C++ 游戏模块（见下表） |
| `Tools/ue.ps1` | 一键：找引擎、编译、导入、运行、出检查图、录巡游片 |
| `Tools/ue_remote.py` | 在**开着的编辑器**里跑一个 Python 脚本（Python Remote Execution） |
| `Tools/import_slice.py` | 导入一个切片：贴图 / 音频 / 身体 + 动作 / 房间 / 材质 / 特效 / 关卡，可只跑其中几步 |
| `Tools/mishi_anim.py` | 动作：Unity 逐帧轨道 → AnimSequence |
| `Tools/mishi_materials.py` | 用代码生成母材质（皮肤 / 眼睛 / 头发 / 睫毛 / 泪 / 房间…）和每个游戏材质的实例 |
| `Tools/mishi_look.py` | 关卡：摆房间、灯光设计、天空、雾、后期；所有"观感"数字都在 `LOOK` 表里 |
| `Tools/shots_lookdev.json` / `tour.json` / `shots_stills.json` | eros15_07 的检查图机位表 / 巡游片分镜表 / 路径追踪定格图机位表 |
| `Tools/shots_<切片>.json` / `tour_<切片>.json` / `stills_<切片>.json` | 某个切片自己的三张表（有就用它，现在有 `a08_s01` 的） |
| `Tools/sheet.py` / `tour_audio.py` | 检查图拼版 / 巡游片的音轨合成 |
| `Tools/make_showcase.py` / `mishi_sky.py` | 展示切片：Unity 导出的原始数据 → `slice.json`（含骨骼布料的配置、特效索引）/ 把舞台的天空盒烘焙成一张经纬图 |
| `Tools/mishi_fx.py` | 技能特效的材质：游戏四个粒子着色器的母材质（代码生成）+ 每个游戏材质一个实例 |
| `Config/` | 硬件光追 Lumen + 虚拟阴影、路径追踪、无烘焙光照、手动曝光、TSR 100%、SM6；默认地图和 GameMode；传统 FBX 导入；动画默认 60 fps；Python 远程执行 |

| C++ 类 | 作用 |
|---|---|
| `AMishiCouple` | 一对角色（展示切片里只有她）：部位（part）状态机 = 游戏 Animator 的规则，自动模式，语音 / 部位音效循环 / BGM，旁白，形态键轨道，皮肤的潮红和出汗（随阶段推进），男性三种画法（皮肤 / 游戏的剪影 / 隐藏）；展示切片的**时间线提示**（cues：到某一秒放音效 / 语音 / 震镜头 / 单位冲刺 / 切技能镜头 / 放技能特效） |
| `UMishiAnimInstance` | 不用动画蓝图的双槽播放器：当前片段 + 渐出片段，在 proxy 的 `Evaluate` 里混合；混合完交给骨骼布料 |
| `FMishiSprings` | **骨骼布料**：头发、锁链、裙摆的骨骼链在动画姿势上做弹簧模拟（Magica Cloth 的 Bone Cloth 思路），在动画线程里跑 |
| `FMishiFx` | **技能特效回放**：读 Unity 逐帧烘焙的粒子几何，画进一个程序化网格（每批一个网格段），粒子自带的灯变成真的点光源 |
| `AMishiCameraPawn` | 游戏 Cinemachine 自由视角的复刻（三条轨道、偏航、缩放、目标盒内平移）+ 真实镜头景深（自动对焦到她的眼睛、近距离自动收光圈）+ 不穿墙 + 挡住角色的细物体淡出；展示切片：跟着她的胯走、震动、游戏的技能镜头、跟机补光 |
| `AMishiPlayerController` | 鼠标键盘、Slate 面板；`-MishiShots` 检查图 / `-MishiTour` 逐帧录片 |
| `SMishiHud` | 面板：切片有几个阶段就有几个按钮（蜜室是阶段 1-4，展示切片是带名字的动作）、自动、语音、男性画法、音效、潮红、技能镜头、物理、特效、镜头预设、旁白 |
| `FMishiSlice` | 读 slice.json |

## 前提

- **Unreal Engine 5.8**（Epic 启动器安装，`D:\Program Files\Epic Games\UE_5.8`）。
- **VS 2022 Build Tools**：`D:\VS\BuildTools`（MSVC 14.44、Windows 11 SDK 22621、**.NET Framework 4.8 SDK** —— 没有它 UBT 报 "Could not find NetFxSDK"）。
- ffmpeg：`D:\Program Files\ffmpeg\bin\ffmpeg.exe`；系统 Python 带 Pillow（拼版用；UE 自带的 Python 没有 numpy / Pillow）。
- 角色材质数据来自 ripper_tpose 的 HQ 材质缓存 `E:\game_export\RiseOfEros\_meta\_hq_materials`（游戏材质的全部贴图和数值）。

## 工作循环

编辑器一直开着（可以随时自己看），脚本通过远程 Python 在里面跑；出图另起一个 `-game` 进程，不占编辑器。

```powershell
cd E:\code\othercode\mishi_ue5
powershell -File Tools\ue.ps1 editor                       # 打开编辑器
python Tools\ue_remote.py Tools\import_slice.py eros15_07 materials level    # 在编辑器里重跑其中几步（全部步骤见下）
powershell -File Tools\ue.ps1 shots -Tag v9                # 检查图 -> Saved\MishiShots\eros15_07_v9\*.png
python Tools\sheet.py Saved\MishiShots\eros15_07_v9        # 拼成 _sheet.jpg
powershell -File Tools\ue.ps1 cpp                          # 改了 C++：存盘关编辑器 -> 编译 -> 重开编辑器
powershell -File Tools\ue.ps1 play                         # 窗口运行，自己操作
powershell -File Tools\ue.ps1 tour -ResX 1920 -ResY 1080   # 巡游片 -> out\eros15_07_tour.mp4（带语音、音效、BGM）；加 -KeepFrames 保留逐帧 BMP（约 16 GB）
powershell -File Tools\ue.ps1 stills                       # 路径追踪定格图 -> out\stills\eros15_07\*.png（2560×1440，每张约 2 分钟）
```

导入步骤：`textures audio bodies room materials level`（不写 = 全部；`--force` 重导）。改了 `mishi_look.py` 的 `LOOK`
只需 `level`，改了母材质（`mishi_materials.py` 的 `VERSION` 加一）只需 `materials level`。

从零开始：先在 Unity 端导出切片（角色和房间分两次跑 —— FBX SDK 在一次运行里建第三个管理器会崩）：

```powershell
cd E:\code\othercode\mishi
.\tools\unity_batch.ps1 -Method Mishi.EditorTools.MishiUeExport.ExportSlice -Name ue_actors -Graphics `
    -Extra '-mishiPosture','suit_Ines_posture_15','-mishiRoom','07','-mishiOut','E:\code\othercode\mishi_ue5\Import','-mishiWhat','actors'
.\tools\unity_batch.ps1 -Method Mishi.EditorTools.MishiUeExport.ExportSlice -Name ue_room -Graphics `
    -Extra '-mishiPosture','suit_Ines_posture_15','-mishiRoom','07','-mishiOut','E:\code\othercode\mishi_ue5\Import','-mishiWhat','room'
cd E:\code\othercode\mishi_ue5
powershell -File Tools\ue.ps1 build ; powershell -File Tools\ue.ps1 import
```

## 切片里有什么（`Import/<场景>_<房间>/`）

| 文件 | 内容 |
|---|---|
| `female.fbx` / `male.fbx` | 游戏自己的裸身模型，**只有模型**（带形态键），不带动作 |
| `female_anim.json` + `.bin` / `male_anim.*` | 每个片段逐帧（60 fps）每根骨骼的局部位置 / 旋转 / 缩放 |
| `room_meshes.fbx` + `room_instances.json` | 房间里每个不同的网格一次 + 683 处摆放（变换、材质、阴影属性） |
| `room.fbx` | 整个房间（世界坐标），只用来检查坐标换算 |
| `materials.json` | 房间每个材质的全部属性（贴图、平铺、数值、颜色、关键字） |
| `slice.json` | 部位、阶段规则、镜头、形态键轨道、语音、音效、旁白、灯光（含烘焙类型）、渲染设置、后期 |
| `eros_pp.json` | 游戏这个房间的后期体积 |
| `textures/`、`audio/` | 房间贴图、语音（日 / 英）、部位音效、BGM |

## 动作为什么走"轨道"

UE 的两个 FBX 导入器（传统和 Interchange）读 Unity FBX Exporter 写的动作时，**位移全是零**。所以 FBX 只带模型，
动作由 Unity 逐帧采样写成 `<who>_anim.json/.bin`，`mishi_anim.py` 用 `anim.controller` 的 `set_bone_track_keys`
在 UE 里建 AnimSequence。几个要点：

- FBX 里**不能**带 take：否则 UE 会从第一个 take 的第一帧取绑定姿势里没有的骨骼的参考姿势，网格被拉长。
- 片段的根曲线（模型根上绕 X 270°）是 root motion，不应用；Unity 每次采样后把模型根复位。
- 项目设置 `DefaultFrameRate=60`，而且动作资产总是删了重建：按 30 fps 建出来的序列装 60 fps 的奇数帧数据，压缩时断言失败、编辑器崩溃。
- UE 的骨架只能有一个根：Unity 端 `CompleteSkeleton` 把游离的辅助节点挂成最大那个 SMR 的骨骼。
- 形态键不在游戏的片段里（全是 0），来自 `slice.json` 的 `shape_tracks`，`AMishiCouple::ApplyShapes` 每帧设 morph target。

## 坐标换算

Unity 点 `(x, y, z)` 米 → UE `(-x, z, y) × 100` 厘米；四元数 `(x, y, z, w)` → `(-x, z, y, w)`；缩放 `(sx, sz, sy)`。
骨骼局部：位置 `(-x, -y, z) × 100`，四元数 `(-x, -y, z, w)`。UE 把骨骼名里的空格换成 `-`（`Bip001-Head`）；
她的骨架是 `Bip001`，他的是 `Bip000`。头骨的轴：**-Y 朝脸外，+X 朝头顶**。
每次建关卡都拿摆好的房间和整体导入的 `room.fbx` 比包围盒（`space_check`）；现在 6 个面里 5 个差 < 0.1 cm，
剩下一个面差 57 cm 是 `room.fbx` 里少一个物体，不是换算问题。

## 材质（`mishi_materials.py`，母材质用代码生成）

| 母材质 | 要点 |
|---|---|
| `M_Mishi_Skin` | Subsurface Profile（Burley，双高光叶）；游戏的 MGAC：G 光泽、B AO、A 曲率；细节法线（毛孔，RNM 混合，4 m 外淡出）；`MPC_Mishi` 的 Wet / Flush 驱动出汗和潮红 |
| `M_Mishi_Eye` | 按游戏 Pinkcore/Heros/Eye 的公式重建：巩膜 / 虹膜、视差、角膜缘、眼睑遮蔽；Clear Coat 做角膜高光 |
| `M_Mishi_Hair` | 发片：Default Lit + 各向异性（沿发丝），时间抖动的软边（TSR 解成半透明），阴影只由发束的实心部分投 |
| `M_Mishi_Lash` / `M_Mishi_Tears` | 睫毛眉毛（逐像素受光的半透明）/ 下眼睑的泪线（只有高光） |
| `M_Mishi_Lit` / `_Masked` / `_Glass` | 房间：平铺、MGA、自发光；都带逐物体的"镜头淡出"（见下）；一律双面（光追需要，见"踩过的坑"） |
| `M_Mishi_Flat` / `_Hidden` | 游戏的剪影 / 还没移植的 Effect 层 |

Unity 材质颜色是 sRGB，转成线性；HDR 自发光保持线性。法线贴图翻转绿色通道；遮罩贴图线性。
母材质必须勾上 SkeletalMesh + MorphTargets 的 usage，否则 `-game` 里画成灰色默认材质。

## 灯光（`mishi_look.py`）

游戏把房间的灯几乎全烘焙了（只有一盏平行光是实时的，打在角色上）。这里全部是实时灯 + Lumen：

- **太阳** = 游戏烘焙的窗光（平行光，3.0，仰角 46°）。它是房间里唯一的硬光，给地板和床单留下窗格和床架的影子。
- **主光** = 游戏的实时平行光（1.3，仰角 22°）。再放一个太阳会被墙挡住、还会让所有影子成双，
  所以它变成一块柔光箱（1.8 × 1.4 m 面光），立在窗和床之间、离角色 3 m。
- 天花板下的天空面板、两盏床补光、吊灯、蜡烛、台灯：都是真的灯，照亮来自它们的位置。
- **光照通道**：太阳的强度是主光的 2.7 倍，直射到皮肤上就是一块死白。两具身体只在通道 1 上；
  太阳只照通道 0（房间），另有一盏同方向、30% 强度的"皮肤太阳"只照通道 1。房间的影子照样落在身上。
  其他灯两个通道都照。
- 天空球 + 实时捕获的天光、指数高度雾 + 体积雾（窗口的光柱）、无界后期体积（手动曝光、bloom、暗角、色差）。

URP 灯光强度 × π = UE 的 lux / candela（URP 的漫反射没有 1/π）。

## 硬件光追和路径追踪

项目打开了硬件光追（`r.RayTracing`），Lumen 的光线打在真实的三角形上 —— 包括两具身体，软件 Lumen（距离场 + 表面缓存）
根本看不见它们。Lumen 的档位在 `LOOK["lumen_ray_lighting"]`，下面是 RTX 4090 笔记本、1600×900、100% 渲染分辨率下量到的：

| 档位 | 帧率 | 说明 |
|---|---|---|
| 软件 Lumen | 46 | 间接光偏亮（同一块墙的画面亮度 89，路径追踪基准 68）；它看到的场景只是一团粗糙的距离场 |
| `surface_cache` | 65 | 光线命中处从表面缓存取光照；身体没有表面缓存，只起遮挡作用 |
| `reflections`（默认） | 51 | 反射在命中处自己算光照：身体会出现在反射里 |
| `hit` | 45 | 间接光也在命中处算：皮肤的颜色会映到旁边的床单上 |

后三档的亮度都和路径追踪基准对得上（同一机位：墙 64–74 对 68，皮肤 187–190 对 186）。

**路径追踪定格图**：机位表里给一个机位加 `"pt": 400`（每像素采样数）。到了拍摄时刻，两具身体和镜头停住
（不再推进动作、形态键、蒙皮），切到路径追踪，每帧累积一个采样，采满后降噪（NNE 降噪器，引擎自带）再存图。
路径追踪里是真的次表面散射、真的面光源软阴影、发光球真的照亮周围、真的景深。它的雾会把光在路上削弱
（光栅化的雾只加辉光不减光），所以拍摄时加 0.3 档曝光（`pt_ev`）。`"hold": 秒数` 是不用路径追踪的定格：
身体停住，让 Lumen 和时域超分在静止画面上收敛。名字以 `_` 开头的机位不存图，只用来推进场景（按阶段键、等过渡）。

## 镜头

- **景深**：全画幅传感器、由视场角算出的焦距、f/2。对焦点跟着她的眼睛（画面里有脸时），否则是轨道目标。
  景深随距离平方缩小 —— 半米处 f/2 只有几毫米清晰 —— 所以近距离自动收光圈，保证 16 cm 的纵深清晰。
- **不穿墙**：从目标向镜头打一条射线（房间网格用自身三角面做碰撞），墙、床头板、床垫挡住时镜头收到它前面
  （立刻收进、慢慢退回）。
- **细物体淡出**：床柱、栏杆、灯杆这类"细长"的物体（自身包围盒的中间边 < 50 cm）不推镜头；
  从镜头到两具身体的头 / 胸 / 胯 / 膝 / 脚 / 手各打一条视线，被哪个细物体挡住，那个物体就抖动淡出
  （材质读逐物体的 custom primitive data），它的影子和反弹光保留。保持 1.2 秒，身体动的时候不会闪。

## 检查图和巡游片

`-MishiShots=<json>` 是一张机位表，每个机位可以：按一个阶段键（`phase`）、跳到部位的某一秒（`at`）、
绕游戏的目标转（`yaw` / `y` / `zoom`）或绕她的一根骨骼（`bone` + `from` 骨骼轴方向 + `distance`；
`up` = 画面的上方向也按骨骼轴，躺着的脸也是正的）、慢慢运动（`drift` 度/秒、`rise`、`dolly`、`push` 厘米/秒）、
跑一条控制台命令（`cmd`，做对照实验用）、切换男性画法（`his_style`）、显示面板（`hud`）。
不带 `-MishiTour` 时每个机位存一张图；带上就逐帧存，机位表就是分镜表。
录片时游戏没有声音设备，但把"哪一帧开始放哪个声音"写进 `timeline.json`，`tour_audio.py` 据此用 ffmpeg
合成和游戏里一样的音轨（语音被下一句打断、部位音效循环到下一段、BGM 垫底）。

成片的三个检查（系统 Python，要 numpy / Pillow；录完后 `Saved\MishiTour\<切片>\timeline.json` 还在，逐帧图已删，所以都从 mp4 里读）：

```powershell
python Tools\film_scan.py   out\a08_s01_tour.mp4 Saved\MishiTour\a08_s01\timeline.json            # 镜头前有东西挡住的帧（柱子、墙）
python Tools\film_jitter.py out\a08_s01_tour.mp4 Saved\MishiTour\a08_s01\timeline.json [镜头名 ...]  # 帧间差：saw 大 = 有东西隔几帧跳一下
python Tools\film_sheet.py  out\a08_s01_tour.mp4 Saved\MishiTour\a08_s01\timeline.json sheet.jpg --per-shot 3 s1_ s2_ s3_   # 某些镜头的拼版
```

## 展示切片：伊娜丝 a08 × 战斗舞台 s01（`a08_s01`）

```powershell
# Unity 端：角色和舞台各跑一次（模型来自 Assets/RoeFighter/Generated/a08，动作表和技能时间线来自 Assets/ROE）
cd E:\code\othercode\mishi
.\tools\unity_batch.ps1 -Method Mishi.EditorTools.MishiUeExport.ExportShowcase -Name ue_show_actors -Graphics `
    -Extra '-mishiChar','a08','-mishiStage','s01','-mishiOut','E:\code\othercode\mishi_ue5\Import','-mishiWhat','actors'
.\tools\unity_batch.ps1 -Method Mishi.EditorTools.MishiUeExport.ExportShowcase -Name ue_show_room -Graphics `
    -Extra '-mishiChar','a08','-mishiStage','s01','-mishiOut','E:\code\othercode\mishi_ue5\Import','-mishiWhat','room'
# 技能特效：逐帧烘焙（60 fps，目标在她正前方 6 m）-> Import\a08_s01\fx
.\tools\unity_batch.ps1 -Method Mishi.EditorTools.MishiUeExport.ExportEffects -Name ue_fx -Graphics `
    -Extra '-mishiChar','a08','-mishiStage','s01','-mishiOut','E:\code\othercode\mishi_ue5\Import','-mishiFxFps','60','-mishiTarget','6'
# UE 端
cd E:\code\othercode\mishi_ue5
python Tools\make_showcase.py Import\a08_s01                 # showcase.json + skill_sheet.json (+ fx\fx.json) -> slice.json，烘焙天空（--no-sky 跳过烘焙）
python Tools\ue_remote.py Tools\import_slice.py a08_s01      # 编辑器要开着；只重做特效材质：... a08_s01 effects level
powershell -File Tools\ue.ps1 play   -Slice a08_s01          # 窗口运行，自己操作
powershell -File Tools\ue.ps1 shots  -Slice a08_s01 -Tag x   # 检查图（Tools\shots_a08_s01.json）
powershell -File Tools\ue.ps1 tour   -Slice a08_s01 -ResX 1920 -ResY 1080   # 影片 -> out\a08_s01_tour.mp4（Tools\tour_a08_s01.json）
powershell -File Tools\ue.ps1 stills -Slice a08_s01          # 路径追踪定格图 -> out\stills\a08_s01（Tools\stills_a08_s01.json）
# 带特效的动作定格（Lumen 实时画面，离屏 4K；路径追踪里没有特效）-> out\stills\a08_s01_fx
powershell -File Tools\ue.ps1 stills -Slice a08_s01 -Tag fx -Shots Tools\stills_a08_s01_fx.json -ResX 3840 -ResY 2160
# 特效检查图（三个技能 24 个时刻）
powershell -File Tools\ue.ps1 shots  -Slice a08_s01 -Tag fx -Shots Tools\shots_a08_s01_fx.json
```

**动作**（面板上 9 个按钮，数字键 1-9）：战斗站姿、展示、互动 1 / 2、技能 1 / 2、大招、受击、倒下。一次性动作播完回到
站姿或展示姿势；"自动"按一张表轮流播。`slice.json` 的 `kind` 是 `showcase`，没有男性，阶段就是按钮。

**时间线**：游戏每个技能是一条 Timeline。`make_showcase.py` 把它变成每个部位的 cues，`AMishiCouple::FireCues` 到点执行：

| cue | 做什么 |
|---|---|
| `sfx` / `voice` | 技能自己的音效（播到完）/ 语音（日 / 英，被下一句打断） |
| `shake` | 命中时震镜头（幅度、时长、频率来自游戏的 Cinemachine impulse） |
| `move` | **单位的位移**：`attack` = 0.2 秒冲到目标前 1 m（目标 = 舞台敌方第一个站位，她正前方 6 m），`return` = 回原位。动作片段是配合这个位移做的 —— 片段里她往回退的量正好是单位往前冲的量；不做位移她会在原地向后滑 2.4 m |
| `camera` | **游戏的技能镜头**：挂在单位身后 4.27 m、高 1.42 m 的虚拟相机，视场角 40°，跟着冲刺走。面板"技能镜头"打开时技能期间切过去（默认关：自由镜头更适合看盔甲）。大招在游戏里没有自己的镜头，这里给了同一个 |
| `fx` | **技能特效**：从这个部位的第 0 秒开始回放烘焙好的那一段（见下） |
| `hit` | 命中时刻（没有用到：命中特效已经在烘焙里） |

技能的编排是给"身后的技能镜头"看的：她冲到敌人面前，然后**转身朝镜头**定格（技能 1 的 1.0–2.0 秒和 3.0–3.8 秒、
大招的 3.2–3.8 秒）。所以从正面的自由镜头看，这几个定格是背影；影片和定格图的机位是按每个姿势的朝向摆的。
技能 1 里巨剑会分成两把，技能 2 把剑扔出去再接住 —— 武器骨骼 `Point007_L/R` 直接挂在根上，自己有动作。

**自由镜头跟人**：轨道中心跟着她的胯（`Bip001`）走，水平全跟、起跳只跟一半、原地晃动不跟，滞后 0.22 秒。
近景的清晰纵深放宽到 36 cm（一块肩甲从前沿到后沿都清楚）。

**天空**：舞台的天空盒是立方体贴图 × 4.59，游戏在它上面盖了一条雾色带，从地平线一直盖到仰角 41°、浓度 86% ——
所以游戏里平视过去天空是一片平的浅蓝，底下的画（云海、雪山、贴着地平线的太阳）根本看不到。`mishi_sky.py`
把立方体贴图烘焙成一张 UE 方向的经纬图（16 位 PNG，线性 / 8），**默认不要雾带**（`--fog-band` 保留）；
关卡里它贴在 10 km 外的天空球上（Is Sky 材质，天光实时捕获它，捕获分辨率 512 —— 抛光的金属要映出云）。

**太阳**：游戏把这个舞台的平行光放在仰角 73°（正午的平光，烘焙）。这里太阳放在天空图里发亮的方位
（她正前方偏右 35°），仰角抬到 32°：从她周围的地毯向天空打射线，量出这个角度下她和前后 5 m 都在阳光里，
城堡塔楼的影子落在远处。颜色偏暖 (1, 0.90, 0.76)。数字都在 `mishi_look.py` 的 `LOOK_SHOWCASE`。

**跟机补光**：一个太阳照不全 —— 站姿朝向偏离太阳 49°，展示姿势 22°，技能的定格姿势背对太阳。
`AMishiCameraPawn::Fill` 是一盏挂在相机上的平行光（沿视线、略从上方），只照角色的光照通道、不投影、不反弹，
光源张角 24°（在金属上是一片柔和的高光而不是闪光灯的亮点），强度约为太阳的 0.29（`LOOK["camera_fill"]`）。
舞台不受它影响；路径追踪同样认光照通道。

**盔甲材质**（`M_Mishi_Armor`，数字在 `mishi_materials.py` 的 `ARMOR_LOOK`）：游戏的贴图 4096²，
遮罩图 R 金属 / G 光泽 / B AO。游戏把金色画在真实黄金反射率的三分之一上（身体那张 (0.31, 0.21, 0.11)，
盔甲那张 (0.48, 0.36, 0.19)，黄金是 (1.0, 0.77, 0.34)）——它的着色器另外加菲涅尔项。在 UE 里金属的底色就是镜面色，
照搬就是一块暗铜。所以金属部分：底色 ×1.7（保持色相，超过 1 整体压回）、饱和度 ×1.25（浅金映着蓝天会发灰绿）、
粗糙度 ×0.7、缝隙按 AO 压暗 0.35（金属没有漫反射可以给 AO 压）。Lumen 追踪反射的粗糙度上限提到 0.65
（默认 0.4 以上的金属只拿到模糊的探针）。

**骨骼布料**（`FMishiSprings`，面板"物理"开关）：a08 的头发、辫子、腰链、剑上的链子、手腕的饰物在所有动作片段里都是不动的
（游戏里由 Magica Cloth 2 驱动），裙片和前发只在技能里有关键帧。这里把这些骨骼链接到一个弹簧解算器上：
动画姿势是基准；继承单位位移和身体转动的一部分惯性（有速度上限）；Verlet 积分 + 阻尼 + 重力 + 风（每条链有自己的阵风相位）；
每个子步从根到梢依次约束 —— 拉回基准角度、角度上限、胶囊碰撞体（胯、大腿、小腿、躯干、脖子、头）、离基准的最大距离、
地面；骨长不变。**两端都挂住的链**（腰链从胯挂到腰带，`pin_tip`）多做一遍从梢往根的 FABRIK。
种类和数字在 `make_showcase.py` 的 `SPRING_KINDS` / `SPRING_PRESETS` / `SPRING_COLLIDERS` / `WIND`，写进 `slice.json` 的 `springs`；
按骨骼名分类（`skirt_chain` → swag，`chain` / `tassel` / `accessories` → chain，`skirt` → skirt，`hair` / `braid` / `bangs` → hair），
胸部骨骼不碰（片段里有关键帧）。切换部位时不重置（惯性带过去），`Seek` 时重置。

**技能特效**（`FMishiFx`，面板"特效"开关）：a08 三个技能共 20 个特效预制体、148 个粒子系统（Shuriken，没有脚本）。
Niagara 没法用脚本搭出来（Python 能碰到的接口几乎是空的），所以走 **Unity 烘焙、UE 回放**：

- Unity（`MishiUeEffects.cs`）按技能时间线重放：单位位移、身体片段逐帧采样、每个特效预制体挂到它的挂点、
  `ParticleSystem.Simulate` 60 fps 定步长，每帧把每个渲染器的 `BakeMesh` 几何写进 `fx_<动作>.bin`
  （单位出发位置的坐标系）。三种几何：网格粒子 / 轨迹原样写（soup）；朝向相机的公告板只写中心和相机空间的偏移（view）；
  拉伸公告板写头、尾、半宽（stretch）—— 后两种在 UE 里按**当前相机**重新摆。粒子的 Lights 模块写成灯（位置、颜色 × 强度、范围）。
- `make_showcase.py` 写 `fx\fx_index.json`（每段动作的批次，按游戏的渲染队列排序）并给有特效的部位加 `fx` cue。
- `mishi_fx.py` 做材质：游戏的四个粒子着色器各一个母材质（Unity 工程里 `RoeParticle*.shader` 的逐行移植）——
  UnlitMaster（偏移给底图 / 溶解图 / 扭曲图之一、溶解 + 发光边、相乘 / 相减着色、遮罩、软粒子、自发光 / 菲涅尔边缘光）、
  Default（滚动贴图 × 颜色 + `_Emissive`）、MutateDistortion、Distortion（把身后的画面按法线图推开：冲击波、热浪）。
  顶点数据怎么带：UV0 = 贴图坐标，UV1 = 自定义数据里的偏移，UV2 = （溶解量，扭曲强度），UV3 = 自发光（亮度 + 色相），
  法线 = 表面自己的法线，顶点色 = 粒子颜色。
- UE 回放：一个 `UProceduralMeshComponent`，每个批次一个网格段（索引取这一批最长的那一帧，以后只更新顶点），
  三盏点光源跟着粒子灯走。

要点：只有 UnlitMaster 的混合方式来自材质；另外三个着色器**固定是普通半透明**，它们材质里的 `_SrcBlend / _DstBlend`
是换着色器留下的旧值（用 Unity 工程的 `tools/shader_asm.py` 读游戏着色器的渲染状态确认）。背面剔除（`_Cull`）在材质里按法线做：
刀光的正面和背面是两张不同的网格（亮的和暗的），发光的外壳不能露出里面。特效贴图在游戏里都是线性的（不勾 sRGB）。
自发光是 HDR（最高 58），在这个场景的曝光下 ×0.3（`FX_LOOK`）；粒子灯 ×0.8（`LOOK["fx_light_scale"]`）。
路径追踪定格图里没有特效（它们不进光追场景）。

## 操作

| 输入 | 作用 |
|---|---|
| 左键拖动 | 转镜头（左右偏航，上下改轨道高度） |
| 右键拖动 | 平移目标（限制在游戏允许的盒子里） |
| 滚轮 / Q E / PageUp PageDown | 缩放 |
| A D / ← →，W S / ↑ ↓ | 偏航，轨道高度 |
| 中键 / Home | 镜头复位 |
| 1 2 3 4 | 阶段 1-4（和游戏一样：先走过渡部位）；展示切片：1-9 是九个动作 |
| 空格 | 自动开 / 关 |
| V | 语音：日 → 英 → 关 |
| M | 男性：皮肤 → 剪影 → 隐藏 |
| X / B | 部位音效 / 潮红出汗 开关 |
| H | 面板显示 / 隐藏 |

## 踩过的坑

- Python 里结构体数组的元素是拷贝：改完要收集起来整个赋回去（骨骼网格的材质槽就是这样丢的）。
- 导入骨架后要立刻 `save_directory`，否则网格的 skeleton 回来是 None。
- `unreal.Quat4f` 不能带值构造；`set_bone_track_keys` 要 `unreal.Vector` / `unreal.Quat`。
- 编辑器在后台时 `take_high_res_screenshot` 不出图：检查图一律走 `-game` 进程。
- 检查图要等相机读到轨道参数（`IsSetUp`）再开拍，否则第一个机位是默认值。
- 1920×1080 的窗口在这台笔记本上会被系统缩成奇数尺寸（x264 拒收）：录片用 `-RenderOffscreen`。
- 录片逐帧存 PNG 时每帧 0.4 秒都花在压缩上（66 秒的片子录 13 分钟）：逐帧存 BMP，编码完删掉。
- 骨骼网格的包围盒是站姿的：角色躺下后头在盒外，脸部特写时**整个身体被视锥剔除**（人突然消失）。
  两具身体的 `BoundsScale` 设成 6。
- 灯光强度 / 曝光怎么改都不变的"高光"多半不是高光：这次鼻梁上的白斑是太阳直射的漫反射。
  用 `ShowFlag.Specular 0`、`ShowFlag.DirectLighting 0` 这类开关一次跑一组对照最快。
- **光追管线默认在后台编译**，没编完的命中着色器用"全黑替代材质"顶着：路径追踪出来一片黑，带命中光照的反射也是黑的。
  出图和录片的进程加 `-dpcvars=r.RayTracing.NonBlockingPipelineCreation=0`（`ue.ps1` 已带）；第一次链接要 3 分钟，之后有缓存。
- **房间外壳是朝内的单面平面**：光线从背面来就直接穿过去。Lumen 给表面缓存算阴影的光线因此让太阳穿过屋顶和墙，
  整个房间都在反弹阳光（间接光是基准的 3 倍）。房间材质一律双面，再加 `r.LumenScene.DirectLighting.HardwareRayTracing.ForceTwoSided=1`。
  判断谁对谁错的办法：出一张路径追踪做基准，再用 `r.Lumen.Visualize.IndirectDiffuse 1` 加各类灯的 ShowFlag 看间接光从哪盏灯来。
- 5.8 里 `r.Lumen.HardwareRayTracing.LightingMode`：0 表面缓存、**1 间接光和反射都算命中光照、2 只有反射**（和后期体积里枚举的顺序不一样）。
  不确定的控制台变量用 `<变量名> ?` 打帮助到日志里看；`DumpConsoleCommands` 的输出不进日志。
- 桌面默认的渲染分辨率是自动的（1600×900 时只有 84%，靠 TSR 放大）：配置里写死 `r.ScreenPercentage=100`。
- 写文件工具会把内容里的 `\uXXXX` 变成字符；bash heredoc 会吃反斜杠。带反斜杠的脚本用写文件工具写。
- **材质编译失败是静默的**：`TextureSampleParameter2D` 采样类型设成 Linear Color、默认贴图却是引擎的 sRGB 默认贴图，
  母材质编不过，引擎悄悄换成默认材质（天空球变黑，屏幕上一行黄字 "skydome mesh ... does not cover"）。
  给参数一张线性的默认贴图；导入后在编辑器日志里搜 `Failed to compile`。
- 指数高度雾会把 10 km 外的天空球整个盖成雾色（看起来像"天空是平的"）：设 `fog_cutoff_distance`。
- Is Sky 的网格不用关"光追可见"：Lumen 的光追场景自己会排除它（`r.RayTracing.ExcludeSky`），路径追踪只让相机光线看见它
  （其余光线拿天光，不会算两遍）。关掉的话路径追踪的背景变成模糊的天光贴图，地平线以下是黑的。
- 编辑器开着时 `-game` 进程的日志是 `Saved\Logs\MishiUE_2.log`，不是 `MishiUE.log`。
- 机位表里 `from` 是**骨骼轴**方向；只有 `bone` 没有 `from` 是绕那根骨骼转（`yaw` / `y` / `zoom`）。
  一个机位同时给 `phase` + `at` 再拍很短的时间，拍到的是混合途中的姿势：先用一个 `_` 机位进入那个部位。
- **程序化网格的 UV 是 16 位浮点**（`FStaticMeshVertexBuffer` 默认半精度）：往一个 UV 里打包"整数部分 + 小数部分"会被截掉
  （特效的自发光色相变成黄 / 品红的色块）。2048 以内的整数能原样通过。
- 顶点切线会被引擎对着法线**正交化**：想借切线多带一个向量（真实法线）不行，带进去的是它垂直于法线的那部分。
- 双面材质画封闭网格时，背面的菲涅尔项是满的（`1 - saturate(N·V)` = 1）：发光外壳变成一整块白。按游戏的 `_Cull` 剔掉背面。
- Unity `ParticleSystemRenderer.BakeMesh` 默认把本地空间的粒子系统留在本地空间：烘焙时加 `BakeRotationAndScale | BakePosition`。
  一个技能里两个挂点可以重名（Skill3_hit01）：时间线节点不能按名字合并。
- **右肩塌陷 = 一根镜像的辅助骨骼**：她两肩的三角肌各由一个辅助球骨骼撑着（`GeoSphere001` / `GeoSphere002`，挂在上臂下面，
  随手臂反向转动）。右边那个是左边的镜像拷贝，缩放是 (-1.133, -1.133, -1.133)。FBX 导入建参考姿势时把镜像去掉了
  （旋转不变、缩放变正），而动作轨道里还是负缩放 —— 蒙皮矩阵 = 动画 × 参考姿势的逆，两边不一致，这根骨骼管的那块皮
  就绕着关节被翻到身体里去了：肩头没了，手臂像从腋下长出来（手臂离绑定姿势越远越明显）。
  过原点的镜像（三个轴都负）在"动画 × 逆绑定"里本来是抵消的，所以 `mishi_anim.py` 写轨道时把它去掉；
  只有一两个轴为负的是真镜像，保留并报警。查法：`female_anim.bin` 里找缩放为负的骨骼，对比骨架参考姿势的缩放。
- 出图 / 录片的 `-game` 进程也开着 Python 远程执行：它在跑的时候 `ue_remote.py` 可能连到它而不是编辑器
  （报 `module 'unreal' has no attribute 'CustomMaterialOutputType'` 之类缺编辑器类的错）。等出图进程结束再导入。
- **机位跳进技能中段马上拍，特效是空的**：引擎默认等一个网格的管线状态（PSO）编译好才开始画它，头几帧没有。
  出图 / 录片的进程带 `r.PSOPrecache.ProxyCreationStrategy=0`、`r.AsyncPipelineCompile=0`（`ue.ps1` 的 `$Capture`）；
  正常运行不受影响（特效在技能开始 0.7 秒后才出现，那时早编译好了）。
- `shots` 是窗口模式：要的分辨率比屏幕大就被系统缩小（要 3840×2160 得到 1423×889）。大图走 `stills`（离屏），
  机位表里不写路径追踪就是 Lumen 画面。
- **解包出来的动作片段里有"阶梯"**：游戏把片段存成每个浮点一条流，恒定不变的分量（单轴关节四元数的 x、y：前臂、小腿、指节、嘴角）
  是带无穷大斜率的阶梯流；写回成四元数曲线后，这种关键帧的出斜率是 `(-Infinity, -Infinity, 0.04, -0.01)`，Unity 重建片段时
  **一个分量无穷大就把整个关键帧当阶梯**——前臂停 40 帧再跳 2.4°，手指一跳 20°（游戏里是平滑的）。特写里手一抽一抽就是它。
  Unity 导出端的 `MishiUeExport.Unstepped` 把"前后两个关键帧数值相同"的无穷大斜率改成 0 再采样；数值真的变了的阶梯保留。
  查法：对成片逐帧求差（单帧尖峰），再看 `female_anim.bin` 里哪些骨骼"多数帧不动、偶尔一跳"。
- 她的朝向不能凭感觉：站姿朝 -19°、展示姿势 +52°、技能里到处转（按两肩的连线算）。机位的 `yaw` = 她的朝向 + 20 时正对她。

## 还没做 / UE5 能继续发挥的方向

- 蜜室切片的 Effect 层（液体、粒子）：可以走展示切片同一条"Unity 烘焙、UE 回放"的路；或者 Niagara + 贴花（要在编辑器里手搭）
- 蜜室切片的弹簧物理（`springs` 目前只有展示切片在配；蜜室的动作是手 K 的，头发不动）、胸部
- 特效：MutateDistortion 的屏幕扭曲部分没做（这个角色的特效没用到）；路径追踪里看不到特效
- Groom 发丝、Substrate 皮肤（带汗水涂层）、路径追踪的动态片段（Movie Render Queue）
- 回忆模式、换身体、更多场景和房间、选择菜单
- 打包（Cook）：中文字体在打包版里需要带一个 CJK 字体
