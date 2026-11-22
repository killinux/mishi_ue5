// Mouse and keys of the eros mode (as in the Unity version: left drag turns, right drag pans, wheel zooms, middle click / Home
// resets; 1-4 phases, Space auto, V voice language, M him, H the panel) and the Slate panel over the view.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "MishiPlayerController.generated.h"

class AMishiCouple;
class AMishiCameraPawn;
class SMishiHud;

UCLASS()
class MISHIUE_API AMishiPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	/** The picture's upscaler: 0 the engine's TSR at full size, 1 DLAA, 2 DLSS quality, 3 balanced, 4 performance.  1-4 are
	    NVIDIA's DLSS (Plugins/DLSS - optional, Tools/install_dlss.py): without the plugin or a card that can, 0 stays. */
	void SetUpscale(int32 Mode);
	int32 GetUpscale() const { return Upscale; }
	/** DLSS ray reconstruction: one trained denoiser for Lumen's reflections and the shadows instead of the engine's own
	    (only with DLSS on: it runs in the same pass). */
	void SetRayReconstruction(bool bOn);
	bool GetRayReconstruction() const { return bRayReconstruction; }
	static bool HasDLSS();
	static bool HasRayReconstruction();
	/** tsr, dlaa, quality, balanced, performance -> 0..4 (INDEX_NONE: none of them). */
	static int32 UpscaleByName(const FString& Name);
	/** "TSR", "DLAA + RR", "DLSS quality" ...: what the picture is made with now. */
	FString PictureName() const;

	AMishiPlayerController();

	AMishiCouple* GetCouple() const { return Couple.Get(); }
	AMishiCameraPawn* GetCam() const;
	void ToggleHud();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void PlayerTick(float DeltaTime) override;

