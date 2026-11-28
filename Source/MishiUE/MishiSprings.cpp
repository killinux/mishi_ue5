#include "MishiSprings.h"

namespace
{
	/** Direction A turned a share of the way to B. */
	FVector TurnTo(const FVector& A, const FVector& B, float Fraction)
	{
		const double Cos = FMath::Clamp(FVector::DotProduct(A, B), -1.0, 1.0);
		const double Angle = FMath::Acos(Cos);
		if (Angle < 1e-5)
			return B;
		FVector Axis = FVector::CrossProduct(A, B);
		if (!Axis.Normalize(1e-8))
			return A;                            // opposite: no way to say which way round
		return FQuat(Axis, Angle * Fraction).RotateVector(A);
	}

	/** Direction Dir, no further than Limit (radians) from G. */
	FVector Within(const FVector& G, const FVector& Dir, float Limit)
	{
		const double Cos = FMath::Clamp(FVector::DotProduct(G, Dir), -1.0, 1.0);
		const double Angle = FMath::Acos(Cos);
		if (Angle <= Limit)
			return Dir;
		FVector Axis = FVector::CrossProduct(G, Dir);
		if (!Axis.Normalize(1e-8))
			return G;
		return FQuat(Axis, Limit).RotateVector(G);
	}
}

void FMishiSprings::Configure(const FMishiSpringSetup& In)
{
	Setup = In;
	if (!Setup.WindDirection.Normalize())
		Setup.WindStrength = 0.f;
	bBuilt = false;
	bReady = false;
}

int32 FMishiSprings::NumBones() const
{
	int32 N = 0;
	for (const FChain& C : Chains)
		N += C.Bones.Num();
	return N;
}

