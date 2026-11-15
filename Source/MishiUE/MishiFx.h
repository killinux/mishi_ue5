// The skills' effects, played back from a bake.
//
// The game's effects are Unity particle systems (Shuriken): 148 of them on Inase's three skills.  Unreal's own (Niagara) cannot be
// built from a script, so they are not rebuilt: Unity replays each skill's timeline and writes down, frame by frame, the geometry
// every particle renderer would draw (mishi: Assets/Mishi/Editor/MishiUeEffects.cs -> Import/<slice>/fx/fx_<action>.bin;
// Tools/make_showcase.py writes fx_index.json for this reader).  Here each frame is drawn again into a procedural mesh, one
// section per particle renderer ("batch"), in the three forms the bake keeps:
//   0 soup     triangles as they stand in the unit's home frame (mesh particles, billboards aligned to their system)
//   1 view     camera-facing things: an element's centre and its vertices' offsets in camera space - turned to this camera
//   2 stretch  stretched billboards: the two ends of the axis and a half width - laid round the axis to face this camera
// with the vertex streams the game's shaders read (M_Mishi_Fx* take them from UV0-3, the colour and the normal), and the lights
// its particles carry as point lights.  A batch's index list never changes shape (a frame with fewer particles is a prefix of
// the longest), so a section is made once and only its vertices are updated.
#pragma once

#include "CoreMinimal.h"
#include "ProceduralMeshComponent.h"

class UMaterialInterface;
class UPointLightComponent;

struct FMishiFxBatch
{
	int32 Id = 0, Kind = 0, Chunk = 0, MaxVerts = 0, MaxIndices = 0, MaxElems = 0, Layout = 0;
	bool bUV1 = false, bUV2 = false;
	FString Material;
	TArray<int32> Indices;                // the longest index list of any frame
	int32 Section = INDEX_NONE;           // the mesh section it draws into while its action plays
};

struct FMishiFxAction
{
	FString Name, Part, File;
	int32 Fps = 60, Frames = 0;
	float Duration = 0.f;
	TArray<FMishiFxBatch> Batches;        // in drawing order
	TMap<int32, int32> BatchOfId;
	TArray<uint8> Data;
	TArray<int64> Offsets;
	bool bLoaded = false;
};

class FMishiFx
{
public:
	/** Reads <Folder>/fx_index.json and the actions' files. */
	bool Load(const FString& Folder);
	bool Has(const FString& Action) const;
	int32 NumActions() const { return Actions.Num(); }
	void Play(const FString& Action, float AtSeconds, UProceduralMeshComponent* Mesh, const TArray<TObjectPtr<UMaterialInterface>>& Materials);
	void Stop(UProceduralMeshComponent* Mesh, const TArray<UPointLightComponent*>& Lights);
	bool IsPlaying() const { return Current != INDEX_NONE; }
	float Time() const { return Clock; }
	/** Advance by Dt and draw that frame.  Home: where the unit was placed; the camera: what faces it is turned to it. */
	void Step(float Dt, UProceduralMeshComponent* Mesh, const TArray<UPointLightComponent*>& Lights, const FTransform& Home, const FVector& CamPos,
		const FRotator& CamRot);

	/** Candela of a particle light of intensity 1 (Unity's point light). */
	float LightScale = 3.f;

private:
	TArray<FMishiFxAction> Actions;
	int32 Current = INDEX_NONE;
	float Clock = 0.f;
	int32 Drawn = -1;                     // the frame the mesh shows
	// scratch, kept between frames
	TArray<FVector> V, N;
	TArray<FVector2D> UV0, UV1, UV2, UV3;
	TArray<FColor> Col;
	TArray<FProcMeshTangent> Tan;
	TArray<bool> Shown;

	bool LoadAction(FMishiFxAction& A, const FString& Folder);
	void Draw(int32 Frame, UProceduralMeshComponent* Mesh, const TArray<UPointLightComponent*>& Lights, const FTransform& Home, const FVector& CamPos,
		const FRotator& CamRot);
};
