#include "MishiFx.h"
#include "MishiUE.h"
#include "Components/PointLightComponent.h"
#include "Dom/JsonObject.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	// little-endian readers over the file's bytes
	struct FCursor
	{
		const uint8* P;
		const uint8* End;

		int32 Int()
		{
			int32 V = 0;
			if (P + 4 <= End)
				FMemory::Memcpy(&V, P, 4);
			P += 4;
			return V;
		}
		const float* Floats(int64 Count)
		{
			const float* F = reinterpret_cast<const float*>(P);
			P += Count * 4;
			return P <= End ? F : nullptr;
		}
		const uint8* Bytes(int64 Count)
		{
			const uint8* B = P;
			P += Count;
			return P <= End ? B : nullptr;
		}
	};

	/** A record of a frame: one batch's geometry. */
	struct FRecord
	{
		int32 Batch = 0, NumVerts = 0, NumIndices = 0, NumElems = 0;
		const float* A = nullptr;             // soup: positions; view: centres; stretch: head, tail, half width
		const float* B = nullptr;             // soup: normals; view: offsets; stretch: (end, side)
		const float* U0 = nullptr;
		const float* U1 = nullptr;
		const float* U2 = nullptr;
		const uint8* Colours = nullptr;
		const uint8* Indices = nullptr;       // int32 each
	};

	bool ReadRecord(FCursor& C, const FMishiFxAction& Action, FRecord& R, const FMishiFxBatch*& OutBatch)
	{
		R.Batch = C.Int();
		R.NumVerts = C.Int();
		R.NumIndices = C.Int();
		R.NumElems = C.Int();
		const int32* Index = Action.BatchOfId.Find(R.Batch);
		// (a batch the index leaves out was never drawn: it cannot be in a frame)
		if (!Index || R.NumVerts < 0 || R.NumIndices < 0 || R.NumElems < 0)
			return false;
		const FMishiFxBatch& Bt = Action.Batches[*Index];
		OutBatch = &Bt;
		const int64 NV = R.NumVerts;
		if (Bt.Kind == 0)
		{
			R.A = C.Floats(NV * 3);
			R.B = C.Floats(NV * 3);
		}
		else if (Bt.Kind == 1)
		{
			R.A = C.Floats(int64(R.NumElems) * 3);
			R.B = C.Floats(NV * 3);
		}
		else
		{
			R.A = C.Floats(int64(R.NumElems) * 7);
			R.B = C.Floats(NV * 2);
		}
		R.U0 = C.Floats(NV * 4);
		R.U1 = Bt.bUV1 ? C.Floats(NV * 4) : nullptr;
		R.U2 = Bt.bUV2 ? C.Floats(NV * 4) : nullptr;
		R.Colours = C.Bytes(NV * 4);
		R.Indices = C.Bytes(int64(R.NumIndices) * 4);
		return C.P <= C.End;
	}
}

bool FMishiFx::Load(const FString& Folder)
{
	Actions.Reset();
	Current = INDEX_NONE;
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *(Folder / TEXT("fx_index.json"))) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		UE_LOG(LogMishi, Warning, TEXT("effects: no %s (Tools/make_showcase.py writes it from Unity's bake)"), *(Folder / TEXT("fx_index.json")));
		return false;
	}
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (!Root->TryGetArrayField(TEXT("actions"), List) || !List)
		return false;
	int64 Bytes = 0;
	for (const TSharedPtr<FJsonValue>& Item : *List)
	{
		const TSharedPtr<FJsonObject> O = Item.IsValid() ? Item->AsObject() : nullptr;
		if (!O.IsValid())
			continue;
		FMishiFxAction& A = Actions.AddDefaulted_GetRef();
		A.Name = O->GetStringField(TEXT("name"));
		A.Part = O->GetStringField(TEXT("part"));
		A.File = O->GetStringField(TEXT("file"));
		A.Fps = int32(O->GetNumberField(TEXT("fps")));
		A.Frames = int32(O->GetNumberField(TEXT("frames")));
		A.Duration = float(O->GetNumberField(TEXT("duration")));
		const TArray<TSharedPtr<FJsonValue>>* Batches = nullptr;
		if (O->TryGetArrayField(TEXT("batches"), Batches) && Batches)
			for (const TSharedPtr<FJsonValue>& BV : *Batches)
			{
				const TSharedPtr<FJsonObject> B = BV.IsValid() ? BV->AsObject() : nullptr;
				if (!B.IsValid())
					continue;
				FMishiFxBatch& Bt = A.Batches.AddDefaulted_GetRef();
				Bt.Id = int32(B->GetNumberField(TEXT("id")));
				Bt.Kind = int32(B->GetNumberField(TEXT("kind")));
				Bt.Chunk = int32(B->GetNumberField(TEXT("chunk")));
				Bt.MaxVerts = int32(B->GetNumberField(TEXT("max_verts")));
				Bt.MaxIndices = int32(B->GetNumberField(TEXT("max_indices")));
				Bt.MaxElems = int32(B->GetNumberField(TEXT("max_elems")));
				Bt.Layout = int32(B->GetNumberField(TEXT("layout")));
				Bt.bUV1 = B->GetBoolField(TEXT("uv1"));
				Bt.bUV2 = B->GetBoolField(TEXT("uv2"));
				Bt.Material = B->GetStringField(TEXT("material"));
				A.BatchOfId.Add(Bt.Id, A.Batches.Num() - 1);
			}
		if (LoadAction(A, Folder))
			Bytes += A.Data.Num();
	}
	UE_LOG(LogMishi, Log, TEXT("effects: %d actions from %s, %.1f MB"), Actions.Num(), *Folder, Bytes / 1048576.0);
	return Actions.Num() > 0;
}

