// The eros mode's free-look camera, rebuilt from the numbers of the game's Cinemachine rig (slice.json "camera"): an orbit round a
// target through three rigs (bottom / middle / top: height and radius), a yaw, a zoom scaling the orbit, a target panned inside a box.
// The orbit is worked out in Unity's space under the posture's camera anchor (as the Unity version does) and then put into Unreal's.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "MishiSlice.h"
#include "MishiCameraPawn.generated.h"

class UCameraComponent;
class AMishiCouple;

UCLASS()
class MISHIUE_API AMishiCameraPawn : public APawn
{
	GENERATED_BODY()

public:
	AMishiCameraPawn();

	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<UCameraComponent> Camera;

	/** Degrees of yaw / orbit height / metres of pan per pixel of mouse drag, the zoom step per wheel notch (the Unity version's). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float TurnPerPixel = 0.2f;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	float HeightPerPixel = 0.00625f;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	float PanPerPixel = 0.003f;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	float ZoomPerNotch = 0.1f;

	void Setup(AMishiCouple* InCouple);
	void ResetView();
	void SetView(float InYaw, float InY, float InZoom);
	void Turn(float DxPixels, float DyPixels);
	void Pan(float DxPixels, float DyPixels);
	void ZoomBy(float Notches);
	void Keys(float DeltaSeconds, float Yaw, float Height, float Zoom);   // held keys, each -1..1

	float GetYaw() const { return Yaw; }
	float GetY() const { return Y; }
	float GetZoom() const { return Zoom; }
	float DefaultZoom() const { return Rig.Zoom; }
	float DefaultYaw() const { return Rig.XAxis; }

	virtual void Tick(float DeltaSeconds) override;

private:
	TWeakObjectPtr<AMishiCouple> Couple;
	FMishiCameraSetup Rig;
	FMishiUnityXform Anchor;              // the camera anchor relative to the couple (Unity space)
	float Yaw = 0.f, Y = 0.5f, Zoom = 1.f;
	FVector PanU = FVector::ZeroVector;   // Unity, anchor space
	FVector RightU = FVector(1, 0, 0), UpU = FVector(0, 1, 0);   // the camera's right / up in anchor space (for panning)

	float ZoomMax() const { return FMath::Max(Rig.ZoomMax, Rig.Zoom * 3.f); }
	FVector2D Orbit(float At) const;
	void UpdatePose();
};
