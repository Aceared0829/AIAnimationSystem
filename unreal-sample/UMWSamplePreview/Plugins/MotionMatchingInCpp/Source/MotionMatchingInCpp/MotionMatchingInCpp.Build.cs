// Copyright ZhaoZining. All Rights Reserved.

using UnrealBuildTool;

public class MotionMatchingInCpp : ModuleRules
{
	public MotionMatchingInCpp(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.Add("Core");

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"CoreUObject",
				"Engine",
				"Slate",
				"SlateCore",
				"AbilitySystemGameFeatureActions",
				"PoseSearch",
				"AnimGraphRuntime",
				"EnhancedInput",
				"MotionWarping",
				"GameplayCameras",
				"GameplayTags",
				"GameplayAbilities",
				"GameplayTasks",
				"Chooser",
				"RewindDebuggerVLog"
			}
		);
	}
}
