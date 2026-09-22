// Copyright ZhaoZining. All Rights Reserved.

using UnrealBuildTool;

public class AIAnimation : ModuleRules
{
	public AIAnimation(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AnimGraphRuntime", "NNE" });
		PrivateDependencyModuleNames.AddRange(new[] { "Json", "RenderCore", "RHI" });
	}
}
