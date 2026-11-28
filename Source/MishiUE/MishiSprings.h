// Bone cloth: hair, chains and skirt panels that swing with the body, on top of the clips.
//
// The method of Magica Cloth 2's BoneCloth as the Unity project has it (Assets/RoeFighter/Runtime/RoeBoneCloth.cs), the part of
// it a chain needs.  The animated pose is the baseline: each bone's tail is a particle; every step
//   1. inertia: the particles ride the body except the share of its motion the cloth feels, never above the speed limits -
//      world inertia (the unit moving over the stage: its dash is hardly felt) and local inertia (the bone the chain hangs on
//      moving in the unit's frame: the animation; less near the root);
//   2. Verlet integration with damping, a particle speed limit, gravity and the wind;
//   3. root to tip, a few iterations: angle restoration (a share of the way back to the animated direction, most of that
//      move not becoming speed), the angle limit (root strict, tip loose), the colliders (capsules on the body), the largest
//      distance from the animated place, the floor.
// Bone lengths are rigid.  The result is written into the pose as bone rotations, in the proxy's Evaluate.
// A clip that keys a chain itself (the skirt in a skill, her front locks) stays what the chain is pulled to: the keys' swirl is
// still there, it trails and bends.
#pragma once

#include "CoreMinimal.h"
#include "BoneContainer.h"
#include "BonePose.h"

/** One kind's numbers (slice.json "springs"."sets"; metres and degrees, Magica's per 1/90 s where a share is meant). */
struct FMishiSpringSettings
{
	float Gravity = 5.f, Damping = 0.05f, Radius = 0.015f;
	float Restore = 0.3f, Attenuation = 0.8f;
	float LimitRoot = 15.f, LimitTip = 50.f;
	float Inertia = 0.3f, MoveLimit = 2.f, TurnLimit = 360.f, DepthInertia = 0.f;
	float WorldInertia = 0.3f, WorldMoveLimit = 2.f, WorldTurnLimit = 360.f;
	float ParticleLimit = 3.f;
	float MaxDistanceRoot = 0.f, MaxDistanceTip = 0.f;
	float PushAttenuation = 0.9f, Friction = 0.05f;
	float Wind = 1.f;
	float Stabilize = 0.1f;
	bool bFloor = true;
	bool bPinTip = false;                 // the far end is fastened too (a chain hung between two points of a belt): it sways, it does not drop
	int32 Iterations = 4;
};

struct FMishiSpringSet
{
	FString Kind;
	TArray<FName> Bones;                  // Unreal's names (dashes for the game's spaces)
	TArray<FString> Colliders;            // by name
	FMishiSpringSettings S;
};

/** A capsule between two bones' origins (B none: a sphere), each end moved in its bone's own axes (cm). */
struct FMishiSpringCollider
{
	FString Name;
	FName A, B;
	float RA = 5.f, RB = 5.f;             // cm
	FVector OffsetA = FVector::ZeroVector, OffsetB = FVector::ZeroVector;
};

struct FMishiSpringSetup
{
	TArray<FMishiSpringSet> Sets;
	TArray<FMishiSpringCollider> Colliders;
	FVector WindDirection = FVector::ZeroVector;      // Unreal's world, the way it blows
	float WindStrength = 0.f;                         // m/s2 on a chain of wind 1
	float WindGust = 0.5f;                            // the share of it that comes and goes
	float WindPeriod = 3.f;                           // seconds of the slowest gust

	bool IsEmpty() const { return Sets.Num() == 0; }
};

class FMishiSprings
{
public:
	void Configure(const FMishiSpringSetup& In);
	bool IsConfigured() const { return !Setup.IsEmpty(); }
	/** Start again from the animated pose (a seek, a teleport). */
	void Reset() { bReady = false; }
	/** The animated local pose in, the simulated one out.  FloorZ: the stage's floor in the world. */
	void Apply(FCompactPose& Pose, const FBoneContainer& Bones, const FTransform& ComponentToWorld, const FTransform& ActorToWorld, float DeltaSeconds,
		float FloorZ);
	int32 NumChains() const { return Chains.Num(); }
	/** The colliders as they stood in the last Apply (world, cm) - for a view of them (console: mishi.SpringColliders 1). */
	struct FColliderShape
	{
		FVector A, B;
		float RA, RB;
		bool bSphere;
	};
	void ColliderShapes(TArray<FColliderShape>& Out) const;
	int32 NumBones() const;

private:
	struct FChain
	{
		int32 Set = 0;
		TArray<FCompactPoseBoneIndex> Bones;          // root to tip, each the child of the one before
		FCompactPoseBoneIndex Anchor = FCompactPoseBoneIndex(INDEX_NONE);
		TArray<FCompactPoseBoneIndex> Child;          // whose place is the bone's tail (none: a leaf, TailLocal)
		TArray<FVector> TailLocal;
		TArray<float> Limit, Depth, MaxDistance;
		TArray<int32> Capsules;
		// the animated pose, this frame and the last
		TArray<FVector> HB, TB, HBPrev, TBPrev;
		TArray<FQuat> RB;
		TArray<FVector> Scale;
		FVector AnchorPos = FVector::ZeroVector, AnchorPosPrev = FVector::ZeroVector;
		FQuat AnchorRot = FQuat::Identity, AnchorRotPrev = FQuat::Identity;
		// the state
		TArray<FVector> X, XOld, Head, G;
		TArray<FQuat> Rot, D;
		float StabilizeLeft = 0.f;
		float Phase = 0.f;                            // of its gusts
	};

	struct FCapsule
	{
		FCompactPoseBoneIndex A = FCompactPoseBoneIndex(INDEX_NONE), B = FCompactPoseBoneIndex(INDEX_NONE);
		FVector PA = FVector::ZeroVector, PB = FVector::ZeroVector;      // world, this frame
		bool bValid = false;
	};

	FMishiSpringSetup Setup;
	TArray<FChain> Chains;
	TArray<FCapsule> Capsules;
	bool bBuilt = false, bReady = false;
	uint16 BuiltSerial = 0;
	FVector WorldPos = FVector::ZeroVector, WorldPosPrev = FVector::ZeroVector;
	FQuat WorldRot = FQuat::Identity, WorldRotPrev = FQuat::Identity;
	double Clock = 0.0;

	void Build(const FCompactPose& Pose, const FBoneContainer& Bones);
	void Simulate(FChain& C, float Dt, float WPrev, float W, float FloorZ, double Time);
	static void Carry(FChain& C, const FVector& Pivot, const FVector& Move, const FQuat& Turn, float Dt, float Inertia, float MoveLimit, float TurnLimit,
		float DepthShare);
	FVector Push(const FChain& C, const FVector& P, float Radius, bool& bHit) const;
};
