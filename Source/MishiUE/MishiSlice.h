// One scene of the eros mode as Unity's exporter wrote it (Import/<scene>_<room>/slice.json): parts, the phase rules of the game's
// animator controller, camera rig, blend-shape tracks, voices, narration.  Every position and rotation here is in Unity's space;
// MishiSpace (MishiUE.h) turns them into Unreal's.
#pragma once

#include "CoreMinimal.h"
#include "MishiSprings.h"

/** A Unity-space transform (metres, left-handed, Y up). */
struct FMishiUnityXform
{
	FVector Pos = FVector::ZeroVector;
	FQuat Rot = FQuat::Identity;
	FVector Scale = FVector::OneVector;

	FVector TransformPoint(const FVector& P) const { return Pos + Rot.RotateVector(Scale * P); }
	FMishiUnityXform operator*(const FMishiUnityXform& Child) const;       // this (parent) x child, as Unity's hierarchy composes
	FTransform ToUE() const;
};

/** A state of the scene: her clip and his, how it ends. */
struct FMishiPart
{
	FString Name, FemaleClip, MaleClip, Next, FemaleFx, MaleFx;
	bool bLoop = true;
	float Speed = 1.f, Duration = 1.f, ExitTime = 0.95f, Blend = 0.25f;
	int32 Phase = -1;                     // 0..3, or -1 for a transition part
};

/** An any-state transition of the game's controller: a trigger, the phases it is allowed from, where it goes. */
struct FMishiRule
{
	FString Trigger, To;
	float Duration = 0.25f;
	TArray<int32> PhaseEquals, PhaseNotEquals;

	bool Matches(const FString& Trig, int32 Phase) const;
};

struct FMishiPhase
{
	FString Trigger;
	FString Label;                        // the button's text (a showcase slice names its actions; empty: "phase N")
	float TimerMin = 10.f, TimerMax = 15.f;  // the auto mode's stay in this phase
};

/** What a part does at a moment of its time, as the game's timeline has it (showcase slices: "cues"). */
struct FMishiCue
{
	float Time = 0.f;
	// 0 a sound, 1 a voice line, 2 a camera shake, 3 anything else (hits), 4 the unit moves (the dash to the one it attacks,
	// the way back), 5 the game's own camera for a while, 6 the skill's baked effects start (Action: which bake)
	int32 Kind = 3;
	FString File, Jp, En, Action;
	FString Move;                         // kind 4: "attack" (to Radius metres in front of the target) or "return"
	float Volume = 1.f, Duration = 0.5f, Amplitude = 0.5f, Frequency = 0.f, Radius = 1.f, Fov = 40.f;
	FVector Pos = FVector::ZeroVector;    // kind 5: where the camera stands, in the unit's space (Unity)
	FQuat Rot = FQuat::Identity;
};

struct FMishiVoice { FString Part, Jp, En; };

/** The game's sound loop of a part (her prefab's "Audio Source/phaseNN_k" node). */
struct FMishiSfx
{
	FString Part, File;
	float Volume = 1.f;
	bool bLoop = true;
};
struct FMishiLine { FString Id, Zh, En, Ja; };

/** The free-look rig of the game's Cinemachine camera: three orbits (height, radius), a yaw, a zoom scaling the orbit, a target
 *  that pans inside a box - all in the camera anchor's space. */
struct FMishiCameraSetup
{
	float Fov = 25.f;
	FVector2D Top = FVector2D(1.7, 0.56), Middle = FVector2D(0, 2.5), Bottom = FVector2D(-1.1, 0.56);
	float YAxis = 0.5f, XAxis = 0.f, Zoom = 1.f, ZoomMin = 0.5f, ZoomMax = 4.f;
	FVector Target = FVector::ZeroVector, BoxCenter = FVector::ZeroVector, BoxExtent = FVector(0.3, 0.3, 0.3);
};

/** Blend-shape weights of a part (Unity's 0..100), sampled at Fps. */
struct FMishiShapeTrack
{
	float Fps = 30.f;
	TMap<FString, TArray<float>> Shapes;

	float Sample(const TArray<float>& Keys, float Time, bool bLoop) const;
};

struct FMishiLight
{
	FString Name, Type;                   // Directional / Point / Spot / Rectangle
	FMishiUnityXform Xform;
	FLinearColor Color = FLinearColor::White;
	float Intensity = 1.f, Range = 10.f, SpotAngle = 30.f;
	bool bBaked = false, bShadows = true;
};

struct FMishiSlice
{
	FString Kind;                         // "eros" (a couple in a room, four phases) or "showcase" (one character, her actions)
	bool bMale = true;                    // the slice has him
	TArray<int32> Auto;                   // the auto mode's round of phases (empty: phase after phase, as the eros mode goes)
	TMap<FString, TArray<FMishiCue>> Cues;   // by part
	FVector Target = FVector(0.0, 0.0, 6.0);   // a showcase: where the one she fights stands, in the anchor's space (Unity)
	FMishiSpringSetup Springs;            // her bone cloth: hair, chains, skirt ("springs"; empty: none)
	FString Effects;                      // the folder of the skills' baked effects, relative to the project ("effects"; empty: none)
	FString Posture, Title, Outfit, Scene, Room;
	FString FemaleRoot, MaleRoot;
	FMishiUnityXform Anchor;              // the couple's origin in the room
	FMishiUnityXform PostureAnchor;       // the posture prefab's Anchor (the camera rig hangs under it), relative to the couple
	FMishiUnityXform FemaleOffset, MaleOffset;   // each model root relative to the couple
	FMishiCameraSetup Camera;
	TArray<FMishiPhase> Phases;
	TArray<FMishiRule> Rules;
	TArray<FMishiPart> Parts;
	TMap<FString, FMishiShapeTrack> Tracks;
	TArray<FMishiVoice> Voices;
	TArray<FMishiSfx> Sfx;
	FString MusicFile;
	float MusicVolume = 0.35f;
	TArray<FMishiLine> Lines;
	TArray<FMishiLight> Lights;

	bool Parse(const FString& Json, FString& OutError);
	const FMishiPart* Part(const FString& Name) const;
	/** The first state a phase button leads to from the current phase, as the game's controller decides it. */
	FString StateFor(int32 CurrentPhase, int32 WantedPhase) const;
};
