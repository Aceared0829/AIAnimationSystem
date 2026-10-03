// Copyright ZhaoZining. All Rights Reserved.

using UnrealBuildTool;

public class UMWSamplePreview : ModuleRules
{
	public UMWSamplePreview(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
	
		PublicIncludePaths.Add(ModuleDirectory);
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "GameplayTags", "PoseSearch" });
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate", "SlateCore", "AbilitySystemGameFeatureActions", "AnimGraphRuntime", "MotionWarping",
			"GameplayCameras", "GameplayAbilities", "GameplayTasks", "Chooser"
		});

		if (Target.bBuildEditor)
		{
			PrivateDependencyModuleNames.Add("RewindDebuggerVLog");
		}
	}
}
