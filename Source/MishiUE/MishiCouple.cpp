#include "MishiCouple.h"
#include "MishiUE.h"
#include "MishiAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Sound/SoundBase.h"
#include "Misc/Paths.h"

AMishiCouple::AMishiCouple()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;

	Origin = CreateDefaultSubobject<USceneComponent>(TEXT("Origin"));
	RootComponent = Origin;
	Her = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Her"));
	Her->SetupAttachment(Origin);
	His = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("His"));
	His->SetupAttachment(Origin);
	for (USkeletalMeshComponent* Body : {Her.Get(), His.Get()})
	{
		Body->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		Body->AnimClass = UMishiAnimInstance::StaticClass();
		Body->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Body->bEnableUpdateRateOptimizations = false;
		// the mesh's bounds are those of its standing pose: lying down, the head is outside them, and a close-up of the face
		// culled the whole body.  Wide bounds: two bodies in one room are never worth culling.
		Body->BoundsScale = 6.f;
		// the bodies are lit on channel 1 only: the room's hard sun (channel 0) does not burn the skin out - a weaker twin of it
		// on channel 1 does the sun on skin (Tools/mishi_look.py puts every other light on both channels)
		Body->LightingChannels.bChannel0 = false;
		Body->LightingChannels.bChannel1 = true;
	}
	Voice = CreateDefaultSubobject<UAudioComponent>(TEXT("Voice"));
	Voice->SetupAttachment(Origin);
	Voice->bAutoActivate = false;
	Music = CreateDefaultSubobject<UAudioComponent>(TEXT("Music"));
	Music->SetupAttachment(Origin);
	Music->bAutoActivate = false;
	Music->bIsUISound = true;              // the room's music is not placed in the room
	Sfx = CreateDefaultSubobject<UAudioComponent>(TEXT("Sfx"));
	Sfx->SetupAttachment(Origin);
	Sfx->bAutoActivate = false;
}

bool AMishiCouple::LoadSlice()
{
	FString Error;
	if (SliceJson.IsEmpty())
	{
		UE_LOG(LogMishi, Warning, TEXT("%s: no slice.json text (run Tools/import_slice.py)"), *GetName());
		return false;
	}
	if (!Data.Parse(SliceJson, Error))
	{
		UE_LOG(LogMishi, Error, TEXT("%s: %s"), *GetName(), *Error);
		return false;
	}
	return true;
}

void AMishiCouple::PlaceBodies()
{
	if (HerMesh && Her->GetSkeletalMeshAsset() != HerMesh)
		Her->SetSkeletalMeshAsset(HerMesh);
	if (HisMesh && His->GetSkeletalMeshAsset() != HisMesh)
		His->SetSkeletalMeshAsset(HisMesh);
	Her->SetRelativeTransform(Data.FemaleOffset.ToUE());
	His->SetRelativeTransform(Data.MaleOffset.ToUE());
	SetHisStyle(HisStyle);
}

void AMishiCouple::SetHisStyle(int32 Style)
{
	HisStyle = FMath::Clamp(Style, 0, 2);
	bShowHim = HisStyle != 2;
	His->SetVisibility(bShowHim);
	// the body's slot keeps the name of the Unity project's stand-in material
	UMaterialInterface* Body = HisStyle == 1 && HisBodySilhouette ? HisBodySilhouette.Get() : HisBodySkin.Get();
	if (Body && His->GetMaterialIndex(TEXT("MaleBody")) != INDEX_NONE)
		His->SetMaterialByName(TEXT("MaleBody"), Body);
}

void AMishiCouple::StepSkin(float DeltaSeconds)
{
	// sweat and blush go towards the phase's level, as the scene builds up
	static const float FlushByPhase[4] = {0.1f, 0.35f, 0.6f, 0.9f};
	static const float WetByPhase[4] = {0.f, 0.2f, 0.45f, 0.8f};
	const int32 Ph = FMath::Clamp(PhaseNow, 0, 3);
	const float K = SkinEase > 0.f ? 1.f - FMath::Exp(-DeltaSeconds / SkinEase) : 1.f;
	Flush = FMath::Lerp(Flush, bSkinState ? FlushByPhase[Ph] : 0.f, K);
	Wet = FMath::Lerp(Wet, bSkinState ? WetByPhase[Ph] : 0.f, K);
	if (SkinState)
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, SkinState, TEXT("Wet"), Wet);
		UKismetMaterialLibrary::SetScalarParameterValue(this, SkinState, TEXT("Flush"), Flush);
	}
}

void AMishiCouple::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	if (LoadSlice())
		PlaceBodies();
}

