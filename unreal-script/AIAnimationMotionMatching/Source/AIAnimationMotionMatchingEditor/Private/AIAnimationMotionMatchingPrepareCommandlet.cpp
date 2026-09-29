// Copyright ZhaoZining. All Rights Reserved.

#include "AIAnimationMotionMatchingPrepareCommandlet.h"
#include "AnimGraphNode_AIAnimationLivePose.h"
#include "AnimGraphNode_Root.h"
#include "Animation/AnimBlueprint.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraph/EdGraphSchema.h"
#include "Engine/Blueprint.h"
#include "FileHelpers.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"

UAIAnimationMotionMatchingPrepareCommandlet::UAIAnimationMotionMatchingPrepareCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;
	LogToConsole = true;
}

int32 UAIAnimationMotionMatchingPrepareCommandlet::Main(const FString& Params)
{
	UAnimBlueprint* Source = LoadObject<UAnimBlueprint>(nullptr, TEXT("/MotionMatchingInCpp/Blueprints/ABP_PlayerCharacter.ABP_PlayerCharacter"));
	if (!Source)
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationMotionMatching: plugin AnimBP asset did not load"));
		return 1;
	}
	// Chooser 的 ContextData 固定要求 ABP_PlayerCharacter_C，必须保留插件原包名与类身份。
	const FString PackageName = TEXT("/MotionMatchingInCpp/Blueprints/ABP_PlayerCharacter");
	UAnimBlueprint* Blueprint = Source;
	UPackage* Package = Source->GetOutermost();
	TArray<UEdGraph*> Graphs;
	Blueprint->GetAllGraphs(Graphs);
	bool bInserted = false;
	for (UEdGraph* Graph : Graphs)
	{
		if (Graph->GetFName() != TEXT("AnimGraph"))
		{
			continue;
		}
		TArray<UAnimGraphNode_Root*> Roots;
		Graph->GetNodesOfClass(Roots);
		TArray<UAnimGraphNode_AIAnimationLivePose*> ExistingNodes;
		Graph->GetNodesOfClass(ExistingNodes);
		if (ExistingNodes.Num() == 1)
		{
			bInserted = true;
			break;
		}
		for (UAnimGraphNode_Root* Root : Roots)
		{
			UEdGraphPin* ResultPin = Root->FindPin(TEXT("Result"));
			if (!ResultPin || ResultPin->LinkedTo.Num() != 1)
			{
				UE_LOG(LogTemp, Error, TEXT("AIAnimationMotionMatching: AnimGraph root has no single source"));
				return 1;
			}
			UEdGraphPin* PreviousOutput = ResultPin->LinkedTo[0];
			FGraphNodeCreator<UAnimGraphNode_AIAnimationLivePose> Creator(*Graph);
			UAnimGraphNode_AIAnimationLivePose* Node = Creator.CreateNode();
			Node->NodePosX = Root->NodePosX - 280;
			Node->NodePosY = Root->NodePosY;
			Creator.Finalize();
			UEdGraphPin* SourcePin = Node->FindPin(TEXT("Source"));
			UEdGraphPin* PosePin = nullptr;
			for (UEdGraphPin* Pin : Node->Pins)
			{
				if (Pin->Direction == EGPD_Output)
				{
					PosePin = Pin;
				}
			}
			ResultPin->BreakAllPinLinks();
			if (!SourcePin || !PosePin || !Graph->GetSchema()->TryCreateConnection(PreviousOutput, SourcePin)
				|| !Graph->GetSchema()->TryCreateConnection(PosePin, ResultPin))
			{
				UE_LOG(LogTemp, Error, TEXT("AIAnimationMotionMatching: unable to insert live pose node"));
				return 1;
			}
			bInserted = true;
		}
	}
	if (!bInserted)
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationMotionMatching: AnimGraph root missing"));
		return 1;
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	FKismetEditorUtilities::CompileBlueprint(Blueprint);
	if (Blueprint->Status == BS_Error)
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationMotionMatching: copied AnimBP did not compile"));
		return 1;
	}
	Package->MarkPackageDirty();
	FSavePackageArgs SaveArgs;
	SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
	const FString Filename = FPackageName::LongPackageNameToFilename(PackageName, FPackageName::GetAssetPackageExtension());
	if (!UPackage::SavePackage(Package, Blueprint, *Filename, SaveArgs))
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationMotionMatching: failed to save live AnimBP"));
		return 1;
	}
	const FString Marker = FPaths::ProjectSavedDir() / TEXT("AIAnimation/MotionMatchingPrepared.txt");
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Marker), true);
	FFileHelper::SaveStringToFile(PackageName, *Marker);
	UE_LOG(LogTemp, Display, TEXT("AIAnimationMotionMatching: inserted live pose into %s"), *PackageName);
	return 0;
}