private:
	TSharedPtr<SMishiHud> Hud;
	TWeakObjectPtr<AMishiCouple> Couple;
	FVector2D LastCursor = FVector2D::ZeroVector;
	bool bHadCursor = false;
	bool bHudShown = true;

	float Axis(const FKey& Minus1, const FKey& Minus2, const FKey& Plus1, const FKey& Plus2) const;

	// -MishiShots=<file.json> -MishiShotsDir=<dir>: look-dev stills.  Each shot presses a phase button (or none), sets a view - round
	// the rig's target or round a bone of hers - lets the scene run for some seconds and saves one frame <dir>/<name>.png; then quit.
	// A shot whose name starts with "_" takes no picture: it only moves the scene on (a phase button and its transition).
	// A shot with "hold" or "pt" makes a still of one held pose: the bodies and the camera stop, the renderer settles (hold, in
	// seconds) or the path tracer adds its samples (pt, samples a pixel: ray tracing must be on in the project), then the picture.
	// With -MishiTour every frame of every shot is saved instead (<dir>/frame_00000.bmp ...): the same list is a film, cut by cut
	// (Tools/ue.ps1 tour runs it with -benchmark -fps=30, so 30 frames are a second of the scene).
	struct FShot
	{
		FString Name;
		int32 Phase = -1;
		float Seconds = 2.f;
		float YawOffset = 0.f;            // degrees from the game's own yaw
		float Y = -1.f;                   // orbit height 0..1 (< 0: the game's own)
		float ZoomScale = 1.f;            // x the game's own zoom
		FString Bone;                     // orbit round this bone of hers (empty: the rig's target)
		FVector BoneOffset = FVector::ZeroVector;   // cm, world axes, added to the bone's place
		FVector BoneOffsetLocal = FVector::ZeroVector;   // cm, in the bone's own axes
		float Fov = 0.f;                  // vertical degrees (0: the game's)
		bool bFrom = false;               // the camera along a direction of the bone's own axes instead of on the orbit
		FVector From = FVector::ZeroVector;   // that direction, in the bone's space (the bone's turning is followed slowly)
		bool bUp = false;                 // the picture's up along a direction of the bone's own axes instead of the world's
		FVector Up = FVector::UpVector;   // ([1, 0, 0] on the head bone: her face upright in the picture however she lies)
		float Distance = 60.f;            // cm from the bone
		FString Command;                  // a console command run when the shot starts (look-dev experiments)
		float Drift = 0.f;                // degrees a second the orbit turns during the shot (a film's slow move)
		float Rise = 0.f;                 // orbit height a second
		float Dolly = 0.f;                // the orbit's zoom changes by this share of itself a second (negative: moves in)
		float Push = 0.f;                 // cm a second a bone shot's camera moves in (negative) or out
		float At = -1.f;                  // seconds into the part at which the shot starts (< 0: the scene just runs on)
		int32 HisStyle = -1;              // 0 skin, 1 silhouette, 2 hidden (< 0: as it is)
		float Hold = 0.f;                 // a still of a held pose: the scene stops for this many seconds before the picture
		                                  // (Lumen and the temporal upscaler settle on a picture that no longer moves)
		int32 PathTrace = 0;              // a path-traced still: the pose is held and the path tracer adds this many samples a pixel
		float PathTraceEv = 0.3f;         // stops of exposure added while it does: the path tracer's fog dims the light on its way
		                                  // (the rasterizer's only adds its glow), its picture is about that much darker
		bool bHud = false;
		bool bHideHim = false;
		bool bHideHer = false;                // "hide_her": him alone (looking at his hands, his wrists)
		bool bSkillCam = false;       // "skill_cam": the game's own camera has the shot while the skill's timeline runs one
		int32 Springs = -1, Fx = -1;  // "springs" / "fx": the bone cloth / the skills' effects on or off from this shot on (-1: as it is)
		int32 Aura = -1;              // "aura": the buff's aura from this shot on - 0 off, 1 in battle, 2 on every part (-1: as it is)
		FString Upscale;              // "upscale": the picture's upscaler from this shot on (tsr, dlaa, quality, balanced, performance)
		int32 RayReconstruction = -1; // "rr": DLSS ray reconstruction on or off from this shot on (-1: as it is)
		int32 Series = 0;             // "series": with "hold", this many frames of the held pose are saved (<name>_00.png ...) - what
		                              // differs between them is the renderer's own unrest (Tools/still_noise.py)
	};
	/** How long a shot took: the scene's clock runs at 30 steps a second in a capture, the frames come as fast as they are
	    rendered - Tools/ue.ps1 bench reads the frame rates of the upscalers from it (timing.json beside the pictures). */
	struct FShotTime
	{
		FString Name, Picture;
		int32 Frames = 0;
		double Seconds = 0.0;
		double GameMs = 0.0, RenderMs = 0.0, RhiMs = 0.0, GpuMs = 0.0;    // a frame's share of each thread and of the card, on average
		TArray<float> FrameMs;            // every frame's own time: on a machine that is doing other things too, the undisturbed
		                                  // frames are still there to be read (Tools/bench_table.py)
	};
	struct FSoundMark
	{
		int32 Frame = 0;
		FString Kind, File;
		float Volume = 1.f;
	};
	TArray<FShot> Shots;
	bool bShots = false;
	int32 Upscale = 0;
	bool bRayReconstruction = false;
	int32 ShotIndex = -1;
	float ShotClock = 0.f;
	float ShotY = 0.5f, ShotZoom = 1.f;
	bool bShotStart = false;
	FVector ShotAt = FVector::ZeroVector;      // a bone shot looks here: the bone's place, followed softly
	FVector ShotDir = FVector::ForwardVector;  // from there to the camera, and the picture's up: the bone's axes in the world,
	FVector ShotUp = FVector::UpVector;        // followed slowly (the camera does not swing with every nod of a head)
	int32 ShotQuitFrames = 0;
	int32 ShotWaitFrames = 0, ShotReadyFrames = 0;   // waiting for shaders and assets to be built before the first shot
	int32 StillStage = 0;                 // 0 none, 1 the scene is held for a still, 2 its picture is taken
	int32 StillFrames = 0;                // frames left until the picture
	bool bStillPathTraced = false;
	int32 StillUpscale = 0;                 // the upscaler a path-traced still put aside
	int32 StillSeries = 0;                  // frames of a held pose still to be saved
	TArray<FShotTime> ShotTimes;
	double ShotRealStart = 0.0;
	int32 ShotFrameCount = 0;
	double ShotGameMs = 0.0, ShotRenderMs = 0.0, ShotRhiMs = 0.0, ShotGpuMs = 0.0;
	double ShotLastFrame = 0.0;
	TArray<float> ShotFrameMs;
	void CountFrame();
	void WriteTiming() const;
	void BeginStill(const FShot& S);
	void EndStill();
	void HoldScene(bool bHold);
	bool bRecordAll = false;
	int32 RecordFrame = 0;
	FString ShotsDir;
	TArray<FSoundMark> SoundMarks;        // -MishiTour: what sounded when, written to <dir>/timeline.json with the shots' first frames
	TArray<int32> ShotFrames;
	FDelegateHandle SoundHandle;
	void WriteTimeline() const;
	void StartShots(const FString& File);
	void StepShots(float DeltaTime);
};
