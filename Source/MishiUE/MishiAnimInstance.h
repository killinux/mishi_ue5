// A two-slot clip player with no Animation Blueprint: the clip now and the one it fades from, blended in the proxy's Evaluate.
// The couple sets the clips and advances the times on the game thread; the proxy gets a copy before each update.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
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

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
	virtual void PreUpdateAnimation(float DeltaSeconds) override;

private:
	FMishiClipSlot Now, Prev;
	float Alpha = 1.f;
	float BlendTime = 0.25f;

	static void Step(FMishiClipSlot& Slot, float DeltaSeconds);
};
