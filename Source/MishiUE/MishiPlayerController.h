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
	// With -MishiTour every frame of every shot is saved instead (<dir>/frame_00000.png ...): the same list is a film, cut by cut
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
		bool bHud = false;
		bool bHideHim = false;
	};
	struct FSoundMark
	{
		int32 Frame = 0;
		FString Kind, File;
		float Volume = 1.f;
	};
	TArray<FShot> Shots;
	bool bShots = false;
	int32 ShotIndex = -1;
	float ShotClock = 0.f;
	float ShotY = 0.5f, ShotZoom = 1.f;
	bool bShotStart = false;
	FVector ShotAt = FVector::ZeroVector;      // a bone shot looks here: the bone's place, followed softly
	FVector ShotDir = FVector::ForwardVector;  // from there to the camera, and the picture's up: the bone's axes in the world,
	FVector ShotUp = FVector::UpVector;        // followed slowly (the camera does not swing with every nod of a head)
	int32 ShotQuitFrames = 0;
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
