#include "MishiCameraPawn.h"
#include "Engine/OverlapResult.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "MishiCouple.h"
#include "MishiUE.h"
#include "Camera/CameraComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "CollisionQueryParams.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/HitResult.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"

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
	Fill = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("Fill"));
	Fill->SetupAttachment(Camera);
	Fill->SetRelativeRotation(FRotator(-14.f, 0.f, 0.f));       // from a little above the lens
	Fill->SetMobility(EComponentMobility::Movable);
	Fill->SetVisibility(false);
	Fill->Intensity = 0.f;
	Fill->CastShadows = false;
	Fill->bAtmosphereSunLight = false;
	Fill->ForwardShadingPriority = 0;                           // the level's sun stays the sun of the fog and of translucent things
	Fill->VolumetricScatteringIntensity = 0.f;
	Fill->IndirectLightingIntensity = 0.f;                      // (Lumen's surface cache knows no channels: no bounce of it)
	Fill->LightingChannels.bChannel0 = false;                   // the bodies' channel alone: the stage keeps its own light
	Fill->LightingChannels.bChannel1 = true;
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
	if (InCouple->Slice().Kind == TEXT("showcase"))
	{
		bFollow = true;
		SharpDepth = FMath::Max(SharpDepth, 36.f);      // close up, an armour plate is sharp from its front edge to its back one
	}
	if (InCouple->CameraFill > 0.f)
	{
		Fill->SetIntensity(InCouple->CameraFill);
		Fill->SetLightColor(InCouple->CameraFillColor);
		Fill->SetLightSourceAngle(InCouple->CameraFillAngle);
		Fill->SetVisibility(true);
	}
	else
		Fill->SetVisibility(false);
	if (!CameraHandle.IsValid())
		CameraHandle = InCouple->OnCamera.AddWeakLambda(this, [this](float Seconds, float Fov, const FVector& PosU, const FQuat& RotU)
		{
			const bool bWas = GameCamLeft > 0.f;
			GameCamLeft = FMath::Max(Seconds, 0.f);
			if (Seconds > 0.f)
			{
				GameCamFov = Fov;
				GameCamPosU = PosU;
				GameCamRotU = RotU;
				bGameCamFresh = true;
			}
			if (bSkillCamera && (bWas || Seconds > 0.f))
				CutView();                                  // into it and out of it by a cut
		});
	if (!ShakeHandle.IsValid())
		ShakeHandle = InCouple->OnShake.AddWeakLambda(this, [this](float Amplitude, float Seconds, float Frequency)
		{
			ShakeAmplitude = Amplitude;
			ShakeSeconds = FMath::Max(Seconds, 0.05f);
			// the timeline's number (0.2 .. 0.6) is the gain on the game's noise profile, not a rate: as hertz it would be a
			// slow drift nobody sees.  A blow shakes at 12 .. 24 Hz.
			ShakeFrequency = 12.f + 12.f * FMath::Clamp(Frequency, 0.f, 1.f);
			ShakeClock = 0.f;
		});
	ResetView();
	UpdatePose();
}

void AMishiCameraPawn::CutView()
{
	// no easing in from the last view, and no temporal history of the last picture
	bCut = true;
	if (const UWorld* W = GetWorld())
		if (APlayerController* PC = W->GetFirstPlayerController())
			if (PC->PlayerCameraManager)
				PC->PlayerCameraManager->SetGameCameraCutThisFrame();
}

void AMishiCameraPawn::ResetView()
{
	CloseUp = 0;
	ClosePanU = FVector::ZeroVector;
	Yaw = Rig.XAxis;
	Y = Rig.YAxis;
	Zoom = Rig.Zoom;
	PanU = FVector::ZeroVector;
}

