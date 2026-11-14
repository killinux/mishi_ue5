using UnrealBuildTool;
using System.Collections.Generic;

public class MishiUEEditorTarget : TargetRules
{
	public MishiUEEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("MishiUE");
	}
}
