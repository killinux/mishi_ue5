#include "MishiAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"

namespace
{
	FAnimExtractContext Extract(const FMishiClipSlot& Slot)
	{
		return FAnimExtractContext(double(Slot.Time), false, FDeltaTimeRecord(), Slot.bLoop);
	}
}

bool FMishiAnimProxy::Evaluate(FPoseContext& Output)
{
	UAnimSequence* A = Now.Seq;
	UAnimSequence* B = Prev.Seq;
	if (!A)
	{
		Output.ResetToRefPose();
		return true;
	}
	if (!B || Alpha >= 1.f)
	{
		FAnimationPoseData Data(Output);
		A->GetAnimationPose(Data, Extract(Now));
	}
	else
	{
		FPoseContext PoseA(Output);
		FPoseContext PoseB(Output);
		FAnimationPoseData DataA(PoseA);
		FAnimationPoseData DataB(PoseB);
		A->GetAnimationPose(DataA, Extract(Now));
		B->GetAnimationPose(DataB, Extract(Prev));
		FAnimationPoseData Out(Output);
		FAnimationRuntime::BlendTwoPosesTogether(DataA, DataB, Alpha, Out);
	}
	// the clips' pose is what the bone cloth hangs on and is pulled to
	if (Springs.IsConfigured())
	{
		if (bSpringsOn)
			Springs.Apply(Output.Pose, GetRequiredBones(), GetComponentTransform(), GetActorTransform(), GetDeltaSeconds(), FloorZ);
		else
			Springs.Reset();
	}
	return true;
}

FAnimInstanceProxy* UMishiAnimInstance::CreateAnimInstanceProxy()
{
	return new FMishiAnimProxy(this);
}

void UMishiAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
	delete static_cast<FMishiAnimProxy*>(InProxy);
}

void UMishiAnimInstance::PreUpdateAnimation(float DeltaSeconds)
{
	Super::PreUpdateAnimation(DeltaSeconds);
	FMishiAnimProxy& Proxy = GetProxyOnGameThread<FMishiAnimProxy>();
	Proxy.Now = Now;
	Proxy.Prev = Prev;
	Proxy.Alpha = Alpha;
	if (bSpringsDirty)
	{
		Proxy.Springs.Configure(SpringSetup);
		bSpringsDirty = false;
	}
	if (bSpringsReset)
	{
		Proxy.Springs.Reset();
		bSpringsReset = false;
	}
	Proxy.bSpringsOn = bSpringsOn;
	Proxy.FloorZ = FloorZ;
}

void UMishiAnimInstance::Play(UAnimSequence* Seq, bool bLoop, float BlendSeconds)
{
	if (Now.Seq && BlendSeconds > 0.f)
	{
		Prev = Now;
		Alpha = 0.f;
	}
	else
	{
		Prev = FMishiClipSlot();
		Alpha = 1.f;
	}
	Now.Seq = Seq;
	Now.Time = 0.f;
	Now.bLoop = bLoop;
	BlendTime = FMath::Max(BlendSeconds, 0.f);
}

void UMishiAnimInstance::Step(FMishiClipSlot& Slot, float DeltaSeconds)
{
	if (!Slot.Seq)
		return;
	const float Length = FMath::Max(Slot.Seq->GetPlayLength(), 1e-3f);
	Slot.Time += DeltaSeconds;
	if (Slot.bLoop)
		Slot.Time = FMath::Fmod(Slot.Time, Length);
	else
		Slot.Time = FMath::Min(Slot.Time, Length);
}

void UMishiAnimInstance::Advance(float DeltaSeconds)
{
	Step(Now, DeltaSeconds);
	if (Prev.Seq)
	{
		Step(Prev, DeltaSeconds);
		Alpha = BlendTime > 0.f ? FMath::Min(1.f, Alpha + DeltaSeconds / BlendTime) : 1.f;
		if (Alpha >= 1.f)
			Prev = FMishiClipSlot();
	}
}
