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
#include "RenderTimer.h"
#include "DynamicRHI.h"
#if WITH_EDITOR
#include "AssetCompilingManager.h"
#include "ShaderCompiler.h"
#endif

namespace
{
	// NVIDIA's DLSS plugin, reached by name: the project builds and runs without it.  Its Blueprint library has static
	// functions for what is wanted here (and EnableDLSSRR knows which of Lumen's own denoisers to put aside and bring back).
	UFunction* DlssFunction(const TCHAR* Name, UObject*& OutObject)
	{
		UClass* Lib = FindObject<UClass>(nullptr, TEXT("/Script/DLSSBlueprint.DLSSLibrary"));
		OutObject = Lib ? Lib->GetDefaultObject() : nullptr;
		return Lib ? Lib->FindFunctionByName(Name) : nullptr;
	}

	/** QueryDLSSSupport / QueryDLSSRRSupport: an enum whose first value says "supported". */
	bool DlssSupported(const TCHAR* Query)
	{
		UObject* O = nullptr;
		UFunction* F = DlssFunction(Query, O);
		const FProperty* Ret = F ? F->GetReturnProperty() : nullptr;
		if (!O || !Ret || F->ParmsSize <= 0)
			return false;
		uint8* Parms = static_cast<uint8*>(FMemory_Alloca(F->ParmsSize));
		FMemory::Memset(Parms, 0xff, F->ParmsSize);
		O->ProcessEvent(F, Parms);
		return Parms[Ret->GetOffset_ForUFunction()] == 0;
	}

	/** EnableDLSS / EnableDLSSRR (bool bEnabled). */
	void DlssEnable(const TCHAR* Name, bool bOn)
	{
		UObject* O = nullptr;
		UFunction* F = DlssFunction(Name, O);
		const FBoolProperty* Arg = F ? CastField<FBoolProperty>(F->FindPropertyByName(TEXT("bEnabled"))) : nullptr;
		if (!O || !Arg)
			return;
		uint8* Parms = static_cast<uint8*>(FMemory_Alloca(F->ParmsSize));
		FMemory::Memzero(Parms, F->ParmsSize);
		Arg->SetPropertyValue_InContainer(Parms, bOn);
		O->ProcessEvent(F, Parms);
	}
}

bool AMishiPlayerController::HasDLSS()
{
	return DlssSupported(TEXT("QueryDLSSSupport"));
}

bool AMishiPlayerController::HasRayReconstruction()
{
	return DlssSupported(TEXT("QueryDLSSRRSupport"));
}

int32 AMishiPlayerController::UpscaleByName(const FString& Name)
{
	static const TCHAR* Names[] = {TEXT("tsr"), TEXT("dlaa"), TEXT("quality"), TEXT("balanced"), TEXT("performance")};
	for (int32 I = 0; I < UE_ARRAY_COUNT(Names); ++I)
		if (Name.Equals(Names[I], ESearchCase::IgnoreCase))
			return I;
	return INDEX_NONE;
}

FString AMishiPlayerController::PictureName() const
{
	static const TCHAR* Names[] = {TEXT("TSR"), TEXT("DLAA"), TEXT("DLSS quality"), TEXT("DLSS balanced"), TEXT("DLSS performance")};
	return FString(Names[FMath::Clamp(Upscale, 0, int32(UE_ARRAY_COUNT(Names)) - 1)]) + (bRayReconstruction ? TEXT(" + RR") : TEXT(""));
}

void AMishiPlayerController::SetUpscale(int32 Mode)
{
	// what DLSS renders of the picture's width: all of it (DLAA: its anti-aliasing alone), two thirds, 58 %, half
	static const float Percent[] = {100.f, 100.f, 66.7f, 58.f, 50.f};
	Mode = FMath::Clamp(Mode, 0, int32(UE_ARRAY_COUNT(Percent)) - 1);
	if (Mode > 0 && !HasDLSS())
		Mode = 0;
	DlssEnable(TEXT("EnableDLSS"), Mode > 0);
	if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage")))
		Var->Set(Percent[Mode], ECVF_SetByCode);
	Upscale = Mode;
	// Ray reconstruction runs inside the DLSS pass: it goes out with DLSS.  The plugin remembers on its own that it was on and
	// would bring it back with DLSS, whatever the panel shows by then - so it is told each time what is wanted here.
	if (Mode == 0)
		bRayReconstruction = false;
	DlssEnable(TEXT("EnableDLSSRR"), bRayReconstruction);
	UE_LOG(LogMishi, Log, TEXT("upscale: %s, %.0f %% of the picture rendered%s"), Mode == 0 ? TEXT("TSR") : Mode == 1 ? TEXT("DLAA") : TEXT("DLSS"), Percent[Mode],
		bRayReconstruction ? TEXT(", ray reconstruction") : TEXT(""));
}

