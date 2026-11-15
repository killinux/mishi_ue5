#include "MishiCameraPawn.h"
#include "MishiCouple.h"
#include "MishiUE.h"
#include "Camera/CameraComponent.h"
#include "CollisionQueryParams.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/HitResult.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
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

bool AMishiCameraPawn::IsSlender(const UPrimitiveComponent* Comp) const
{
	const UStaticMeshComponent* Mesh = Cast<UStaticMeshComponent>(Comp);
	if (!Mesh || !Mesh->GetStaticMesh())
		return false;
	// the object's own box, not the world's (which grows when a long board stands at an angle)
	const FVector Size = Mesh->GetStaticMesh()->GetBounds().BoxExtent * 2.0 * Mesh->GetComponentScale().GetAbs();
	return Size.X + Size.Y + Size.Z - Size.GetMax() - Size.GetMin() < SlenderSize;
}

void AMishiCameraPawn::UpdateSeeThrough(float DeltaSeconds, const FVector& Pos)
{
	AMishiCouple* C = Couple.Get();
	const UWorld* W = GetWorld();
	if (!C || !W)
		return;
	// the lines of sight to the bodies: what a slender thing crosses of them, it hides
	TSet<UPrimitiveComponent*> Between;
	if (bSeeThrough)
	{
		// her skeleton is Bip001, his Bip000
		static const FName Bones[] = {TEXT("Bip001-Head"), TEXT("Bip001-Neck"), TEXT("Bip001-Spine2"), TEXT("Bip001-Pelvis"),
			TEXT("Bip001-L-UpperArm"), TEXT("Bip001-R-UpperArm"), TEXT("Bip001-L-Forearm"), TEXT("Bip001-R-Forearm"),
			TEXT("Bip001-L-Hand"), TEXT("Bip001-R-Hand"), TEXT("Bip001-L-Thigh"), TEXT("Bip001-R-Thigh"),
			TEXT("Bip001-L-Calf"), TEXT("Bip001-R-Calf"), TEXT("Bip001-L-Foot"), TEXT("Bip001-R-Foot"),
			TEXT("Bip000-Head"), TEXT("Bip000-Neck"), TEXT("Bip000-Spine1"), TEXT("Bip000-Pelvis"),
			TEXT("Bip000-L-UpperArm"), TEXT("Bip000-R-UpperArm"), TEXT("Bip000-L-Hand"), TEXT("Bip000-R-Hand"),
			TEXT("Bip000-L-Thigh"), TEXT("Bip000-R-Thigh"), TEXT("Bip000-L-Calf"), TEXT("Bip000-R-Calf"),
			TEXT("Bip000-L-Foot"), TEXT("Bip000-R-Foot")};
		for (const USkeletalMeshComponent* Body : {C->GetHer(), C->GetHim()})
		{
			if (!Body || !Body->IsVisible())
				continue;
			for (const FName& Bone : Bones)
			{
				if (Body->GetBoneIndex(Bone) == INDEX_NONE)
					continue;
				FVector At = Body->GetBoneLocation(Bone);
				if (Bone.ToString().EndsWith(TEXT("-Head")))
					At += Body->GetBoneQuaternion(Bone).RotateVector(FVector(9.0, -3.0, 0.0));      // the head's middle, not the top of the neck
				FCollisionQueryParams Params(SCENE_QUERY_STAT(MishiSeeThrough), true);
				Params.AddIgnoredActor(this);
				Params.AddIgnoredActor(C);
				FVector From = Pos;
				for (int32 Step = 0; Step < 6; ++Step)
				{
					FHitResult Hit;
					if (!W->LineTraceSingleByChannel(Hit, From, At, ECC_Camera, Params))
						break;
					UPrimitiveComponent* Comp = Hit.GetComponent();
					if (!Comp || !IsSlender(Comp))
						break;                                  // furniture and walls stay
					if (FVector::DistSquared(Hit.Location, At) > FMath::Square(25.0))      // what the body rests against stays
						Between.Add(Comp);
					Params.AddIgnoredComponent(Comp);
					From = Hit.Location;
				}
			}
		}
	}
	for (UPrimitiveComponent* Comp : Between)
		Faded.FindOrAdd(Comp).Hold = SeeThroughHold;
	for (auto It = Faded.CreateIterator(); It; ++It)
	{
		UPrimitiveComponent* Comp = It.Key().Get();
		if (!Comp)
		{
			It.RemoveCurrent();
			continue;
		}
		FFade& F = It.Value();
		if (bCut && !Between.Contains(Comp))
			F.Hold = 0.f;                               // a cut shows the new view as it is
		// out quickly, back in gently and only after it has stayed out of the way for a moment
		const float Want = F.Hold > 0.f ? 1.f : 0.f;
		const float Ease = Want > F.Amount ? 0.12f : 0.35f;
		F.Amount = bCut || DeltaSeconds <= 0.f ? Want : FMath::Lerp(F.Amount, Want, 1.f - FMath::Exp(-DeltaSeconds / Ease));
		if (FMath::Abs(F.Amount - Want) < 0.01f)
			F.Amount = Want;
		F.Hold = FMath::Max(F.Hold - DeltaSeconds, 0.f);
		Comp->SetCustomPrimitiveDataFloat(0, F.Amount);   // LensFade of the room's materials
		if (F.Amount <= 0.f && F.Hold <= 0.f)
			It.RemoveCurrent();
	}
}