void FMishiSprings::Build(const FCompactPose& Pose, const FBoneContainer& Bones)
{
	Chains.Reset();
	Capsules.Reset();
	const int32 N = Bones.GetCompactPoseNumBones();
	auto Find = [&Bones](const FName& Name)
	{
		const int32 Mesh = Bones.GetPoseBoneIndexForBoneName(Name);
		return Mesh == INDEX_NONE ? FCompactPoseBoneIndex(INDEX_NONE) : Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(Mesh));
	};
	TArray<int32> Raw;
	Raw.Init(INDEX_NONE, N);
	for (int32 S = 0; S < Setup.Sets.Num(); ++S)
		for (const FName& Name : Setup.Sets[S].Bones)
		{
			const FCompactPoseBoneIndex I = Find(Name);
			if (I.GetInt() != INDEX_NONE && I.GetInt() < N)
				Raw[I.GetInt()] = S;
		}
	TArray<TArray<int32>> Children;
	Children.SetNum(N);
	for (int32 I = 1; I < N; ++I)
	{
		const FCompactPoseBoneIndex P = Bones.GetParentBoneIndex(FCompactPoseBoneIndex(I));
		if (P.GetInt() != INDEX_NONE)
			Children[P.GetInt()].Add(I);
	}
	// a bone with several named children is not simulated itself (they hang on it); nor is one whose only child sits on it
	// (a holder: no length to swing)
	TArray<int32> SetOf = Raw;
	for (int32 I = 0; I < N; ++I)
	{
		if (Raw[I] == INDEX_NONE)
			continue;
		int32 Named = 0;
		for (int32 Ch : Children[I])
			Named += Raw[Ch] != INDEX_NONE ? 1 : 0;
		if (Named > 1)
			SetOf[I] = INDEX_NONE;
		else if (Children[I].Num() == 1 && Pose[FCompactPoseBoneIndex(Children[I][0])].GetTranslation().Size() < 0.2)
			SetOf[I] = INDEX_NONE;
	}
	for (const FMishiSpringCollider& Col : Setup.Colliders)
	{
		FCapsule& Cap = Capsules.AddDefaulted_GetRef();
		Cap.A = Find(Col.A);
		Cap.B = Col.B.IsNone() ? FCompactPoseBoneIndex(INDEX_NONE) : Find(Col.B);
		Cap.bValid = Cap.A.GetInt() != INDEX_NONE;
	}
	int32 Serial = 0;
	for (int32 I = 0; I < N; ++I)
	{
		if (SetOf[I] == INDEX_NONE)
			continue;
		const FCompactPoseBoneIndex Parent = Bones.GetParentBoneIndex(FCompactPoseBoneIndex(I));
		if (Parent.GetInt() != INDEX_NONE && SetOf[Parent.GetInt()] != INDEX_NONE)
			continue;                           // not a root: its chain picks it up
		FChain& C = Chains.AddDefaulted_GetRef();
		C.Set = SetOf[I];
		C.Anchor = Parent;
		C.Phase = 1.7f * float(Serial++);
		TArray<float> Lengths;
		for (int32 At = I; At != INDEX_NONE;)
		{
			C.Bones.Add(FCompactPoseBoneIndex(At));
			int32 Next = INDEX_NONE, Only = Children[At].Num() == 1 ? Children[At][0] : INDEX_NONE;
			for (int32 Ch : Children[At])
				if (SetOf[Ch] == C.Set)
				{
					Next = Ch;
					break;
				}
			const int32 Tail = Next != INDEX_NONE ? Next : Only;
			FVector Local = FVector::ZeroVector;
			if (Tail != INDEX_NONE && Pose[FCompactPoseBoneIndex(Tail)].GetTranslation().Size() > 0.2)
			{
				C.Child.Add(FCompactPoseBoneIndex(Tail));
				Lengths.Add(float(Pose[FCompactPoseBoneIndex(Tail)].GetTranslation().Size()));
			}
			else
			{
				// a leaf: it goes on the way it came, as long as it is itself (an earring, the last link)
				const FTransform& Own = Pose[FCompactPoseBoneIndex(At)];
				const float Len = FMath::Clamp(float(Own.GetTranslation().Size()), 2.f, 10.f);
				Local = Own.GetRotation().UnrotateVector(Own.GetTranslation().GetSafeNormal(1e-6, FVector(1, 0, 0))) * Len;
				C.Child.Add(FCompactPoseBoneIndex(INDEX_NONE));
				Lengths.Add(Len);
			}
			C.TailLocal.Add(Local);
			At = Next;
		}
		const int32 M = C.Bones.Num();
		float Total = 0.f;
		for (float L : Lengths)
			Total += L;
		const FMishiSpringSettings& S = Setup.Sets[C.Set].S;
		float Run = 0.f;
		for (int32 K = 0; K < M; ++K)
		{
			Run += Lengths[K];
			const float Depth = Total > 0.f ? Run / Total : 1.f;
			C.Depth.Add(Depth);
			C.Limit.Add(FMath::DegreesToRadians(FMath::Lerp(S.LimitRoot, S.LimitTip, Depth)));
			C.MaxDistance.Add(FMath::Lerp(S.MaxDistanceRoot, S.MaxDistanceTip, Depth) * 100.f);
		}
		for (const FString& Name : Setup.Sets[C.Set].Colliders)
		{
			const int32 Index = Setup.Colliders.IndexOfByPredicate([&Name](const FMishiSpringCollider& X) { return X.Name == Name; });
			if (Index != INDEX_NONE && Capsules[Index].bValid)
				C.Capsules.Add(Index);
		}
		for (TArray<FVector>* A : {&C.HB, &C.TB, &C.HBPrev, &C.TBPrev, &C.X, &C.XOld, &C.Head, &C.G, &C.Scale})
			A->Init(FVector::ZeroVector, M);
		for (TArray<FQuat>* A : {&C.RB, &C.Rot, &C.D})
			A->Init(FQuat::Identity, M);
	}
}

