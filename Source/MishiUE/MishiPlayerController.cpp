#include "MishiPlayerController.h"
#include "MishiCameraPawn.h"
#include "MishiCouple.h"
#include "MishiUE.h"
#include "SMishiHud.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"

AMishiPlayerController::AMishiPlayerController()
{
	bShowMouseCursor = true;
	bEnableClickEvents = false;
	bEnableMouseOverEvents = false;
}

AMishiCameraPawn* AMishiPlayerController::GetCam() const
{
	return Cast<AMishiCameraPawn>(GetPawn());
}

void AMishiPlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (!IsLocalController())
		return;
	FInputModeGameAndUI Mode;
	Mode.SetHideCursorDuringCapture(false);
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	SetInputMode(Mode);
	if (UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
	{
		Hud = SNew(SMishiHud).Owner(this);
		Viewport->AddViewportWidgetContent(Hud.ToSharedRef(), 10);
	}
	FString ShotsFile;
	if (FParse::Value(FCommandLine::Get(), TEXT("MishiShots="), ShotsFile))
		StartShots(ShotsFile);
}

void AMishiPlayerController::StartShots(const FString& File)
{
	FString Text;
	TSharedPtr<FJsonValue> Root;
	if (!FFileHelper::LoadFileToString(Text, *File) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid()
		|| Root->Type != EJson::Array)
	{
		UE_LOG(LogMishi, Error, TEXT("shots: %s is not a JSON list"), *File);
		ConsoleCommand(TEXT("quit"));
		return;
	}
	if (!FParse::Value(FCommandLine::Get(), TEXT("MishiShotsDir="), ShotsDir))
		ShotsDir = FPaths::ProjectSavedDir() / TEXT("MishiShots");
	IFileManager::Get().MakeDirectory(*ShotsDir, true);
	for (const TSharedPtr<FJsonValue>& V : Root->AsArray())
	{
		const TSharedPtr<FJsonObject> O = V.IsValid() && V->Type == EJson::Object ? V->AsObject() : nullptr;
		if (!O.IsValid())
			continue;
		FShot& S = Shots.AddDefaulted_GetRef();
		double N = 0.0;
		O->TryGetStringField(TEXT("name"), S.Name);
		if (O->TryGetNumberField(TEXT("phase"), N)) S.Phase = int32(N);
		if (O->TryGetNumberField(TEXT("seconds"), N)) S.Seconds = float(N);
		if (O->TryGetNumberField(TEXT("yaw"), N)) S.YawOffset = float(N);
		if (O->TryGetNumberField(TEXT("y"), N)) S.Y = float(N);
		if (O->TryGetNumberField(TEXT("zoom"), N)) S.ZoomScale = float(N);
		if (O->TryGetNumberField(TEXT("fov"), N)) S.Fov = float(N);
		O->TryGetStringField(TEXT("bone"), S.Bone);
		O->TryGetBoolField(TEXT("hud"), S.bHud);
		O->TryGetBoolField(TEXT("hide_him"), S.bHideHim);
		O->TryGetBoolField(TEXT("skill_cam"), S.bSkillCam);
		bool bFlag = false;
		if (O->TryGetBoolField(TEXT("springs"), bFlag)) S.Springs = bFlag ? 1 : 0;
		if (O->TryGetBoolField(TEXT("fx"), bFlag)) S.Fx = bFlag ? 1 : 0;
		const TArray<TSharedPtr<FJsonValue>>* Off = nullptr;
		if (O->TryGetArrayField(TEXT("offset"), Off) && Off && Off->Num() >= 3)
			S.BoneOffset = FVector((*Off)[0]->AsNumber(), (*Off)[1]->AsNumber(), (*Off)[2]->AsNumber());
		const TArray<TSharedPtr<FJsonValue>>* OffLocal = nullptr;
		if (O->TryGetArrayField(TEXT("offset_local"), OffLocal) && OffLocal && OffLocal->Num() >= 3)
			S.BoneOffsetLocal = FVector((*OffLocal)[0]->AsNumber(), (*OffLocal)[1]->AsNumber(), (*OffLocal)[2]->AsNumber());
		const TArray<TSharedPtr<FJsonValue>>* From = nullptr;
		if (O->TryGetArrayField(TEXT("from"), From) && From && From->Num() >= 3)
		{
			S.bFrom = true;
			S.From = FVector((*From)[0]->AsNumber(), (*From)[1]->AsNumber(), (*From)[2]->AsNumber());
		}
		const TArray<TSharedPtr<FJsonValue>>* UpAxis = nullptr;
		if (O->TryGetArrayField(TEXT("up"), UpAxis) && UpAxis && UpAxis->Num() >= 3)
		{
			S.bUp = true;
			S.Up = FVector((*UpAxis)[0]->AsNumber(), (*UpAxis)[1]->AsNumber(), (*UpAxis)[2]->AsNumber());
		}
		if (O->TryGetNumberField(TEXT("distance"), N)) S.Distance = float(N);
		O->TryGetStringField(TEXT("cmd"), S.Command);
		if (O->TryGetNumberField(TEXT("drift"), N)) S.Drift = float(N);
		if (O->TryGetNumberField(TEXT("rise"), N)) S.Rise = float(N);
		if (O->TryGetNumberField(TEXT("dolly"), N)) S.Dolly = float(N);
		if (O->TryGetNumberField(TEXT("push"), N)) S.Push = float(N);
		if (O->TryGetNumberField(TEXT("at"), N)) S.At = float(N);
		if (O->TryGetNumberField(TEXT("his_style"), N)) S.HisStyle = int32(N);
		if (O->TryGetNumberField(TEXT("hold"), N)) S.Hold = float(N);
		if (O->TryGetNumberField(TEXT("pt"), N)) S.PathTrace = int32(N);
		if (O->TryGetNumberField(TEXT("pt_ev"), N)) S.PathTraceEv = float(N);
		if (S.Name.IsEmpty())
			S.Name = FString::Printf(TEXT("shot_%02d"), Shots.Num());
	}
	bShots = Shots.Num() > 0;
	bRecordAll = FParse::Param(FCommandLine::Get(), TEXT("MishiTour"));
	RecordFrame = 0;
	ShotIndex = -1;
	ShotClock = 0.f;
	UE_LOG(LogMishi, Log, TEXT("shots: %d from %s into %s"), Shots.Num(), *File, *ShotsDir);
}

