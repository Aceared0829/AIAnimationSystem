// Copyright ZhaoZining. All Rights Reserved.

using UnrealBuildTool;

public class AIAnimationEditor : ModuleRules
{
	public AIAnimationEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AIAnimation", "AnimGraph" });
		PrivateDependencyModuleNames.AddRange(new[] { "UnrealEd", "BlueprintGraph", "Kismet", "AssetRegistry", "Json", "NNE", "Slate", "SlateCore", "PropertyEditor", "AdvancedPreviewScene", "InputCore", "ToolMenus", "MainFrame" });
		AddEngineThirdPartyPrivateStaticDependencies(Target, "OpenSSL");
	}
}
