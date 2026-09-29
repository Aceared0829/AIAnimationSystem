// Copyright ZhaoZining. All Rights Reserved.

using UnrealBuildTool;

public class AIAnimationMotionMatchingEditor : ModuleRules
{
	public AIAnimationMotionMatchingEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AnimGraph", "AIAnimationMotionMatching" });
		PrivateDependencyModuleNames.AddRange(new[] { "UnrealEd", "BlueprintGraph", "Kismet", "AssetRegistry" });
	}
}