bool FMishiFx::LoadAction(FMishiFxAction& A, const FString& Folder)
{
	if (!FFileHelper::LoadFileToArray(A.Data, *(Folder / A.File)) || A.Data.Num() < 24 || FMemory::Memcmp(A.Data.GetData(), "MFX1", 4) != 0)
	{
		UE_LOG(LogMishi, Warning, TEXT("effects: %s is not a baked effect file"), *(Folder / A.File));
		A.Data.Reset();
		return false;
	}
	const uint8* D = A.Data.GetData();
	const uint8* End = D + A.Data.Num();
	int32 Fps = 0, Frames = 0;
	int64 Table = 0;
	FMemory::Memcpy(&Fps, D + 4, 4);
	FMemory::Memcpy(&Frames, D + 8, 4);
	FMemory::Memcpy(&Table, D + 16, 8);
	if (Frames <= 0 || Table <= 0 || Table + int64(Frames) * 8 > A.Data.Num())
		return false;
	A.Fps = Fps;
	A.Frames = Frames;
	A.Offsets.SetNumUninitialized(Frames);
	FMemory::Memcpy(A.Offsets.GetData(), D + Table, int64(Frames) * 8);
	// each batch's longest index list: its section's triangles
	for (int32 F = 0; F < Frames; ++F)
	{
		FCursor C{D + A.Offsets[F], D + Table};
		const int32 Records = C.Int();
		C.Int();
		for (int32 K = 0; K < Records; ++K)
		{
			FRecord R;
			const FMishiFxBatch* Bt = nullptr;
			if (!ReadRecord(C, A, R, Bt))
			{
				UE_LOG(LogMishi, Warning, TEXT("effects: %s breaks off in frame %d"), *A.File, F);
				A.Frames = F;
				F = Frames;
				break;
			}
			FMishiFxBatch& Mine = A.Batches[A.BatchOfId[R.Batch]];
			if (R.NumIndices > Mine.Indices.Num())
			{
				Mine.Indices.SetNumUninitialized(R.NumIndices);
				FMemory::Memcpy(Mine.Indices.GetData(), R.Indices, int64(R.NumIndices) * 4);
			}
			Mine.MaxVerts = FMath::Max(Mine.MaxVerts, R.NumVerts);
		}
	}
	A.bLoaded = true;
	return true;
}

bool FMishiFx::Has(const FString& Action) const
{
	return Actions.ContainsByPredicate([&Action](const FMishiFxAction& A) { return A.Name == Action && A.bLoaded; });
}

void FMishiFx::Play(const FString& Action, float AtSeconds, UProceduralMeshComponent* Mesh, const TArray<TObjectPtr<UMaterialInterface>>& Materials)
{
	const int32 Index = Actions.IndexOfByPredicate([&Action](const FMishiFxAction& A) { return A.Name == Action && A.bLoaded; });
	if (Index == INDEX_NONE || !Mesh)
		return;
	Mesh->ClearAllMeshSections();
	FMishiFxAction& A = Actions[Index];
	int32 Section = 0, Missing = 0;
	for (FMishiFxBatch& Bt : A.Batches)
	{
		Bt.Section = INDEX_NONE;
		if (Bt.MaxVerts <= 0 || Bt.Indices.Num() < 3)
			continue;
		// every vertex at one point until a frame fills it in: nothing to see
		V.Init(FVector::ZeroVector, Bt.MaxVerts);
		N.Init(FVector(0, 0, 1), Bt.MaxVerts);
		UV0.Init(FVector2D::ZeroVector, Bt.MaxVerts);
		Col.Init(FColor(0, 0, 0, 0), Bt.MaxVerts);
		Tan.Init(FProcMeshTangent(1.f, 0.f, 0.f), Bt.MaxVerts);
		Mesh->CreateMeshSection(Section, V, Bt.Indices, N, UV0, UV0, UV0, UV0, Col, Tan, false);
		const TObjectPtr<UMaterialInterface>* Mat = Materials.FindByPredicate([&Bt](const TObjectPtr<UMaterialInterface>& M) { return M && M->GetName() == Bt.Material; });
		if (Mat)
			Mesh->SetMaterial(Section, *Mat);
		else
			++Missing;
		Mesh->SetMeshSectionVisible(Section, false);
		Bt.Section = Section++;
	}
	if (Missing > 0)
		UE_LOG(LogMishi, Warning, TEXT("effects %s: %d batches have no material (import the slice's materials)"), *Action, Missing);
	Shown.Init(false, Section);
	Current = Index;
	Clock = FMath::Max(AtSeconds, 0.f);
	Drawn = -1;
}

