// Mishi in Unreal Engine 5 - the game module.
#pragma once

#include "CoreMinimal.h"

DECLARE_LOG_CATEGORY_EXTERN(LogMishi, Log, All);

/**
 * Unity's space (metres, left-handed, Y up, Z forward) to the space Unreal's FBX import gives the Unity FBX Exporter's files.
 * The exporter writes x mirrored (-x, y, z) in centimetres, Y up; Unreal turns Y up into Z up and mirrors its Y back, so a Unity
 * point lands at (-x, z, y) * 100: Unity's forward +Z becomes Unreal's +Y (imported characters face +Y), its right +X becomes -X.
 * The map is a proper rotation (determinant +1), so a quaternion's vector part goes the same way and its angle stays.
 * Tools/import_slice.py checks it on every import: the room placed from room_instances.json has to cover room.fbx exactly.
 */
namespace MishiSpace
{
	inline FVector Position(const FVector& U) { return FVector(-U.X, U.Z, U.Y) * 100.0; }
	inline FVector Direction(const FVector& U) { return FVector(-U.X, U.Z, U.Y); }
	inline FQuat Rotation(const FQuat& Q) { return FQuat(-Q.X, Q.Z, Q.Y, Q.W); }
	inline FVector Scale(const FVector& S) { return FVector(S.X, S.Z, S.Y); }
	inline FTransform Transform(const FVector& Pos, const FQuat& Rot, const FVector& Scl = FVector::OneVector)
	{
		return FTransform(Rotation(Rot), Position(Pos), Scale(Scl));
	}
}
