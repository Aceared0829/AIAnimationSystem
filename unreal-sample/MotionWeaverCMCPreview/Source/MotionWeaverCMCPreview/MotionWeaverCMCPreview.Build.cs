// Copyright ZhaoZining. All Rights Reserved.

using UnrealBuildTool;

public class MotionWeaverCMCPreview : ModuleRules
{
	public MotionWeaverCMCPreview(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new[] { "Json", "NNE" });
	}
}