void FMishiSprings::Carry(FChain& C, const FVector& Pivot, const FVector& Move, const FQuat& Turn, float Dt, float Inertia, float MoveLimit, float TurnLimit,
	float DepthShare)
{
	// the particles go with a rigid motion, all but the share the cloth feels: Inertia, less above the speed limits
	const float Speed = float(Move.Size()) / Dt;
	const float FeltT = Speed > 1e-4f ? Inertia * FMath::Min(1.f, MoveLimit / Speed) : Inertia;
	float Angle = FMath::RadiansToDegrees(float(Turn.GetAngle()));
	if (Angle > 180.f)
		Angle = 360.f - Angle;
	const float FeltR = Angle > 1e-4f ? Inertia * FMath::Min(1.f, TurnLimit * Dt / Angle) : Inertia;
	for (int32 I = 0; I < C.X.Num(); ++I)
	{
		const float K = 1.f - DepthShare * (1.f - C.Depth[I]);
		const FQuat Q = FQuat::Slerp(FQuat::Identity, Turn, 1.f - FeltR * K);
		const FVector Shift = Move * (1.f - FeltT * K);
		C.X[I] = Q.RotateVector(C.X[I] - Pivot) + Pivot + Shift;
		C.XOld[I] = Q.RotateVector(C.XOld[I] - Pivot) + Pivot + Shift;
	}
}

FVector FMishiSprings::Push(const FChain& C, const FVector& P, float Radius, bool& bHit) const
{
	FVector Out = P;
	bHit = false;
	for (int32 Index : C.Capsules)
	{
		const FCapsule& Cap = Capsules[Index];
		const FMishiSpringCollider& Col = Setup.Colliders[Index];
		const FVector AB = Cap.PB - Cap.PA;
		const double Len2 = AB.SizeSquared();
		const double T = Len2 > 1e-6 ? FMath::Clamp(FVector::DotProduct(Out - Cap.PA, AB) / Len2, 0.0, 1.0) : 0.0;
		const FVector On = Cap.PA + AB * T;
		const double R = FMath::Lerp(double(Col.RA), double(Col.RB), T) + Radius;
		const FVector Off = Out - On;
		const double Dist = Off.Size();
		if (Dist < R && Dist > 1e-4)
		{
			Out = On + Off * (R / Dist);
			bHit = true;
		}
	}
	return Out;
}