void AMishiPlayerController::StepShots(float DeltaTime)
{
	AMishiCouple* C = Couple.Get();
	AMishiCameraPawn* Cam = GetCam();
	if (!C || !C->IsReady() || !Cam || !Cam->IsSetUp())
		return;
	if (ShotQuitFrames > 0)
	{
		// the last frame's file is written a frame or two after it was asked for
		if (--ShotQuitFrames == 0)
			ConsoleCommand(TEXT("quit"));
		return;
	}
	C->bAuto = false;
	Cam->bLimits = false;
	if (StillStage == 1)
	{
		// the scene is held: nothing moves until the picture is taken
		if (--StillFrames <= 0)
		{
			const FShot& Held = Shots[ShotIndex];
			FScreenshotRequest::RequestScreenshot(ShotsDir / (Held.Name + TEXT(".png")), Held.bHud, false);
			StillStage = 2;
		}
		return;
	}
	if (StillStage == 2)
		EndStill();
	if (bRecordAll && !SoundHandle.IsValid())
	{
		SoundHandle = C->OnSound.AddWeakLambda(this, [this](const FString& Kind, const FString& File, float Volume)
		{
			FSoundMark& M = SoundMarks.AddDefaulted_GetRef();
			M.Frame = RecordFrame;
			M.Kind = Kind;
			M.File = File;
			M.Volume = Volume;
		});
		// the loop the scene started with plays on into the film
		if (!C->PlayingSfx().IsEmpty())
		{
			FSoundMark& M = SoundMarks.AddDefaulted_GetRef();
			M.Frame = 0;
			M.Kind = TEXT("sfx");
			M.File = C->PlayingSfx();
			M.Volume = C->PlayingSfxVolume();
		}
	}
	if (ShotIndex < 0 || ShotClock >= Shots[ShotIndex].Seconds)
	{
		++ShotIndex;
		ShotClock = 0.f;
		if (ShotIndex >= Shots.Num())
		{
			UE_LOG(LogMishi, Log, TEXT("shots: done"));
			if (bRecordAll)
				WriteTimeline();
			ShotIndex = Shots.Num() - 1;
			ShotQuitFrames = 6;
			return;
		}
		const FShot& S = Shots[ShotIndex];
		UE_LOG(LogMishi, Log, TEXT("shot %d %s"), ShotIndex, *S.Name);       // the log's time stamps tell how long each one took
		ShotFrames.Add(RecordFrame);
		Cam->bSkillCamera = S.bSkillCam;
		if (S.Springs >= 0)
			C->bSprings = S.Springs > 0;
		if (S.Fx >= 0)
			C->bFx = S.Fx > 0;
		if (S.Phase >= 0)
			C->GoPhase(S.Phase);
		if (S.At >= 0.f)
			C->Seek(S.At);
		if (S.HisStyle >= 0)
			C->SetHisStyle(S.HisStyle);
		else
			C->SetShowHim(!S.bHideHim);
		Cam->SetFovOverride(S.Fov);
		bShotStart = true;
		ShotY = S.Y < 0.f ? Cam->DefaultY() : S.Y;
		ShotZoom = Cam->DefaultZoom() * S.ZoomScale;
		// a cut: no easing in from the last view, no temporal history of the last picture
		Cam->Cut();
		if (PlayerCameraManager)
			PlayerCameraManager->SetGameCameraCutThisFrame();
		if (Hud.IsValid())
			Hud->SetVisibility(S.bHud ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed);
		if (!S.Command.IsEmpty())
			ConsoleCommand(S.Command);
	}
	const FShot& S = Shots[ShotIndex];
	Cam->ClearPose();
	if (!S.Bone.IsEmpty() && C->GetHer())
	{
		const FName Bone(*S.Bone);
		const FQuat Q = C->GetHer()->GetBoneQuaternion(Bone);
		const FVector At = C->GetHer()->GetBoneLocation(Bone) + S.BoneOffset + Q.RotateVector(S.BoneOffsetLocal);
		if (bShotStart)
		{
			ShotAt = At;
			ShotDir = Q.RotateVector(S.From.GetSafeNormal());
			ShotUp = S.bUp ? Q.RotateVector(S.Up.GetSafeNormal()) : FVector::UpVector;
		}
		else
		{
			// the bone's place is followed closely, its turning slowly: the camera neither swings with every nod nor is left
			// looking at a chin when the head goes back
			ShotAt = FMath::Lerp(ShotAt, At, 1.f - FMath::Exp(-DeltaTime / 0.2f));
			const float Turn = 1.f - FMath::Exp(-DeltaTime / 0.7f);
			ShotDir = FMath::Lerp(ShotDir, Q.RotateVector(S.From.GetSafeNormal()), Turn).GetSafeNormal();
			if (S.bUp)
				ShotUp = FMath::Lerp(ShotUp, Q.RotateVector(S.Up.GetSafeNormal()), Turn).GetSafeNormal();
		}
		Cam->SetTargetWorld(ShotAt);
		if (S.bFrom)
			Cam->SetPose(ShotAt + ShotDir * FMath::Max(S.Distance + S.Push * ShotClock, 12.f), ShotAt, ShotUp);
	}
	else
		Cam->ClearTargetWorld();
	bShotStart = false;
	Cam->SetView(Cam->DefaultYaw() + S.YawOffset + S.Drift * ShotClock, ShotY + S.Rise * ShotClock, ShotZoom * FMath::Max(1.f + S.Dolly * ShotClock, 0.05f));
	ShotClock += DeltaTime;
	if (bRecordAll)
		FScreenshotRequest::RequestScreenshot(ShotsDir / FString::Printf(TEXT("frame_%05d.bmp"), RecordFrame++), S.bHud, false);     // .bmp: no time lost packing
	else if (ShotClock >= S.Seconds && !S.Name.StartsWith(TEXT("_")))
	{
		if (S.PathTrace > 0 || S.Hold > 0.f)
			BeginStill(S);
		else
			FScreenshotRequest::RequestScreenshot(ShotsDir / (S.Name + TEXT(".png")), S.bHud, false);
	}
}

