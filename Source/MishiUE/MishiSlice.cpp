#include "MishiSlice.h"
#include "MishiUE.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	using FObj = TSharedPtr<FJsonObject>;
	using FArr = TArray<TSharedPtr<FJsonValue>>;

	FObj Obj(const FObj& O, const TCHAR* Field)
	{
		const FObj* Out = nullptr;
		return O.IsValid() && O->TryGetObjectField(Field, Out) && Out ? *Out : FObj();
	}

	const FArr* Arr(const FObj& O, const TCHAR* Field)
	{
		const FArr* Out = nullptr;
		return O.IsValid() && O->TryGetArrayField(Field, Out) ? Out : nullptr;
	}

	FString Str(const FObj& O, const TCHAR* Field)
	{
		FString Out;
		return O.IsValid() && O->TryGetStringField(Field, Out) ? Out : FString();
	}

	float Num(const FObj& O, const TCHAR* Field, float Default = 0.f)
	{
		double Out = 0.0;
		return O.IsValid() && O->TryGetNumberField(Field, Out) ? float(Out) : Default;
	}

	bool Bool(const FObj& O, const TCHAR* Field, bool Default = false)
	{
		bool Out = false;
		return O.IsValid() && O->TryGetBoolField(Field, Out) ? Out : Default;
	}

	double At(const FArr& A, int32 I) { return A.IsValidIndex(I) && A[I].IsValid() ? A[I]->AsNumber() : 0.0; }

	FVector Vec(const FObj& O, const TCHAR* Field, const FVector& Default = FVector::ZeroVector)
	{
		const FArr* A = Arr(O, Field);
		return A && A->Num() >= 3 ? FVector(At(*A, 0), At(*A, 1), At(*A, 2)) : Default;
	}

	FVector2D Vec2(const FObj& O, const TCHAR* Field, const FVector2D& Default = FVector2D::ZeroVector)
	{
		const FArr* A = Arr(O, Field);
		return A && A->Num() >= 2 ? FVector2D(At(*A, 0), At(*A, 1)) : Default;
	}

	FQuat Quat(const FObj& O, const TCHAR* Field)
	{
		const FArr* A = Arr(O, Field);
		if (!A || A->Num() < 4)
			return FQuat::Identity;
		FQuat Q(At(*A, 0), At(*A, 1), At(*A, 2), At(*A, 3));
		Q.Normalize();
		return Q;
	}

	TArray<int32> Ints(const FObj& O, const TCHAR* Field)
	{
		TArray<int32> Out;
		if (const FArr* A = Arr(O, Field))
			for (const TSharedPtr<FJsonValue>& V : *A)
				Out.Add(V.IsValid() ? int32(V->AsNumber()) : 0);
		return Out;
	}

	FMishiUnityXform Xform(const FObj& O)
	{
		FMishiUnityXform X;
		if (O.IsValid())
		{
			X.Pos = Vec(O, TEXT("position"));
			X.Rot = Quat(O, TEXT("rotation"));
			X.Scale = Vec(O, TEXT("scale"), FVector::OneVector);
		}
		return X;
	}

	template <typename F>
	void Each(const FObj& O, const TCHAR* Field, F&& Fn)
	{
		if (const FArr* A = Arr(O, Field))
			for (const TSharedPtr<FJsonValue>& V : *A)
				if (V.IsValid() && V->Type == EJson::Object)
					Fn(V->AsObject());
	}
}

FMishiUnityXform FMishiUnityXform::operator*(const FMishiUnityXform& Child) const
{
	FMishiUnityXform R;
	R.Pos = TransformPoint(Child.Pos);
	R.Rot = Rot * Child.Rot;
	R.Scale = Scale * Child.Scale;
	return R;
}

FTransform FMishiUnityXform::ToUE() const
{
	return MishiSpace::Transform(Pos, Rot, Scale);
}

bool FMishiRule::Matches(const FString& Trig, int32 Phase) const
{
	if (Trig != Trigger)
		return false;
	for (int32 V : PhaseEquals)
		if (Phase != V)
			return false;
	for (int32 V : PhaseNotEquals)
		if (Phase == V)
			return false;
	return true;
}

