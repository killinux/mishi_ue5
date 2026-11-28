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
| `Tools/install_dlss.py` | 把 NVIDIA 的 DLSS 插件从它的 zip 装进本工程的 `Plugins/`（可选，见"画质选项"） |
| `Tools/bench_table.py` / `shots_bench.json` | 各档画质的帧率：`ue.ps1 bench` 在**同一次运行**里轮流切换并计时；显卡被别的程序分走时也读得出可信的数（见"画质选项"） |
| `Tools/still_noise.py` / `shots_noise.json` | 定住一个姿势连拍 N 帧，量画面自己的闪动和细节（比较抗锯齿 / 降噪方案用） |
| `Tools/check_tracks.py` / `check_parents.py` | 体检：动作轨道里的阶梯、镜像骨骼、手腕错位（导入前，系统 Python）/ 丢了父级的材质实例（编辑器里跑） |
| `Tools/film_scan.py` / `film_jitter.py` / `film_sheet.py` | 成片检查：被挡住的帧 / 帧间跳变 / 拼版 |
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
| `M_Mishi_Skin` | Subsurface Profile（Burley，双高光叶）；游戏的 MGAC：G 光泽、B AO；自己画的细纹 + 毛孔（见下"皮肤和头发的近景"）；`MPC_Mishi` 的 Wet / Flush 驱动出汗（汗膜 + 汗珠）和潮红 |
| `M_Mishi_Eye` | 按游戏 Pinkcore/Heros/Eye 的公式重建：巩膜 / 虹膜、视差、角膜缘、眼睑遮蔽；Clear Coat 做角膜高光 |
| `M_Mishi_Hair` | 发片：Default Lit + 各向异性（高光横跨发丝成一条带，游戏的偏移噪声图让每缕头发的带子高低不一），时间抖动的软边（TSR 解成半透明），阴影只由发束的实心部分投 |
| `M_Mishi_Lash` / `M_Mishi_Tears` | 睫毛眉毛（逐像素受光的半透明）/ 下眼睑的泪线（只有高光） |
| `M_Mishi_Lit` / `_Masked` / `_Glass` | 房间：平铺、MGA、自发光；都带逐物体的"镜头淡出"（见下）；一律双面（光追需要，见"踩过的坑"） |
| `M_Mishi_Flat` / `_Hidden` | 游戏的剪影 / 还没移植的 Effect 层 |

Unity 材质颜色是 sRGB，转成线性；HDR 自发光保持线性。法线贴图翻转绿色通道；遮罩贴图线性。
母材质必须勾上 SkeletalMesh + MorphTargets 的 usage，否则 `-game` 里画成灰色默认材质。

### 皮肤和头发的近景（`mishi_materials.py` 的 `SKIN_LOOK` / `HAIR_LOOK`）

样张：`out\skin_hair_samples\`（四张前后对比）。数值都在这两个字典里，改完 `import_slice.py <切片> materials` 重建实例即可
（动了母材质的图才需要改 `VERSION`）。

- **细纹和毛孔**。游戏只有一张 256 px 的细节法线（`pc_common_detailskin`，一张细胞网），裸体的身体（平铺 120）和脸（平铺 70）用，
  穿盔甲的那套皮肤和男性身体没有；它只在掠射的高光里看得见，脸上比身上细一倍。现在所有皮肤统一用自己画的
  `Tools/textures/skin_detail.png`（`python Tools/make_skin_detail.py`，1024 px 无缝：R G = 细纹的法线 xy——皮肤是一张细沟围着
  小块的网；B A = 毛孔的法线 xy）。平铺数 = 这块材质 1 个 UV 单位在身上是多少厘米 ÷ `tile_cm`：`Tools/mishi_fbx.py` 直接读 FBX
  算（纯 Python，UE 的 Python 也能跑；身体 150 cm、脸 41 cm），所以脸上和大腿上的毛孔一样大。脸以毛孔为主、身体以细纹为主
  （`lines` / `pores`）；沟和孔的壁让高光变暗变糙（`cavity`）、颜色略深（`shade`）；强弱在身上不均匀（`patches`）。
  **尺寸是放大过的**：真实的皮肤小块只有半毫米，镜头在半米外时一个像素就是 0.2 mm，按真实尺寸画只会让整片高光变暗、什么也看不出，
  所以一格是 1.25 mm（`tile_cm` 6）。柔光下本来就含蓄，阳光、高光和出汗时明显。
- **换成真实皮肤的微法线（本地，可选）**。别的游戏的皮肤包（比如给 HoneySelect 2 做的 Hanmen NEXT-GEN：8K 的身体微法线、4K 的脸）
  是按那个游戏的身体 / 脸的 UV 画的，**不能直接贴到 ROE 的身体上**（`out\skin_hair_samples\06_*.jpg`：两套 UV 排法完全不同），
  但它的微细节本身可以借来：`Tools/make_skin_tile.py` 从法线贴图上均匀的一块（背、脸颊）裁一个方块，只留细的部分
  （身体的起伏在低频里），首尾交叉淡化成无缝平铺块，写到 `Import/_local/skin_detail.png`（R G = 身体，B A = 脸）和
  `skin_detail.json`（每个区域一格是多少厘米、用哪一层）。`Import/_local/` 里有这一对时导入脚本用它代替程序画的那张
  （日志 `T_Mishi_SkinDetail: the local ...`），删掉再跑一次 materials 就换回来。**这类贴图是别人的作品（多半是付费的）：只在本机用，
  `Import/` 不进仓库。** 源图用 UnityPy 从 zipmod 的 .unity3d 里导成 PNG（`Texture2D.image.save`）；Unity 的 DXT5nm 法线 x 在 A、y 在 G
  （`--body-layout ag`），普通的在 R G。

  ```powershell
  python Tools\make_skin_tile.py --body cf_nextgen_body_base_n.png --body-box 2304,1280,1536 --body-layout ag --body-mm 0.2 `
      --face cf_nextgen_head_00_00_n.png --face-box 2440,1900,768 --face-layout rg --face-mm 0.087 --face-repeat 2 --scale 2
  python Tools\ue_remote.py Tools\import_slice.py eros15_07 materials
  ```

  `--*-mm` 是源图一个像素在它自己的身体上是多少毫米（8K 身体图约 0.2，4K 脸图约 0.087），`--scale 2` 是比真实尺寸放大一倍——
  真实尺寸的纹理比画面分辨率还细，和程序版一样要放大才看得见。对比见 `05_*.jpg`：阳光下的高光里是不规则的真实纹理，
  不再是蜂窝格；柔光下三种几乎没有差别（法线层面的细节在柔光里本来就看不出）。
  包里另外还有按 HS2 身体画的整身出汗图（汗流 + 汗珠）、血管图、厚度图、8K 肤色——这些要先把两个身体的表面对应起来、
  把贴图烘到 ROE 的 UV 上才能用（没做）。