void AMishiCameraPawn::SetCloseUp(int32 Which)
{
	Which = FMath::Clamp(Which, 0, 2);
	if (Which == CloseUp)
		return;
	if (CloseUp == 0)
		ZoomBefore = Zoom;
	CloseUp = Which;
	ClosePanU = FVector::ZeroVector;
	if (CloseUp == 0)
		Zoom = ZoomBefore;
	else
	{
		// it begins at arm's length from the face, a little more from the chest (Orbit: metres at zoom 1)
		const float Base = FMath::Max(float(Orbit(Y).Size()), 0.01f);
		Zoom = (CloseUp == 1 ? 0.4f : 0.65f) / Base;
	}
	bCut = true;
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
	if (CloseUp > 0)
	{
		// (a pixel shifts the aim by as much as it shows: less, the nearer the lens)
		const float K = PanPerPixel * FMath::Clamp(Zoom / FMath::Max(Rig.Zoom, 0.01f), 0.02f, 1.f);
		ClosePanU -= RightU * (DxPixels * K) - UpU * (DyPixels * K);
		ClosePanU = ClosePanU.GetClampedToMaxSize(0.25);
		return;
	}
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
	if (bSeeThrough)
	{
		// ... and what the lens is about to brush past.  A slender thing does not stop the camera, so a drifting camera can pass
		// a bed post at a few centimetres: no line to a body crosses it, and yet it sweeps over half the picture, dark and out
		// of focus, for a quarter of a second (the film's p1_side shot).  Whatever slender stands within reach of the lens fades.
		TArray<FOverlapResult> Near;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(MishiSeeThroughNear), true);
		Params.AddIgnoredActor(this);
		Params.AddIgnoredActor(C);
		if (W->OverlapMultiByChannel(Near, Pos, FQuat::Identity, ECC_Camera, FCollisionShape::MakeSphere(NearFadeRadius), Params))
			for (const FOverlapResult& O : Near)
				if (UPrimitiveComponent* Comp = O.GetComponent())
					if (IsSlender(Comp))
						Between.Add(Comp);
		// (-MishiCamDebug: what stands within 1.2 m of the lens, every few frames)
		static const bool bDebug = FParse::Param(FCommandLine::Get(), TEXT("MishiCamDebug"));
		if (bDebug && GFrameCounter % 3 == 0)
		{
			TArray<FOverlapResult> Around;
			W->OverlapMultiByChannel(Around, Pos, FQuat::Identity, ECC_Camera, FCollisionShape::MakeSphere(120.f), Params);
			Around.Sort([&Pos](const FOverlapResult& A, const FOverlapResult& B)
			{
				return A.GetComponent() && B.GetComponent()
					&& A.GetComponent()->Bounds.ComputeSquaredDistanceFromBoxToPoint(Pos) < B.GetComponent()->Bounds.ComputeSquaredDistanceFromBoxToPoint(Pos);
			});
			FString Line;
			TSet<const UPrimitiveComponent*> Seen;
			for (const FOverlapResult& O : Around)
				if (const UPrimitiveComponent* Comp = O.GetComponent())
				{
					if (Seen.Contains(Comp) || Seen.Num() >= 8)
						continue;
					Seen.Add(Comp);
					const UStaticMeshComponent* Mesh = Cast<UStaticMeshComponent>(Comp);
					const FVector Size = Mesh && Mesh->GetStaticMesh() ? Mesh->GetStaticMesh()->GetBounds().BoxExtent * 2.0 * Mesh->GetComponentScale().GetAbs() : FVector::ZeroVector;
					Line += FString::Printf(TEXT(" %s(%.0fx%.0fx%.0f%s d%.0f)"), Mesh && Mesh->GetStaticMesh() ? *Mesh->GetStaticMesh()->GetName() : *Comp->GetName(), Size.X, Size.Y, Size.Z,
						IsSlender(Comp) ? TEXT(" slender") : TEXT(""), FMath::Sqrt(Comp->Bounds.ComputeSquaredDistanceFromBoxToPoint(Pos)));
				}
			UE_LOG(LogMishi, Log, TEXT("camdebug f%llu pos (%.0f %.0f %.0f) near %d between %d:%s"), GFrameCounter, Pos.X, Pos.Y, Pos.Z, Near.Num(), Between.Num(), *Line);
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
		if (F.Amount != F.Sent)
		{
			Comp->SetCustomPrimitiveDataFloat(0, F.Amount);      // LensFade of the room's materials
			F.Sent = F.Amount;
		}
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
			break;
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
	// ... and what the lens itself would touch.  The line is thin: the drifting camera can come up behind the end of a board
	// with the line still passing an inch beside it - the board fills a third of the picture, dark and out of focus, until
	// the line meets it and the camera jumps in front (the film's p1_side shot, a quarter of a second).  A ball the size of
	// the lens, pushed along the last stretch of the way, meets the board before it comes into the picture.
	const double Stretch = FMath::Min(Dist - 20.0, double(LensReach));
	for (int32 Step = 0; Step < 6 && Stretch > 5.0; ++Step)
	{
		FHitResult Hit;
		if (!W->SweepSingleByChannel(Hit, Pos - Dir * Stretch, Pos, FQuat::Identity, ECC_Camera, FCollisionShape::MakeSphere(LensClearance), Params))
			break;
		const UPrimitiveComponent* Comp = Hit.GetComponent();
		if (Comp && IsSlender(Comp))
		{
			Params.AddIgnoredComponent(Comp);           // (it fades: UpdateSeeThrough)
			continue;
		}
		const double At = Hit.bStartPenetrating ? Dist - Stretch : ((Hit.ImpactPoint - Target) | Dir);
		return float(FMath::Clamp((At - 12.0 - LensClearance) / Dist, 0.08, 1.0));
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
		// (a close-up may go in to 10 cm from the bone it rides on)
		Zoom = CloseUp > 0 ? FMath::Clamp(Zoom, 0.10f / FMath::Max(float(Orbit(Y).Size()), 0.01f), ZoomMax())
			: FMath::Clamp(Zoom, Rig.ZoomMin, ZoomMax());
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
		const FVector L = C->Home().InverseTransformPosition(TargetOverrideWorld);      // (Home: UnityToWorld's own frame)
		TargetU = FVector(-L.X, L.Z, L.Y) / 100.0;
	}
	// a close-up: the target rides on her head (a hand's breadth before and above the bone at the skull's base: the face)
	// or her chest, the orbit goes with it
	const USkeletalMeshComponent* Ridden = C->GetHer();
	const FName CloseBone = CloseUp == 1 ? FName(TEXT("Bip001-Head")) : FName(TEXT("Bip001-Spine2"));
	const bool bClose = CloseUp > 0 && !bTargetOverride && !bPoseOverride && Ridden && Ridden->GetBoneIndex(CloseBone) != INDEX_NONE;
	if (bClose)
	{
		const FVector Local = CloseUp == 1 ? FVector(6.0, -6.0, 0.0) : FVector(0.0, -6.0, 0.0);
		const FVector World = Ridden->GetBoneLocation(CloseBone) + Ridden->GetBoneQuaternion(CloseBone).RotateVector(Local);
		const FVector L = C->Home().InverseTransformPosition(World);
		TargetU = FVector(-L.X, L.Z, L.Y) / 100.0 + (Anchor.TransformPoint(ClosePanU) - Anchor.TransformPoint(FVector::ZeroVector));
	}
	const FVector OffsetU = Rot.RotateVector(FVector(0, O.X, -O.Y)) * Zoom;
	const FVector PosU = TargetU + OffsetU;
	FVector Pos = C->UnityToWorld(PosU);
	FVector Target = C->UnityToWorld(TargetU);
	FVector Up = C->UnityDirToWorld(Anchor.Rot.RotateVector(FVector(0, 1, 0)));
	// a showcase: the orbit goes with her hips - a skill carries her metres across the stage - but not with her swaying on the spot
	const USkeletalMeshComponent* Her = C->GetHer();
	if (bFollow && !bClose && !bTargetOverride && !bPoseOverride && Her && Her->GetBoneIndex(FollowBone) != INDEX_NONE)
	{
		FVector Want = Her->GetBoneLocation(FollowBone) - C->Home().GetLocation() - FVector(0.0, 0.0, FollowHeight);
		Want.Z *= 0.5;                                  // a leap lifts the view half as far
		Want *= FMath::SmoothStep(12.0, 40.0, Want.Size());
		const float K = DeltaSeconds > 0.f && !bCut && FollowEase > 0.f ? 1.f - FMath::Exp(-DeltaSeconds / FollowEase) : 1.f;
		Follow = FMath::Lerp(Follow, Want, K);
		Pos += Follow;
		Target += Follow;
	}
	else
		Follow = FVector::ZeroVector;
	// a skill's own camera, as the game's timeline has it: it hangs on the unit (behind her, where the skill is made to be seen
	// from - she dashes off and turns to it), goes with the unit's dash, and hands back to the orbit by a cut
	if (GameCamLeft > 0.f && DeltaSeconds > 0.f)
	{
		GameCamLeft -= DeltaSeconds;
		if (GameCamLeft <= 0.f && bSkillCamera)
			CutView();
	}
	const bool bGameCam = bSkillCamera && GameCamLeft > 0.f && !bPoseOverride && !bTargetOverride;
	if (bGameCam)
	{
		const FTransform Unit = C->GetActorTransform();
		const FVector Want = Unit.TransformPosition(MishiSpace::Position(GameCamPosU));
		GameCamAt = bGameCamFresh || DeltaSeconds <= 0.f ? Want : FMath::Lerp(GameCamAt, Want, 1.f - FMath::Exp(-DeltaSeconds / 0.12f));
		bGameCamFresh = false;
		Pos = GameCamAt;
		Target = Pos + Unit.TransformVectorNoScale(MishiSpace::Direction(GameCamRotU.RotateVector(FVector(0.0, 0.0, 1.0)))) * GameCamPosU.Size() * 100.0;
		Up = FVector::UpVector;
	}
	if (bPoseOverride)
	{
		Pos = PoseOverridePos;
		Target = PoseOverrideTarget;
		Up = PoseOverrideUp;
	}
	else if (bAvoidWalls && !bGameCam)
	{
		// in at once, out again gently
		const float Free = FreeFraction(Target, Pos);
		const float Ease = Free < Pull ? 0.05f : 0.5f;
		Pull = DeltaSeconds > 0.f && !bCut ? FMath::Lerp(Pull, Free, 1.f - FMath::Exp(-DeltaSeconds / Ease)) : Free;
		Pos = Target + (Pos - Target) * FMath::Min(Pull, 1.f);
	}
	const FRotator Look = FRotationMatrix::MakeFromXZ(Target - Pos, Up).Rotator();
	FVector Shaken = Pos;
	if (ShakeClock < ShakeSeconds)
	{
		// two sines out of step, dying away: the picture sways across and up and down, the look stays on the target's side
		const float Left = 1.f - ShakeClock / ShakeSeconds;
		const float W = ShakeClock * ShakeFrequency * 2.f * PI;
		const FRotationMatrix M(Look);
		Shaken += (M.GetUnitAxis(EAxis::Y) * FMath::Sin(W) + M.GetUnitAxis(EAxis::Z) * FMath::Sin(W * 1.31f + 1.7f))
			* (ShakeAmplitude * ShakeScale * Left * Left);
		ShakeClock += DeltaSeconds;
	}
	SetActorLocationAndRotation(Shaken, Look);
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
				const float VerticalFov = FovOverride > 0.f ? FovOverride : bGameCam ? GameCamFov : Rig.Fov;
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
