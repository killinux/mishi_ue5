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

	// -MishiTour -MishiTourDir=<dir>: a fixed path through the scene, one frame a tick into the folder (Tools/ue.ps1 tour runs it with
	// -benchmark -fps=30, so 30 frames are a second of the scene), then quit
	struct FTourStop
	{
		int32 Phase;                      // the phase button pressed at the stop (-1: none, the scene goes on)
		float Seconds;
		float YawOffset;                  // degrees from the game's own yaw
		float Y;                          // orbit height 0..1 (< 0: the game's own)
		float ZoomScale;                  // x the game's own zoom
	};
	TArray<FTourStop> Tour;
	bool bTour = false;
	int32 TourIndex = -1;
	float TourClock = 0.f;
	float TourStopStart = 0.f;
	int32 TourFrame = 0;
	FString TourDir;
	float FromYaw = 0.f, FromY = 0.5f, FromZoom = 1.f;
	void StartTour();
	void StepTour(float DeltaTime);