void AMishiCouple::BeginPlay()
{
	Super::BeginPlay();
	bReady = LoadSlice();
	if (!bReady)
		return;
	PlaceBodies();
	// the bodies' poses after this actor's tick, which sets their clips and times
	Her->AddTickPrerequisiteActor(this);
	His->AddTickPrerequisiteActor(this);
	if (!Player(Her) || !Player(His))
		UE_LOG(LogMishi, Error, TEXT("%s: the bodies have no MishiAnimInstance"), *GetName());
	if (USoundBase* Bgm = FindSound(Data.MusicFile))
	{
		Music->SetSound(Bgm);
		Music->SetVolumeMultiplier(Data.MusicVolume);
		Music->Play();
	}
	PhaseNow = 0;
	LineIndex = 0;
	LineTimer = 0.f;
	FString First = Data.StateFor(0, 0);
	Enter(First.IsEmpty() ? Data.Parts[0].Name : First, 0.f);
	ResetAutoTimer();
	UE_LOG(LogMishi, Log, TEXT("%s: %s (%s) in room %s - %d parts, %d rules, her %d clips, his %d clips, %d sounds"), *GetName(), *Data.Title,
		*Data.Posture, *Data.Room, Data.Parts.Num(), Data.Rules.Num(), HerClips.Num(), HisClips.Num(), Sounds.Num());
}

UMishiAnimInstance* AMishiCouple::Player(USkeletalMeshComponent* Body) const
{
	return Body ? Cast<UMishiAnimInstance>(Body->GetAnimInstance()) : nullptr;
}

UAnimSequence* AMishiCouple::FindClip(const TArray<TObjectPtr<UAnimSequence>>& Clips, const FString& Name) const
{
	if (Name.IsEmpty())
		return nullptr;
	for (UAnimSequence* S : Clips)
		if (S && S->GetName() == Name)
			return S;
	for (UAnimSequence* S : Clips)
		if (S && S->GetName().EndsWith(TEXT("_") + Name))
			return S;
	return nullptr;
}

USoundBase* AMishiCouple::FindSound(const FString& File) const
{
	if (File.IsEmpty())
		return nullptr;
	const FString Stem = FPaths::GetBaseFilename(File);
	for (USoundBase* S : Sounds)
		if (S && S->GetName() == Stem)
			return S;
	return nullptr;
}

FString AMishiCouple::CurrentPart() const
{
	const FMishiPart* P = PartNow();
	return P ? P->Name : FString();
}

FString AMishiCouple::CurrentLine() const
{
	return Data.Lines.IsValidIndex(LineIndex) ? Data.Lines[LineIndex].Zh : FString();
}

void AMishiCouple::GoPhase(int32 Wanted)
{
	if (!bReady)
		return;
	const FString To = Data.StateFor(PhaseNow, Wanted);
	if (To.IsEmpty())
		return;
	Enter(To, 0.25f);
	PhaseNow = Wanted;
	ResetAutoTimer();
}

void AMishiCouple::Enter(const FString& PartName, float Blend)
{
	const int32 Index = Data.Parts.IndexOfByPredicate([&PartName](const FMishiPart& P) { return P.Name == PartName; });
	if (Index == INDEX_NONE)
	{
		UE_LOG(LogMishi, Warning, TEXT("%s: no part %s"), *GetName(), *PartName);
		return;
	}
	PartIndex = Index;
	PartTime = 0.f;
	const FMishiPart& P = Data.Parts[Index];
	if (P.Phase >= 0)
		PhaseNow = P.Phase;
	if (UMishiAnimInstance* A = Player(Her))
		A->Play(FindClip(HerClips, P.FemaleClip), P.bLoop, Blend);
	if (UMishiAnimInstance* A = Player(His))
		A->Play(FindClip(HisClips, P.MaleClip), P.bLoop, Blend);
	ApplyShapes();
	ApplySfx(P.Name);
	PlayVoice(P.Name);
}

void AMishiCouple::Seek(float Seconds)
{
	const FMishiPart* P = PartNow();
	if (!P)
		return;
	const FString Name = P->Name;
	Enter(Name, 0.f);
	PartTime = FMath::Max(Seconds, 0.f);
	if (UMishiAnimInstance* A = Player(Her))
		A->Advance(PartTime);
	if (UMishiAnimInstance* A = Player(His))
		A->Advance(PartTime);
	ApplyShapes();
}

void AMishiCouple::SetShowHim(bool bShow)
{
	SetHisStyle(bShow ? (HisStyle == 2 ? 0 : HisStyle) : 2);
}