void AMishiPlayerController::SetRayReconstruction(bool bOn)
{
	bOn = bOn && Upscale > 0 && HasRayReconstruction();
	DlssEnable(TEXT("EnableDLSSRR"), bOn);
	bRayReconstruction = bOn;
	UE_LOG(LogMishi, Log, TEXT("ray reconstruction: %s"), bOn ? TEXT("on") : TEXT("off"));
}

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
	// (a close-up stands a hand's breadth from her face: the engine's near plane is 10 cm away and would cut into it)
	ConsoleCommand(TEXT("r.SetNearClipPlane 2"));
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
	// The picture's upscaler.  Where NVIDIA's DLSS is there (its plugin installed, a card that can) the game starts with it
	// (user 11-22: "打开默认就是dlss") - as DLAA, its anti-aliasing on the full picture: the calmest picture of those measured
	// here and a little faster than the engine's TSR; the panel's button goes on to the upscaling modes.  The command line
	// can name another (Tools/ue.ps1 -Upscale tsr | dlaa | quality | balanced | performance, -RR).
	int32 Wanted = HasDLSS() ? 1 : 0;
	FString UpscaleName;
	if (FParse::Value(FCommandLine::Get(), TEXT("MishiUpscale="), UpscaleName))
	{
		const int32 Picked = UpscaleByName(UpscaleName);
		if (Picked == INDEX_NONE)
		{
			UE_LOG(LogMishi, Warning, TEXT("-MishiUpscale=%s: not one of tsr, dlaa, quality, balanced, performance"), *UpscaleName);
		}
		else if (Picked > 0 && !HasDLSS())
		{
			UE_LOG(LogMishi, Warning, TEXT("-MishiUpscale=%s: no DLSS here (the plugin is not installed, or the card or its driver cannot)"), *UpscaleName);
		}
		else
		{
			Wanted = Picked;
		}
	}
	SetUpscale(Wanted);
	if (FParse::Param(FCommandLine::Get(), TEXT("MishiRR")))
	{
		SetRayReconstruction(true);
		if (!bRayReconstruction)
		{
			UE_LOG(LogMishi, Warning, TEXT("-MishiRR: ray reconstruction needs DLSS on (-MishiUpscale=dlaa ...) and a card that can"));
		}
	}
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
		O->TryGetBoolField(TEXT("hide_her"), S.bHideHer);
		O->TryGetBoolField(TEXT("skill_cam"), S.bSkillCam);
		bool bFlag = false;
		if (O->TryGetBoolField(TEXT("springs"), bFlag)) S.Springs = bFlag ? 1 : 0;
		if (O->TryGetBoolField(TEXT("fx"), bFlag)) S.Fx = bFlag ? 1 : 0;
		if (O->TryGetNumberField(TEXT("aura"), N)) S.Aura = int32(N);
		if (O->TryGetNumberField(TEXT("skin"), N)) S.Skin = int32(N);
		if (O->TryGetNumberField(TEXT("closeup"), N)) S.CloseUp = int32(N);
		if (O->TryGetNumberField(TEXT("wet"), N)) S.Wet = float(N);
		if (O->TryGetNumberField(TEXT("flush"), N)) S.Flush = float(N);
		O->TryGetStringField(TEXT("upscale"), S.Upscale);
		if (O->TryGetBoolField(TEXT("rr"), bFlag)) S.RayReconstruction = bFlag ? 1 : 0;
		if (O->TryGetNumberField(TEXT("series"), N)) S.Series = int32(N);
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
#if WITH_EDITOR
	// Nothing is shot before everything is built.  A material whose shaders are still compiling is drawn as the engine's grey
	// default material and a texture still being built as a grey square - with a cold cache (the masters rebuilt since this
	// slice was last drawn, another machine) a whole film of them.
	if (ShotIndex < 0)
	{
		const int32 Shaders = GShaderCompilingManager ? GShaderCompilingManager->GetNumRemainingJobs() : 0;
		const int32 Assets = FAssetCompilingManager::Get().GetNumRemainingAssets();
		if (Shaders > 0 || Assets > 0)
		{
			ShotReadyFrames = 0;
			if (ShotWaitFrames++ % 150 == 0)
				UE_LOG(LogMishi, Log, TEXT("shots: waiting for %d shader jobs and %d assets to be built"), Shaders, Assets);
			return;
		}
		// (what was built asks for more: a texture brings its material in)
		if (++ShotReadyFrames < 30)
			return;
	}
