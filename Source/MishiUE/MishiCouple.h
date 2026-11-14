// The couple of one eros-mode scene: her body and his, the parts they play (the game's controller rules), the auto mode, voices,
// music and the narration.  Tools/import_slice.py places one in the level at the room's anchor and fills its asset lists.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MishiSlice.h"
#include "MishiCouple.generated.h"

class UAnimSequence;
class UAudioComponent;
class USkeletalMesh;
class USkeletalMeshComponent;
class USoundBase;
class UMishiAnimInstance;

UCLASS()
class MISHIUE_API AMishiCouple : public AActor
{
	GENERATED_BODY()

public:
	AMishiCouple();

	/** slice.json as text: the import script copies it in, so a cooked game carries it with the level. */
	UPROPERTY(EditAnywhere, Category = "Mishi", meta = (MultiLine = true))
	FString SliceJson;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	TObjectPtr<USkeletalMesh> HerMesh;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	TObjectPtr<USkeletalMesh> HisMesh;

	/** Her takes and his (an asset's name ends with the clip's name, e.g. female_Anim_eros15_p1 for eros15_p1). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	TArray<TObjectPtr<UAnimSequence>> HerClips;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	TArray<TObjectPtr<UAnimSequence>> HisClips;

	/** Voices and the room's music, each named after its file (vo_Inase_nk_eros15_p1_jp for vo_Inase_nk_eros15_p1_jp.ogg). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	TArray<TObjectPtr<USoundBase>> Sounds;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bAuto = true;

	/** 0 off, 1 Japanese, 2 English. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	int32 VoiceLanguage = 1;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	float SubtitleSeconds = 7.f;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bShowHim = true;

	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<USceneComponent> Origin;

	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<USkeletalMeshComponent> Her;

	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<USkeletalMeshComponent> His;

	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<UAudioComponent> Voice;

	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<UAudioComponent> Music;

	const FMishiSlice& Slice() const { return Data; }
	bool IsReady() const { return bReady; }
	int32 CurrentPhase() const { return PhaseNow; }
	FString CurrentPart() const;
	FString CurrentLine() const;

	/** A phase button: the state the game's controller would go to from the current phase. */
	void GoPhase(int32 Wanted);
	void Enter(const FString& PartName, float Blend);
	void SetShowHim(bool bShow);

	/** A point / direction given in Unity's space relative to the couple's origin, in Unreal's world. */
	FVector UnityToWorld(const FVector& P) const;
	FVector UnityDirToWorld(const FVector& D) const;

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	FMishiSlice Data;
	bool bReady = false;
	int32 PartIndex = INDEX_NONE;
	float PartTime = 0.f;
	int32 PhaseNow = 0;
	float AutoTimer = 10.f;
	int32 LineIndex = 0;
	float LineTimer = 0.f;

	bool LoadSlice();
	void PlaceBodies();
	const FMishiPart* PartNow() const { return Data.Parts.IsValidIndex(PartIndex) ? &Data.Parts[PartIndex] : nullptr; }
	UAnimSequence* FindClip(const TArray<TObjectPtr<UAnimSequence>>& Clips, const FString& Name) const;
	USoundBase* FindSound(const FString& File) const;
	UMishiAnimInstance* Player(USkeletalMeshComponent* Body) const;
	void PlayVoice(const FString& PartName);
	void ResetAutoTimer();
	void ApplyShapes();
};