- **整身搬运：把别的身体的皮肤包烘进 ROE 的 UV（v0.2，`Tools/skin_transfer/`，本地，可选）**。平铺块只借到"纹理的样子"，
  皮肤包真正的内容——跟着身体走向的微法线、整身的汗流和水珠、血管、厚度、肤色里的细腻色斑——都钉在它自己身体的 UV 上。
  做法是把那个身体"贴"到 ROE 的身体上，然后对 ROE 贴图的每个像素问一句"你在那个身体的哪一点"：

  ```powershell
  # 0. 源：HS2 的底模（ripper_tpose 的 scripts\honeyselect2）和皮肤包的贴图（Hanmen NEXT-GEN：两个下载的 zip）
  python E:\code\othercode\ripper_tpose\scripts\honeyselect2\export_model.py --body female --head 0 --no-preview --out _work\hs2
  python -I Tools\skin_transfer\pack_export.py "<Skin Textures v1.2.zip>" "<Shaders 415 Beta.zip>"          # -> _work\hs2\pack\*.png
  $B = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
  & $B -b --factory-startup _work\hs2\bodies\body_female\body_female.blend --python Tools\skin_transfer\hs2_dump.py -- _work\hs2\body_female.npz
  # 1. 配准：HS2 的身体和头贴到目标身体上（--skin：目标里算皮肤的材质）
  & $B -b --factory-startup --python Tools\skin_transfer\fit.py -- _work\hs2\body_female.npz Import\a08_s01\female.fbx _work\hs2\fit_a08.npz --skin pc_a08_hd_skin,pc_a_nk_face
  # 2. 对应：目标材质贴图的每个像素 -> 皮肤包身体上的 UV（身体 8K，脸 4K）
  & $B -b --factory-startup --python Tools\skin_transfer\correspond.py -- _work\hs2\body_female.npz _work\hs2\fit_a08.npz Import\a08_s01\female.fbx pc_a08_hd_skin 8192 _work\hs2\corr_a08_pc_a08_hd_skin_8192.npz
  & $B -b --factory-startup --python Tools\skin_transfer\correspond.py -- _work\hs2\body_female.npz _work\hs2\fit_a08.npz Import\a08_s01\female.fbx pc_a_nk_face 4096 _work\hs2\corr_a08_pc_a_nk_face_4096.npz
  # 3. 烘焙 -> Import\_local\skin\<材质>_hm_{n,c,w,wn}.png；4. 导入（编辑器开着）
  python Tools\skin_transfer\bake.py _work\hs2\corr_a08_pc_a08_hd_skin_8192.npz pc_a08_hd_skin
  python Tools\skin_transfer\bake.py _work\hs2\corr_a08_pc_a_nk_face_4096.npz pc_a_nk_face
  python Tools\ue_remote.py Tools\import_slice.py a08_s01 materials
  # 蜜室切片的裸体身体：同样三步（fit 不写 --skin 就是 pc_a01_nk_body + pc_a_nk_face），身体烘焙带 --own；
  # 脸要用这个身体自己的配准再烘一套，放进 on_<身体的材质>\（见下"一个身体一次配准"）
  & $B -b --factory-startup --python Tools\skin_transfer\fit.py -- _work\hs2\body_female.npz Import\eros15_07\female.fbx _work\hs2\fit_nude.npz
  & $B -b --factory-startup --python Tools\skin_transfer\correspond.py -- _work\hs2\body_female.npz _work\hs2\fit_nude.npz Import\eros15_07\female.fbx pc_a01_nk_body 8192 _work\hs2\corr_nude_pc_a01_nk_body_8192.npz
  & $B -b --factory-startup --python Tools\skin_transfer\correspond.py -- _work\hs2\body_female.npz _work\hs2\fit_nude.npz Import\eros15_07\female.fbx pc_a_nk_face 4096 _work\hs2\corr_nude_pc_a_nk_face_4096.npz
  python Tools\skin_transfer\bake.py _work\hs2\corr_nude_pc_a01_nk_body_8192.npz pc_a01_nk_body --own E:\game_export\RiseOfEros\_meta\_hq_materials\textures\pc_a01_nk_body_rgbx_Albedo.png --uv-cm 150.5
  python Tools\skin_transfer\bake.py _work\hs2\corr_nude_pc_a_nk_face_4096.npz pc_a_nk_face --out Import\_local\skin\on_pc_a01_nk_body
  python Tools\ue_remote.py Tools\import_slice.py eros15_07 materials
  ```

  **一个身体一次配准。** 脸的材质 `pc_a_nk_face` 每个身体都用，但它的烘焙图取决于"整个身体那次配准"：同一张脸换一个身体就是
  另一次配准，拿错了在脖子接缝两侧读到的是皮肤包上相距 3.5 mm 的两点（水珠在接缝处被切成两半）。所以某个身体专用的图放在
  `Import\_local\skin\on_<那个身体的材质>\`，导入时优先于公共的那套，并且得到自己的实例 `MI_<材质>_on_<身体>`
  （现在：`pc_a_nk_face` 公共那套来自 a08 的配准，`on_pc_a01_nk_body\` 那套来自裸体身体的配准，接缝两侧相差 0.57 mm）。

  - **配准**（`fit.py`）：两个身体都是 T 姿、朝向相同。先用两套骨架里"同一个地方"的骨骼做地标（髋、膝、肩、肘、每个指节；
    以及长在特征上的骨骼：乳头、嘴角、上下唇、鼻翼、眼球、眉头眉尾），求一个把每个地标送到对应位置、其余地方尽量平滑的
    空间变形（径向基函数）；**脊柱的关节不用**——两套骨架切脊柱的高度不一样，用了肚子会整体错位 11 cm。然后让表面贴上去：
    每个顶点找目标上朝向相同的最近点，位移在网格上平滑后再走，十轮，平滑逐轮减弱。目标只露出一部分皮肤（盔甲）时，
    落在碎片边缘上的最近点不算（否则边缘外的皮肤会被挤到边上）。结果：两层皮肤相距中位数 0.2 mm。
  - **对应**（`correspond.py`）：把目标的三角形画进它的 UV 方格（像素 -> 空间里的一点和朝向），再用 Blender 的 BVH 查贴好的
    源网格上朝向相同的最近点，换成源的 UV。8K 有 3350 万个皮肤像素，约 3.5 分钟。
  - **烘焙**（`bake.py`）：`_n` 微法线——源法线图减去它平滑的部分（身体的大起伏留给 ROE 自己的法线图），x、y 从源 UV 的方向
    **转到**目标 UV 的方向（两套 UV 在皮肤上的走向不同；转角取"源 UV 沿目标 UV 怎么变"最近的旋转，一边是另一边的镜像时取镜像）；
    `_c` RGB 肤色的细节（源肤色除以它自己的模糊：毛孔、细色斑；嘴唇、鼻孔这类"它的身体的特征"按中尺度对比度去掉，
    幅度限制在 ±12 %），A 光泽的细节；`_w` R 汗流、G 水珠 / 湿斑、B 血管、A 厚度；`_wn` 汗流和水珠的法线。
    两层皮肤相距超过 1.2 cm 的像素（耳朵里面、指甲）保持中性。每块 UV 岛的内容向外补 64 像素（`pad`）——否则贴图过滤和 mip
    在岛的边界上读到的是外面的中性值：水面的高度在边界上"掉下去"，在水的法线图里就是一圈斜坡，出汗时沿每条 UV 接缝一条亮线。
    `--own <目标材质自己的肤色图>`：目标自己画了特征的地方（乳晕、肚脐、阴毛、私处）不套皮肤包的微法线、肤色、光泽和血管，
    边缘柔和过渡：那里的皮肤是给另一个身体的特征画的，会偏开几毫米；皮肤包自己画了特征的地方，身体的微法线同样不取。汗照常。
    "特征"的判定是**比周围几厘米的皮肤**更红或更暗（`--uv-cm` 给出贴图一个单位在身上是多少厘米，用来定"周围"3.5 cm 和
    边缘 7 mm），小于 0.2 cm² 的碎点丢掉；整块都红的岛（身体内侧，周围没有皮肤可比）按红度本身算。膝盖、脚底的红晕是缓变的，
    不算特征。同时写出 `<材质>_hm_m.png`（这些部位的遮罩）：皮肤材质在这里**保留游戏自己的细节法线、不铺平铺纹理**——
    平铺纹理是"哪儿都不是"的皮肤，铺在乳晕上被拉成一排梳齿，游戏自己的细节图在那里是乳晕的颗粒。`--only-own` 只重写这张遮罩。
    裸体身体要带这个参数烘（a08 露出的皮肤没有这些部位，脸不带——嘴唇的纹理对得上，留着）。
  - **材质**（`SKIN_LOOK["baked"]`）：微法线按源的 2 倍强度叠在 ROE 法线上（按 1 倍在半米外和没有一样——比像素细的起伏会被
    平均掉），平铺块留 0.7 作为"放大的颗粒"；肤色细节 ×1.5、光泽细节 ×1.0、血管 0.3、厚度让薄的地方多透一点光；出汗时
    水珠从最湿的地方先出现，湿度过 0.55 后汗流才出来，原来均匀的小汗珠减半。
  - **坑**：包里默认的身体肤色图带痣，第一次烘出来她胯上多了一颗——肤色细节改用包里的 NoMoles 那张；Blender 3.6 的 FBX 导入器读不了
    Unity 导出的带蒙皮的 FBX（`link_hierarchy` 里 KeyError），所以 `mishi_fbx.meshes()` 自己读网格、UV、蒙皮和绑定姿势；
    Unity 导出的 cluster `Transform` 是"网格到骨骼"，网格的绑定位置是 `Transform × TransformLink`；8K 的 BC7 贴图编辑器要压一两分钟，
    期间 Python 里查到的尺寸是 32×32 的占位图。
    "特征"第一版的判定是"比全身肤色的中位数红多少"：这个身体的乳晕红 0.10-0.15、膝盖的红晕 0.08-0.12、脚底到 0.19——
    分不开，结果乳晕只标了一半、膝盖上一片碎点。要看的是和周围的反差，不是绝对的红。
    在已有的贴图资产上重新导入，编辑器会往 `Saved\Crashes` 写两份 ensure 报告（`!bIsAReimport`）——不是崩溃，导入照常完成。
  - **检查过的**（男性隐藏后的近景，原版 / v0.1 / v0.2，干和湿；样张在 `out\skin_v0.2_room\`）：身体自己的特征上没有第二圈、
    接缝或错位；脖子接缝修后还剩一条淡线——**原版自己就有**（两块材质在接缝处的遮蔽值 0.64 / 0.75 和细节法线的密度都不一样，
    出汗的高光把它显出来），没有动。脸的贴图比身体密 3.7 倍而水的法线是按像素算的，所以同样的水珠在脸上比在身上扁——也没有动。
  - 贴图都是别人的作品：只在本机（`Import/_local/`、`_work/` 不进仓库）。
- **三档皮肤，运行时切换**（`AMishiCouple::SkinVersion`，键 N / 面板"皮肤" / 机位表 `skin`）：**2 = v0.2** 皮肤包烘进来的
  贴图（材质有的话）+ 减弱的平铺纹理 + 包里的汗流水珠；**1 = v0.1** 只有平铺的细纹毛孔和均匀小汗珠；**0 = 原版** 游戏自己的细节法线、
  没有汗珠（汗膜和潮红还在）。材质里是 `MPC_Mishi` 的两个开关 `SkinBaked` / `SkinRelief`，实例里同时存着三档各自的数值
  （`BakedTile`、`BakedBeads`、`ReliefOn`、游戏的 `DetailStrength`），所以切换不用重建任何东西。对比图也这样拍：同一个机位表里
  写 `"skin": 2` / `1` / `0`。
- **出汗**。场景的湿度 `MPC_Mishi.Wet`（0-1）先是一层**汗膜**：粗糙度降到 `WetRoughness` 0.3、颜色暗 8 %、细纹被填平一半多；
  然后是**汗珠**：`Tools/textures/sweat.png`（`python Tools/make_sweat.py`：R G = 汗珠的法线，B = 汗珠在哪，A = 这颗汗珠在多大的湿度
  出现）—— 湿度越高冒出来的越多，小的先出、大的后出，直径 0.5-2.3 mm（`sweat_tile_cm` 8），3 m 外只剩汗膜的光泽；
  身上的分布不均匀（一片多一片少）。脸上的汗珠量是身体的 0.75（`sweat`）。
- **潮红**：和 Unity 版一样（`RoeSkin.shader`）——满值时颜色 ×(1.07, 0.92, 0.90)，全身略偏暖偏红。
- **谁来推**：蜜室切片按阶段走（潮红 0.1 / 0.35 / 0.6 / 0.9，汗 0 / 0.2 / 0.45 / 0.8，4 秒缓入，`B` 键 / 面板开关）；展示切片不随阶段变。
  机位表可以直接指定：`"wet": 0.8`、`"flush": 0.9` 从这个机位起定住，`-1` 还给阶段。
- **头发高光**。Unreal 的各向异性为正时高光**沿** Tangent 拉长；给的 Tangent 是发丝方向，所以数值必须是负的（`anisotropy` -0.7）
  高光才横跨发丝成一条带。粗糙度 0.5 时带子的宽度和游戏自己的 Kajiya-Kay（幂 15）差不多。游戏的 `_ShiftNoiseMap`
  （沿发丝的条纹噪声）让法线沿发丝前后倾一点（`shift_noise`），每缕头发的高光位置不同，带子是参差的而不是一条直线。
  在房间的柔光里几乎没有高光可言，区别主要在阳光下（展示切片）。
- **开销**：v0.1（细纹、汗、头发）同一时刻前后各测一次（1080p DLAA，蜜室房间）45.2 / 44.6 / 47.8 fps → 45.5 / 45.5 / 47.3 fps，
  量不出差别。v0.2 的烘焙图：三档皮肤是同一个着色器换了几个数，按 N 切换量不出任何东西，所以把皮肤母材质
  **带着这些图 / 不带 / 再带着**各构建一次来测（`import_slice.py <切片> materials --no-baked` 不带：没有这五张图的采样，也没有
  由它们算出的东西；再导入一次不带这个参数就恢复）。出汗 0.8、每个机位三轮，当时显卡同时被别的程序占着，所以数值整体偏低，
  但三次构建受到的占用相同：全景 25.3 / 24.3 / 24.7，脸 23.3 / 22.4 / 22.0，胸口 16.6 / 15.8 / 16.0，腹部 18.1 / 17.9 / 17.5 fps——
  差别在机器自身的漂移之内。**真正花钱的是出汗的皮肤占满画面**：同一轮里同样的机位，干 26.7 / 25.0 / 21.4 / 21.5，
  湿 25.2 / 22.1 / 16.2 / 18.3（胸口近景 -24 %）——那是 v0.1 就有的汗膜（粗糙度 0.3 的高光反射），不是这些图。
  定住的画面连拍 8 帧量闪动（`still_noise.py`，1080p DLAA）：三档皮肤、干湿都一样（房间 0.8-1.1，阳光下 0.7-0.9）。

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
  贴着镜头的细物体也淡出（镜头周围 45 cm 内，`NearFadeRadius`），不管它挡没挡住人。
- **镜头是个球，不是一个点**：不穿墙那条射线很细，缓慢横移的镜头可以绕到一块床板端头的后面而射线还从它旁边一寸处穿过——
  床板又黑又虚地盖住三分之一个画面，直到射线碰上它、镜头才猛地跳到前面（巡游片 p1_side 里有四分之一秒，`film_jitter.py`
  查出来的：帧间差 27）。现在最后 45 cm 路程上再推一个半径 12 cm 的球（`LensClearance` / `LensReach`），球碰到什么镜头就停在它前面。
  镜头还是会"跳"到前面（只是不再先被挡住），所以分镜的横移方向要避开这种位置：p1_side 的 drift 从 -3 改成 +3。
  查是什么东西贴着镜头：进程加 `-MishiCamDebug`，日志里每 3 帧一行 `camdebug`（镜头位置、最近的 8 个网格和尺寸）。

## 检查图和巡游片

`-MishiShots=<json>` 是一张机位表，每个机位可以：按一个阶段键（`phase`）、跳到部位的某一秒（`at`）、
绕游戏的目标转（`yaw` / `y` / `zoom`）或绕她的一根骨骼（`bone` + `from` 骨骼轴方向 + `distance`；
`up` = 画面的上方向也按骨骼轴，躺着的脸也是正的）、慢慢运动（`drift` 度/秒、`rise`、`dolly`、`push` 厘米/秒）、
跑一条控制台命令（`cmd`，做对照实验用）、切换男性画法（`his_style`）、显示面板（`hud`）、
换画质（`upscale`: tsr / dlaa / quality / balanced / performance，`rr`: 光线重建开或关——和面板按钮走同一条路）、
开关展示切片的弹簧 / 技能特效 / UR 光环（`springs`、`fx`: true / false，`aura`: 0 关 / 1 战斗 / 2 常开）、
定住出汗和潮红的程度（`wet`、`flush`: 0-1，-1 还给阶段）、换皮肤版本（`skin`: 2 / 1 / 0，见下）、
特写（`closeup`: 1 脸 / 2 胸 / 0 关，之后的 `yaw` / `y` / `zoom` 就绕那根骨骼转）。
带 `hold`（秒）的机位先把场景定住再拍；再带 `series`: N 就把定住的姿势连拍 N 帧（`<名字>_00.png` …）。
每次运行还在图片旁边写一份 `timing.json`：每个机位跑了多少帧、用了多久、每一帧的耗时，以及引擎自己的四块秒表
（游戏线程 / 渲染线程 / RHI 线程 / 显卡，就是 `stat unit` 显示的那几个数）。
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
| `fx` | **技能特效**：从这个部位的第 0 秒开始回放烘焙好的那一段（见下）。UR 光环不是 cue：它是循环的，按部位亮灭（见下） |
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

**UR 光环**（面板"光环：战斗 / 常开 / 关"；机位表 `aura`: 1 / 2 / 0）：单位的技能表里还有一条不属于任何动作的**循环**时间线 `ur` ——
稀有度 UR 的战斗服共用的增益特效 `FX_H_demonize_ur`：一圈贴着身体的橙色火焰（25 张大公告板，不透明度最高只有 3.5%，
靠 ×36 的 HDR 自发光发亮）加十几颗火星。游戏里它就很淡，这里也一样：头肩上方几缕火焰丝、身边飘着火星。

- **烘焙成首尾相接的一个周期**（`MishiUeEffects.cs` 的 `FxLoop`）。循环的粒子系统一直随机发射，"前 5 秒"的最后一帧和第一帧
  是两批不相干的粒子，照原样循环就是每 5 秒所有粒子同时换一批。做法：先空跑到粒子数稳定（最长寿命 ×2 + 1 秒），再跑两个周期；
  第 f 帧 = 时刻 f 那些"在这个周期里出生"的粒子 + 时刻 f + 周期 那些"在周期结束前出生、年龄大于 f"的粒子
  （`ParticleSystem.SetParticles` 摆好再 `BakeMesh`）。每个粒子的一生恰好出现一遍，寿命跨过周期末尾的那段绕回开头。
  量过：接缝处出生 + 消失的粒子 0–2 个，平时相邻两帧最多 3 个。`fx.json` 里这段动作标 `"loop": true`，300 帧。
- **什么时候亮**：`slice.json` 的 `aura`（`make_showcase.py` 的 `AURA_PARTS`）—— 战斗站姿、三个技能、受击；展示姿势和互动
  （图鉴里的姿势）不亮，倒下不亮。"常开"则除了倒下都亮。0.4 秒淡入淡出。它和技能特效互不相干
  （另一个 `FMishiFx` + 自己的网格），技能期间照样烧；路径追踪的机位里和技能特效一起隐藏。
- **跟着她的胯**：游戏把它挂在单位原点（`transformPivot/VfxAnchor/ur`）。可是动作片段会把她带离原点好几米
  （大招收尾 2.3 m，技能 2 前冲 1.6 m），照搬的话火焰会留在她身后的空地上烧。这里让它待在她胯的正下方、
  单位所在的地面高度，滞后 0.1 秒（胯的晃动不传给火焰）。
- **亮度**：技能特效的自发光统一 ×0.3（不然火花烧成一片白）。光环的火焰本来就是"很亮的颜色 × 很低的不透明度"，
  进到画面里只有 1 左右，再 ×0.3 就只剩 Unity 里的三分之一，看不见。所以**只被循环动作用到的材质**另算：
  自发光最强分量 × 粒子最高不透明度（烘焙时记在 `fx.json` 的 `max_alpha`）不超过 1.5 的不压，超过的压到刚好 1.5、
  最多压到 0.3（`FX_LOOK["aura_knee"]`）。于是火焰 ×1，火星（不透明度到 1、自发光 24）仍是 ×0.3。
- Unity 里的对照图（按游戏自己的时间线播）：
  `.\tools\unity_batch.ps1 -Method RoeFighter.EditorTools.RoeSkillTest.Run -Graphics -Extra '-roeChar','a08','-roeAction','ur','-roeTimes','1,2,3,4.5','-roeOut','<目录>'`

## 画面风格：游戏 / 电影（`mishi_look.py` 的 `STYLE` / `STYLES`）

风格是盖在 `LOOK` 表上面的一层，**建关卡时**生效（曝光、补光比例、暗角、调色都写进关卡的后期体积和灯里）：

```powershell
python Tools\ue_remote.py Tools\import_slice.py a08_s01 level                 # 默认风格 cinema
python Tools\ue_remote.py Tools\import_slice.py a08_s01 level --style game    # 换回游戏风（或环境变量 MISHI_STYLE）
```

| | game（游戏原样） | cinema（用户 11-21："偏电影"） |
|---|---|---|
| 思路 | 明亮、均匀，皮肤压在影调曲线高处 | 低调：主光比补光强，身体有受光面和背光面 |
| 曝光 | 蜜室 -1.1，展示 -0.7 | 蜜室 -1.4，展示 -1.1 |
| 补光 | 蜜室 fill 0.35 / 天空板 0.10 / 天光 1.0；展示跟机补光 0.5 / 天光 0.7 | 0.25 / 0.08 / 0.8；0.3 / 0.62 |
| 影调 | 引擎默认胶片曲线 | 斜率 0.92、趾部 0.57、肩部 0.30，对比 1.03，最深的暗部提一点（gamma 1.06：暗角是暗的不是死黑） |
| 颜色 | — | 饱和度 0.93，高光偏暖 (1.04, 1, 0.95)、暗部偏冷 (0.95, 1, 1.06) |
| 其它 | 暗角 0.25 / 0.3 | 暗角 0.42，胶片颗粒 0.18 |

11-22 起两部成片和所有定格图都是电影风（成片用 DLAA 录）；之前游戏风的留在旁边作对照：`out\*_tour_game.mp4`、`out\stills\*_game`。

量出来（`Tools/measure_look.py`：画面亮度分位数、皮肤亮度；`Tools/ab_sheet.py` 把两个检查图文件夹拼成左右对比）：皮肤中位数基本不变（0.5–0.6），整幅画面中位数 0.49 → 0.36（a08），
接近全黑的像素 3% → 6%（a08）、4% → 12%（蜜室全景）。`grade` 里的键就是引擎后期设置的名字，想加什么直接加。

## 画质选项：TSR / DLSS（可选插件）

装了 NVIDIA 的 DLSS 插件、显卡也支持时，**启动就是 DLSS**（用户 11-22："打开默认就是dlss"）—— DLAA 档：原生分辨率，只用它做抗锯齿，
量下来画面最稳，还比 TSR 快一点（见下面两张表）。没装插件就是引擎自己的 TSR、100% 分辨率。运行、出图、录片都是这个默认。
面板上多出两个按钮：

- **画质**：TSR → DLAA（原生分辨率，只用 DLSS 做抗锯齿）→ DLSS 质量（渲染 67% 宽度）→ 平衡（58%）→ 性能（50%）
- **光线重建**（DLSS Ray Reconstruction）：Lumen 的反射和阴影改由 DLSS 的一个降噪器处理（只在 DLSS 开着时可用）

```powershell
# 安装（编辑器关着）：zip 是 NVIDIA 官方的 "DLSS 4.5 plugin for UE 5.8"（developer.nvidia.com/rtx/dlss，公开链接，1.2 GB；
# 经代理很慢的话 curl 加 --noproxy "*"）
python Tools\install_dlss.py E:\tools\ue_dlss\UE5.8_DLSS4.5Plugin_v8.9.0.zip
powershell -File Tools\ue.ps1 cpp
# 运行 / 出图 / 录片：不写 -Upscale 就是 DLAA（没装插件则 TSR）
powershell -File Tools\ue.ps1 play  -Slice a08_s01                              # 启动就是 DLAA
powershell -File Tools\ue.ps1 play  -Slice a08_s01 -Upscale quality -RR         # tsr | dlaa | quality | balanced | performance；-RR = 光线重建
powershell -File Tools\ue.ps1 shots -Slice a08_s01 -Tag x -Upscale tsr          # 要引擎自己的 TSR
```

- 插件放在 `Plugins/`（**不进仓库**：NVIDIA 的二进制，按它的 RTX SDK 许可分发），`MishiUE.uproject` 里标成可选：没装照常编译运行，只有 TSR。
- 游戏模块不依赖插件的模块：按名字找它 Blueprint 库的静态函数（`QueryDLSSSupport` / `EnableDLSS` / `EnableDLSSRR`）来调用，
  分辨率档位就是 `r.ScreenPercentage`。`EnableDLSSRR` 自己知道要关掉哪些 Lumen 的降噪（并在关闭时恢复）。
- `Config/DefaultEngine.ini`：`bAllowOTAUpdate=False`（不从应用里联网取新模型）、`bShowDLSSSDebugOnScreenMessages=False`（画面里不出调试字）。
- **路径追踪的机位**：引擎在路径追踪期间本来就不跑任何时域放大器（`FSceneRenderer`："path tracer does its own anti-aliasing"），
  DLSS 也不跑。所以 DLSS **保持开着不动**，只做两件事：把渲染比例暂时拉回 100%（质量 / 平衡 / 性能档下路径追踪也要画满分辨率），
  让插件别把闲置的网络丢掉（`r.NGX.FramesUntilFeatureDestruction`：它默认闲置 3 帧就销毁，定格图之间又要重建）。
  **不要在定格图前后开关 DLSS**：原来是"拍之前关、拍完再开"，第二张定格图就把显卡弄崩了
  （D3D12 PageFault / device removed：网络刚建好 14 帧又被拆掉）。现在两张表 25 张定格图连着出，网络只建一次。
- 驱动里的 NGX 仍会在初始化时拉起若干 `nvngx_update.exe` 去联网查更新，可能一直挂着：`ue.ps1` 等的是引擎进程本身，
  结束后把它拉起的这些进程清掉。
- 帧生成（DLSS-G）没有接：还要装 Streamline 那几个插件（`install_dlss.py --frame-generation`），只对实时运行有意义。
- 插件自己记着光线重建：关 DLSS 时它顺手把光线重建关掉，但记下"之前开着"，下次开 DLSS 又自动打开——面板这时显示的却是关。
  所以 `SetUpscale` 每次都明确告诉它要不要（`EnableDLSSRR`）。

### 帧率（`ue.ps1 bench`）

```powershell
powershell -File Tools\ue.ps1 bench -Slice a08_s01 -ResX 3840 -ResY 2160 -Tag r2160     # 离屏渲染，任何分辨率都行；不写分辨率 = 1920x1080
python Tools\bench_table.py Saved\MishiShots\a08_s01_bench_r1080 Saved\MishiShots\a08_s01_bench_r1440 Saved\MishiShots\a08_s01_bench_r2160
```

`Tools/shots_bench.json` 在**一次运行**里把八种组合轮四遍（机位表的 `upscale` / `rr`），每次先让它稳定 1 秒、再量 3 秒同一段展示动作，
并各存一张图。出图时场景的时钟固定每秒 30 步、画面能多快就多快，所以"帧数 / 用时"就是这档画质能跑到的帧率。
a08_s01 展示动作、RTX 4090 Laptop、硬件光追 Lumen（帧/秒）：

| 画质 | 1920×1080 | 2560×1440 | 3840×2160 |
|---|---|---|---|
| TSR 100%（默认） | 89 | 63 | 32 |
| DLAA | 96 | 73 | 36 |
| DLAA + 光线重建 | 74 | 48 | 23 |
| DLSS 质量（67%） | 112 | 113 | 63 |
| DLSS 质量 + 光线重建 | 110 | 83 | 44 |
| DLSS 平衡（58%） | 114 | 103 | 73 |
| DLSS 性能（50%） | 128 | 112 | 81 |
| DLSS 性能 + 光线重建 | 133 | 116 | 69 |

- 110–130 帧已经是 CPU 的上限（渲染线程一帧 7.5–9 ms）：1080p 和 1440p 上 DLSS 各档之间的差别在测量误差之内。
  分辨率越高差得越开：4K 下质量档是 TSR 的 2 倍，性能档 2.6 倍。
- DLAA 比 TSR 还快一点（TSR 在全分辨率上自己就不便宜）；光线重建要掉 15–35% 的帧率。
- **机器不空闲也能量**：显卡被别的程序分走时（另一个窗口在跑 Blender 批处理：显卡 100% 十几秒、歇两三秒，循环），
  同一档画质一帧要么 10 ms 要么 55 ms，整段平均出来的数毫无意义（TSR 16–91 帧都量到过）。`bench_table.py` 把每档四轮的逐帧耗时
  切成 45 帧的片段，只认**没被打扰**的那些（最快片段的 1.25 倍以内），取它们的中位数；"undisturbed" 一列是这种片段占的比例，
  空闲的机器上接近 100%。某一格比上下两格离谱、比例又只有百分之几，就是那一档从头到尾没碰上空档：再跑一遍，
  同一分辨率的几次运行可以一起交给 `bench_table.py`，它会合并。
- 单帧的耗时不能直接用：离屏出图没有交换链把游戏线程拦住，它会领先显卡几帧，然后一次等上几百毫秒（6 6 6 6 60 19 403 …）。

### 怎么选（量出来的）

`Tools/shots_noise.json` + `Tools/still_noise.py`：把姿势定住、关掉胶片颗粒，连拍 16 帧。场景里什么都没动，帧与帧之间的差别
就是渲染器自己的不安分（Lumen 的噪声、抗锯齿的抖动、亮边的闪烁）。a08 和蜜室各三个机位（全身 / 胸 / 脸），1920×1080：

| | TSR | DLAA | DLAA + 光线重建 |
|---|---|---|---|
| 闪动（每个像素偏离 16 帧平均值多少，8 位亮度级） | 0.21–0.34 | **0.15–0.22** | 0.16–0.32 |
| 最闪的 1% 画面 | 0.9–3.9 | **0.6–1.3** | 0.7–3.6 |
| 细节（16 帧平均图的拉普拉斯标准差，TSR = 1） | 1 | 0.90–0.95 | 1.01–1.10 |

- **DLAA 最稳**：闪动比 TSR 低三四成，差别主要在发丝上；细节略少一点（TSR 带锐化）。
- **光线重建**：细节比 TSR 还多一点，但不比 DLAA 稳（金属边缘、发丝更闪），还掉帧。它是为反射 / 阴影噪声很重的场景准备的，
  这两个场景里 Lumen 自己的降噪已经够干净。想要最锐的单张图可以开，录片不开。
- 运动中（把三段技能分别用 TSR 和 DLAA 逐帧录下来对比）两者几乎一样，没有看到论坛上说的 DLSS 拖影。
- 所以**默认就是 DLAA**，成片和 4K 的特效定格图都用它录；路径追踪的定格图不受影响。没装插件就是 TSR，差别不大。

## 操作

| 输入 | 作用 |
|---|---|
| 左键拖动 | 转镜头（左右偏航，上下改轨道高度） |
| 右键拖动 | 平移目标（限制在游戏允许的盒子里） |
| 滚轮 / Q E / PageUp PageDown | 缩放 |
| A D / ← →，W S / ↑ ↓ | 偏航，轨道高度 |
| 中键 / Home | 镜头复位 |
| F | **特写：脸 → 胸 → 关**（面板"特写"按钮同样）—— 镜头绕她的头 / 胸转，滚轮能拉近到 10 cm（游戏原版的轨道最近只到 0.2 倍，这个场景是 66 cm）；右键拖动微调对准的位置 |
| 1 2 3 4 | 阶段 1-4（和游戏一样：先走过渡部位）；展示切片：1-9 是九个动作 |
| 空格 | 自动开 / 关 |
| V | 语音：日 → 英 → 关 |
| M | 男性：皮肤 → 剪影 → 隐藏 |
| X / B | 部位音效 / 潮红出汗 开关（展示切片默认关：按 B 再按 4，汗和潮红几秒后出来；1 / 2 / 3 / 4 = 汗 0 / 0.2 / 0.45 / 0.8） |
| N | **皮肤：v0.2 → v0.1 → 原版**（面板上的"皮肤"按钮同样）—— 当场对比新旧皮肤 |
| H | 面板显示 / 隐藏 |
| 面板（展示切片） | 技能镜头、物理（弹簧）、特效、**光环**（战斗 → 常开 → 关）；装了 DLSS 插件还有画质、光线重建 |

## 踩过的坑

- **Unreal 的 Python 把 bool 属性名开头的 b 去掉**：C++ 里同时有 `bSkinState`（开关）和 `SkinState`（材质参数集）时，两个在 Python 里都叫
  `skin_state`，拿到的是那个 bool。导入脚本给它赋参数集失败，又被一句 `except: pass` 吞掉——结果参数集从来没挂上，
  **UE 版的出汗和潮红几个星期里一直没生效**，直到 11-22 做汗珠时三档湿度拍出来一模一样才发现。现在参数集叫 `SkinCollection`，
  没挂时 BeginPlay 自己按路径加载，赋值失败会报警告。教训：属性名不要只差一个 b；`set_editor_property` 的失败不要静默。
- 各向异性的符号：见"皮肤和头发的近景"。+0.8 用了很久，高光一直是顺着发丝的亮线，没人把它当高光带。
- 材质 Custom 节点接向量参数要选 `RGBA` 输出：默认输出是 RGB，代码里写 `.zw` 编译失败，游戏里整个材质变成灰色棋盘格
  （日志 `Failed to compile Material`）。
- 实例参数写了一半脚本就报错的话，实例已经被 `clear_all_material_instance_parameters` 清空——同样是一头灰发；修好脚本重跑即可。
- 测帧率要同一时刻 A/B：笔记本显卡热了以后同一画面会慢 7 %（下午 49 fps，傍晚 45 fps），和改动无关。
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
- 机位表的 `bone` 也可以是男方的骨骼（`Bip000-R-Hand`：女方骨架里没有这个名字就找男方）；`"hide_her": true` 只留男方
  （看他的手、手腕）。路径追踪的机位自动把技能特效连同它们的灯一起关掉（特效不在光追场景里，只剩地上一片橙光更怪）。
- 机位表里 `from` 是**骨骼轴**方向；只有 `bone` 没有 `from` 是绕那根骨骼转（`yaw` / `y` / `zoom`）。
  一个机位同时给 `phase` + `at` 再拍很短的时间，拍到的是混合途中的姿势：先用一个 `_` 机位进入那个部位。
- **程序化网格的 UV 是 16 位浮点**（`FStaticMeshVertexBuffer` 默认半精度）：往一个 UV 里打包"整数部分 + 小数部分"会被截掉
  （特效的自发光色相变成黄 / 品红的色块）。2048 以内的整数能原样通过。
- 顶点切线会被引擎对着法线**正交化**：想借切线多带一个向量（真实法线）不行，带进去的是它垂直于法线的那部分。
- 双面材质画封闭网格时，背面的菲涅尔项是满的（`1 - saturate(N·V)` = 1）：发光外壳变成一整块白。按游戏的 `_Cull` 剔掉背面。
- Unity `ParticleSystemRenderer.BakeMesh` 默认把本地空间的粒子系统留在本地空间：烘焙时加 `BakeRotationAndScale | BakePosition`。
  一个技能里两个挂点可以重名（Skill3_hit01）：时间线节点不能按名字合并。
- **男方的手腕错位 = 上面说的"阶梯"**（用户 11-21："男性的动作似乎手腕有问题"）：前臂骨骼（单轴的肘关节）是阶梯的，
  而带着前臂蒙皮的扭转骨骼 `ForeTwist` / `ForeTwist1` 挂在**上臂**下面、自己有平滑的曲线。于是手掌骨骼跟着停住的前臂走，
  前臂的皮跟着扭转骨骼走：旧轨道里手掌离前臂末端平均 1 cm、最大 8.8 cm，前臂骨和扭转骨最多差 21°——手腕被扯开、还一跳一跳。
  去掉阶梯后最大 0.13 cm / 0.3°。量法：在上臂空间里分别用"前臂 → 手"和"ForeTwist → ForeTwist1 → 末端"算手腕位置，求差。
  `python Tools\check_tracks.py Import\<切片>` 一条命令出这三样：阶梯轨道数、负缩放骨骼、两只手腕的错位。
  女方同理（a08 和蜜室都已重新导出）。eros15_07 女方 445 条、男方 178 条骨骼轨道是阶梯的，脚趾一跳 50°、男方小腿一跳 24°。
- **重建母材质后，别的切片整个变灰**：`mishi_materials.Graph` 原来是把母材质资产删掉再新建——所有切片里引用它的材质实例
  都丢了父级（没有父级的实例 = 引擎的灰色默认材质，带棋盘格），只有当时正在导入的那个切片被重新关联。
  a08 那次升级母材质版本之后，eros15_07 的 89 个实例里 87 个没有父级，一周后才发现。现在母材质**原地重建**
  （清空节点重搭，资产不换），实例的父级一直在；检查：`python Tools\ue_remote.py Tools\check_parents.py`。
- **出图 / 录片等着色器和资源编译完再开拍**（`StepShots` 开头）：材质的着色器还在编译时画出来的是灰色默认材质，
  贴图还在生成时是灰块；缓存是冷的（母材质刚重建、换了机器）时整部片子都是。
- **右肩塌陷 = 一根镜像的辅助骨骼**：她两肩的三角肌各由一个辅助球骨骼撑着（`GeoSphere001` / `GeoSphere002`，挂在上臂下面，
  随手臂反向转动）。右边那个是左边的镜像拷贝，缩放是 (-1.133, -1.133, -1.133)。FBX 导入建参考姿势时把镜像去掉了
  （旋转不变、缩放变正），而动作轨道里还是负缩放 —— 蒙皮矩阵 = 动画 × 参考姿势的逆，两边不一致，这根骨骼管的那块皮
  就绕着关节被翻到身体里去了：肩头没了，手臂像从腋下长出来（手臂离绑定姿势越远越明显）。
  过原点的镜像（三个轴都负）在"动画 × 逆绑定"里本来是抵消的，所以 `mishi_anim.py` 写轨道时把它去掉；
  只有一两个轴为负的是真镜像，保留并报警。查法：`female_anim.bin` 里找缩放为负的骨骼，对比骨架参考姿势的缩放。
- 出图 / 录片的 `-game` 进程也开着 Python 远程执行：它在跑的时候 `ue_remote.py` 可能连到它而不是编辑器
  （报 `module 'unreal' has no attribute 'CustomMaterialOutputType'` 之类缺编辑器类的错）。等出图进程结束再导入。
- **DLSS 开了又关、关了又开，中间只隔十几帧，显卡会缺页崩溃**（日志 `LogD3D12RHI: Error: PageFault ... GPU Crashed or D3D Device Removed`，
  进程退出码 3）。出在路径追踪定格图上：每张图"关 DLSS → 拍 → 开 DLSS"，两张图之间只有半秒。见"画质选项"里路径追踪那条。
  面板上连续点"画质"按钮各档之间至少隔了一次点击的时间，量帧率时每档隔 1 秒以上，都没出过问题。
- **量帧率时先看显卡是不是只有自己在用**：`nvidia-smi` 看占用和功耗，`timing.json` 里显卡那块秒表（card ms）在 10 和 55 之间跳、
  和画质档位无关，就是有别的程序在分显卡。两天里量出的"DLSS 各档忽快忽慢"全是这个原因，不是 DLSS 的问题。见"画质选项 · 帧率"。
- **循环的特效不能烘"前 N 秒"拿去循环**：粒子是随机发射的，末帧和首帧是两批粒子，接缝处全体换人。
  要烘成周期性的一段（见"UR 光环"）。另外带预热（prewarm）的系统重启后的头几帧粒子数也不稳（19 → 9 → 25）。
- **特效材质第一次被画时会漏**：引擎可能还在给它建管线状态，这几帧就不画——技能 1 的第一刀在出图里时有时无地缺一串火花，
  画面渲染得快的时候（DLSS 质量档）整帧特效都没有。开场时 `FMishiFx::Prewarm` 用每个特效材质各画一个半毫米的三角形（24 帧）。
- **出图进程的日志窗口被点一下，整个进程就暂停**（Windows 控制台的"快速编辑"：标题变成"选择 ..."，写日志的线程卡住）。
  `ue.ps1` 不再带 `-log`（没有控制台窗口，日志照样在 `Saved\Logs`）。
- PowerShell 的 `Start-Process -Wait` 等的是**整个进程树**：引擎拉起的子进程不退出它就一直等（DLSS 的 `nvngx_update.exe`）。
  改成 `-PassThru` 之后 `$p.WaitForExit()`（先取一次 `$p.Handle`，否则退出码读不到）。
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
- Groom 发丝（没有发丝数据，只有发片）、Substrate 皮肤、路径追踪的动态片段（Movie Render Queue）
- 头发近看像"铁丝"：发片贴图只有 512 px，每缕画得粗。可以试 AI 放大贴图，或在材质里把每缕再分细
- 潮红只是全身偏暖；脸颊 / 耳朵 / 胸口的局部红晕需要一张区域遮罩（游戏的 MGAC.A 不是）
- 回忆模式、换身体、更多场景和房间、选择菜单
- 打包（Cook）：中文字体在打包版里需要带一个 CJK 字体