#endif
	if (StillStage == 1)
	{
		// the scene is held: nothing moves until the picture is taken
		CountFrame();
		if (--StillFrames <= 0)
		{
			const FShot& Held = Shots[ShotIndex];
			if (StillSeries > 0)
			{
				// (one request a frame: the next is asked for when this one has been taken)
				if (!FScreenshotRequest::IsScreenshotRequested())
				{
					FScreenshotRequest::RequestScreenshot(ShotsDir / FString::Printf(TEXT("%s_%02d.png"), *Held.Name, Held.Series - StillSeries), Held.bHud, false);
					if (--StillSeries == 0)
						StillStage = 2;
				}
				return;
			}
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
		const double Now = FPlatformTime::Seconds();
		if (ShotIndex >= 0)
		{
			FShotTime& T = ShotTimes.AddDefaulted_GetRef();
			T.Name = Shots[ShotIndex].Name;
			T.Picture = PictureName();
			T.Frames = ShotFrameCount;
			T.Seconds = Now - ShotRealStart;
			const double Per = 1.0 / FMath::Max(ShotFrameCount, 1);
			T.GameMs = ShotGameMs * Per;
			T.RenderMs = ShotRenderMs * Per;
			T.RhiMs = ShotRhiMs * Per;
			T.GpuMs = ShotGpuMs * Per;
			T.FrameMs = MoveTemp(ShotFrameMs);
		}
		ShotFrameMs.Reset();
		ShotRealStart = Now;
		ShotFrameCount = 0;
		ShotGameMs = ShotRenderMs = ShotRhiMs = ShotGpuMs = 0.0;
		++ShotIndex;
		ShotClock = 0.f;
		if (ShotIndex >= Shots.Num())
		{
			UE_LOG(LogMishi, Log, TEXT("shots: done"));
			WriteTiming();
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
		if (S.Aura >= 0)
			C->AuraMode = FMath::Clamp(S.Aura, 0, 2);
		if (S.Skin >= 0)
			C->SkinVersion = FMath::Clamp(S.Skin, 0, 2);
		if (S.CloseUp >= 0)
			Cam->SetCloseUp(S.CloseUp);
		if (S.Wet > -1.5f)
			C->WetHeld = S.Wet;
		if (S.Flush > -1.5f)
			C->FlushHeld = S.Flush;
		if (!S.Upscale.IsEmpty())
		{
			const int32 Picked = UpscaleByName(S.Upscale);
			if (Picked == INDEX_NONE)
			{
				UE_LOG(LogMishi, Warning, TEXT("shot %s: \"upscale\": \"%s\" is not one of tsr, dlaa, quality, balanced, performance"), *S.Name, *S.Upscale);
			}
			else
			{
				SetUpscale(Picked);
			}
		}
		if (S.RayReconstruction >= 0)
			SetRayReconstruction(S.RayReconstruction > 0);
		if (S.Phase >= 0)
			C->GoPhase(S.Phase);
		if (S.At >= 0.f)
			C->Seek(S.At);
		if (S.HisStyle >= 0)
			C->SetHisStyle(S.HisStyle);
		else
			C->SetShowHim(!S.bHideHim);
		if (C->GetHer() && C->GetHer()->IsVisible() == S.bHideHer)
			C->GetHer()->SetVisibility(!S.bHideHer, true);
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
		// (a bone of his, where her skeleton has none of that name: Bip000-R-Hand)
		const USkeletalMeshComponent* Body = C->GetHer();
		if (Body->GetBoneIndex(Bone) == INDEX_NONE && C->GetHim() && C->GetHim()->GetBoneIndex(Bone) != INDEX_NONE)
			Body = C->GetHim();
		const FQuat Q = Body->GetBoneQuaternion(Bone);
		const FVector At = Body->GetBoneLocation(Bone) + S.BoneOffset + Q.RotateVector(S.BoneOffsetLocal);
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
	CountFrame();
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
		// (the skills' effects are not in the ray tracing scene: their lights go out with them)
		if (AMishiCouple* C = Couple.Get())
			C->SetFxHidden(true);
		// The path tracer does its own anti-aliasing: while it is shown the engine runs no temporal upscaler at all, DLSS
		// neither (FSceneRenderer: "path tracer does its own anti-aliasing").  So DLSS is left switched on - switched off for
		// the still and on again after it, the card page-faulted at the next still: its network set up, 14 frames on torn
		// down again.  Two things only: a path-traced still is rendered whole, whatever share of the picture DLSS was
		// rendering; and the plugin throws a network away that has been idle for 3 frames, which would be the same setting
		// up and tearing down between every two stills - for the still it keeps it.
		if (IConsoleVariable* Percent = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage")))
		{
			StillPercent = Percent->GetFloat();
			if (StillPercent != 100.f)
				Percent->Set(100.f, ECVF_SetByCode);
		}
		if (IConsoleVariable* Keep = IConsoleManager::Get().FindConsoleVariable(TEXT("r.NGX.FramesUntilFeatureDestruction")))
		{
			StillKeep = Keep->GetInt();
			Keep->Set(1000000, ECVF_SetByCode);
		}
	}
	else
		StillFrames = FMath::Max(1, FMath::RoundToInt(S.Hold * 30.f));
	StillSeries = bStillPathTraced ? 0 : FMath::Clamp(S.Series, 0, 99);
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
		if (AMishiCouple* C = Couple.Get())
			C->SetFxHidden(false);
		if (StillPercent > 0.f && StillPercent != 100.f)
			if (IConsoleVariable* Percent = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage")))
				Percent->Set(StillPercent, ECVF_SetByCode);
		if (StillKeep >= 0)
			if (IConsoleVariable* Keep = IConsoleManager::Get().FindConsoleVariable(TEXT("r.NGX.FramesUntilFeatureDestruction")))
				Keep->Set(StillKeep, ECVF_SetByCode);
		StillPercent = 0.f;
		StillKeep = -1;
	}
	bStillPathTraced = false;
	HoldScene(false);
	StillStage = 0;
}

void AMishiPlayerController::CountFrame()
{
	// the engine's own stop watches (what "stat unit" shows), of the frame before this one
	++ShotFrameCount;
	const double Now = FPlatformTime::Seconds();
	if (ShotLastFrame > 0.0)
		ShotFrameMs.Add(float((Now - ShotLastFrame) * 1000.0));
	ShotLastFrame = Now;
	ShotGameMs += FPlatformTime::ToMilliseconds(GGameThreadTime);
	ShotRenderMs += FPlatformTime::ToMilliseconds(GRenderThreadTime);
	ShotRhiMs += FPlatformTime::ToMilliseconds(GRHIThreadTime);
	ShotGpuMs += FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles());
}

void AMishiPlayerController::WriteTiming() const
{
	// read by Tools/bench_table.py: how fast each shot's frames came
	FIntPoint Size(0, 0);
	if (const UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
		if (Viewport->Viewport)
			Size = Viewport->Viewport->GetSizeXY();
	FString Text = FString::Printf(TEXT("{\n  \"width\": %d, \"height\": %d,\n  \"shots\": ["), Size.X, Size.Y);
	for (int32 I = 0; I < ShotTimes.Num(); ++I)
	{
		const FShotTime& T = ShotTimes[I];
		Text += FString::Printf(TEXT("%s\n    {\"name\": \"%s\", \"picture\": \"%s\", \"frames\": %d, \"seconds\": %.4f, \"game_ms\": %.2f, \"render_ms\": %.2f, \"rhi_ms\": %.2f, \"gpu_ms\": %.2f, \"frame_ms\": ["),
			I ? TEXT(",") : TEXT(""), *T.Name.ReplaceCharWithEscapedChar(), *T.Picture, T.Frames, T.Seconds, T.GameMs, T.RenderMs, T.RhiMs, T.GpuMs);
		for (int32 F = 0; F < T.FrameMs.Num(); ++F)
			Text += FString::Printf(TEXT("%s%.2f"), F ? TEXT(", ") : TEXT(""), T.FrameMs[F]);
		Text += TEXT("]}");
	}
	Text += TEXT("\n  ]\n}\n");
	FFileHelper::SaveStringToFile(Text, *(ShotsDir / TEXT("timing.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
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
		if (WasInputKeyJustPressed(EKeys::F)) Cam->SetCloseUp((Cam->GetCloseUp() + 1) % 3);     // the face, the chest, the orbit
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
		if (WasInputKeyJustPressed(EKeys::N)) C->SkinVersion = (C->SkinVersion + 2) % 3;        // 2 -> 1 -> 0 -> 2
	}
	if (WasInputKeyJustPressed(EKeys::H)) ToggleHud();
}
