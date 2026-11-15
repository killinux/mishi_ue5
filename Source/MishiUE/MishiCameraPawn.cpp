#include "MishiCameraPawn.h"
#include "MishiCouple.h"
#include "MishiUE.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"

AMishiCameraPawn::AMishiCameraPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostPhysics;
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	RootComponent = Camera;
	Camera->bConstrainAspectRatio = false;
	Camera->FieldOfView = 25.f;
	// Unreal's FieldOfView is horizontal; the game's 25 degrees are vertical (Unity), handled in UpdatePose
	SetActorEnableCollision(false);
}

namespace
{
	/** Luf's older posture prefabs give the free-look three identical rigs - no way up or down. A copy with a top rig 1.2 m higher and
	 *  a bottom rig 1.5 m lower keeps the game's own view in the middle (y 0.5) and adds room to move (as the Unity version does). */
	FMishiCameraSetup WithRigs(const FMishiCameraSetup& S)
	{
		if ((S.Top - S.Middle).SizeSquared() > 1e-4 || (S.Bottom - S.Middle).SizeSquared() > 1e-4)
			return S;
		FMishiCameraSetup R = S;
		R.YAxis = 0.5f;
		R.Top = FVector2D(S.Middle.X + 1.2, FMath::Max(0.3, S.Middle.Y * 0.8));
		R.Bottom = FVector2D(FMath::Max(0.1, S.Middle.X - 1.5), FMath::Max(0.6, S.Middle.Y * 1.6));
		return R;
	}
}

void AMishiCameraPawn::Setup(AMishiCouple* InCouple)
{
	Couple = InCouple;
	if (!InCouple || !InCouple->IsReady())
		return;
	Rig = WithRigs(InCouple->Slice().Camera);
	Anchor = InCouple->Slice().PostureAnchor;
	ResetView();
	UpdatePose();
}

void AMishiCameraPawn::ResetView()
{
	Yaw = Rig.XAxis;
	Y = Rig.YAxis;
	Zoom = Rig.Zoom;
	PanU = FVector::ZeroVector;
}

void AMishiCameraPawn::SetView(float InYaw, float InY, float InZoom)
{
	Yaw = InYaw;
	Y = FMath::Clamp(InY, 0.f, 1.f);
	Zoom = bLimits ? FMath::Clamp(InZoom, Rig.ZoomMin, ZoomMax()) : FMath::Max(InZoom, 0.01f);
}

void AMishiCameraPawn::Turn(float DxPixels, float DyPixels)
{
	Yaw += DxPixels * TurnPerPixel;
	Y += DyPixels * HeightPerPixel;        // screen y grows downwards: dragging down lifts the camera, as in the game
}

void AMishiCameraPawn::Pan(float DxPixels, float DyPixels)
{
	PanU -= RightU * (DxPixels * PanPerPixel) - UpU * (DyPixels * PanPerPixel);
}

void AMishiCameraPawn::ZoomBy(float Notches)
{
	Zoom -= Notches * ZoomPerNotch * Zoom;
}

void AMishiCameraPawn::Keys(float DeltaSeconds, float InYaw, float InHeight, float InZoom)
{
	Yaw += 60.f * DeltaSeconds * InYaw;
	Y += 0.4f * DeltaSeconds * InHeight;
	Zoom += 1.2f * DeltaSeconds * InZoom * Zoom;
}

FVector2D AMishiCameraPawn::Orbit(float At) const
{
	FVector2D A, B;
	float T;
	if (At < 0.5f) { A = Rig.Bottom; B = Rig.Middle; T = At * 2.f; }
	else { A = Rig.Middle; B = Rig.Top; T = (At - 0.5f) * 2.f; }
	T = FMath::SmoothStep(0.f, 1.f, T);
	return FMath::Lerp(A, B, double(T));
}

void AMishiCameraPawn::UpdateLens(float DeltaSeconds, const FVector& Pos, const FRotator& Look, float VerticalFov, double Aspect)
{
	FPostProcessSettings& PP = Camera->PostProcessSettings;
	PP.bOverride_DepthOfFieldFstop = true;
	PP.bOverride_DepthOfFieldFocalDistance = true;
	PP.bOverride_DepthOfFieldSensorWidth = true;
	if (!bDepthOfField)
	{
		PP.DepthOfFieldFocalDistance = 0.f;       // 0 = off
		return;
	}
	// what to focus on: her face when the picture holds it, the orbit's target otherwise
	float Want = LastDistance;
	AMishiCouple* C = Couple.Get();
	if (C && C->GetHer() && !FocusBone.IsNone() && C->GetHer()->GetBoneIndex(FocusBone) != INDEX_NONE)
	{
		const FVector Local = Look.UnrotateVector(C->GetHer()->GetBoneLocation(FocusBone) - Pos);       // x forward, y right, z up
		if (Local.X > 5.0)
		{
			const double TanV = FMath::Tan(FMath::DegreesToRadians(VerticalFov * 0.5));
			const double Sx = Local.Y / (Local.X * TanV * Aspect), Sy = Local.Z / (Local.X * TanV);
			if (FMath::Abs(Sx) < 0.95 && FMath::Abs(Sy) < 0.95)
				Want = float(Local.X);
		}
	}
	const float K = FocusEase > 0.f && DeltaSeconds > 0.f ? 1.f - FMath::Exp(-DeltaSeconds / FocusEase) : 1.f;
	Focus = FMath::Lerp(Focus, Want, K);
	PP.DepthOfFieldFocalDistance = Focus;
	PP.DepthOfFieldFstop = Aperture;
	PP.DepthOfFieldSensorWidth = 36.f;
}