void AMishiPlayerController::HoldScene(bool bHold)
{
	// the bodies keep their pose (no clip time, no morph targets, no skinning update), the camera its place and its lens
	if (AMishiCouple* C = Couple.Get())
	{
		C->SetActorTickEnabled(!bHold);
		for (USkeletalMeshComponent* Body : {C->GetHer(), C->GetHim()})
			if (Body)
				Body->SetComponentTickEnabled(!bHold);
	}
	if (AMishiCameraPawn* Cam = GetCam())
		Cam->SetActorTickEnabled(!bHold);
}

void AMishiPlayerController::BeginStill(const FShot& S)
{
	HoldScene(true);
	bStillPathTraced = S.PathTrace > 0;
	if (bStillPathTraced)
	{
		// the path tracer adds one sample a frame to a picture that must not change meanwhile; then its denoiser runs once
		ConsoleCommand(FString::Printf(TEXT("r.PathTracing.SamplesPerPixel %d"), S.PathTrace));
		ConsoleCommand(TEXT("r.PathTracing.ProgressDisplay 0"));
		ConsoleCommand(FString::Printf(TEXT("r.ExposureOffset %.3f"), S.PathTraceEv));
		ConsoleCommand(TEXT("ShowFlag.PathTracing 1"));
		StillFrames = S.PathTrace + 20;
	}
	else
		StillFrames = FMath::Max(1, FMath::RoundToInt(S.Hold * 30.f));
	StillStage = 1;
	UE_LOG(LogMishi, Log, TEXT("still %s: the pose is held for %d frames%s"), *S.Name, StillFrames, bStillPathTraced ? TEXT(", path traced") : TEXT(""));
}

