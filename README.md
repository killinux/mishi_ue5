# 蜜室 Mishi — Unreal Engine 5 版

把《Rise of Eros》蜜室（eros mode）的一个场景在 UE5 里重做：游戏自己的模型、动作、声音和房间，
但灯光、材质、镜头按 UE5 的能力重新设计（Lumen 全局光照、虚拟阴影、次表面皮肤、真实镜头景深）。
Unity 版在 `E:\code\othercode\mishi`（GitHub killinux/mishi），它负责把一个场景（体位 × 房间）导出成"切片"。

**只提交代码。** `Import/`（游戏导出物）、`Content/`（导入后的资产）、`out/`、`Saved/` 都不进 git，仅供个人使用。

当前做完的切片：**Ines（伊娜丝）eros15 × 房间 07**（`eros15_07`）。

## 目录

| 路径 | 内容 |
|---|---|
| `Source/MishiUE/` | C++ 游戏模块（见下表） |
| `Tools/ue.ps1` | 一键：找引擎、编译、导入、运行、出检查图、录巡游片 |
| `Tools/ue_remote.py` | 在**开着的编辑器**里跑一个 Python 脚本（Python Remote Execution） |
| `Tools/import_slice.py` | 导入一个切片：贴图 / 音频 / 身体 + 动作 / 房间 / 材质 / 关卡，可只跑其中几步 |
| `Tools/mishi_anim.py` | 动作：Unity 逐帧轨道 → AnimSequence |
| `Tools/mishi_materials.py` | 用代码生成母材质（皮肤 / 眼睛 / 头发 / 睫毛 / 泪 / 房间…）和每个游戏材质的实例 |
| `Tools/mishi_look.py` | 关卡：摆房间、灯光设计、天空、雾、后期；所有"观感"数字都在 `LOOK` 表里 |
| `Tools/shots_lookdev.json` / `tour.json` | 检查图的机位表 / 巡游片的分镜表 |
| `Tools/sheet.py` / `tour_audio.py` | 检查图拼版 / 巡游片的音轨合成 |
| `Config/` | 硬件光追 Lumen + 虚拟阴影、路径追踪、无烘焙光照、手动曝光、TSR 100%、SM6；默认地图和 GameMode；传统 FBX 导入；动画默认 60 fps；Python 远程执行 |
| `Tools/shots_stills.json` | 路径追踪定格图的机位表 |

| C++ 类 | 作用 |
|---|---|
| `AMishiCouple` | 一对角色：部位（part）状态机 = 游戏 Animator 的规则，自动模式，语音 / 部位音效循环 / BGM，旁白，形态键轨道，皮肤的潮红和出汗（随阶段推进），男性三种画法（皮肤 / 游戏的剪影 / 隐藏） |
| `UMishiAnimInstance` | 不用动画蓝图的双槽播放器：当前片段 + 渐出片段，在 proxy 的 `Evaluate` 里混合 |
| `AMishiCameraPawn` | 游戏 Cinemachine 自由视角的复刻（三条轨道、偏航、缩放、目标盒内平移）+ 真实镜头景深（自动对焦到她的眼睛、近距离自动收光圈）+ 不穿墙 + 挡住角色的细物体淡出 |
| `AMishiPlayerController` | 鼠标键盘、Slate 面板；`-MishiShots` 检查图 / `-MishiTour` 逐帧录片 |
| `SMishiHud` | 面板：阶段 1-4、自动、语音、男性画法、音效、潮红、镜头预设、旁白 |
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

## 操作

| 输入 | 作用 |
|---|---|
| 左键拖动 | 转镜头（左右偏航，上下改轨道高度） |
| 右键拖动 | 平移目标（限制在游戏允许的盒子里） |
| 滚轮 / Q E / PageUp PageDown | 缩放 |
| A D / ← →，W S / ↑ ↓ | 偏航，轨道高度 |
| 中键 / Home | 镜头复位 |
| 1 2 3 4 | 阶段 1-4（和游戏一样：先走过渡部位） |
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

## 还没做 / UE5 能继续发挥的方向

- Effect 层（液体、粒子）：Niagara + 贴花
- 头发和胸部的弹簧物理（游戏里蜜室的动作是手 K 的，头发不动）
- Groom 发丝、Substrate 皮肤（带汗水涂层）、路径追踪的动态片段（Movie Render Queue）
- 回忆模式、换身体、更多场景和房间、选择菜单
- 打包（Cook）：中文字体在打包版里需要带一个 CJK 字体
