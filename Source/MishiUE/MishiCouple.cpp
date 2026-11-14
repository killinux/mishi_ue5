#include "MishiCouple.h"
#include "MishiUE.h"
#include "MishiAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
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
	}
	Voice = CreateDefaultSubobject<UAudioComponent>(TEXT("Voice"));
	Voice->SetupAttachment(Origin);
	Voice->bAutoActivate = false;
	Music = CreateDefaultSubobject<UAudioComponent>(TEXT("Music"));
	Music->SetupAttachment(Origin);
	Music->bAutoActivate = false;
	Music->bIsUISound = true;              // the room's music is not placed in the room
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
	His->SetVisibility(bShowHim);
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
	PlayVoice(P.Name);
}

void AMishiCouple::SetShowHim(bool bShow)
{
	bShowHim = bShow;
	His->SetVisibility(bShowHim);
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
	}
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