void AMishiCameraPawn::UpdatePose(float DeltaSeconds)
{
	AMishiCouple* C = Couple.Get();
	if (!C)
		return;
	Y = FMath::Clamp(Y, 0.f, 1.f);
	if (bLimits)
	{
		Zoom = FMath::Clamp(Zoom, Rig.ZoomMin, ZoomMax());
		// the pan stays inside the box the game allows (anchor space)
		const FVector Box = Rig.BoxCenter - Rig.Target;
		PanU.X = FMath::Clamp(PanU.X, Box.X - Rig.BoxExtent.X, Box.X + Rig.BoxExtent.X);
		PanU.Y = FMath::Clamp(PanU.Y, Box.Y - Rig.BoxExtent.Y, Box.Y + Rig.BoxExtent.Y);
		PanU.Z = FMath::Clamp(PanU.Z, Box.Z - Rig.BoxExtent.Z, Box.Z + Rig.BoxExtent.Z);
	}
	const FVector2D O = Orbit(Y);
	// Unity: rot = anchor.rotation * Euler(0, yaw, 0); offset = rot * (0, height, -radius) * zoom; the camera looks at the target
	const FQuat YawQ(FVector(0, 1, 0), FMath::DegreesToRadians(Yaw));
	const FQuat Rot = Anchor.Rot * YawQ;
	FVector TargetU = Anchor.TransformPoint(Rig.Target + PanU);
	if (bTargetOverride)
	{
		// a world point back in the couple's Unity space (the inverse of MishiSpace::Position)
		const FVector L = C->GetActorTransform().InverseTransformPosition(TargetOverrideWorld);
		TargetU = FVector(-L.X, L.Z, L.Y) / 100.0;
	}
	const FVector OffsetU = Rot.RotateVector(FVector(0, O.X, -O.Y)) * Zoom;
	const FVector PosU = TargetU + OffsetU;
	const FVector Pos = C->UnityToWorld(PosU);
	const FVector Target = C->UnityToWorld(TargetU);
	const FVector Up = C->UnityDirToWorld(Anchor.Rot.RotateVector(FVector(0, 1, 0)));
	const FRotator Look = FRotationMatrix::MakeFromXZ(Target - Pos, Up).Rotator();
	SetActorLocationAndRotation(Pos, Look);
	LastDistance = float((Target - Pos).Size());
	// the camera's right and up back in anchor space, for panning in the screen plane
	const FVector ForwardU = (TargetU - PosU).GetSafeNormal();
	const FVector AnchorUp = Anchor.Rot.RotateVector(FVector(0, 1, 0));
	FVector R = FVector::CrossProduct(AnchorUp, ForwardU).GetSafeNormal();       // Unity is left-handed: up x forward = right
	FVector U = FVector::CrossProduct(ForwardU, R).GetSafeNormal();
	RightU = Anchor.Rot.Inverse().RotateVector(R);
	UpU = Anchor.Rot.Inverse().RotateVector(U);
	// Unity's field of view is vertical, Unreal's horizontal
	if (const UWorld* W = GetWorld())
		if (const UGameViewportClient* V = W->GetGameViewport())
		{
			FVector2D Size;
			V->GetViewportSize(Size);
			if (Size.Y > 1.0)
			{
				const double Aspect = Size.X / Size.Y;
				const float VerticalFov = FovOverride > 0.f ? FovOverride : Rig.Fov;
				const double Half = FMath::DegreesToRadians(VerticalFov * 0.5);
				Camera->SetFieldOfView(float(FMath::RadiansToDegrees(2.0 * FMath::Atan(FMath::Tan(Half) * Aspect))));
				UpdateLens(DeltaSeconds, Pos, Look, VerticalFov, Aspect);
			}
		}
}

void AMishiCameraPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!Couple.IsValid())
		for (TActorIterator<AMishiCouple> It(GetWorld()); It; ++It)
			if (It->IsReady())
			{
				Setup(*It);
				break;
			}
	UpdatePose(DeltaSeconds);
}
