using UnrealBuildTool;

public class MishiUE : ModuleRules
{
	public MishiUE(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "Slate", "SlateCore", "Json", "JsonUtilities", "AnimGraphRuntime", "ProceduralMeshComponent"
		});
	}
}
