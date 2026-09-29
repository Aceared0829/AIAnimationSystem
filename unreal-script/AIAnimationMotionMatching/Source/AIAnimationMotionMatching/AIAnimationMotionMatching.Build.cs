// Copyright ZhaoZining. All Rights Reserved.

using UnrealBuildTool;

public class AIAnimationMotionMatching : ModuleRules
{
	public AIAnimationMotionMatching(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AnimGraphRuntime", "AIAnimation", "MotionMatchingInCpp" });
		PrivateDependencyModuleNames.AddRange(new[] { "EnhancedInput", "InputCore", "GameplayCameras" });
	}
}
