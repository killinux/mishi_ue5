#include "MishiPlayerController.h"
#include "MishiCameraPawn.h"
#include "MishiCouple.h"
#include "MishiUE.h"
#include "SMishiHud.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
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
	if (FParse::Param(FCommandLine::Get(), TEXT("MishiTour")))
		StartTour();
}

void AMishiPlayerController::StartTour()
{
	if (!FParse::Value(FCommandLine::Get(), TEXT("MishiTourDir="), TourDir))
		TourDir = FPaths::ProjectSavedDir() / TEXT("MishiTour");
	IFileManager::Get().MakeDirectory(*TourDir, true);
	// the game's own view first, then round the couple through the four phases (phase 4's climax runs into its after-loop)
	Tour = {
		{0, 7.f, 0.f, -1.f, 1.f},
		{1, 7.f, 35.f, 0.62f, 0.85f},
		{2, 7.f, 150.f, 0.55f, 0.9f},
		{3, 9.f, 220.f, 0.6f, 1.05f},
		{-1, 6.f, 300.f, 0.78f, 1.25f},
	};
	bTour = true;
	TourIndex = -1;
	TourClock = 0.f;
	TourFrame = 0;
	UE_LOG(LogMishi, Log, TEXT("tour: %d stops into %s"), Tour.Num(), *TourDir);
}

void AMishiPlayerController::StepTour(float DeltaTime)
{
	AMishiCouple* C = Couple.Get();
	AMishiCameraPawn* Cam = GetCam();
	if (!C || !C->IsReady() || !Cam)
		return;
	C->bAuto = false;
	// the next stop: its phase button, the camera on its way to the stop's view
	float End = 0.f;
	for (int32 I = 0; I <= TourIndex && I < Tour.Num(); ++I)
		End += Tour[I].Seconds;
	if (TourIndex < 0 || TourClock >= End)
	{
		++TourIndex;
		if (TourIndex >= Tour.Num())
		{
			UE_LOG(LogMishi, Log, TEXT("tour: %d frames, done"), TourFrame);
			bTour = false;
			ConsoleCommand(TEXT("quit"));
			return;
		}
		if (Tour[TourIndex].Phase >= 0)
			C->GoPhase(Tour[TourIndex].Phase);
		TourStopStart = TourClock;
		FromYaw = Cam->GetYaw();
		FromY = Cam->GetY();
		FromZoom = Cam->GetZoom();
	}
	const FTourStop& S = Tour[TourIndex];
	const float T = FMath::SmoothStep(0.f, 1.f, FMath::Clamp((TourClock - TourStopStart) / 3.f, 0.f, 1.f));
	const float ToYaw = Cam->DefaultYaw() + S.YawOffset + 3.f * (TourClock - TourStopStart);     // and a slow drift
	const float ToY = S.Y < 0.f ? FromY : S.Y;
	const float ToZoom = Cam->DefaultZoom() * S.ZoomScale;
	Cam->SetView(FMath::Lerp(FromYaw, ToYaw, T), FMath::Lerp(FromY, ToY, T), FMath::Lerp(FromZoom, ToZoom, T));
	FScreenshotRequest::RequestScreenshot(TourDir / FString::Printf(TEXT("frame_%05d.png"), TourFrame++), true, false);
	TourClock += DeltaTime;
}

void AMishiPlayerController::EndPlay(const EEndPlayReason::Type Reason)
{
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
	if (bTour)
	{
		StepTour(DeltaTime);
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
		const FKey Phases[] = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four};
		for (int32 I = 0; I < 4; ++I)
			if (WasInputKeyJustPressed(Phases[I]))
				C->GoPhase(I);
		if (WasInputKeyJustPressed(EKeys::SpaceBar)) C->bAuto = !C->bAuto;
		if (WasInputKeyJustPressed(EKeys::V)) C->VoiceLanguage = (C->VoiceLanguage + 1) % 3;
		if (WasInputKeyJustPressed(EKeys::M)) C->SetShowHim(!C->bShowHim);
	}
	if (WasInputKeyJustPressed(EKeys::H)) ToggleHud();
}
