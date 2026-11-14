#include "MishiCameraPawn.h"
#include "MishiCouple.h"
#include "MishiUE.h"
#include "Camera/CameraComponent.h"
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
	Zoom = FMath::Clamp(InZoom, Rig.ZoomMin, ZoomMax());
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

void AMishiCameraPawn::UpdatePose()
{
	AMishiCouple* C = Couple.Get();
	if (!C)
		return;
	Y = FMath::Clamp(Y, 0.f, 1.f);
	Zoom = FMath::Clamp(Zoom, Rig.ZoomMin, ZoomMax());
	// the pan stays inside the box the game allows (anchor space)
	const FVector Box = Rig.BoxCenter - Rig.Target;
	PanU.X = FMath::Clamp(PanU.X, Box.X - Rig.BoxExtent.X, Box.X + Rig.BoxExtent.X);
	PanU.Y = FMath::Clamp(PanU.Y, Box.Y - Rig.BoxExtent.Y, Box.Y + Rig.BoxExtent.Y);
	PanU.Z = FMath::Clamp(PanU.Z, Box.Z - Rig.BoxExtent.Z, Box.Z + Rig.BoxExtent.Z);
	const FVector2D O = Orbit(Y);
	// Unity: rot = anchor.rotation * Euler(0, yaw, 0); offset = rot * (0, height, -radius) * zoom; the camera looks at the target
	const FQuat YawQ(FVector(0, 1, 0), FMath::DegreesToRadians(Yaw));
	const FQuat Rot = Anchor.Rot * YawQ;
	const FVector TargetU = Anchor.TransformPoint(Rig.Target + PanU);
	const FVector OffsetU = Rot.RotateVector(FVector(0, O.X, -O.Y)) * Zoom;
	const FVector PosU = TargetU + OffsetU;
	const FVector Pos = C->UnityToWorld(PosU);
	const FVector Target = C->UnityToWorld(TargetU);
	const FVector Up = C->UnityDirToWorld(Anchor.Rot.RotateVector(FVector(0, 1, 0)));
	const FRotator Look = FRotationMatrix::MakeFromXZ(Target - Pos, Up).Rotator();
	SetActorLocationAndRotation(Pos, Look);
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
				const double Half = FMath::DegreesToRadians(Rig.Fov * 0.5);
				Camera->SetFieldOfView(float(FMath::RadiansToDegrees(2.0 * FMath::Atan(FMath::Tan(Half) * Aspect))));
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
	UpdatePose();
}
