// The eros mode's free-look camera, rebuilt from the numbers of the game's Cinemachine rig (slice.json "camera"): an orbit round a
// target through three rigs (bottom / middle / top: height and radius), a yaw, a zoom scaling the orbit, a target panned inside a box.
// The orbit is worked out in Unity's space under the posture's camera anchor (as the Unity version does) and then put into Unreal's.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "MishiSlice.h"
#include "MishiCameraPawn.generated.h"

class UCameraComponent;
class UDirectionalLightComponent;
class AMishiCouple;

UCLASS()
class MISHIUE_API AMishiCameraPawn : public APawn
{
	GENERATED_BODY()

public:
	AMishiCameraPawn();

	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<UCameraComponent> Camera;

	/** The fill that goes with the camera: a directional light along the view (from a little above it), on the bodies' lighting
	 *  channel only, without shadows or bounce - the same on her at any distance.  Off unless the couple asks for it. */
	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<UDirectionalLightComponent> Fill;

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

	/** From the head bone (at the top of the neck) to between her eyes, in the bone's own axes: +X up the head, -Y out of the face. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	FVector FocusOffset = FVector(7.0, -9.0, 0.0);

	/** What stays sharp round the focus, cm (front to back): close up the lens stops down so a face is sharp from nose to ear. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float SharpDepth = 16.f;

	/** The camera does not sit behind walls or furniture: it comes in front of what stands between it and what it looks at. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bAvoidWalls = true;

	/** Slender things (a bed post, a rail, a lamp's stem) never move the camera: where one stands between the lens and the couple
	 *  it fades out of the picture instead - its shadow and its bounce stay in the room. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bSeeThrough = true;

	/** Slender: the middle side of the object's own box is under this many cm. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float SlenderSize = 50.f;

	/** Seconds a faded thing stays away after it last stood in the way (the bodies move: without it a post would flicker). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float SeeThroughHold = 1.2f;
	/** A slender thing nearer to the lens than this (cm) fades, whether it hides the couple or not. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float NearFadeRadius = 45.f;
	/** The lens as a ball of this radius (cm), pushed along the last LensReach cm of the way: what it meets, the camera stops before. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float LensClearance = 12.f;
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float LensReach = 45.f;

	/** A blow of a skill shakes the camera: cm of sway for a shake of amplitude 1 (the game's Cinemachine impulse). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float ShakeScale = 4.f;

	/** Seconds the focus takes to settle on a new distance. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float FocusEase = 0.25f;

	/** A showcase's orbit goes with her: its centre follows her hips when a skill carries her across the stage (set from the
	 *  slice's kind; the eros postures stay where they are). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bFollow = false;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	FName FollowBone = TEXT("Bip001");

	/** Where the hips are when she stands: cm above the actor. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float FollowHeight = 96.f;

	/** Seconds the camera takes to catch up with her. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float FollowEase = 0.22f;

	/** A skill is seen through the game's own camera while its timeline has one (behind the unit, following its dash); off: the
	 *  orbit stays.  A showcase starts with it on. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bSkillCamera = false;

	/** The game's camera has the picture now. */
	bool IsGameCamera() const { return bSkillCamera && GameCamLeft > 0.f; }

	void Setup(AMishiCouple* InCouple);
	/** The rig's numbers are read (the first tick after the couple is ready). */
	bool IsSetUp() const { return Couple.IsValid(); }
	void ResetView();
	void SetView(float InYaw, float InY, float InZoom);
	void Turn(float DxPixels, float DyPixels);
	void Pan(float DxPixels, float DyPixels);
	void ZoomBy(float Notches);
	void Keys(float DeltaSeconds, float Yaw, float Height, float Zoom);   // held keys, each -1..1

