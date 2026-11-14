using UnrealBuildTool;
using System.Collections.Generic;

public class MishiUETarget : TargetRules
{
	public MishiUETarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("MishiUE");
	}
}