void FMishiSprings::Simulate(FChain& C, float Dt, float WPrev, float W, float FloorZ, double Time)
{
	const FMishiSpringSettings& S = Setup.Sets[C.Set].S;
	const int32 N = C.Bones.Num();
	const float Step90 = Dt * 90.f;
	const float Damp = 1.f - FMath::Pow(1.f - S.Damping, Step90);
	const float Restore = 1.f - FMath::Pow(1.f - S.Restore, Step90);
	const float Radius = S.Radius * 100.f;

	// the animated pose and the anchor in between the frames
	TArray<FVector, TInlineAllocator<16>> HB, TB, D0;
	HB.SetNum(N);
	TB.SetNum(N);
	D0.SetNum(N);
	for (int32 I = 0; I < N; ++I)
	{
		HB[I] = FMath::Lerp(C.HBPrev[I], C.HB[I], W);
		TB[I] = FMath::Lerp(C.TBPrev[I], C.TB[I], W);
		D0[I] = (TB[I] - HB[I]).GetSafeNormal(1e-8, FVector(0, 0, -1));
	}
	const FVector CPos = FMath::Lerp(C.AnchorPosPrev, C.AnchorPos, W);
	const FQuat CRot = FQuat::Slerp(C.AnchorRotPrev, C.AnchorRot, W);
	const FVector PrevPos = FMath::Lerp(C.AnchorPosPrev, C.AnchorPos, WPrev);
	const FQuat PrevRot = FQuat::Slerp(C.AnchorRotPrev, C.AnchorRot, WPrev);

	// 1. inertia: the unit over the stage, then the anchor in the unit's frame (the animation)
	const FVector WPos = FMath::Lerp(WorldPosPrev, WorldPos, W);
	const FQuat WRot = FQuat::Slerp(WorldRotPrev, WorldRot, W);
	const FVector WPos0 = FMath::Lerp(WorldPosPrev, WorldPos, WPrev);
	const FQuat WRot0 = FQuat::Slerp(WorldRotPrev, WorldRot, WPrev);
	Carry(C, WPos0, WPos - WPos0, WRot * WRot0.Inverse(), Dt, S.WorldInertia, S.WorldMoveLimit * 100.f, S.WorldTurnLimit, 0.f);
	const FVector Local0 = WRot0.UnrotateVector(PrevPos - WPos0);
	const FVector Local1 = WRot.UnrotateVector(CPos - WPos);
	const FQuat LR0 = WRot0.Inverse() * PrevRot;
	const FQuat LR1 = WRot.Inverse() * CRot;
	Carry(C, WPos + WRot.RotateVector(Local0), WRot.RotateVector(Local1 - Local0), WRot * (LR1 * LR0.Inverse()) * WRot.Inverse(), Dt, S.Inertia,
		S.MoveLimit * 100.f, S.TurnLimit, S.DepthInertia);

	// 2. Verlet: damping, the speed limit, gravity and the wind (it comes and goes, each chain in its own time, and flutters
	// across its way)
	FVector Accel(0.0, 0.0, -S.Gravity * 100.0);
	if (Setup.WindStrength > 0.f && S.Wind > 0.f)
	{
		const double P = FMath::Max(double(Setup.WindPeriod), 0.2);
		const double T = Time * 2.0 * PI / P;
		const double Gust = 0.5 + 0.5 * (0.6 * FMath::Sin(T + C.Phase) + 0.4 * FMath::Sin(T * 2.7 + C.Phase * 1.7));
		const double Level = 1.0 - Setup.WindGust + Setup.WindGust * Gust;
		const FVector Across = FVector::CrossProduct(Setup.WindDirection, FVector::UpVector).GetSafeNormal();
		const double Flutter = 0.35 * FMath::Sin(T * 5.3 + C.Phase * 2.3);
		Accel += (Setup.WindDirection + Across * Flutter) * (Setup.WindStrength * 100.0 * S.Wind * Level);
	}
	const float SpeedLimit = S.ParticleLimit * 100.f;
	for (int32 I = 0; I < N; ++I)
	{
		FVector V = (C.X[I] - C.XOld[I]) / Dt * (1.f - Damp);
		const double Sp = V.Size();
		if (Sp > SpeedLimit)
			V *= SpeedLimit / Sp;
		V += Accel * Dt;
		C.XOld[I] = C.X[I];
		C.X[I] += V * Dt;
	}

	// 3. constraints, root to tip
	for (int32 It = 0; It < FMath::Max(S.Iterations, 1); ++It)
	{
		for (int32 I = 0; I < N; ++I)
		{
			const float L = float((TB[I] - HB[I]).Size());
			// the parent's turn away from its animated pose carries this bone's baseline
			C.D[I] = I == 0 ? FQuat::Identity : C.Rot[I - 1] * C.RB[I - 1].Inverse();
			C.Head[I] = I == 0 ? HB[0] : C.X[I - 1];
			C.G[I] = C.D[I].RotateVector(D0[I]).GetSafeNormal(1e-8, D0[I]);
			FVector Dir = (C.X[I] - C.Head[I]).GetSafeNormal(1e-8, C.G[I]);
			if (It == 0)
			{
				// angle restoration, once a step; most of the move does not become speed
				const FVector D2 = TurnTo(Dir, C.G[I], Restore);
				const FVector NX = C.Head[I] + D2 * L;
				C.XOld[I] += (NX - C.X[I]) * S.Attenuation;
				C.X[I] = NX;
				Dir = D2;
			}
			Dir = Within(C.G[I], Dir, C.Limit[I]);
			C.X[I] = C.Head[I] + Dir * L;
			// the body: the leg carries the cloth along, it does not bat it away - most of the push does not become speed
			if (C.Capsules.Num() > 0)
			{
				bool bHit = false;
				FVector NX = Push(C, C.X[I], Radius, bHit);
				NX = C.Head[I] + (NX - C.Head[I]).GetSafeNormal(1e-8, Dir) * L;
				if (bHit)
				{
					C.XOld[I] += (NX - C.X[I]) * S.PushAttenuation;
					C.XOld[I] += (NX - C.XOld[I]) * S.Friction;
				}
				C.X[I] = NX;
			}
			// no further from its animated place than this
			if (C.MaxDistance[I] > 0.f)
			{
				const FVector Off = C.X[I] - TB[I];
				if (Off.Size() > C.MaxDistance[I])
				{
					const FVector To = TB[I] + Off.GetSafeNormal() * C.MaxDistance[I];
					C.X[I] = C.Head[I] + (To - C.Head[I]).GetSafeNormal(1e-8, Dir) * L;
				}
			}
			// the floor: the bone turns up just enough; into the floor the speed is stopped
			if (S.bFloor)
			{
				const double Lo = FloorZ + Radius;
				FVector Dn = (C.X[I] - C.Head[I]).GetSafeNormal(1e-8, Dir);
				const double ZMin = FMath::Clamp((Lo - C.Head[I].Z) / FMath::Max(double(L), 1e-4), -1.0, 1.0);
				if (Dn.Z < ZMin)
				{
					FVector Hor(Dn.X, Dn.Y, 0.0);
					if (!Hor.Normalize(1e-6))
						Hor = FVector(D0[I].X, D0[I].Y, 0.0).GetSafeNormal(1e-6, FVector(1, 0, 0));
					Dn = Hor * FMath::Sqrt(FMath::Max(0.0, 1.0 - ZMin * ZMin)) + FVector(0.0, 0.0, ZMin);
					C.X[I] = C.Head[I] + Dn * L;
					C.XOld[I].Z = FMath::Max(C.XOld[I].Z, C.X[I].Z);
				}
			}
			// the bone's frame: the animated one carried by the parent, swung onto the simulated direction
			const FVector Sim = (C.X[I] - C.Head[I]).GetSafeNormal(1e-8, C.G[I]);
			C.Rot[I] = FQuat::FindBetweenNormals(C.G[I], Sim) * C.D[I] * C.RB[I];
		}
		// a chain fastened at both ends: its last tail goes back to its animated place, and from there the links are drawn
		// in towards the root (the next round, from the root out again, makes the lengths exact)
		if (S.bPinTip && N > 1)
		{
			C.X[N - 1] = TB[N - 1];
			for (int32 I = N - 1; I >= 1; --I)
			{
				const float L = float((TB[I] - HB[I]).Size());
				C.X[I - 1] = C.X[I] + (C.X[I - 1] - C.X[I]).GetSafeNormal(1e-8, -D0[I]) * L;
			}
		}
	}
	// the frames once more from the root, lengths exact, where the last round moved the links
	if (S.bPinTip && N > 1)
		for (int32 I = 0; I < N; ++I)
		{
			const float L = float((TB[I] - HB[I]).Size());
			C.D[I] = I == 0 ? FQuat::Identity : C.Rot[I - 1] * C.RB[I - 1].Inverse();
			C.Head[I] = I == 0 ? HB[0] : C.X[I - 1];
			C.G[I] = C.D[I].RotateVector(D0[I]).GetSafeNormal(1e-8, D0[I]);
			const FVector Sim = (C.X[I] - C.Head[I]).GetSafeNormal(1e-8, C.G[I]);
			C.X[I] = C.Head[I] + Sim * L;
			C.Rot[I] = FQuat::FindBetweenNormals(C.G[I], Sim) * C.D[I] * C.RB[I];
		}
	// just after a reset nothing that was pushed into place becomes speed
	if (C.StabilizeLeft > 0.f)
		C.XOld = C.X;
}

