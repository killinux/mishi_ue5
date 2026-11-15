// The couple of one eros-mode scene: her body and his, the parts they play (the game's controller rules), the auto mode, voices,
// music and the narration.  Tools/import_slice.py places one in the level at the room's anchor and fills its asset lists.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MishiFx.h"
#include "MishiSlice.h"
#include "MishiCouple.generated.h"

class UPointLightComponent;

class UAnimSequence;
class UAudioComponent;
class UMaterialInterface;
class UMaterialParameterCollection;
class USkeletalMesh;
class USkeletalMeshComponent;
class USoundBase;
class UMishiAnimInstance;

/** A sound starts or stops: Kind "voice" / "sfx", the file's name (empty: that kind stops), its volume.  The recorded tour writes
 *  these down with their frames, so the film's sound track is put together afterwards exactly as the game played it. */
DECLARE_MULTICAST_DELEGATE_ThreeParams(FMishiSoundEvent, const FString& /*Kind*/, const FString& /*File*/, float /*Volume*/);
/** The scene shakes the camera (a blow of a skill): how hard, how long, how fast (0: the camera's own rate). */
DECLARE_MULTICAST_DELEGATE_ThreeParams(FMishiShakeEvent, float /*Amplitude*/, float /*Seconds*/, float /*Frequency*/);
/** The game's own camera takes over for a while (a skill's camera track): seconds (0: it ends now), vertical field of view, where
 *  it stands and how it is turned in the unit's space (Unity). */
DECLARE_MULTICAST_DELEGATE_FourParams(FMishiCameraEvent, float /*Seconds*/, float /*Fov*/, const FVector& /*PosU*/, const FQuat& /*RotU*/);

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

	/** How he is drawn: 0 his own skin, 1 the game's flat silhouette, 2 not at all. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	int32 HisStyle = 0;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	TObjectPtr<UMaterialInterface> HisBodySkin;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	TObjectPtr<UMaterialInterface> HisBodySilhouette;

	/** MPC_Mishi: Wet (sweat) and Flush (blush), which the skin materials read; they follow the phase. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	TObjectPtr<UMaterialParameterCollection> SkinState;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bSkinState = true;

	/** Seconds the skin takes to follow a new phase. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float SkinEase = 4.f;

	/** A fill that goes with the camera and lights the bodies alone (lux; 0: none) - a showcase under one sun: her poses face
	 *  every way, and what faces away from the sun would be left to the sky.  Tools/mishi_look.py sets it (LOOK "camera_fill"). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float CameraFill = 0.f;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	FLinearColor CameraFillColor = FLinearColor::White;

	/** Degrees the fill's source spans: its highlight in gold and on skin is a soft patch, not a flash's point. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float CameraFillAngle = 24.f;

	/** The skills' effects (a showcase): the instances of the game's effect materials, MI_fx_<name> (the import fills this). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	TArray<TObjectPtr<UMaterialInterface>> FxMaterials;

	/** The mesh the baked effects are drawn into, frame by frame (world space: it stays unturned at the world's origin). */
	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<UProceduralMeshComponent> FxMesh;

	/** The lights the effects' particles carry (a blow lights the armour). */
	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TArray<TObjectPtr<UPointLightComponent>> FxLights;

	/** Candela of a particle light of intensity 1. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	float FxLightScale = 3.f;

	/** The skills' effects are played. */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bFx = true;

	/** Hair, chains and skirt swing (the bone cloth over the clips). */
	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bSprings = true;

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

	/** The part's own sound loop (the game's per-part SFX). */
	UPROPERTY(VisibleAnywhere, Category = "Mishi")
	TObjectPtr<UAudioComponent> Sfx;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	bool bSfx = true;

	UPROPERTY(EditAnywhere, Category = "Mishi")
	float SfxVolume = 0.8f;

	FMishiSoundEvent OnSound;
	FMishiShakeEvent OnShake;
	FMishiCameraEvent OnCamera;

	/** Where the couple was placed.  A skill carries the actor away from it and back - the unit's dash to the one it attacks, as
	 *  the game's timeline moves it; the clips are made for that: without it she would slide back where the unit should have gone. */
	FTransform Home() const { return bHome ? HomeXform : GetActorTransform(); }

	const FMishiSlice& Slice() const { return Data; }
	bool IsReady() const { return bReady; }
	bool HasFx() const { return Fx.NumActions() > 0; }
	bool HasSprings() const { return !Data.Springs.IsEmpty(); }
	int32 CurrentPhase() const { return PhaseNow; }
	FString CurrentPart() const;
	FString CurrentLine() const;
	/** The part's sound loop that plays now (empty: none) and its volume. */
	const FString& PlayingSfx() const { return SfxFile; }
	float PlayingSfxVolume() const { return SfxVolumeNow; }

	/** A phase button: the state the game's controller would go to from the current phase. */
	void GoPhase(int32 Wanted);
	void Enter(const FString& PartName, float Blend);
	/** The current part again, from this many seconds into it (look-dev stills of one moment of the motion). */
	void Seek(float Seconds);
	void SetShowHim(bool bShow);
	void SetSfx(bool bOn);
	void SetHisStyle(int32 Style);
	float GetWet() const { return Wet; }
	float GetFlush() const { return Flush; }
	USkeletalMeshComponent* GetHer() const { return Her; }
	USkeletalMeshComponent* GetHim() const { return His; }

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
	float Wet = 0.f;
	float Flush = 0.f;
	FString SfxFile;                      // the part loop that plays now
	int32 CueIndex = 0;                   // the part's next cue
	int32 AutoIndex = -1;                 // where the auto mode is in the slice's round
	FMishiFx Fx;                          // the skills' baked effects
	FTransform HomeXform;
	bool bHome = false;
	bool bMoving = false;                 // the unit is on its way (a timeline's move)
	FVector MoveFrom = FVector::ZeroVector, MoveTo = FVector::ZeroVector;
	float MoveClock = 0.f, MoveSeconds = 0.2f;
	FVector MoveGoal(const FMishiCue& C) const;
	void StartMove(const FVector& To, float Seconds);
	void StepMove(float DeltaSeconds);
	void StepFx(float DeltaSeconds);
	void SkipCues();
	void FireCues();
	float SfxVolumeNow = 0.f;
	void StepSkin(float DeltaSeconds);

	bool LoadSlice();
	void PlaceBodies();
	const FMishiPart* PartNow() const { return Data.Parts.IsValidIndex(PartIndex) ? &Data.Parts[PartIndex] : nullptr; }
	UAnimSequence* FindClip(const TArray<TObjectPtr<UAnimSequence>>& Clips, const FString& Name) const;
	USoundBase* FindSound(const FString& File) const;
	UMishiAnimInstance* Player(USkeletalMeshComponent* Body) const;
	void PlayVoice(const FString& PartName);
	void ApplySfx(const FString& PartName);
	void ResetAutoTimer();
	void ApplyShapes();
};
