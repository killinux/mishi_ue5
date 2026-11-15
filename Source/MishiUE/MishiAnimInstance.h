// A two-slot clip player with no Animation Blueprint: the clip now and the one it fades from, blended in the proxy's Evaluate.
// The couple sets the clips and advances the times on the game thread; the proxy gets a copy before each update.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "MishiSprings.h"
#include "MishiAnimInstance.generated.h"

class UAnimSequence;

struct FMishiClipSlot
{
	UAnimSequence* Seq = nullptr;         // held by the couple's UPROPERTY clip lists
	float Time = 0.f;
	bool bLoop = true;
};

struct FMishiAnimProxy : public FAnimInstanceProxy
{
	FMishiAnimProxy() {}
	FMishiAnimProxy(UAnimInstance* InInstance) : FAnimInstanceProxy(InInstance) {}

	virtual bool Evaluate(FPoseContext& Output) override;

	FMishiClipSlot Now, Prev;
	float Alpha = 1.f;                    // weight of Now
	FMishiSprings Springs;                // hair, chains, skirt: simulated over the clips' pose (MishiSprings.h)
	bool bSpringsOn = true;
	float FloorZ = 0.f;
};

UCLASS(Transient, NotBlueprintable)
class MISHIUE_API UMishiAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	/** Start a clip; the one playing fades out over BlendSeconds. */
	void Play(UAnimSequence* Seq, bool bLoop, float BlendSeconds);
	/** Advance both slots by DeltaSeconds (loops wrap, one-shots hold their last frame). */
	void Advance(float DeltaSeconds);

	UAnimSequence* Current() const { return Now.Seq; }
	float CurrentTime() const { return Now.Time; }

	/** The bone cloth of this body (a slice's "springs"); the proxy takes it up before its next update. */
	void SetSprings(const FMishiSpringSetup& Setup) { SpringSetup = Setup; bSpringsDirty = true; }
	/** From the animated pose again (after a seek or a teleport). */
	void ResetSprings() { bSpringsReset = true; }
	bool bSpringsOn = true;
	/** The stage's floor under her, in the world (skirt tips and chains do not go through it). */
	float FloorZ = 0.f;

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
	virtual void PreUpdateAnimation(float DeltaSeconds) override;

private:
	FMishiClipSlot Now, Prev;
	float Alpha = 1.f;
	float BlendTime = 0.25f;
	FMishiSpringSetup SpringSetup;
	bool bSpringsDirty = false, bSpringsReset = false;

	static void Step(FMishiClipSlot& Slot, float DeltaSeconds);
};
