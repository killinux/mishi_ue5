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

	/** Depth of field: a real lens - full-frame sensor, the focal length the field of view gives, this aperture.  The focus follows
	 *  her face while it is in the picture, the orbit's target otherwise. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bDepthOfField = true;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	float Aperture = 2.0f;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	FName FocusBone = TEXT("Bip001-Head");

	/** Seconds the focus takes to settle on a new distance. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float FocusEase = 0.25f;

	void Setup(AMishiCouple* InCouple);
	void ResetView();
	void SetView(float InYaw, float InY, float InZoom);
	void Turn(float DxPixels, float DyPixels);
	void Pan(float DxPixels, float DyPixels);
	void ZoomBy(float Notches);
	void Keys(float DeltaSeconds, float Yaw, float Height, float Zoom);   // held keys, each -1..1

	/** Orbit round a point of the world (a bone) instead of the rig's own target; ClearTargetWorld goes back. */
	void SetTargetWorld(const FVector& World) { bTargetOverride = true; TargetOverrideWorld = World; }
	void ClearTargetWorld() { bTargetOverride = false; }
	/** Vertical field of view in degrees (<= 0: the game's own). */
	void SetFovOverride(float VerticalDegrees) { FovOverride = VerticalDegrees; }
	/** The game's limits on zoom and pan (off for the look-dev shots, which go closer than the game lets the player). */
	bool bLimits = true;
	/** Distance from the camera to what it orbits, cm - the focus distance for the depth of field. */
	float FocusDistance() const { return LastDistance; }

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
	bool bTargetOverride = false;
	FVector TargetOverrideWorld = FVector::ZeroVector;
	float FovOverride = 0.f;
	float LastDistance = 300.f;
	float Focus = 300.f;
	void UpdateLens(float DeltaSeconds, const FVector& Pos, const FRotator& Look, float VerticalFov, double Aspect);

	float ZoomMax() const { return FMath::Max(Rig.ZoomMax, Rig.Zoom * 3.f); }
	FVector2D Orbit(float At) const;
	void UpdatePose(float DeltaSeconds = 0.f);
};