void AMishiCouple::PlayVoice(const FString& PartName)
{
	const FMishiVoice* V = Data.Voices.FindByPredicate([&PartName](const FMishiVoice& X) { return X.Part == PartName; });
	if (!V || VoiceLanguage == 0)
		return;
	const FString& File = VoiceLanguage == 1 ? (V->Jp.IsEmpty() ? V->En : V->Jp) : (V->En.IsEmpty() ? V->Jp : V->En);
	if (USoundBase* S = FindSound(File))
	{
		Voice->Stop();
		Voice->SetSound(S);
		Voice->Play();
		OnSound.Broadcast(TEXT("voice"), File, 1.f);
	}
}

void AMishiCouple::SetSfx(bool bOn)
{
	bSfx = bOn;
	if (!bSfx)
	{
		Sfx->Stop();
		SfxFile.Reset();
		OnSound.Broadcast(TEXT("sfx"), FString(), 0.f);
	}
	else if (const FMishiPart* P = PartNow())
		ApplySfx(P->Name);
}

void AMishiCouple::ApplySfx(const FString& PartName)
{
	// as the game: the phaseNN_k node of the part pk plays, the others are off; a transition part keeps what plays
	if (!PartName.StartsWith(TEXT("p")) || !PartName.Mid(1).IsNumeric())
		return;
	const FMishiSfx* X = Data.Sfx.FindByPredicate([&PartName](const FMishiSfx& S) { return S.Part == PartName; });
	USoundBase* Sound = X && bSfx ? FindSound(X->File) : nullptr;
	if (!Sound)
	{
		Sfx->Stop();
		SfxFile.Reset();
		OnSound.Broadcast(TEXT("sfx"), FString(), 0.f);
		return;
	}
	// the loop that already plays goes on (by its file: without a sound device nothing "is playing")
	if (SfxFile == X->File)
		return;
	Sfx->Stop();
	Sfx->SetSound(Sound);
	Sfx->SetVolumeMultiplier(X->Volume * SfxVolume);
	Sfx->Play();
	SfxFile = X->File;
	SfxVolumeNow = X->Volume * SfxVolume;
	OnSound.Broadcast(TEXT("sfx"), X->File, SfxVolumeNow);
}

void AMishiCouple::ResetAutoTimer()
{
	if (Data.Phases.IsValidIndex(PhaseNow))
		AutoTimer = FMath::FRandRange(Data.Phases[PhaseNow].TimerMin, Data.Phases[PhaseNow].TimerMax);
}

void AMishiCouple::ApplyShapes()
{
	const FMishiPart* P = PartNow();
	const FMishiShapeTrack* Track = P ? Data.Tracks.Find(P->Name) : nullptr;
	if (!Track)
		return;
	for (const TPair<FString, TArray<float>>& Kv : Track->Shapes)
		Her->SetMorphTarget(FName(*Kv.Key), Track->Sample(Kv.Value, PartTime, P->bLoop) / 100.f, false);
}

FVector AMishiCouple::UnityToWorld(const FVector& P) const
{
	return GetActorTransform().TransformPosition(MishiSpace::Position(P));
}

FVector AMishiCouple::UnityDirToWorld(const FVector& D) const
{
	return GetActorTransform().TransformVectorNoScale(MishiSpace::Direction(D));
}

void AMishiCouple::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const FMishiPart* P = PartNow();
	if (!bReady || !P)
		return;
	const float Dt = DeltaSeconds * FMath::Max(P->Speed, 0.f);
	PartTime += Dt;
	if (UMishiAnimInstance* A = Player(Her))
		A->Advance(Dt);
	if (UMishiAnimInstance* A = Player(His))
		A->Advance(Dt);
	StepSkin(DeltaSeconds);
	// the narration: a line every few seconds, in the scene's order, the last one kept
	LineTimer += DeltaSeconds;
	if (LineTimer >= SubtitleSeconds && LineIndex < Data.Lines.Num() - 1)
	{
		LineTimer = 0.f;
		++LineIndex;
	}
	const float Length = P->Duration > 0.f ? P->Duration : 1.f;
	if (P->bLoop && PartTime >= Length)
	{
		PartTime = FMath::Fmod(PartTime, Length);
		PlayVoice(P->Name);                   // a loop's line again with the loop
	}
	ApplyShapes();
	if (!P->bLoop && !P->Next.IsEmpty() && PartTime >= Length * P->ExitTime)
	{
		Enter(P->Next, P->Blend);
		return;
	}
	if (bAuto && P->bLoop && P->Phase >= 0 && P->Phase < Data.Phases.Num() - 1)
	{
		AutoTimer -= DeltaSeconds;
		if (AutoTimer <= 0.f)
			GoPhase(P->Phase + 1);
	}
}