	/** Orbit round a point of the world (a bone) instead of the rig's own target; ClearTargetWorld goes back. */
	void SetTargetWorld(const FVector& World) { bTargetOverride = true; TargetOverrideWorld = World; }
	void ClearTargetWorld() { bTargetOverride = false; }
	/** The camera at a place of the world looking at another (look-dev shots along a bone's axis); ClearPose goes back to the orbit. */
	void SetPose(const FVector& WorldPos, const FVector& WorldTarget, const FVector& WorldUp = FVector::UpVector)
	{
		bPoseOverride = true;
		PoseOverridePos = WorldPos;
		PoseOverrideTarget = WorldTarget;
		PoseOverrideUp = WorldUp;
	}
	void ClearPose() { bPoseOverride = false; }
	/** Vertical field of view in degrees (<= 0: the game's own). */
	void SetFovOverride(float VerticalDegrees) { FovOverride = VerticalDegrees; }
	/** A cut: the next frame stands where the walls leave it and focuses at once, without easing in from the last view. */
	void Cut() { bCut = true; }
	/** The game's limits on zoom and pan (off for the look-dev shots, which go closer than the game lets the player). */
	bool bLimits = true;
	/** Distance from the camera to what it orbits, cm - the focus distance for the depth of field. */
	float FocusDistance() const { return LastDistance; }

	float GetYaw() const { return Yaw; }
	float GetY() const { return Y; }
	float GetZoom() const { return Zoom; }
	float DefaultZoom() const { return Rig.Zoom; }
	float DefaultYaw() const { return Rig.XAxis; }
	float DefaultY() const { return Rig.YAxis; }

	virtual void Tick(float DeltaSeconds) override;

private:
	TWeakObjectPtr<AMishiCouple> Couple;
	FMishiCameraSetup Rig;
	FMishiUnityXform Anchor;              // the camera anchor relative to the couple (Unity space)
	float Yaw = 0.f, Y = 0.5f, Zoom = 1.f;
	FVector PanU = FVector::ZeroVector;   // Unity, anchor space
	FVector RightU = FVector(1, 0, 0), UpU = FVector(0, 1, 0);   // the camera's right / up in anchor space (for panning)
	bool bPoseOverride = false;
	FVector PoseOverridePos = FVector::ZeroVector, PoseOverrideTarget = FVector::ZeroVector, PoseOverrideUp = FVector::UpVector;
	bool bTargetOverride = false;
	FVector TargetOverrideWorld = FVector::ZeroVector;
	float FovOverride = 0.f;
	float LastDistance = 300.f;
	float Focus = 300.f;
	float Pull = 1.f;                     // how much of the orbit's distance the walls leave (eased)
	FVector Follow = FVector::ZeroVector; // how far the orbit has gone with her (world, eased)
	float GameCamLeft = 0.f, GameCamFov = 40.f;       // the game's camera: seconds it still has, its vertical field of view,
	FVector GameCamPosU = FVector::ZeroVector;        // its place and turn in the unit's space (Unity),
	FQuat GameCamRotU = FQuat::Identity;
	FVector GameCamAt = FVector::ZeroVector;          // where it is now (world, eased behind the unit)
	bool bGameCamFresh = false;
	FDelegateHandle CameraHandle;
	void CutView();
	float ShakeAmplitude = 0.f, ShakeSeconds = 0.f, ShakeFrequency = 18.f, ShakeClock = 0.f;
	FDelegateHandle ShakeHandle;
	bool bCut = true;
	struct FFade
	{
		float Amount = 0.f;               // 0 whole .. 1 gone
		float Hold = 0.f;                 // seconds it still stays away after the last time it stood in the way
		float Sent = -1.f;                // what the component was told last (told again only when it changes)
	};
	TMap<TWeakObjectPtr<UPrimitiveComponent>, FFade> Faded;   // what hides the couple now or did a moment ago
	bool IsSlender(const UPrimitiveComponent* Comp) const;
	float FreeFraction(const FVector& Target, const FVector& Pos) const;
	void UpdateSeeThrough(float DeltaSeconds, const FVector& Pos);
	void UpdateLens(float DeltaSeconds, const FVector& Pos, const FRotator& Look, float VerticalFov, double Aspect);

	float ZoomMax() const { return FMath::Max(Rig.ZoomMax, Rig.Zoom * 3.f); }
	FVector2D Orbit(float At) const;
	void UpdatePose(float DeltaSeconds = 0.f);
};