float FMishiShapeTrack::Sample(const TArray<float>& Keys, float Time, bool bLoop) const
{
	const int32 N = Keys.Num();
	if (N == 0)
		return 0.f;
	if (N == 1)
		return Keys[0];
	float F = FMath::Max(0.f, Time) * Fps;
	if (bLoop)
		F = FMath::Fmod(F, float(N - 1));
	else
		F = FMath::Min(F, float(N - 1));
	const int32 I = FMath::Min(int32(F), N - 2);
	return FMath::Lerp(Keys[I], Keys[I + 1], F - I);
}

bool FMishiSlice::Parse(const FString& Json, FString& OutError)
{
	FObj Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		OutError = FString::Printf(TEXT("slice.json does not parse: %s"), *Reader->GetErrorMessage());
		return false;
	}
	Kind = Str(Root, TEXT("kind"));
	if (Kind.IsEmpty())
		Kind = TEXT("eros");
	Posture = Str(Root, TEXT("posture"));
	Title = Str(Root, TEXT("title"));
	Outfit = Str(Root, TEXT("outfit"));
	Scene = Str(Root, TEXT("scene"));
	Room = Str(Root, TEXT("room"));
	const FObj Female = Obj(Root, TEXT("female")), Male = Obj(Root, TEXT("male"));
	FemaleRoot = Str(Female, TEXT("root"));
	MaleRoot = Str(Male, TEXT("root"));
	FemaleOffset = Xform(Obj(Female, TEXT("offset")));
	MaleOffset = Xform(Obj(Male, TEXT("offset")));
	bMale = Bool(Male, TEXT("ok"), true);
	Auto = Ints(Root, TEXT("auto"));
	Cues.Reset();
	if (const FObj AllCues = Obj(Root, TEXT("cues")))
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Kv : AllCues->Values)
		{
			if (!Kv.Value.IsValid() || Kv.Value->Type != EJson::Array)
				continue;
			TArray<FMishiCue>& List = Cues.Add(Kv.Key);
			for (const TSharedPtr<FJsonValue>& V : Kv.Value->AsArray())
			{
				if (!V.IsValid() || V->Type != EJson::Object)
					continue;
				const FObj O = V->AsObject();
				FMishiCue& C = List.AddDefaulted_GetRef();
				const FString K = Str(O, TEXT("kind"));
				C.Kind = K == TEXT("sfx") ? 0 : K == TEXT("voice") ? 1 : K == TEXT("shake") ? 2 : K == TEXT("move") ? 4 : K == TEXT("camera") ? 5
					: K == TEXT("fx") ? 6 : 3;
				C.Action = Str(O, TEXT("action"));
				C.Move = Str(O, TEXT("move"));
				C.Radius = Num(O, TEXT("radius"), 1.f);
				C.Fov = Num(O, TEXT("fov"), 40.f);
				C.Pos = Vec(O, TEXT("position"));
				C.Rot = Quat(O, TEXT("rotation"));
				C.Time = Num(O, TEXT("time"));
				C.File = Str(O, TEXT("file"));
				C.Jp = Str(O, TEXT("jp"));
				C.En = Str(O, TEXT("en"));
				C.Volume = Num(O, TEXT("volume"), 1.f);
				C.Duration = Num(O, TEXT("duration"), 0.5f);
				C.Amplitude = Num(O, TEXT("amplitude"), 0.5f);
				C.Frequency = Num(O, TEXT("frequency"), 0.f);
			}
			List.StableSort([](const FMishiCue& A, const FMishiCue& B) { return A.Time < B.Time; });
		}
	Target = Vec(Root, TEXT("target"), FVector(0.0, 0.0, 6.0));
	Effects = Str(Root, TEXT("effects"));
	AuraAction.Reset();
	AuraParts.Reset();
	AuraNever.Reset();
	AuraFollow = NAME_None;
	if (const FObj Au = Obj(Root, TEXT("aura")))
	{
		AuraAction = Str(Au, TEXT("action"));
		if (const FArr* A = Arr(Au, TEXT("parts")))
			for (const TSharedPtr<FJsonValue>& V : *A)
				AuraParts.Add(V.IsValid() ? V->AsString() : FString());
		if (const FArr* A = Arr(Au, TEXT("never")))
			for (const TSharedPtr<FJsonValue>& V : *A)
				AuraNever.Add(V.IsValid() ? V->AsString() : FString());
		const FString Follow = Str(Au, TEXT("follow"));
		if (!Follow.IsEmpty())
			AuraFollow = FName(*Follow.Replace(TEXT(" "), TEXT("-")));
	}
	// the bone cloth: the sets of bones by kind with their numbers, the body's capsules, the wind
	Springs = FMishiSpringSetup();
	if (const FObj Sp = Obj(Root, TEXT("springs")))
	{
		auto Bone = [](const FString& Name) { return Name.IsEmpty() ? FName() : FName(*Name.Replace(TEXT(" "), TEXT("-"))); };
		const FObj Wind = Obj(Sp, TEXT("wind"));
		Springs.WindDirection = MishiSpace::Direction(Vec(Wind, TEXT("direction")));
		Springs.WindStrength = Num(Wind, TEXT("strength"));
		Springs.WindGust = Num(Wind, TEXT("gust"), 0.5f);
		Springs.WindPeriod = Num(Wind, TEXT("period"), 3.f);
		Each(Sp, TEXT("colliders"), [this, &Bone](const FObj& O)
		{
			FMishiSpringCollider& C = Springs.Colliders.AddDefaulted_GetRef();
			C.Name = Str(O, TEXT("name"));
			C.A = Bone(Str(O, TEXT("a")));
			C.B = Bone(Str(O, TEXT("b")));
			C.RA = Num(O, TEXT("ra"), 0.05f) * 100.f;
			C.RB = Num(O, TEXT("rb"), Num(O, TEXT("ra"), 0.05f)) * 100.f;
			C.OffsetA = Vec(O, TEXT("offset_a"));              // cm, in the bone's own (Unreal) axes
			C.OffsetB = Vec(O, TEXT("offset_b"));
		});
		Each(Sp, TEXT("sets"), [this, &Bone](const FObj& O)
		{
			FMishiSpringSet& Set = Springs.Sets.AddDefaulted_GetRef();
			Set.Kind = Str(O, TEXT("kind"));
			if (const FArr* A = Arr(O, TEXT("bones")))
				for (const TSharedPtr<FJsonValue>& V : *A)
					if (V.IsValid())
						Set.Bones.Add(Bone(V->AsString()));
			if (const FArr* A = Arr(O, TEXT("colliders")))
				for (const TSharedPtr<FJsonValue>& V : *A)
					if (V.IsValid())
						Set.Colliders.Add(V->AsString());
			FMishiSpringSettings& S = Set.S;
			S.Gravity = Num(O, TEXT("gravity"), S.Gravity);
			S.Damping = Num(O, TEXT("damping"), S.Damping);
			S.Radius = Num(O, TEXT("radius"), S.Radius);
			S.Restore = Num(O, TEXT("restore"), S.Restore);
			S.Attenuation = Num(O, TEXT("attenuation"), S.Attenuation);
			S.LimitRoot = Num(O, TEXT("limit_root"), S.LimitRoot);
			S.LimitTip = Num(O, TEXT("limit_tip"), S.LimitTip);
			S.Inertia = Num(O, TEXT("inertia"), S.Inertia);
			S.MoveLimit = Num(O, TEXT("move_limit"), S.MoveLimit);
			S.TurnLimit = Num(O, TEXT("turn_limit"), S.TurnLimit);
			S.DepthInertia = Num(O, TEXT("depth_inertia"), S.DepthInertia);
			S.WorldInertia = Num(O, TEXT("world_inertia"), S.WorldInertia);
			S.WorldMoveLimit = Num(O, TEXT("world_move_limit"), S.WorldMoveLimit);
			S.WorldTurnLimit = Num(O, TEXT("world_turn_limit"), S.WorldTurnLimit);
			S.ParticleLimit = Num(O, TEXT("particle_limit"), S.ParticleLimit);
			S.MaxDistanceRoot = Num(O, TEXT("max_distance_root"), S.MaxDistanceRoot);
			S.MaxDistanceTip = Num(O, TEXT("max_distance_tip"), S.MaxDistanceTip);
			S.PushAttenuation = Num(O, TEXT("push_attenuation"), S.PushAttenuation);
			S.Friction = Num(O, TEXT("friction"), S.Friction);
			S.Wind = Num(O, TEXT("wind"), S.Wind);
			S.Stabilize = Num(O, TEXT("stabilize"), S.Stabilize);
			S.bFloor = Bool(O, TEXT("floor"), S.bFloor);
			S.bPinTip = Bool(O, TEXT("pin_tip"), S.bPinTip);
			S.Iterations = int32(Num(O, TEXT("iterations"), float(S.Iterations)));
		});
	}
	Anchor = Xform(Obj(Root, TEXT("anchor")));
	PostureAnchor = Xform(Obj(Root, TEXT("posture_anchor")));

	const FObj C = Obj(Root, TEXT("camera"));
	Camera.Fov = Num(C, TEXT("fov"), 25.f);
	Camera.Top = Vec2(C, TEXT("top"), Camera.Top);
	Camera.Middle = Vec2(C, TEXT("middle"), Camera.Middle);
	Camera.Bottom = Vec2(C, TEXT("bottom"), Camera.Bottom);
	Camera.YAxis = Num(C, TEXT("y_axis"), 0.5f);
	Camera.XAxis = Num(C, TEXT("x_axis"), 0.f);
	Camera.Zoom = Num(C, TEXT("zoom"), 1.f);
	Camera.ZoomMin = Num(C, TEXT("zoom_min"), 0.5f);
	Camera.ZoomMax = Num(C, TEXT("zoom_max"), 4.f);
	Camera.Target = Vec(C, TEXT("target"));
	Camera.BoxCenter = Vec(C, TEXT("box_center"), Camera.Target);
	Camera.BoxExtent = Vec(C, TEXT("box_extent"), Camera.BoxExtent);

	Phases.Reset();
	Each(Root, TEXT("phases"), [this](const FObj& O)
	{
		FMishiPhase& P = Phases.AddDefaulted_GetRef();
		P.Trigger = Str(O, TEXT("trigger"));
		P.Label = Str(O, TEXT("label"));
		const FVector2D T = Vec2(O, TEXT("timer"), FVector2D(10, 15));
		P.TimerMin = T.X;
		P.TimerMax = T.Y;
	});
	Rules.Reset();
	Each(Root, TEXT("phase_rules"), [this](const FObj& O)
	{
		FMishiRule& R = Rules.AddDefaulted_GetRef();
		R.Trigger = Str(O, TEXT("trigger"));
		R.To = Str(O, TEXT("to"));
		R.Duration = Num(O, TEXT("duration"), 0.25f);
		R.PhaseEquals = Ints(O, TEXT("phase_equals"));
		R.PhaseNotEquals = Ints(O, TEXT("phase_not_equals"));
	});
	Parts.Reset();
	Each(Root, TEXT("parts"), [this](const FObj& O)
	{
		FMishiPart& P = Parts.AddDefaulted_GetRef();
		P.Name = Str(O, TEXT("name"));
		P.FemaleClip = Str(O, TEXT("female_clip"));
		P.MaleClip = Str(O, TEXT("male_clip"));
		P.bLoop = Bool(O, TEXT("loop"), true);
		P.Speed = Num(O, TEXT("speed"), 1.f);
		P.Duration = Num(O, TEXT("duration"), 1.f);
		P.Next = Str(O, TEXT("next"));
		P.ExitTime = Num(O, TEXT("exit_time"), 0.95f);
		P.Blend = Num(O, TEXT("blend"), 0.25f);
		P.Phase = int32(Num(O, TEXT("phase"), -1.f));
		P.FemaleFx = Str(O, TEXT("female_fx"));
		P.MaleFx = Str(O, TEXT("male_fx"));
	});
	Tracks.Reset();
	if (const FObj T = Obj(Root, TEXT("shape_tracks")))
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Kv : T->Values)
		{
			if (!Kv.Value.IsValid() || Kv.Value->Type != EJson::Object)
				continue;
			const FObj O = Kv.Value->AsObject();
			FMishiShapeTrack& Track = Tracks.Add(Kv.Key);
			Track.Fps = Num(O, TEXT("fps"), 30.f);
			if (const FObj S = Obj(O, TEXT("shapes")))
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Shape : S->Values)
				{
					TArray<float>& Keys = Track.Shapes.Add(Shape.Key);
					if (Shape.Value.IsValid() && Shape.Value->Type == EJson::Array)
						for (const TSharedPtr<FJsonValue>& V : Shape.Value->AsArray())
							Keys.Add(V.IsValid() ? float(V->AsNumber()) : 0.f);
				}
		}
	Voices.Reset();
	Each(Root, TEXT("voices"), [this](const FObj& O)
	{
		Voices.Add({Str(O, TEXT("part")), Str(O, TEXT("jp")), Str(O, TEXT("en"))});
	});
	Sfx.Reset();
	Each(Root, TEXT("sfx"), [this](const FObj& O)
	{
		FMishiSfx& X = Sfx.AddDefaulted_GetRef();
		X.Part = Str(O, TEXT("part"));
		X.File = Str(O, TEXT("file"));
		X.Volume = Num(O, TEXT("volume"), 1.f);
		X.bLoop = Bool(O, TEXT("loop"), true);
	});
	const FObj Music = Obj(Root, TEXT("music"));
	MusicFile = Str(Music, TEXT("file"));
	MusicVolume = Num(Music, TEXT("volume"), 0.35f);
	Lines.Reset();
	Each(Root, TEXT("lines"), [this](const FObj& O)
	{
		Lines.Add({Str(O, TEXT("id")), Str(O, TEXT("zh")), Str(O, TEXT("en")), Str(O, TEXT("ja"))});
	});
	Lights.Reset();
	Each(Root, TEXT("lights"), [this](const FObj& O)
	{
		FMishiLight& L = Lights.AddDefaulted_GetRef();
		L.Name = Str(O, TEXT("name"));
		L.Type = Str(O, TEXT("type"));
		L.Xform.Pos = Vec(O, TEXT("position"));
		L.Xform.Rot = Quat(O, TEXT("rotation"));
		const FVector Col = Vec(O, TEXT("color"), FVector::OneVector);
		L.Color = FLinearColor(Col.X, Col.Y, Col.Z);
		L.Intensity = Num(O, TEXT("intensity"), 1.f);
		L.Range = Num(O, TEXT("range"), 10.f);
		L.SpotAngle = Num(O, TEXT("spot_angle"), 30.f);
		L.bBaked = Bool(O, TEXT("baked"));
		L.bShadows = Bool(O, TEXT("shadows"), true);
	});
	if (Parts.Num() == 0)
	{
		OutError = TEXT("slice.json has no parts");
		return false;
	}
	return true;
}

const FMishiPart* FMishiSlice::Part(const FString& Name) const
{
	return Parts.FindByPredicate([&Name](const FMishiPart& P) { return P.Name == Name; });
}

FString FMishiSlice::StateFor(int32 CurrentPhase, int32 WantedPhase) const
{
	if (!Phases.IsValidIndex(WantedPhase))
		return FString();
	const FString& Trig = Phases[WantedPhase].Trigger;
	for (const FMishiRule& R : Rules)
		if (R.Matches(Trig, CurrentPhase))
			return R.To;
	// no such rule: the phase's own loop part
	const FMishiPart* Direct = Parts.FindByPredicate([WantedPhase](const FMishiPart& P) { return P.Phase == WantedPhase && P.bLoop; });
	return Direct ? Direct->Name : FString();
}