void FMishiSprings::ColliderShapes(TArray<FColliderShape>& Out) const
{
	for (int32 K = 0; K < Capsules.Num(); ++K)
		if (Capsules[K].bValid)
			Out.Add({Capsules[K].PA, Capsules[K].PB, Setup.Colliders[K].RA, Setup.Colliders[K].RB, Capsules[K].B.GetInt() == INDEX_NONE});
}

void FMishiSprings::Apply(FCompactPose& Pose, const FBoneContainer& Bones, const FTransform& ComponentToWorld, const FTransform& ActorToWorld,
	float DeltaSeconds, float FloorZ)
{
	if (Setup.IsEmpty())
		return;
	if (!bBuilt || BuiltSerial != Bones.GetSerialNumber())
	{
		Build(Pose, Bones);
		BuiltSerial = Bones.GetSerialNumber();
		bBuilt = true;
		bReady = false;
	}
	if (Chains.Num() == 0)
		return;
	FCSPose<FCompactPose> CS;
	CS.InitPose(Pose);
	auto World = [&CS, &ComponentToWorld](FCompactPoseBoneIndex I) { return CS.GetComponentSpaceTransform(I) * ComponentToWorld; };

	WorldPos = ActorToWorld.GetLocation();
	WorldRot = ActorToWorld.GetRotation();
	for (int32 K = 0; K < Capsules.Num(); ++K)
	{
		FCapsule& Cap = Capsules[K];
		if (!Cap.bValid)
			continue;
		const FMishiSpringCollider& Col = Setup.Colliders[K];
		Cap.PA = World(Cap.A).TransformPosition(Col.OffsetA);
		Cap.PB = Cap.B.GetInt() != INDEX_NONE ? World(Cap.B).TransformPosition(Col.OffsetB) : Cap.PA;
	}
	for (FChain& C : Chains)
	{
		for (int32 I = 0; I < C.Bones.Num(); ++I)
		{
			const FTransform T = World(C.Bones[I]);
			C.HB[I] = T.GetLocation();
			C.RB[I] = T.GetRotation();
			C.Scale[I] = T.GetScale3D();
			C.TB[I] = C.Child[I].GetInt() != INDEX_NONE ? World(C.Child[I]).GetLocation() : T.TransformPosition(C.TailLocal[I]);
		}
		const FTransform A = C.Anchor.GetInt() != INDEX_NONE ? World(C.Anchor) : ComponentToWorld;
		C.AnchorPos = A.GetLocation();
		C.AnchorRot = A.GetRotation();
	}
	// a start, a seek or a long stall: from the animated pose
	if (!bReady || DeltaSeconds > 0.25f)
	{
		for (FChain& C : Chains)
		{
			C.X = C.TB;
			C.XOld = C.TB;
			C.HBPrev = C.HB;
			C.TBPrev = C.TB;
			C.Rot = C.RB;
			C.Head = C.HB;
			C.AnchorPosPrev = C.AnchorPos;
			C.AnchorRotPrev = C.AnchorRot;
			C.StabilizeLeft = Setup.Sets[C.Set].S.Stabilize;
		}
		WorldPosPrev = WorldPos;
		WorldRotPrev = WorldRot;
		bReady = true;
	}
	if (DeltaSeconds > 0.f)
	{
		const int32 Sub = FMath::Max(1, FMath::RoundToInt(DeltaSeconds * 120.f));
		for (FChain& C : Chains)
		{
			for (int32 K = 0; K < Sub; ++K)
				Simulate(C, DeltaSeconds / Sub, float(K) / Sub, float(K + 1) / Sub, FloorZ, Clock + DeltaSeconds * (K + 1) / Sub);
			C.HBPrev = C.HB;
			C.TBPrev = C.TB;
			C.AnchorPosPrev = C.AnchorPos;
			C.AnchorRotPrev = C.AnchorRot;
			C.StabilizeLeft -= DeltaSeconds;
		}
		WorldPosPrev = WorldPos;
		WorldRotPrev = WorldRot;
		Clock += DeltaSeconds;
	}

	// into the pose: each bone where its head is and turned as the chain has it, relative to its (new) parent
	for (FChain& C : Chains)
	{
		FTransform ParentCS = C.Anchor.GetInt() != INDEX_NONE ? CS.GetComponentSpaceTransform(C.Anchor) : FTransform::Identity;
		for (int32 I = 0; I < C.Bones.Num(); ++I)
		{
			const FVector At = I == 0 ? C.HB[0] : C.X[I - 1];
			const FTransform NewCS = FTransform(C.Rot[I], At, C.Scale[I]).GetRelativeTransform(ComponentToWorld);
			FTransform Local = NewCS.GetRelativeTransform(ParentCS);
			Local.SetScale3D(Pose[C.Bones[I]].GetScale3D());
			Local.NormalizeRotation();
			if (!Local.ContainsNaN())
				Pose[C.Bones[I]] = Local;
			ParentCS = NewCS;
		}
	}
}