void AMishiPlayerController::EndStill()
{
	if (bStillPathTraced)
	{
		ConsoleCommand(TEXT("ShowFlag.PathTracing 0"));
		ConsoleCommand(TEXT("r.ExposureOffset 0"));
		ConsoleCommand(TEXT("r.PathTracing.SamplesPerPixel -1"));
		ConsoleCommand(TEXT("r.PathTracing.ProgressDisplay 1"));
	}
	bStillPathTraced = false;
	HoldScene(false);
	StillStage = 0;
}

void AMishiPlayerController::WriteTimeline() const
{
	// read by Tools/tour_audio.py: the film's sound track is mixed from the sound files as the scene played them
	FString Text = FString::Printf(TEXT("{\n  \"frames\": %d,\n  \"shots\": ["), RecordFrame);
	for (int32 I = 0; I < ShotFrames.Num() && I < Shots.Num(); ++I)
		Text += FString::Printf(TEXT("%s\n    {\"name\": \"%s\", \"frame\": %d}"), I ? TEXT(",") : TEXT(""), *Shots[I].Name.ReplaceCharWithEscapedChar(), ShotFrames[I]);
	Text += TEXT("\n  ],\n  \"sounds\": [");
	for (int32 I = 0; I < SoundMarks.Num(); ++I)
	{
		const FSoundMark& M = SoundMarks[I];
		Text += FString::Printf(TEXT("%s\n    {\"frame\": %d, \"kind\": \"%s\", \"file\": \"%s\", \"volume\": %.3f}"), I ? TEXT(",") : TEXT(""), M.Frame, *M.Kind,
			*M.File.ReplaceCharWithEscapedChar(), M.Volume);
	}
	Text += TEXT("\n  ]\n}\n");
	FFileHelper::SaveStringToFile(Text, *(ShotsDir / TEXT("timeline.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

void AMishiPlayerController::EndPlay(const EEndPlayReason::Type Reason)
{
	if (SoundHandle.IsValid() && Couple.IsValid())
		Couple->OnSound.Remove(SoundHandle);
	SoundHandle.Reset();
	if (Hud.IsValid())
		if (UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
			Viewport->RemoveViewportWidgetContent(Hud.ToSharedRef());
	Hud.Reset();
	Super::EndPlay(Reason);
}

void AMishiPlayerController::ToggleHud()
{
	bHudShown = !bHudShown;
	if (Hud.IsValid())
		Hud->SetVisibility(bHudShown ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed);
}

float AMishiPlayerController::Axis(const FKey& Minus1, const FKey& Minus2, const FKey& Plus1, const FKey& Plus2) const
{
	float V = 0.f;
	if (IsInputKeyDown(Minus1) || IsInputKeyDown(Minus2)) V -= 1.f;
	if (IsInputKeyDown(Plus1) || IsInputKeyDown(Plus2)) V += 1.f;
	return V;
}

void AMishiPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	if (!Couple.IsValid())
		for (TActorIterator<AMishiCouple> It(GetWorld()); It; ++It)
		{
			Couple = *It;
			break;
		}
	if (bShots)
	{
		StepShots(DeltaTime);
		return;
	}
	AMishiCouple* C = Couple.Get();
	AMishiCameraPawn* Cam = GetCam();

	// drags: the cursor's own pixels (the panel's buttons take their clicks before the game sees them)
	float X = 0.f, Y = 0.f;
	const bool bHave = GetMousePosition(X, Y);
	const FVector2D Cursor(X, Y);
	if (Cam && bHave && bHadCursor)
	{
		const FVector2D D = Cursor - LastCursor;
		if (IsInputKeyDown(EKeys::LeftMouseButton))
			Cam->Turn(D.X, D.Y);
		if (IsInputKeyDown(EKeys::RightMouseButton))
			Cam->Pan(D.X, D.Y);
	}
	LastCursor = Cursor;
	bHadCursor = bHave;
	if (Cam)
	{
		if (WasInputKeyJustPressed(EKeys::MouseScrollUp)) Cam->ZoomBy(1.f);
		if (WasInputKeyJustPressed(EKeys::MouseScrollDown)) Cam->ZoomBy(-1.f);
		if (WasInputKeyJustPressed(EKeys::MiddleMouseButton) || WasInputKeyJustPressed(EKeys::Home)) Cam->ResetView();
		Cam->Keys(DeltaTime,
			Axis(EKeys::Left, EKeys::A, EKeys::Right, EKeys::D),
			Axis(EKeys::Down, EKeys::S, EKeys::Up, EKeys::W),
			Axis(EKeys::PageUp, EKeys::Q, EKeys::PageDown, EKeys::E));
	}
	if (C)
	{
		const FKey Phases[] = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six, EKeys::Seven, EKeys::Eight,
			EKeys::Nine, EKeys::Zero};
		for (int32 I = 0; I < UE_ARRAY_COUNT(Phases) && I < C->Slice().Phases.Num(); ++I)
			if (WasInputKeyJustPressed(Phases[I]))
				C->GoPhase(I);
		if (WasInputKeyJustPressed(EKeys::SpaceBar)) C->bAuto = !C->bAuto;
		if (WasInputKeyJustPressed(EKeys::V)) C->VoiceLanguage = (C->VoiceLanguage + 1) % 3;
		if (WasInputKeyJustPressed(EKeys::M)) C->SetHisStyle((C->HisStyle + 1) % 3);
		if (WasInputKeyJustPressed(EKeys::X)) C->SetSfx(!C->bSfx);
		if (WasInputKeyJustPressed(EKeys::B)) C->bSkinState = !C->bSkinState;
	}
	if (WasInputKeyJustPressed(EKeys::H)) ToggleHud();
}