float AMishiCameraPawn::FreeFraction(const FVector& Target, const FVector& Pos) const
{
	const UWorld* W = GetWorld();
	const double Dist = (Pos - Target).Size();
	if (!W || Dist < 30.0)
		return 1.f;
	const FVector Dir = (Pos - Target) / Dist;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(MishiCamera), true);        // against the meshes' own triangles
	Params.AddIgnoredActor(this);
	if (Couple.IsValid())
		Params.AddIgnoredActor(Couple.Get());
	FVector From = Target;
	for (int32 Step = 0; Step < 12; ++Step)
	{
		FHitResult Hit;
		if (!W->LineTraceSingleByChannel(Hit, From, Pos, ECC_Camera, Params))
			return 1.f;
		const double At = (Hit.Location - Target) | Dir;
		const UPrimitiveComponent* Comp = Hit.GetComponent();
		// a slender thing only passes through the picture (and fades where it hides the couple); a wall, a headboard or a
		// mattress is what the camera must not end up behind
		if (Comp && IsSlender(Comp))
		{
			Params.AddIgnoredComponent(Comp);
			From = Hit.Location + Dir * 1.0;
			continue;
		}
		return float(FMath::Clamp((At - 12.0) / Dist, 0.08, 1.0));
	}
	return 1.f;
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
		const FVector Eyes = C->GetHer()->GetBoneLocation(FocusBone) + C->GetHer()->GetBoneQuaternion(FocusBone).RotateVector(FocusOffset);
		const FVector Local = Look.UnrotateVector(Eyes - Pos);       // x forward, y right, z up
		if (Local.X > 5.0)
		{
			const double TanV = FMath::Tan(FMath::DegreesToRadians(VerticalFov * 0.5));
			const double Sx = Local.Y / (Local.X * TanV * Aspect), Sy = Local.Z / (Local.X * TanV);
			if (FMath::Abs(Sx) < 0.95 && FMath::Abs(Sy) < 0.95)
				Want = float(Local.X);
		}
	}
	const float K = FocusEase > 0.f && DeltaSeconds > 0.f && !bCut ? 1.f - FMath::Exp(-DeltaSeconds / FocusEase) : 1.f;
	Focus = FMath::Lerp(Focus, Want, K);
	PP.DepthOfFieldFocalDistance = Focus;
	PP.DepthOfFieldSensorWidth = 36.f;
	// a real lens: the depth of field shrinks with the square of the distance - wide open a face at half a metre is sharp over
	// millimetres.  The lens stops down as far as SharpDepth asks (depth of field ~ 2 N c s^2 / f^2, c = 0.03 mm on full frame).
	const double FocalMm = 36.0 / (2.0 * FMath::Tan(FMath::DegreesToRadians(VerticalFov * 0.5)) * Aspect);
	const double SMm = FMath::Max(double(Focus), 10.0) * 10.0;
	const double Needed = SharpDepth * 10.0 * FocalMm * FocalMm / (2.0 * 0.03 * SMm * SMm);
	PP.DepthOfFieldFstop = float(FMath::Clamp(FMath::Max(double(Aperture), Needed), 1.2, 22.0));
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
	FVector Pos = C->UnityToWorld(PosU);
	FVector Target = C->UnityToWorld(TargetU);
	FVector Up = C->UnityDirToWorld(Anchor.Rot.RotateVector(FVector(0, 1, 0)));
	if (bPoseOverride)
	{
		Pos = PoseOverridePos;
		Target = PoseOverrideTarget;
		Up = PoseOverrideUp;
	}
	else if (bAvoidWalls)
	{
		// in at once, out again gently
		const float Free = FreeFraction(Target, Pos);
		const float Ease = Free < Pull ? 0.05f : 0.5f;
		Pull = DeltaSeconds > 0.f && !bCut ? FMath::Lerp(Pull, Free, 1.f - FMath::Exp(-DeltaSeconds / Ease)) : Free;
		Pos = Target + (Pos - Target) * FMath::Min(Pull, 1.f);
	}
	const FRotator Look = FRotationMatrix::MakeFromXZ(Target - Pos, Up).Rotator();
	SetActorLocationAndRotation(Pos, Look);
	UpdateSeeThrough(DeltaSeconds, Pos);
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
	if (DeltaSeconds > 0.f)
		bCut = false;
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