void FMishiFx::Stop(UProceduralMeshComponent* Mesh, const TArray<UPointLightComponent*>& Lights)
{
	if (Mesh && Current != INDEX_NONE)
		Mesh->ClearAllMeshSections();
	for (UPointLightComponent* L : Lights)
		if (L && L->IsVisible())
			L->SetVisibility(false);
	Current = INDEX_NONE;
	Drawn = -1;
}

void FMishiFx::Step(float Dt, UProceduralMeshComponent* Mesh, const TArray<UPointLightComponent*>& Lights, const FTransform& Home, const FVector& CamPos,
	const FRotator& CamRot)
{
	if (Current == INDEX_NONE || !Mesh)
		return;
	Clock += Dt;
	const FMishiFxAction& A = Actions[Current];
	const int32 Frame = FMath::FloorToInt(Clock * A.Fps);
	if (Frame >= A.Frames)
	{
		Stop(Mesh, Lights);
		return;
	}
	// (the same frame again is drawn again: what faces the camera turns with it)
	Draw(FMath::Max(Frame, 0), Mesh, Lights, Home, CamPos, CamRot);
}

void FMishiFx::Draw(int32 Frame, UProceduralMeshComponent* Mesh, const TArray<UPointLightComponent*>& Lights, const FTransform& Home, const FVector& CamPos,
	const FRotator& CamRot)
{
	const FMishiFxAction& A = Actions[Current];
	const uint8* D = A.Data.GetData();
	FCursor C{D + A.Offsets[Frame], D + A.Data.Num()};
	const int32 Records = C.Int();
	const int32 NumLights = C.Int();
	const FRotationMatrix CamAxes(CamRot);
	const FVector Forward = CamAxes.GetUnitAxis(EAxis::X), Right = CamAxes.GetUnitAxis(EAxis::Y), Up = CamAxes.GetUnitAxis(EAxis::Z);
	// Unity's home frame (x right, y up, z ahead, metres) -> the world
	auto Place = [&Home](const float* P) { return Home.TransformPosition(FVector(-P[0], P[2], P[1]) * 100.0); };
	auto Turn = [&Home](const float* P) { return Home.TransformVectorNoScale(FVector(-P[0], P[2], P[1])); };
	TArray<bool, TInlineAllocator<128>> Now;
	Now.Init(false, Shown.Num());

	for (int32 K = 0; K < Records; ++K)
	{
		FRecord R;
		const FMishiFxBatch* Bt = nullptr;
		if (!ReadRecord(C, A, R, Bt))
			break;
		if (Bt->Section == INDEX_NONE || R.NumVerts <= 0 || R.NumVerts > Bt->MaxVerts)
			continue;
		const int32 Max = Bt->MaxVerts, NV = R.NumVerts;
		V.SetNumUninitialized(Max);
		N.SetNumUninitialized(Max);
		UV0.SetNumUninitialized(Max);
		UV1.SetNumUninitialized(Max);
		UV2.SetNumUninitialized(Max);
		UV3.SetNumUninitialized(Max);
		Col.SetNumUninitialized(Max);
		Tan.SetNumUninitialized(Max);
		const int32 Chunk = FMath::Max(Bt->Chunk, 1);
		for (int32 I = 0; I < NV; ++I)
		{
			FVector Normal = -Forward;                  // what faces the camera has its normal towards it
			if (Bt->Kind == 0)
			{
				V[I] = Place(R.A + I * 3);
				Normal = Turn(R.B + I * 3).GetSafeNormal(1e-6, -Forward);
			}
			else if (Bt->Kind == 1)
			{
				const float* O = R.B + I * 3;
				V[I] = Place(R.A + (I / Chunk) * 3) + (Right * O[0] + Up * O[1] + Forward * O[2]) * 100.0;
			}
			else
			{
				const float* E = R.A + (I / 4) * 7;
				const FVector P0 = Place(E), P1 = Place(E + 3);
				const FVector View = ((P0 + P1) * 0.5 - CamPos).GetSafeNormal(1e-6, Forward);
				const FVector Side = FVector::CrossProduct(P1 - P0, View).GetSafeNormal(1e-6, Right);
				V[I] = FMath::Lerp(P0, P1, double(R.B[I * 2])) + Side * (double(R.B[I * 2 + 1]) * E[6] * 100.0);
			}
			const float* U = R.U0 + I * 4;
			UV0[I] = FVector2D(U[0], U[1]);
			FVector Emission = FVector::ZeroVector;
			if (Bt->Layout == 1)
			{
				// the newest shader: TEXCOORD1 = (uv offset, dissolve, distortion), TEXCOORD2 = emission colour
				const float* U1p = R.U1 ? R.U1 + I * 4 : nullptr;
				UV1[I] = U1p ? FVector2D(U1p[0], U1p[1]) : FVector2D::ZeroVector;
				UV2[I] = U1p ? FVector2D(U1p[2], U1p[3]) : FVector2D::ZeroVector;
				if (R.U2)
					Emission = FVector(R.U2[I * 4], R.U2[I * 4 + 1], R.U2[I * 4 + 2]);
			}
			else
			{
				// the older ones: custom data in TEXCOORD0.zw and TEXCOORD1.xy
				UV1[I] = FVector2D(U[2], U[3]);
				UV2[I] = R.U1 ? FVector2D(R.U1[I * 4], R.U1[I * 4 + 1]) : FVector2D::ZeroVector;
			}
			// The emission colour rides in UV3 (a UV is all the floats a vertex has): red + green + blue, and its hue as one
			// whole number - 45 x the red share + the green share, each in 44ths.  The mesh keeps its UVs as 16-bit floats:
			// whole numbers up to 2048 pass through them exactly, a fraction on top of them does not.  A particle's
			// vertices all carry the same number, so nothing interpolates it apart.  (The normal stays the surface's own:
			// the materials cull by it and take their rim light from it.  The engine squares the tangent up against the
			// normal, so a second vector cannot ride there.)
			Emission = Emission.ComponentMax(FVector::ZeroVector);
			const double Bright = Emission.X + Emission.Y + Emission.Z;
			double Hue = 0.0;
			if (Bright > 1e-6)
				Hue = FMath::RoundToDouble(Emission.X / Bright * 44.0) * 45.0 + FMath::RoundToDouble(Emission.Y / Bright * 44.0);
			N[I] = Normal;
			UV3[I] = FVector2D(Bright, Hue);
			Tan[I] = FProcMeshTangent(Right, false);
			const uint8* Cb = R.Colours + I * 4;
			Col[I] = FColor(Cb[0], Cb[1], Cb[2], Cb[3]);
		}
		// the vertices this frame has no particle for: on the last one, so their triangles have no area
		for (int32 I = NV; I < Max; ++I)
		{
			V[I] = V[NV - 1];
			N[I] = N[NV - 1];
			UV0[I] = UV0[NV - 1];
			UV1[I] = UV1[NV - 1];
			UV2[I] = UV2[NV - 1];
			UV3[I] = UV3[NV - 1];
			Col[I] = Col[NV - 1];
			Tan[I] = Tan[NV - 1];
		}
		Mesh->UpdateMeshSection(Bt->Section, V, N, UV0, UV1, UV2, UV3, Col, Tan);
		Now[Bt->Section] = true;
	}
	for (int32 S = 0; S < Shown.Num(); ++S)
		if (Now[S] != Shown[S])
		{
			Mesh->SetMeshSectionVisible(S, Now[S]);
			Shown[S] = Now[S];
		}

	// the lights its particles carry: place, colour x intensity, range
	const float* L = C.Floats(int64(NumLights) * 7);
	for (int32 I = 0; I < Lights.Num(); ++I)
	{
		UPointLightComponent* Light = Lights[I];
		if (!Light)
			continue;
		const bool bOn = L && I < NumLights;
		if (bOn)
		{
			const float* P = L + I * 7;
			const FLinearColor Colour(P[3], P[4], P[5]);
			const float Peak = FMath::Max3(Colour.R, Colour.G, Colour.B);
			Light->SetWorldLocation(Place(P));
			Light->SetLightColor(Peak > 1e-6f ? Colour / Peak : FLinearColor::White);
			Light->SetIntensity(Peak * LightScale);
			Light->SetAttenuationRadius(FMath::Max(P[6], 0.5f) * 100.f);
		}
		if (Light->IsVisible() != bOn)
			Light->SetVisibility(bOn);
	}
	Drawn = Frame;
}
